"""
J.A.R.V.I.S Memory Bridge — Cognee Integration
================================================
Single source of truth for all persistent memory.
Uses Cognee's knowledge graph + vector search locally.

No external APIs. All data stored in ./data/cognee_db/
"""

import asyncio
import os
import logging
import contextlib
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("jarvis.memory")

# Optional dependency probe: never fail module import if transformers/torch stack is unstable.
try:
    from transformers import AutoTokenizer  # noqa: F401
    logger.info("Transformers AutoTokenizer pre-loaded successfully.")
except Exception as e:
    logger.warning(f"Transformers preload skipped: {e}")

# Force local dummy keys for Cognee/LiteLLM validation
os.environ["OPENAI_API_KEY"] = "sk-dummy"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-dummy"
os.environ["OLLAMA_API_KEY"] = "sk-dummy"
os.environ["LLM_API_KEY"] = "sk-dummy"
os.environ["COGNEE_LLM_PROVIDER"] = "ollama"
os.environ["HUGGINGFACE_TOKENIZER"] = "gpt2"
os.environ["COGNEE_HUGGINGFACE_TOKENIZER"] = "gpt2" # Try both variations
os.environ["COGNEE_SKIP_CONNECTION_TEST"] = "true" 
# Paths — everything inside J.A.R.V.I.S folder
BASE_DIR = Path(__file__).parent.parent
CONTEXT_DIR = BASE_DIR / "context"
COGNEE_DB_DIR = BASE_DIR / "data" / "cognee_db"

# Silence noisy internal loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cognee").setLevel(logging.CRITICAL)
logging.getLogger("cognee.shared.logging_utils").setLevel(logging.CRITICAL)
logging.getLogger("cognee.modules.graph.cognee_graph.CogneeGraph").setLevel(logging.CRITICAL)
logging.getLogger("cognee.modules.retrieval.lexical").setLevel(logging.CRITICAL)
logging.getLogger("cognee.modules.retrieval.lexical.LexicalRetriever").setLevel(logging.CRITICAL)

class JarvisMemory:
    """
    Unified memory interface for J.A.R.V.I.S.
    
    Wraps Cognee to provide:
    - remember(text)  → store to knowledge graph
    - recall(query)   → semantic search over all memories
    - forget(query)   → remove specific memories
    - improve()       → consolidate/optimize knowledge graph
    - load_context()  → ingest personal .md files on startup
    - record_reflection(task, outcome) → store internal learnings
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(COGNEE_DB_DIR)
        self._initialized = False
        self._context_loaded = False
        self._db_lock = None # Initialized lazily
        self._improve_lock = None # Initialized lazily
        self.add_timeout = float(os.getenv("JARVIS_COGNEE_ADD_TIMEOUT", "20"))
        self.cognify_timeout = float(os.getenv("JARVIS_COGNEE_COGNIFY_TIMEOUT", "300"))
        self.search_timeout = float(os.getenv("JARVIS_COGNEE_SEARCH_TIMEOUT", "15"))
        self.health_timeout = float(os.getenv("JARVIS_OLLAMA_HEALTH_TIMEOUT", "3"))

    async def get_personality_directive(self, section: str) -> str:
        """Retrieve a specific directive from personality.md."""
        personality_file = CONTEXT_DIR / "personality.md"
        if not personality_file.exists():
            return ""
        try:
            content = personality_file.read_text(encoding="utf-8")
            if section in content:
                # Simple markdown section parser
                parts = content.split(f"## {section}")
                if len(parts) > 1:
                    return parts[1].split("##")[0].strip()
        except: pass
        return ""

    @staticmethod
    def _retry_error_types():
        # tenacity is optional; import lazily to avoid hard dependency at startup.
        with contextlib.suppress(Exception):
            from tenacity import RetryError  # type: ignore
            return (RetryError, RuntimeError)
        return (RuntimeError,)

    async def is_healthy(self) -> bool:
        """Quick health probe for local Ollama before heavy memory operations."""
        try:
            import httpx
            ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
            url = f"{ollama_host}/api/tags"
            async with httpx.AsyncClient(timeout=self.health_timeout) as client:
                resp = await client.get(url)
            healthy = resp.status_code == 200
            if not healthy:
                logger.warning(f"Memory health probe failed with status {resp.status_code} at {url}")
            return healthy
        except Exception as e:
            logger.warning(f"Memory health probe failed: {e}")
            return False

    async def initialize(self) -> bool:
        """Initialize Cognee engine and database."""
        if self._initialized:
            return True

        if self._db_lock is None:
            self._db_lock = asyncio.Lock()
        if self._improve_lock is None:
            self._improve_lock = asyncio.Lock()
            
        logger.info("Initializing Jarvis Neural Memory (Cognee)...")

        try:
            # Configure Cognee for fully local operation
            import cognee
            
            print("Initializing J.A.R.V.I.S Memory (this may take a moment)...")

            # 1. Set Providers first
            logger.info("Memory init step 1/5: setting providers...")
            cognee.config.set_llm_provider("ollama")
            cognee.config.set_embedding_provider("ollama")
            logger.info("Memory init step 1/5 complete.")
            
            # 2. Set Models
            # LLM for reasoning (entities/relations)
            llm_model = os.getenv("OLLAMA_MODEL", "qwen3:latest")
            if not llm_model.startswith("ollama/"):
                llm_model = f"ollama/{llm_model}"
            
            # Specialized model for vector embeddings (Fast & Accurate)
            embed_model = "ollama/nomic-embed-text"
            
            cognee.config.set_llm_model(llm_model)
            cognee.config.set_embedding_model(embed_model)
            logger.info(f"Memory init step 2/5 complete. LLM={llm_model}, Embed={embed_model}")
            
            # 3. Set Endpoint
            logger.info("Memory init step 3/5: setting endpoints...")
            ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
            cognee.config.set_llm_endpoint(ollama_host)
            cognee.config.set_embedding_endpoint(ollama_host)
            cognee.config.set_llm_api_key("sk-dummy")
            cognee.config.set_embedding_api_key("sk-dummy")
            logger.info(f"Memory init step 3/5 complete. endpoint={ollama_host}")
            
            # 4. Storage
            logger.info("Memory init step 4/5: setting storage...")
            cognee.config.set_vector_db_provider("lancedb")
            cognee.config.set_vector_db_url(self.db_path)
            logger.info(f"Memory init step 4/5 complete. db={self.db_path}")

            # 5. Explicit tokenizer to avoid HF search for local Ollama names
            logger.info("Memory init step 5/5: setting embedding config...")
            cognee.config.set_embedding_config({
                "huggingface_tokenizer": "gpt2"
            })
            logger.info("Memory init step 5/5 complete.")

            healthy = await self.is_healthy()
            if not healthy:
                logger.warning("Ollama health probe failed after memory init. Continuing in degraded mode.")

            self._initialized = True
            
            # AGGRESSIVE SILENCING: Physically block specific Cognee spam strings
            class CogneeSpamFilter(logging.Filter):
                def filter(self, record):
                    msg = record.getMessage().lower()
                    blocked = ["empty knowledge graph", "run cognify", "search attempt on an empty", "empty context was provided"]
                    return not any(s in msg for s in blocked)

            for logger_name in ["cognee", "cognee.shared.logging_utils", "GraphCompletionRetriever"]:
                l = logging.getLogger(logger_name)
                l.setLevel(logging.ERROR)
                l.addFilter(CogneeSpamFilter())
                
            logger.info(f"Memory initialized. DB: {self.db_path}")

        except ImportError as e:
            logger.error(f"Cognee import failed: {e}. Run: pip install cognee")
        except Exception as e:
            logger.error(f"Memory init failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

    async def load_context(self):
        """
        Load all personal context .md files into memory on startup.
        Files: memory.md, personality.md, skills.md, projects.md, tasks.md
        
        Only runs once per session. Files are loaded as persistent knowledge.
        """
        if self._context_loaded:
            logger.info("Context already loaded this session.")
            return

        if not self._initialized:
            await self.initialize()
        if not await self.is_healthy():
            logger.warning("Memory context load skipped: Ollama health check failed.")
            return

        context_files = list(CONTEXT_DIR.glob("*.md"))
        if not context_files:
            logger.warning(f"No context files found in {CONTEXT_DIR}")
            return

        loaded = 0
        import cognee
        
        # Batch add all files first (lightweight)
        for md_file in context_files:
            try:
                content = md_file.read_text(encoding="utf-8").strip()
                if not content:
                    logger.warning(f"Skipping empty context file: {md_file.name}")
                    continue
                await asyncio.wait_for(cognee.add(content), timeout=self.add_timeout)
                loaded += 1
                logger.info(f"Buffered context: {md_file.name}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout buffering context file: {md_file.name}")
            except self._retry_error_types() as e:
                logger.warning(f"Retry/runtime error buffering {md_file.name}: {e}")
            except Exception as e:
                logger.error(f"Failed to buffer {md_file.name}: {e}")

        # Run improve in background so we don't block startup or hit timeouts
        if loaded > 0:
            logger.info(f"Buffered {loaded} context files. Spawning background memory graph builder...")
            # We don't await this; we let it run in the background.
            asyncio.create_task(self.improve())

        self._context_loaded = True
        logger.info(f"Context ingestion complete. Neural indexing continuing in background.")

    async def remember(self, text: str, metadata: Optional[dict] = None):
        """Store text into the knowledge graph."""
        if not self._initialized:
            await self.initialize()

        # [NEURAL LOCK] Safety check
        if self._db_lock is None:
            self._db_lock = asyncio.Lock()

        # Guard against empty/spam text
        if not text or len(text.strip()) < 5:
            return

        # [NEURAL LOCK] Kuzu is sensitive to concurrent access
        async with self._db_lock:
            try:
                import cognee
                # New Cognee 1.x 'remember' API
                await asyncio.wait_for(cognee.remember(text), timeout=self.add_timeout)
                logger.debug(f"Remembered (buffered): {text[:80]}...")
            except asyncio.TimeoutError:
                logger.warning("Remember timed out while buffering memory.")
            except Exception as e:
                error_str = str(e).lower()
                if "lock" in error_str:
                    logger.info("Memory database is currently locked by another process. Skipping buffer.")
                else:
                    logger.error(f"Remember failed: {e}")

    def get_recent_reflections(self, count: int = 3) -> str:
        """
        Retrieve the latest N reflections from mind_journal.md.
        Synchronous method for fast access during MindLoop cycles.
        """
        journal_file = CONTEXT_DIR / "mind_journal.md"
        if not journal_file.exists():
            return "No recent reflections available."
            
        try:
            content = journal_file.read_text(encoding="utf-8")
            # Split by ## [timestamp]
            entries = content.split("## [")
            if len(entries) <= 1:
                return "No structured reflections found."
                
            # Get the last N entries (skip the first split which is empty or header)
            recent = entries[-count:]
            return "\n".join([f"## [{e.strip()}" for e in recent])
        except Exception as e:
            logger.error(f"Failed to read reflections: {e}")
            return "Error retrieving reflections."

    async def recall(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Semantic search over all memories with Keyword Fallback.
        """
        if not self._initialized:
            await self.initialize()

        formatted = []
        async with self._db_lock:
            try:
                if not await self.is_healthy():
                    raise RuntimeError("Ollama unavailable during recall")
                import cognee
                
                # Using the new Cognee 1.x 'recall' API
                results = await asyncio.wait_for(cognee.recall(query_text=query), timeout=self.search_timeout)
                
                if results:
                    for r in results[:top_k]:
                        text_content = r.get("text") if isinstance(r, dict) else getattr(r, "text", str(r))
                        formatted.append({
                            "text": str(text_content),
                            "score": 0.8,
                            "source": "cognee_graph"
                        })
            except Exception as e:
                error_str = (repr(e) + " " + str(e)).lower()
                if "lock" in error_str:
                    logger.info("Memory database locked. Using Keyword Fallback.")
                elif "empty" in error_str or "no valid chunks" in error_str or "nodataerror" in error_str:
                    logger.info("Knowledge graph is currently empty or warming up. Using Keyword fallback.")
                else:
                    logger.warning(f"Cognee recall failed: {e}. Falling back to Keyword search.")

        # KEYWORD FALLBACK: Always run against context files to supplement graph results.
        # This ensures recall works even when the knowledge graph is empty/building.
        try:
            keywords = [w.lower() for w in query.split() if len(w) > 3]
            context_files = list(CONTEXT_DIR.glob("*.md"))
            keyword_hits = []
            
            for md_file in context_files:
                content = md_file.read_text(encoding="utf-8")
                if any(kw in content.lower() for kw in keywords):
                    # Find relevant paragraph
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if any(kw in line.lower() for kw in keywords):
                            chunk = "\n".join(lines[max(0, i-2):min(len(lines), i+3)])
                            keyword_hits.append({
                                "text": f"[{md_file.name}]: {chunk}",
                                "score": 0.5,
                                "source": "file_scan"
                            })
                            if len(keyword_hits) >= top_k:
                                break
                if len(keyword_hits) >= top_k:
                    break

            # Merge: prefer graph results but fill remaining slots with keyword hits
            existing_texts = {r["text"] for r in formatted}
            for hit in keyword_hits:
                if hit["text"] not in existing_texts and len(formatted) < top_k:
                    formatted.append(hit)

        except Exception as e:
            logger.error(f"Keyword fallback failed: {e}")

        return formatted

    async def record_reflection(self, task: str, outcome: str, reflection: str = ""):
        """
        Store a self-journaled insight into the knowledge graph and mind_journal.md.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n## [{timestamp}] Task: {task}\n"
            f"**Outcome:** {outcome}\n"
            f"**Reflection:** {reflection}\n"
        )
        
        # 1. Update the persistent file
        journal_file = CONTEXT_DIR / "mind_journal.md"
        try:
            with open(journal_file, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info(f"Self-reflection recorded in {journal_file.name}")
            
            # PROACTIVE NOTIFICATION: Email the user about this reflection
            from skills.notifier_skill import notifier
            asyncio.create_task(notifier.notify(
                title=f"Memory Reflection: {task}",
                message=f"OUTCOME: {outcome}\nREFLECTION: {reflection}",
                priority="normal"
            ))
        except Exception as e:
            logger.error(f"Failed to write reflection to file: {e}")

        # 2. Add to active memory
        await self.remember(entry, metadata={"type": "reflection", "task": task})

    async def forget(self, query: str):
        """Remove specific memories matching the query."""
        if not self._initialized:
            await self.initialize()

        normalized = (query or "").strip().lower()
        if not normalized:
            logger.warning("Forget skipped: empty query.")
            return

        try:
            import cognee
            if normalized in {"all", "*", "everything"}:
                await cognee.prune.prune_system() # Cognee 1.x prune API
                logger.warning("Pruned full memory graph via explicit forget-all request.")
                return

            # Cognee currently does not expose a stable selective-delete API here.
            logger.warning(
                "Selective forget is not supported by current Cognee bridge. "
                f"Requested query retained: '{query}'."
            )
        except Exception as e:
            logger.error(f"Forget failed: {e}")

    async def force_cognify(self):
        """
        Manually rebuild the full knowledge graph.
        Call this via voice command 'Jarvis, rebuild memory' when Ollama is ready.
        """
        if not self._initialized:
            await self.initialize()

        try:
            if not await self.is_healthy():
                logger.warning("force_cognify skipped: Ollama health check failed.")
                return "Ollama is not available. Please ensure it is running."
            import cognee
            logger.info("Manually rebuilding knowledge graph (force_cognify)...")
            await asyncio.wait_for(cognee.cognify(), timeout=self.cognify_timeout)
            logger.info("Knowledge graph rebuilt successfully via force_cognify.")
            return "Memory graph rebuilt successfully, Sir."
        except asyncio.TimeoutError:
            logger.warning("force_cognify timed out. Try increasing JARVIS_COGNEE_COGNIFY_TIMEOUT.")
            return "Memory rebuild timed out. Ollama may need more time. Try again later."
        except Exception as e:
            logger.error(f"force_cognify failed: {e}")
            return f"Memory rebuild failed: {e}"

    async def improve(self):
        """
        Consolidate and optimize the knowledge graph.
        Run this after batch operations (e.g., nightly learning).
        """
        if not self._initialized:
            await self.initialize()

        if self._improve_lock.locked():
            logger.info("Memory improvement already in progress. Skipping redundant cycle.")
            return

        async with self._improve_lock:
            # Also respect the global DB lock
            async with self._db_lock:
                try:
                    if not await self.is_healthy():
                        logger.warning("Memory improve skipped: Ollama health check failed.")
                        return
                    import cognee
                    # New Cognee 1.x 'improve' API
                    logger.info("Initiating Neural Graph Consolidation (improve)...")
                    await asyncio.wait_for(cognee.improve(), timeout=self.cognify_timeout)
                    logger.info("Knowledge graph improved/consolidated.")
                except asyncio.TimeoutError:
                    logger.warning("Memory improve timed out.")
                except Exception as e:
                    error_str = (repr(e) + " " + str(e)).lower()
                    if "lock" in error_str:
                         logger.info("Memory database locked. Skipping consolidation cycle.")
                    elif "no valid chunks" in error_str or "nodataerror" in error_str:
                         logger.info("Neural graph is currently empty or warming up. Skipping improvement.")
                    else:
                         logger.error(f"Improve failed: {e}")

    def recall_sync(self, query: str, top_k: int = 5) -> list[dict]:
        """Synchronous wrapper for recall."""
        try:
            return asyncio.run(self.recall(query, top_k))
        except Exception as e:
            logger.error(f"Sync recall error: {e}")
            return []

    def remember_sync(self, text: str, metadata: Optional[dict] = None):
        """
        NON-BLOCKING synchronous wrapper for remember.
        Pushes to a background thread to prevent JARVIS from hanging.
        """
        import threading
        def _bg_remember():
            try:
                asyncio.run(self.remember(text, metadata))
            except Exception as e:
                logger.error(f"Background memory error: {e}")
        
        threading.Thread(target=_bg_remember, daemon=True).start()
        logger.debug(f"Backgrounding memory storage for: {text[:50]}...")


# Singleton instance — import this in other modules
memory = JarvisMemory()
