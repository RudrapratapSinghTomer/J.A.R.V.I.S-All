"""
J.A.R.V.I.S. 2.0 Memory Bridge - Cognee Integration
===================================================
Single source of truth for persistent memory.

Cognee is available as an optional backend. By default, the bridge uses a local
markdown fallback so imports, unit tests, and basic conversations never write
outside this workspace or require Ollama/Cognee to be healthy.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("jarvis.memory")

# Local defaults for Cognee/LiteLLM validation. Existing user secrets win.
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-dummy")
os.environ.setdefault("OLLAMA_API_KEY", "sk-dummy")
os.environ.setdefault("LLM_API_KEY", "sk-dummy")
os.environ.setdefault("COGNEE_LLM_PROVIDER", "ollama")
os.environ.setdefault("HUGGINGFACE_TOKENIZER", "gpt2")
os.environ.setdefault("COGNEE_HUGGINGFACE_TOKENIZER", "gpt2")
os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")

BASE_DIR = Path(__file__).parent.parent.parent
CONTEXT_DIR = BASE_DIR / "context"
COGNEE_DB_DIR = BASE_DIR / "data" / "cognee_db"
LOCAL_MEMORY_FILE = CONTEXT_DIR / "memory.md"

CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
COGNEE_DB_DIR.mkdir(parents=True, exist_ok=True)


class JarvisMemory:
    """Unified memory interface for J.A.R.V.I.S. 2.0."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or str(COGNEE_DB_DIR)
        self.cognee_enabled = os.getenv("JARVIS_COGNEE_ENABLED", "0") == "1"
        self._initialized = False
        self._context_loaded = False
        self._db_lock: asyncio.Lock | None = None
        self._improve_lock: asyncio.Lock | None = None
        self.add_timeout = float(os.getenv("JARVIS_COGNEE_ADD_TIMEOUT", "20"))
        self.cognify_timeout = float(os.getenv("JARVIS_COGNEE_COGNIFY_TIMEOUT", "300"))
        self.search_timeout = float(os.getenv("JARVIS_COGNEE_SEARCH_TIMEOUT", "15"))
        self.health_timeout = float(os.getenv("JARVIS_OLLAMA_HEALTH_TIMEOUT", "3"))

    async def is_healthy(self) -> bool:
        """Return whether the configured memory backend is usable."""
        if not self.cognee_enabled:
            return True

        try:
            import httpx

            ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
            url = f"{ollama_host}/api/tags"
            async with httpx.AsyncClient(timeout=self.health_timeout) as client:
                resp = await client.get(url)
            return resp.status_code == 200
        except Exception:
            return False

    async def initialize(self) -> bool:
        """Initialize the selected memory backend."""
        if self._initialized:
            return True

        self._ensure_locks()
        if not self.cognee_enabled:
            self._initialized = True
            logger.info("Cognee disabled; using local markdown memory fallback.")
            return True

        logger.info("Initializing J.A.R.V.I.S. Neural Memory (Cognee)...")
        try:
            import cognee

            cognee.config.set_llm_provider("ollama")
            cognee.config.set_embedding_provider("ollama")

            llm_model = os.getenv("OLLAMA_MODEL", "qwen2.5:latest")
            if not llm_model.startswith("ollama/"):
                llm_model = f"ollama/{llm_model}"

            cognee.config.set_llm_model(llm_model)
            cognee.config.set_embedding_model("ollama/nomic-embed-text")

            ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
            cognee.config.set_llm_endpoint(ollama_host)
            cognee.config.set_embedding_endpoint(ollama_host)
            cognee.config.set_llm_api_key("sk-dummy")
            cognee.config.set_embedding_api_key("sk-dummy")

            cognee.config.set_vector_db_provider("lancedb")
            cognee.config.set_vector_db_url(self.db_path)
            cognee.config.set_embedding_config({"huggingface_tokenizer": "gpt2"})

            self._initialized = True
            logger.info(f"Memory initialized. DB: {self.db_path}")
            return True
        except Exception as exc:
            logger.error(f"Memory init failed: {exc}")
            self.cognee_enabled = False
            self._initialized = True
            return True

    async def load_context(self) -> None:
        """Load context files into the active memory backend."""
        if self._context_loaded or not self._initialized:
            return

        if not self.cognee_enabled:
            self._context_loaded = True
            return

        context_files = list(CONTEXT_DIR.glob("*.md"))
        if not context_files:
            self._context_loaded = True
            return

        try:
            import cognee
        except Exception as exc:
            logger.error(f"Cognee import failed while loading context: {exc}")
            self._context_loaded = True
            return

        loaded = 0
        for md_file in context_files:
            try:
                content = md_file.read_text(encoding="utf-8").strip()
                if not content:
                    continue
                await asyncio.wait_for(cognee.add(content), timeout=self.add_timeout)
                loaded += 1
            except Exception as exc:
                logger.error(f"Failed to buffer {md_file.name}: {exc}")

        if loaded > 0:
            asyncio.create_task(self.improve())

        self._context_loaded = True

    async def remember(self, text: str, metadata: Optional[dict] = None) -> None:
        """Store text into memory."""
        if not self._initialized:
            await self.initialize()

        if not text or len(text.strip()) < 5:
            return

        self._ensure_locks()
        if not self.cognee_enabled:
            await self._remember_local(text, metadata=metadata)
            return

        async with self._db_lock:
            try:
                import cognee

                await asyncio.wait_for(cognee.remember(text), timeout=self.add_timeout)
            except Exception as exc:
                logger.error(f"Remember failed: {exc}")
                await self._remember_local(text, metadata=metadata)

    async def recall(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search over all memories, with keyword fallback."""
        if not self._initialized:
            await self.initialize()

        self._ensure_locks()
        formatted: list[dict[str, Any]] = []
        if self.cognee_enabled:
            async with self._db_lock:
                try:
                    import cognee

                    results = await asyncio.wait_for(
                        cognee.recall(query_text=query),
                        timeout=self.search_timeout,
                    )
                    if results:
                        for result in results[:top_k]:
                            text_content = (
                                result.get("text")
                                if isinstance(result, dict)
                                else getattr(result, "text", str(result))
                            )
                            formatted.append(
                                {
                                    "text": str(text_content),
                                    "score": 0.8,
                                    "source": "cognee_graph",
                                }
                            )
                except Exception as exc:
                    logger.warning(f"Cognee recall failed: {exc}. Falling back to file scan.")

        formatted.extend(self._recall_local(query, top_k - len(formatted)))
        return formatted[:top_k]

    async def record_reflection(self, task: str, outcome: str, reflection: str = "") -> None:
        """Record a self-journaled insight."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n## [{timestamp}] Task: {task}\n"
            f"**Outcome:** {outcome}\n"
            f"**Reflection:** {reflection}\n"
        )

        journal_file = CONTEXT_DIR / "mind_journal.md"
        try:
            with open(journal_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as exc:
            logger.error(f"Failed to write reflection: {exc}")

        await self.remember(entry, metadata={"type": "reflection", "task": task})

    async def improve(self) -> None:
        """Optimize the knowledge graph when Cognee is enabled."""
        if not self._initialized:
            await self.initialize()

        self._ensure_locks()
        if not self.cognee_enabled:
            return

        async with self._improve_lock:
            async with self._db_lock:
                try:
                    import cognee

                    await asyncio.wait_for(cognee.improve(), timeout=self.cognify_timeout)
                except Exception as exc:
                    logger.error(f"Improve failed: {exc}")

    def _ensure_locks(self) -> None:
        if self._db_lock is None:
            self._db_lock = asyncio.Lock()
        if self._improve_lock is None:
            self._improve_lock = asyncio.Lock()

    async def _remember_local(self, text: str, metadata: Optional[dict] = None) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata_text = f" metadata={metadata}" if metadata else ""
        entry = f"\n## [{timestamp}]\n{text.strip()}{metadata_text}\n"
        async with self._db_lock:
            try:
                with open(LOCAL_MEMORY_FILE, "a", encoding="utf-8") as f:
                    f.write(entry)
            except Exception as exc:
                logger.error(f"Local remember failed: {exc}")

    @staticmethod
    def _recall_local(query: str, top_k: int = 5) -> list[dict[str, Any]]:
        if top_k <= 0:
            return []

        formatted: list[dict[str, Any]] = []
        try:
            keywords = [word.lower() for word in query.split() if len(word) > 3]
            if not keywords:
                return formatted

            for md_file in CONTEXT_DIR.glob("*.md"):
                content = md_file.read_text(encoding="utf-8")
                lowered = content.lower()
                if not any(keyword in lowered for keyword in keywords):
                    continue

                lines = content.splitlines()
                for index, line in enumerate(lines):
                    if not any(keyword in line.lower() for keyword in keywords):
                        continue
                    chunk = "\n".join(lines[max(0, index - 2) : min(len(lines), index + 3)])
                    formatted.append(
                        {
                            "text": f"[{md_file.name}]: {chunk}",
                            "score": 0.5,
                            "source": "file_scan",
                        }
                    )
                    if len(formatted) >= top_k:
                        return formatted
        except Exception:
            return formatted

        return formatted


memory = JarvisMemory()
