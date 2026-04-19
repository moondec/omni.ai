from PySide6.QtCore import QThread, Signal
import json

class ChatWorker(QThread):
    finished = Signal(str)
    chunk_received = Signal(str)
    error = Signal(str)
    log_message = Signal(str)
    cancelled = Signal()

    def __init__(self, api_client, model, messages):
        super().__init__()
        self.api_client = api_client
        self.model = model
        self.messages = messages
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.log_message.emit(f"ChatWorker: Sending request to model '{self.model}'...")
            self.log_message.emit(f"ChatWorker: Input messages: {len(self.messages)}")

            response = self.api_client.chat_completion(
                model=self.model,
                messages=self.messages,
                stream=True
            )

            if self._is_cancelled:
                self.cancelled.emit()
                return

            content = ""

            if hasattr(response, '__iter__') and not isinstance(response, (str, bytes)):
                # True streaming response — iterable of delta chunks
                for chunk in response:
                    if self._is_cancelled:
                        self.cancelled.emit()
                        return
                    delta_text = ""
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        if hasattr(delta, 'content') and delta.content:
                            delta_text = delta.content
                    elif isinstance(chunk, dict) and 'choices' in chunk:
                        delta_text = (chunk['choices'][0].get('delta') or {}).get('content') or ''
                    if delta_text:
                        content += delta_text
                        self.chunk_received.emit(delta_text)
            elif isinstance(response, str):
                if response.strip().startswith("data: "):
                    # Raw SSE string fallback
                    self.log_message.emit("ChatWorker: Detected SSE stream in string response. Parsing...")
                    for line in response.splitlines():
                        if line.startswith("data: "):
                            payload = line[6:].strip()
                            if payload == "[DONE]":
                                break
                            try:
                                data = json.loads(payload)
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    msg = data["choices"][0].get("message", {})
                                    piece = delta.get("content", "") or msg.get("content", "")
                                    if piece:
                                        content += piece
                                        self.chunk_received.emit(piece)
                            except Exception:
                                pass
                else:
                    content = response
                    self.chunk_received.emit(response)
            elif hasattr(response, 'choices'):
                content = response.choices[0].message.content
                self.chunk_received.emit(content)
            elif isinstance(response, dict) and 'choices' in response:
                content = response['choices'][0]['message']['content']
                self.chunk_received.emit(content)
            else:
                self.log_message.emit(f"ChatWorker: Received unusual response type: {type(response).__name__}")
                content = str(response)
                self.chunk_received.emit(content)

            self.log_message.emit("ChatWorker: Response received.")
            self.log_message.emit(f"ChatWorker: Response length: {len(content)} chars.")
            self.finished.emit(content)

        except Exception as e:
            if not self._is_cancelled:
                self.log_message.emit(f"ChatWorker Error: {str(e)}")
                self.error.emit(str(e))

class AgentWorker(QThread):
    """
    Worker to handle Agent interactions via LangChain Engine
    """
    finished = Signal(str)
    status_update = Signal(str)
    error = Signal(str)
    cancelled = Signal()  # Signal when cancelled
    chunk_received = Signal(str)
    tool_action_requested = Signal(object)

    def __init__(self, agent_engine, text, chat_history=None, initial_scratchpad: str = ""):
        super().__init__()
        self.agent_engine = agent_engine
        self.text = text
        self.chat_history = chat_history if chat_history else []
        self.initial_scratchpad = initial_scratchpad
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker."""
        self._is_cancelled = True
        if hasattr(self.agent_engine, 'cancel'):
            self.agent_engine.cancel()

    def run(self):
        try:
            if self._is_cancelled:
                self.cancelled.emit()
                return
                
            self.status_update.emit("Agent thinking...")
            
            final_response = ""
            agent_gen = self.agent_engine.run(self.text, self.chat_history, self.initial_scratchpad)
            
            if hasattr(agent_gen, '__next__'):
                while True:
                    try:
                        if self._is_cancelled:
                            self.cancelled.emit()
                            return
                        chunk = next(agent_gen)
                        if self._is_cancelled:
                            self.cancelled.emit()
                            return
                        if chunk:
                            if type(chunk).__name__ == "AgentToolAction":
                                self.tool_action_requested.emit(chunk)
                                # Poll the event with a short timeout so cancellation is responsive
                                # instead of blocking forever on event.wait()
                                while not chunk.event.wait(timeout=0.5):
                                    if self._is_cancelled:
                                        chunk.event.set()  # unblock whoever is waiting on approval
                                        self.cancelled.emit()
                                        return
                            else:
                                self.chunk_received.emit(chunk)
                    except StopIteration as e:
                        if e.value is not None:
                            final_response = e.value
                        break
            else:
                # Fallback if run() simply returns a string
                final_response = agent_gen
            
            if self._is_cancelled:
                self.cancelled.emit()
                return
                
            self.finished.emit(final_response)
                
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))

class ConsiliumWorker(QThread):
    """Worker for multi-model consilium execution."""
    finished = Signal(str)
    status_update = Signal(str)
    phase_update = Signal(str)
    error = Signal(str)
    cancelled = Signal()
    chunk_received = Signal(str)

    def __init__(self, orchestrator, text, chat_history=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.text = text
        self.chat_history = chat_history or []
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker and orchestrator."""
        self._is_cancelled = True
        if hasattr(self.orchestrator, 'cancel'):
            self.orchestrator.cancel()

    def run(self):
        try:
            if self._is_cancelled:
                self.cancelled.emit()
                return

            self.status_update.emit("Consilium processing...")
            
            gen = self.orchestrator.run(self.text, self.chat_history)
            final_response = ""
            
            if hasattr(gen, '__next__'):
                while True:
                    try:
                        chunk = next(gen)
                        if self._is_cancelled:
                            self.cancelled.emit()
                            return
                        if chunk:
                            self.chunk_received.emit(chunk)
                    except StopIteration as e:
                        if e.value is not None:
                            final_response = e.value
                        break
            else:
                final_response = gen
                
            if self._is_cancelled:
                self.cancelled.emit()
                return
                
            self.finished.emit(final_response)
        except Exception as e:
            if not self._is_cancelled:
                self.error.emit(str(e))
