import os
import hashlib
import yaml
import json
from mem0 import Memory

try:
    import networkx as nx
except ImportError:
    nx = None


class MHC_Memory:
    def __init__(self):
        # We use a robust configuration for Jarvis 8.0:
        # - Chroma for persistent local vector storage
        # - Ollama for fast, local memory parsing
        # - Graph support for hyperconnected entities

        # Load environment variables
        from dotenv import load_dotenv

        load_dotenv()

        # Load config
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        ollama_host = os.getenv(
            "OLLAMA_HOST",
            cfg.get("models", {})
            .get("local", {})
            .get("endpoint", "http://localhost:11434"),
        ).replace("/api", "")
        ollama_model = cfg.get("models", {}).get("local", {}).get("slm", "qwen2.5:7b")

        os.environ["OLLAMA_HOST"] = ollama_host

        # Ensure data directory exists
        data_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "data")
        )
        os.makedirs(data_path, exist_ok=True)
        db_path = os.path.join(data_path, "chroma_db")

        # Use NVIDIA NIM for more robust extraction (fixes JSON parsing errors)
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        nvidia_base = (
            cfg.get("models", {})
            .get("cloud", {})
            .get("api_base", "https://integrate.api.nvidia.com/v1")
        )
        nvidia_model = (
            cfg.get("models", {})
            .get("cloud", {})
            .get("lrm", "meta/llama-3.3-70b-instruct")
        )

        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "jarvis_mhc_v8",
                    "path": db_path,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": nvidia_model,
                    "api_key": nvidia_key,
                    "openai_base_url": nvidia_base,
                },
            },
            "embedder": {
                "provider": "ollama",
                "config": {
                    "model": "nomic-embed-text:latest",
                    "ollama_base_url": ollama_host,
                },
            },
            "graph_store": {
                "provider": "neo4j",
                "config": {
                    "url": os.getenv("NEO4J_URL", "bolt://localhost:7687"),
                    "username": os.getenv("NEO4J_USER", "neo4j"),
                    "password": os.getenv("NEO4J_PASSWORD", "password"),
                },
            },
            "version": "v1.1",
        }

        try:
            # If neo4j is not available, we fall back to vector-only
            if not os.getenv("NEO4J_URL"):
                config.pop("graph_store")

            self.memory = Memory.from_config(config)
            print(
                "[MHC Memory] Initialized successfully with NVIDIA NIM + Ollama Embedder."
            )
        except Exception as e:
            print(f"[MHC Memory] Initialization Error: {e}")
            # Fallback to a simpler config if the above fails
            try:
                self.memory = Memory.from_config(
                    {
                        "vector_store": {
                            "provider": "chroma",
                            "config": {"path": db_path},
                        }
                    }
                )
                print("[MHC Memory] Initialized with fallback (Vector only).")
            except:
                self.memory = None

        # Initialize local graph fallback
        self.graph_path = os.path.join(data_path, "manifold_graph.json")
        if nx:
            if os.path.exists(self.graph_path):
                try:
                    with open(self.graph_path, "r") as f:
                        data = json.load(f)
                        self.nx_graph = nx.node_link_graph(data)
                except:
                    self.nx_graph = nx.Graph()
            else:
                self.nx_graph = nx.Graph()
        else:
            self.nx_graph = None

    def _load_hashes(self):
        hash_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "memory_hashes.json"
        )
        if os.path.exists(hash_path):
            try:
                import json

                with open(hash_path, "r") as f:
                    return set(json.load(f))
            except:
                return set()
        return set()

    def _save_hash(self, content_hash: str):
        hash_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "memory_hashes.json"
        )
        hashes = self._load_hashes()
        hashes.add(content_hash)
        try:
            import json

            with open(hash_path, "w") as f:
                json.dump(list(hashes), f)
        except:
            pass

    def add_to_manifold(self, user_id: str, interaction: str, metadata: dict = None):
        """Adds an interaction to the memory manifold with optional metadata."""
        if not self.memory:
            return
        try:
            content_hash = hashlib.md5(interaction.encode()).hexdigest()
            if not metadata:
                metadata = {}
            metadata["hash"] = content_hash

            self.memory.add(interaction, user_id=user_id, metadata=metadata)
            self._save_hash(content_hash)

            # Local Graph Hyperconnection: Link this interaction to recent ones
            if self.nx_graph is not None:
                self.nx_graph.add_node(content_hash, text=interaction[:100])
                # Find similar nodes and link them
                try:
                    recent = self.memory.search(interaction, limit=3)
                    for res in recent:
                        if isinstance(res, dict):
                            meta = res.get("metadata") or {}
                            other_hash = meta.get("hash")
                            if other_hash and other_hash != content_hash:
                                self.nx_graph.add_edge(content_hash, other_hash)

                    # Save graph
                    with open(self.graph_path, "w") as f:
                        json.dump(nx.node_link_data(self.nx_graph), f)
                except:
                    pass

        except Exception as e:
            print(f"[MHC Memory] Add Error: {e}")

    def has_learned(self, content: str, user_id: str = "system") -> bool:
        """
        Checks if the exact content (by hash) has already been learned.
        Used for incremental scanning.
        """
        content_hash = hashlib.md5(content.encode()).hexdigest()
        learned_hashes = self._load_hashes()
        if content_hash in learned_hashes:
            return True

        # Fallback to vector search if JSON is missing
        if not self.memory:
            return False
        try:
            results = self.memory.search(
                content_hash, filters={"user_id": user_id}, limit=1
            )
            for res in results:
                if isinstance(res, dict):
                    meta = res.get("metadata") or {}
                    if meta.get("hash") == content_hash:
                        return True
            return False
        except Exception:
            return False

    def get_context(self, user_id: str, current_query: str) -> str:
        """Retrieves hyperconnected context for the current query."""
        if not self.memory:
            return ""
        try:
            search_res = self.memory.search(
                current_query, filters={"user_id": user_id}, limit=5
            )
            # Normalize results
            if search_res is None:
                return ""

            results = (
                search_res
                if isinstance(search_res, list)
                else search_res.get("results", [])
            )

            if not results:
                return ""

            context = "### Relevant Memory Context (Vector + Hyperconnected):\n"
            seen_content = set()
            for res in results:
                content = ""
                if isinstance(res, dict):
                    content = res.get("memory") or res.get("text") or str(res)
                    meta = res.get("metadata") or {}
                    content_hash = meta.get("hash")

                    # Graph Traversal: If we have a local graph, find connected thoughts
                    if self.nx_graph and content_hash and content_hash in self.nx_graph:
                        for neighbor in list(self.nx_graph.neighbors(content_hash))[:2]:
                            node_data = self.nx_graph.nodes[neighbor]
                            if isinstance(node_data, dict) and "text" in node_data:
                                context += (
                                    f"* [Connected Thought] {node_data['text']}...\n"
                                )

                else:
                    content = str(res)

                if content not in seen_content:
                    context += f"* {content}\n"
                    seen_content.add(content)
            return context
        except Exception as e:
            print(f"[MHC Memory] Search Error: {e}")
            return ""

    def get_all_memories(self, user_id: str = None) -> list:
        """Returns all stored memories for a user or system."""
        if not self.memory:
            return []
        try:
            return self.memory.get_all(user_id=user_id)
        except Exception as e:
            print(f"[MHC Memory] Retrieval Error: {e}")
            return []
