import os
from mem0 import Memory


class MHC_Memory:
    def __init__(self):
        # Initialize Mem0. By default it uses local Qdrant/Chroma if configured,
        # or in-memory. For persistence, we should configure a local DB path.
        # Mem0 supports various configs. We'll use local SQLite/Chroma.
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "jarvis_mhc",
                    "path": os.path.join(
                        os.path.dirname(__file__), "..", "data", "chroma_db"
                    ),
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
                    "openai_base_url": "https://integrate.api.nvidia.com/v1",
                    "api_key": os.getenv("NVIDIA_API_KEY"),
                },
            },
            "embedder": {
                "provider": "gemini",
                "config": {
                    "model": "models/gemini-embedding-001",
                    "api_key": os.getenv("GOOGLE_API_KEY"),
                },
            },
        }

        # Ensure data directory exists
        os.makedirs(
            os.path.join(os.path.dirname(__file__), "..", "data"), exist_ok=True
        )

        try:
            self.memory = Memory.from_config(config)
        except Exception as e:
            print(
                f"[MHC Memory] Could not initialize Mem0 with Chroma, falling back to default. Error: {e}"
            )
            # If fallback is needed, we still want to avoid OpenAI default if possible
            self.memory = Memory.from_config(
                config
            )  # Try again with same config if it failed for some reason

    def add_to_manifold(self, user_id: str, interaction: str):
        """
        Saves text to Vector DB and creates graph links in Mem0.
        """
        try:
            self.memory.add(interaction, user_id=user_id)
            print(f"[MHC Memory] Added to manifold for user {user_id}")
        except Exception as e:
            print(f"[MHC Memory] Error adding to manifold: {e}")

    def get_context(self, user_id: str, current_query: str) -> str:
        """
        Retrieves the 'Hyperconnected' context.
        """
        try:
            results = self.memory.search(current_query, filters={"user_id": user_id})
            if not results:
                return ""

            context = "Context from previous interactions:\n"
            for res in results:
                if isinstance(res, dict):
                    # Try common keys
                    memory_content = (
                        res.get("memory") or res.get("text") or res.get("content")
                    )
                    if not memory_content:
                        # Fallback to string representation of the whole dict but skip metadata
                        memory_content = str(
                            {
                                k: v
                                for k, v in res.items()
                                if k not in ["id", "metadata", "score"]
                            }
                        )
                    context += f"- {memory_content}\n"
                else:
                    context += f"- {res}\n"

            return context
        except Exception as e:
            print(f"[MHC Memory] Error retrieving context: {e}")
            return ""
