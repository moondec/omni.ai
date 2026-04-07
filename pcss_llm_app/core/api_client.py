from openai import OpenAI
from pcss_llm_app.config import ConfigManager

class PcssApiClient:
    """
    Wrapper around OpenAI client for PCSS LLM Service
    """
    OBSERVABILITY_MASK = "******"
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        api_key = self.config.get_api_key()
        if api_key:
            self.client = OpenAI(
                api_key=api_key,
                base_url=self.config.get_base_url()
            )

    def is_configured(self):
        return self.client is not None

    def list_models(self):
        if not self.is_configured():
            return []
        # No try/except here - let exceptions propagate to UI
        models = self.client.models.list()
        # Filter out non-chat models (whisper, embedding, etc.)
        chat_models = []
        for m in models.data:
            mid = m.id.lower()
            if "whisper" in mid or "embedding" in mid or "dall" in mid or "tts" in mid:
                continue
            chat_models.append(m.id)
        return chat_models

    def chat_completion(self, model, messages, **kwargs):
        """
        Standard Chat Completion
        """
        if not self.is_configured():
            raise ValueError("API Client not configured")
        
        return self.client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs
        )
    
    # Assistant API wrappers (Agent Mode)
    def create_assistant(self, name, instructions, model):
        if not self.is_configured():
             raise ValueError("API Client not configured")
        return self.client.beta.assistants.create(
            name=name,
            instructions=instructions,
            model=model
        )

    def create_thread(self):
        if not self.is_configured():
             raise ValueError("API Client not configured")
        return self.client.beta.threads.create()
    
    def add_message_to_thread(self, thread_id, content):
        if not self.is_configured():
             raise ValueError("API Client not configured")
        return self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=content
        )

    def run_thread(self, thread_id, assistant_id):
        if not self.is_configured():
             raise ValueError("API Client not configured")
        return self.client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id
        )
    
    def get_run_status(self, thread_id, run_id):
         if not self.is_configured():
             raise ValueError("API Client not configured")
         return self.client.beta.threads.runs.retrieve(
             thread_id=thread_id, run_id=run_id
         )

    def get_thread_messages(self, thread_id):
         if not self.is_configured():
             raise ValueError("API Client not configured")
         return self.client.beta.threads.messages.list(
             thread_id=thread_id
         )
