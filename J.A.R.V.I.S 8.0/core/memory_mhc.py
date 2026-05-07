import os
from mem0 import Memory


class MHC_Memory:
    def __init__(self):
        # We use a robust configuration for Jarvis 8.0:
        # - Chroma for persistent local vector storage
        # - Gemini for fast embeddings and memory parsing
        
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("Gemini_API_KEY")
        
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "jarvis_mhc_v8",
                    "path": os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")),
                },
            },
            "llm": {
                "provider": "gemini",
                "config": {
                    "model": "gemini-flash-latest",
                    "api_key": google_key,
                },
            },
            "embedder": {
                "provider": "gemini",
                "config": {
                    "model": "models/gemini-embedding-001",
                    "api_key": google_key,
                },
            },
        }

        # Ensure data directory exists
        data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        os.makedirs(data_path, exist_ok=True)

        try:
            self.memory = Memory.from_config(config)
            print("[MHC Memory] Initialized successfully.")
        except Exception as e:
            print(f"[MHC Memory] Initialization Error: {e}")
            self.memory = None

    def add_to_manifold(self, user_id: str, interaction: str):
        if not self.memory: return
        try:
            self.memory.add(interaction, user_id=user_id)
        except Exception as e:
            print(f"[MHC Memory] Add Error: {e}")

    def get_context(self, user_id: str, current_query: str) -> str:
        if not self.memory: return ""
        try:
            search_res = self.memory.search(current_query, filters={"user_id": user_id})
            results = search_res.get("results", []) if isinstance(search_res, dict) else search_res
            if not results: return ""

            context = "Previous context:\n"
            for res in results:
                if isinstance(res, dict):
                    content = res.get("memory") or res.get("text") or str(res)
                else:
                    content = str(res)
                context += f"- {content}\n"
            return context
        except Exception as e:
            print(f"[MHC Memory] Search Error: {e}")
            return ""
