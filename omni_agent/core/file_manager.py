import json

class FileManager:
    @staticmethod
    def save_conversation(filepath, conversation_data):
        """
        Saves conversation data to a JSON file.
        conversation_data structure:
        {
            "meta": {"model": "...", "date": "..."},
            "messages": [{"role": "user", "content": "..."}, ...]
        }
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving file: {e}")
            return False

    @staticmethod
    def load_conversation(filepath):
        """
        Loads conversation data from a JSON file.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading file: {e}")
            return None
