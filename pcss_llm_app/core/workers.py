from PySide6.QtCore import QThread, Signal
import json

class ChatWorker(QThread):
    finished = Signal(str)
    error = Signal(str)
    log_message = Signal(str)
    cancelled = Signal()  # Signal when cancelled

    def __init__(self, api_client, model, messages):
        super().__init__()
        self.api_client = api_client
        self.model = model
        self.messages = messages
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation of the worker."""
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
                messages=self.messages
            )
            
            if self._is_cancelled:
                self.cancelled.emit()
                return
                
            content = response.choices[0].message.content
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
                        chunk = next(agent_gen)
                        if self._is_cancelled:
                            self.cancelled.emit()
                            return
                        if chunk:
                            if type(chunk).__name__ == "AgentToolAction":
                                self.tool_action_requested.emit(chunk)
                                chunk.event.wait()
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
