from typing import List, Dict, Any
import re
import json
import datetime
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pcss_llm_app.core.tools import (
    DocumentTools, OCRTools, PandocTools, VisionTools, 
    WebSearchTools, ChartTools, FolderTools, PythonREPL,
    EditFileTool, SearchTools
)

class LangChainAgentEngine:
    def __init__(self, api_key: str, model_name: str, workspace_path: str, 
                 log_callback=None, custom_instructions: str = None):
        self.api_key = api_key
        self.model_name = model_name
        self.workspace_path = workspace_path
        self.log_callback = log_callback
        self.custom_instructions = custom_instructions or ""
        self.active_scratchpad = "" # Persistence layer for long tasks
        self._initialize_agent()

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(message)

    def _initialize_agent(self):
        # 1. Initialize LLM with performance optimizations
        self.llm = ChatOpenAI(
            api_key=self.api_key,
            base_url="https://llm.hpc.pcss.pl/v1",
            model=self.model_name,
            temperature=0.2,  # Small randomness to prevent deterministic loops
            max_tokens=2048,  # Limit response length for faster generation
            request_timeout=120  # 2 minute timeout
        )

        # 2. Initialize Tools
        # print("DEBUG: Init FileToolkit", flush=True)
        toolkit = FileManagementToolkit(root_dir=str(self.workspace_path))

        self.tools = toolkit.get_tools()
        
        # Add Document Tools
        # print("DEBUG: Init DocumentTools", flush=True)
        doc_tools = DocumentTools(root_dir=str(self.workspace_path))
        # print("DEBUG: Getting DocumentTools", flush=True)
        new_tools = doc_tools.get_tools()
        # print(f"DEBUG: Got {len(new_tools)} doc tools", flush=True)
        self.tools.extend(new_tools)

        # Add OCR Tools
        ocr_tools = OCRTools(root_dir=str(self.workspace_path), api_key=self.api_key)
        self.tools.extend(ocr_tools.get_tools())

        # Add Folder Tools
        folder_tools = FolderTools(root_dir=str(self.workspace_path))
        self.tools.extend(folder_tools.get_tools())

        # Add Pandoc Tools
        pandoc_tools = PandocTools(root_dir=str(self.workspace_path))
        self.tools.extend(pandoc_tools.get_tools())

        # Vision tools - specifically use Qwen3-VL for image analysis
        vision_model = "Qwen3-VL-235B-A22B-Instruct"
        vision_tools = VisionTools(root_dir=str(self.workspace_path), api_key=self.api_key, model_name=vision_model)
        self.tools.extend(vision_tools.get_tools())

        # Add Web Search Tools
        web_search_tools = WebSearchTools(
            api_key=self.api_key, 
            model_name=self.model_name,
            base_url="https://llm.hpc.pcss.pl/v1"
        )
        self.tools.extend(web_search_tools.get_tools())

        # Add Chart Generation Tools
        chart_tools = ChartTools(root_dir=str(self.workspace_path))
        self.tools.extend(chart_tools.get_tools())

        # Add Python REPL
        repl = PythonREPL(root_dir=str(self.workspace_path))
        self.tools.extend(repl.get_tools())

        # Add Edit File Tool
        edit_tool = EditFileTool(root_dir=str(self.workspace_path))
        self.tools.extend(edit_tool.get_tools())

        # Add Search Tools
        search_tools = SearchTools(root_dir=str(self.workspace_path))
        self.tools.extend(search_tools.get_tools())




        # print("DEBUG: Building map", flush=True)
        self.tool_map = {t.name: t for t in self.tools}

    def run_step(self, prompt, stop=None):
         return self.llm.invoke(prompt, stop=stop).content

    # Intelligent Run method with loop detection and flexible limits
    # Intelligent Run method with loop detection and flexible limits
    def run(self, input_text: str, chat_history: List = None):
        if chat_history is None:
            chat_history = []

        tool_names = ", ".join(self.tool_map.keys())
        tool_descriptions = "\n".join([f"{t.name}: {t.description}" for t in self.tools])
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        system_template = f"""You are an AI assistant with tools. Date: {current_date}

Tools:
{tool_descriptions}

Format:
Question: [user's question]
Thought: [your reasoning]
Action: [one of: {tool_names}]
Action Input: [JSON for multi-arg tools, string for single-arg]
Observation: [result]
... (repeat as needed)
Thought: I have the answer
Final Answer: [your response]

Examples:
- convert_document: {{"source_path": "report.html", "output_format": "docx"}}
- save_document: {{"file_path": "doc.html", "content": "<h1>Title</h1><p>...</p>", "title": "Doc"}}
- write_file: {{"file_path": "notes.txt", "text": "Details..."}}
- list_directory: {{"dir_path": "."}}
- search_web: {{"query": "news Poland"}}

Rules:
- Speak strictly POLISH to the user.
- Write Code, Comments, and Technical docs strictly in ENGLISH.
- Use `search_files` to find content within files.
- Use `edit_file` to modify existing code instead of rewriting everything.
- Use `run_python` for math, data analysis, or testing logic.
- Use `search_news` for current events, `search_web` for general info.
- Use `deep_research` for complex topics that need multiple sources and analysis.
- Use `visit_page` to read full content from URLs (2-3 max).
- For documents: use `save_document` with HTML content.
- Be efficient - stop when you have enough information.
- IF YOU NEED TO ASK THE USER A QUESTION: You MUST use "Final Answer: [your question]" to return control to the user. Do not just "think" the question.

{f"User Instructions: " + self.custom_instructions if self.custom_instructions else ""}
Begin!"""
        
        # Build conversation history
        history_text = ""
        for msg in chat_history:
            role = "Question" if isinstance(msg, HumanMessage) else "Final Answer" 
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(msg, HumanMessage):
                history_text += f"Question: {content}\n"
            else:
                 history_text += f"Final Answer: {content}\n"

        # Stateful Continuation Logic
        # Smart Resume: If we have an active scratchpad from a previous turn (because we asked a question), resume automatically.
        if self.active_scratchpad:
            self._log("Resuming from persistent interaction state...")
            # We treat the user's new input as an observation/answer to the agent's previous state
            prompt = f"{system_template}\n{history_text}\n(Resuming task context...)\nThought: I should continue my work. Here is the history of my previous steps:\n{self.active_scratchpad}\nObservation: User Feedback/Answer: {input_text}\nNote: Decide if this answers your question or if you need to adjust your plan.\nThought:"
        else:
            self.active_scratchpad = "" # Ensure clean start
            prompt = f"{system_template}\n{history_text}\nQuestion: {input_text}\nThought:"

        max_steps = 50
        self._consecutive_format_errors = 0  # Reset format error counter
        action_history = []
        thought_history = []
        observation_history = []
        
        for i in range(max_steps):
            # Reset variables at start of each iteration to prevent stale values
            action = None
            action_input = None
            tool_args = None
            match = None
            
            self._log(f"--- Step {i+1} ---")
            
            # Invoke LLM with stop sequence
            self._log("Thinking...")
            response = self.llm.invoke(prompt, stop=["Observation:"])
            output = response.content
            # print(f"--- Step {i} ---\nLLM Output:\n{output}\n----------------")
            self._log(f"Agent Thought:\n{output}")
            
            # Smart Loop Detection (Thoughts)
            # Normalize thought (remove whitespace/newlines for comparison)
            current_thought = output.replace("Thought:", "").strip()
            
            # Strict stop only after 3 consecutive identical thoughts
            if len(thought_history) >= 2 and current_thought == thought_history[-1] and current_thought == thought_history[-2]:
                 self._log("⚠️ Thought Loop detected! Agent is repeating itself 3 times.")
                 return "Agent stopped: Repetitive thought process detected. The task seems completed or the agent is stuck."
            
            # Warning on 2nd identical thought
            if len(thought_history) >= 1 and current_thought == thought_history[-1]:
                 self._log("⚠️ Potential Thought Loop (2nd occurrence). Injecting warning.")
                 warning_msg = "\nObservation: Warning: You are repeating your exact same thought. Please move to the next step or change your approach.\nThought:"
                 prompt += warning_msg
                 self.active_scratchpad += warning_msg
            
            thought_history.append(current_thought)
            
            prompt += output
            self.active_scratchpad += output # Mirror to scratchpad
            
            if "Final Answer:" in output:
                final_ans = output.split("Final Answer:")[-1].strip()
                
                # Context Preservation Logic
                # If Final Answer is a question, KEEP the scratchpad so we can resume next turn.
                is_question_end = final_ans.endswith("?")
                question_markers = ["czy", "pytanie", "question", "should i", "decide"]
                is_question_content = any(m in final_ans.lower() for m in question_markers)
                
                if is_question_end or is_question_content:
                    self._log("Context Preserved: Agent asked a question. Scratchpad kept for next turn.")
                    # Do not clear active_scratchpad
                else:
                    self._log("Task Completed. Clearing Context.")
                    self.active_scratchpad = "" # Task finished, clear scratchpad
                
                return final_ans
            
            # Parse Action
            pattern = r"Action:\s*(.+?)\nAction Input:\s*(.+)"
            match = re.search(pattern, output, re.DOTALL)
            
            # Fallback 1: Single-line format "Action: tool_name {args}"
            if not match:
                single_line_pattern = r"Action:\s*([a-z_]+)\s*(\{.*?\})"
                single_match = re.search(single_line_pattern, output, re.DOTALL)
                if single_match:
                    action = single_match.group(1).strip()
                    action_input = single_match.group(2).strip()
                    match = True  # Signal that we found action
                    self._log(f"⚙️ Using single-line format parser for: {action}")
            
            # Fallback 2: "function call" style
            if not match:
                 json_pattern = r'function call\s*({.*?})'
                 json_match = re.search(json_pattern, output, re.DOTALL)
                 if json_match:
                     try:
                         func_data = json.loads(json_match.group(1))
                         if "name" in func_data:
                             action = func_data["name"]
                             args = func_data.get("arguments", {})
                             action_input = json.dumps(args) if isinstance(args, dict) else str(args)
                             match = True 
                     except Exception: pass

            if match:
                if hasattr(match, 'group'):
                    action = match.group(1).strip()
                    action_input = match.group(2).strip()
                
                # Safe Sanitization: stripping markdown wrappers only if they encompass the whole input
                action_input = action_input.strip()
                if "```" in action_input:
                    # Look for a block that starts at the beginning and ends at the end
                    block_match = re.search(r"^```(?:json)?\s*(.*?)\s*```$", action_input, re.DOTALL)
                    if block_match:
                        action_input = block_match.group(1).strip()
                    else:
                        # If not a whole-block wrap, only strip if it explicitly starts and ends with backticks
                        if action_input.startswith("```") and action_input.endswith("```"):
                             action_input = re.sub(r"^```(?:json)?", "", action_input)
                             action_input = re.sub(r"```$", "", action_input).strip()

                # Remove surrounding quotes only if they wrap the whole thing
                if (action_input.startswith('"') and action_input.endswith('"')) or \
                   (action_input.startswith("'") and action_input.endswith("'")):
                    action_input = action_input[1:-1].strip()
                
                # Try parsing as JSON
                try:
                    tool_args = json.loads(action_input)
                except json.JSONDecodeError:
                    # Robust extraction: finding the outer-most JSON object if parsing failed
                    # This handles cases like: {"key": "val"}?? or text ending with garbage
                    json_obj_match = re.search(r"(\{.*\})", action_input, re.DOTALL)
                    if json_obj_match:
                        try:
                            tool_args = json.loads(json_obj_match.group(1))
                        except:
                            tool_args = action_input
                    else:
                         tool_args = action_input

                # Argument Mapping Fallback
                if isinstance(tool_args, dict):
                    # Handle nested JSON string in a single field (Agent hallucination)
                    if len(tool_args) == 1:
                        key = list(tool_args.keys())[0]
                        val = tool_args[key]
                        if isinstance(val, str) and val.strip().startswith("{"):
                            try:
                                nested = json.loads(val)
                                if isinstance(nested, dict):
                                    tool_args = nested
                            except json.JSONDecodeError:
                                # Try fixing common JSON string errors (unescaped newlines)
                                try:
                                    fixed_val = val.replace('\n', '\\n').replace('\r', '')
                                    nested = json.loads(fixed_val)
                                    if isinstance(nested, dict):
                                        tool_args = nested
                                except: pass
                            except: pass

                    # Tool-specific Alias Mapping
                    if action == "list_directory":
                        if "path" in tool_args: tool_args["dir_path"] = tool_args.pop("path")
                        elif "file_path" in tool_args: tool_args["dir_path"] = tool_args.pop("file_path")
                    
                    elif action == "create_directory":
                        if "file_path" in tool_args: tool_args["directory_path"] = tool_args.pop("file_path")
                        elif "path" in tool_args: tool_args["directory_path"] = tool_args.pop("path")
                    
                    elif action in ["read_file", "write_file", "delete_file", "move_file", "copy_file", "read_docx", "read_pdf"]:
                        if "path" in tool_args and "file_path" not in tool_args:
                            tool_args["file_path"] = tool_args.pop("path")
                    
                    elif action == "convert_document":
                        if "path" in tool_args: tool_args["source_path"] = tool_args.pop("path")
                        elif "file_path" in tool_args: tool_args["source_path"] = tool_args.pop("file_path")

                    if action in ["write_file", "write_docx"] and "content" in tool_args and "text" not in tool_args:
                         tool_args["text"] = tool_args.pop("content")

                # Heuristic Question Detection (Force Interaction)
                # Check if agent is trying to "write" a question to a file or "think" a question without asking
                question_patterns = [
                    "pytanie do ciebie", "czy mam", "should i", "do you want", 
                    "czy chcesz", "mam przystąpić", "mogę rozpocząć",
                    "czy mam teraz", "czy powinienem", "czy mogę",
                    "proszę o decyzję", "pytanie:", "decyzja:"
                ]
                
                # Combine Thought, Action Input, and potential File Content into one check string
                check_text = (str(action_input) + " " + output.replace("Thought:", "")).lower()
                
                # Explicitly check content if writing a file
                if action in ["write_file", "save_document", "write_docx"] and isinstance(tool_args, dict):
                    content = tool_args.get("text", "") or tool_args.get("content", "")
                    check_text += " " + str(content).lower()

                is_question = any(p in check_text for p in question_patterns)
                
                # Special check for Question Headers in artifacts
                if "<h2>pytanie" in check_text or "<h1>pytanie" in check_text or "### pytanie" in check_text:
                    is_question = True
                
                # If it looks like a question, but NOT a Final Answer, intercept it.
                if is_question and "Final Answer" not in output:
                     self._log("⚠️ Heuristic: Agent is trying to ask a question via Tool/Thought. Intercepting.")
                     interception_msg = "\nObservation: SYSTEM INTERVENTION: It looks like you want to ask the user a question (e.g., 'Czy mam...'). \nSTOP. Do not write this to a file or just think about it. \nYou MUST use the format: 'Final Answer: [your question]' to actually ask the user and get a response.\nThought:"
                     prompt += interception_msg
                     self.active_scratchpad += interception_msg
                     continue

                # Action Loop Detection
                current_action = (action, action_input)
                if action_history.count(current_action) >= 3: # Allow one retry
                    self._log("⚠️ Action Loop detected! Stopping agent.")
                    return "Agent stopped: Repetitive action loop. I have tried this too many times."
                
                action_history.append(current_action)

                # Execute Tool
                if action in self.tool_map:
                    self._log(f"Executing Tool: {action} (Step {i+1}/{max_steps})")
                    tool = self.tool_map[action]
                    try:
                        observation = tool.run(tool_args) if hasattr(tool, "run") else tool(tool_args)
                        
                        # Observation Loop / Stagnation check
                        if len(observation_history) > 0 and observation == observation_history[-1]:
                             self._log("⚠️ Stagnation detected (Repeated Observation).")
                             observation += " (Warning: You received this exact same result in the previous step. Stop if you are done.)"
                        
                        observation_history.append(observation)
                        self._log(f"Observation: {observation}")
                    except Exception as e:
                        observation = f"Error executing {action}: {e}"
                        self._log(f"Error: {observation}")
                else:
                    observation = f"Error: Tool '{action}' not found."
                
                obs_text = f"\nObservation: {observation}\nThought:"
                prompt += obs_text
                self.active_scratchpad += obs_text
            else:
                # No Action and no Final Answer found in output
                if "Action:" in output and "Action Input:" not in output:
                     # Model started an action but didn't provide input — help it complete
                     prompt += "\nAction Input:"
                     self.active_scratchpad += "\nAction Input:"
                     continue
                
                if not output.strip():
                    return "Error: Agent produced empty response."

                # ----------------------------------------------------------------
                # Smart fallback: if the model produced a natural-language response
                # without the ReAct format, treat it as a direct Final Answer
                # rather than forcing it into a tool-usage loop.
                # ----------------------------------------------------------------
                clean_output = output.replace("Thought:", "").strip()
                
                # Heuristic: a direct answer is usually >30 chars of plain text
                # with no Action markers at all.
                has_no_action_markers = "Action:" not in output and "Action Input:" not in output
                is_substantial = len(clean_output) > 30
                
                if has_no_action_markers and is_substantial:
                    self._log("Auto-detecting direct response as Final Answer (no ReAct markers found).")
                    self.active_scratchpad = ""
                    return clean_output
                
                # If it's very short and not a final answer, give the model ONE more chance
                # but limit consecutive format errors to prevent infinite loops
                if not hasattr(self, '_consecutive_format_errors'):
                    self._consecutive_format_errors = 0
                self._consecutive_format_errors += 1
                
                if self._consecutive_format_errors >= 3:
                    self._log("⚠️ Too many format errors. Returning last output as Final Answer.")
                    self._consecutive_format_errors = 0
                    self.active_scratchpad = ""
                    return clean_output if clean_output else "Agent could not produce a valid response."
                
                fmt_error = "\nObservation: Invalid format. You MUST use either 'Final Answer: [response]' or 'Action: [tool]' with 'Action Input: [args]'.\nThought:"
                prompt += fmt_error
                self.active_scratchpad += fmt_error

        return f"Agent reached safety limit of {max_steps} steps without finishing. To prevent excessive API usage, I have stopped here. You can ask me to 'continue' if you believe more progress can be made."
