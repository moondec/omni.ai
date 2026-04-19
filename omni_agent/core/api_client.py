from openai import OpenAI
from omni_agent.config import ConfigManager

class OmniApiClient:
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
        """Return sorted list of chat model IDs available on the server."""
        return [m["id"] for m in self.list_models_full()]

    def list_models_full(self):
        """Return rich model list: [{"id": ..., "is_free": bool, "pricing": {...}}, ...]

        Models are sorted alphabetically (provider/name). Free-tier models are
        detected either from the API pricing data (cost == 0) or by the ':free'
        suffix common on OpenRouter.
        """
        if not self.is_configured():
            return []
        models = self.client.with_options(timeout=8.0).models.list()

        SKIP_KEYWORDS = ("whisper", "embedding", "dall", "tts")
        result = []
        for m in models.data:
            mid = m.id.lower()
            if any(kw in mid for kw in SKIP_KEYWORDS):
                continue

            # Detect free tier: ':free' suffix OR pricing data with zero costs
            is_free = mid.endswith(":free")
            pricing = getattr(m, "pricing", None)
            if pricing and not is_free:
                try:
                    prompt_cost = float(getattr(pricing, "prompt", 1) or 1)
                    completion_cost = float(getattr(pricing, "completion", 1) or 1)
                    if prompt_cost == 0 and completion_cost == 0:
                        is_free = True
                except (TypeError, ValueError):
                    pass

            result.append({"id": m.id, "is_free": is_free, "pricing": pricing})

        # Sort alphabetically by model ID (provider/name)
        result.sort(key=lambda x: x["id"].lower())
        return result

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

    def transcribe_audio(self, file_path, model="whisper-large-v3-turbo:0.8b"):
        """ Transcribe audio file using Whisper """
        if not self.is_configured():
            raise ValueError("API Client not configured")
        with open(file_path, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model=model,
                file=audio_file
            )
        return transcript.text
