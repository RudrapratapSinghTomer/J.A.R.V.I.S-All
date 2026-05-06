import os
import sys
import yaml
import requests
from openai import OpenAI
from typing import Optional

# -----------------------------------------------------------------------
# Bootstrap paths
# -----------------------------------------------------------------------
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

OLLAMA_URL = (
    config.get("models", {}).get("local", {}).get("endpoint", "http://localhost:11434/api")
)


class AutoResearcher:
    """
    Recursive Best-First AutoResearch agent.

    Workflow (Karpathy-style):
    1. generate_sub_queries  — NIM expands the topic into 3–5 targeted queries
    2. web_search            — DuckDuckGo HTML for each sub-query
    3. score_relevance       — NIM rates each scraped page (0.0–1.0)
    4. prune                 — keep only the top-N most relevant pages
    5. recurse               — extract new terms → queue them (up to max_depth)
    6. synthesize_report     — NIM writes a final coherent report from all facts
    """

    def __init__(self):
        self.nvidia_key = os.getenv("NVIDIA_API_KEY")
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
        self._client: Optional[OpenAI] = None

    def _nim_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.nvidia_key,
            )
        return self._client

    def _call_nim(self, prompt: str, max_tokens: int = 1024) -> str:
        """Call NVIDIA NIM and return text. Returns empty string on failure."""
        try:
            completion = self._nim_client().chat.completions.create(
                model=self.nvidia_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Researcher] NIM call failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # Step 1: Expand topic into sub-queries
    # ------------------------------------------------------------------
    def generate_sub_queries(self, topic: str) -> list[str]:
        prompt = (
            f"You are a research assistant. Generate exactly 3 specific, targeted web search queries "
            f"that together would comprehensively cover this research topic:\n\n'{topic}'\n\n"
            "Output ONLY the 3 queries, one per line, no numbering or extra text."
        )
        result = self._call_nim(prompt, max_tokens=256)
        if not result:
            return [topic]  # Fallback to original topic
        queries = [q.strip() for q in result.split("\n") if q.strip()]
        return queries[:3]  # Cap at 3

    # ------------------------------------------------------------------
    # Step 2: Web search
    # ------------------------------------------------------------------
    def _web_search(self, query: str, max_results: int = 5) -> list[dict]:
        from tools.browser import web_search
        return web_search(query, max_results=max_results)

    # ------------------------------------------------------------------
    # Step 3: Scrape and score relevance
    # ------------------------------------------------------------------
    def _scrape(self, url: str) -> str:
        from tools.browser import extract_text_from_url
        return extract_text_from_url(url)

    def score_relevance(self, content: str, topic: str) -> float:
        """Ask NIM to rate how relevant scraped content is. Returns 0.0–1.0."""
        if not content or len(content) < 50:
            return 0.0
        prompt = (
            f"Rate the relevance of this web content to the research topic '{topic}' "
            f"on a scale from 0.0 (completely irrelevant) to 1.0 (highly relevant).\n\n"
            f"Content preview (first 500 chars):\n{content[:500]}\n\n"
            "Reply with ONLY a single floating-point number (e.g. 0.8). No other text."
        )
        result = self._call_nim(prompt, max_tokens=10)
        try:
            import re
            match = re.search(r"0\.[0-9]+|1\.0|0|1", result)
            return float(match.group()) if match else 0.5
        except Exception:
            return 0.5

    # ------------------------------------------------------------------
    # Step 4 & 5: Recursive BFS research loop
    # ------------------------------------------------------------------
    def _research_loop(self, topic: str, depth: int, max_depth: int) -> list[dict]:
        """
        BFS loop: search → scrape → score → prune → recurse.
        Returns a list of {'url': ..., 'content': ..., 'score': ...} dicts.
        """
        if depth > max_depth:
            return []

        print(f"[Researcher] Depth {depth}/{max_depth} — researching: '{topic}'")
        sub_queries = self.generate_sub_queries(topic)
        all_results = []

        for query in sub_queries:
            links = self._web_search(query, max_results=5)
            for item in links:
                url = item.get("link", "")
                if not url:
                    continue
                print(f"[Researcher]   Scraping: {url[:80]}...")
                content = self._scrape(url)
                score = self.score_relevance(content, topic)
                all_results.append({"url": url, "content": content, "score": score})

        # Prune: keep top 2 by score
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top_results = all_results[:2]

        # Recurse: extract new terms from top content and go deeper
        if depth < max_depth and top_results:
            combined = " ".join(r["content"][:300] for r in top_results)
            expand_prompt = (
                f"From this text, extract ONE new specific sub-topic or technical term "
                f"that would be worth researching further in the context of '{topic}'.\n\n"
                f"Text: {combined}\n\n"
                "Reply with ONLY the sub-topic name. No extra text."
            )
            new_term = self._call_nim(expand_prompt, max_tokens=50)
            if new_term and new_term.lower() != topic.lower():
                print(f"[Researcher]   Expanding to sub-topic: '{new_term}'")
                child_results = self._research_loop(new_term, depth + 1, max_depth)
                top_results.extend(child_results)

        return top_results

    # ------------------------------------------------------------------
    # Step 6: Synthesize a final report from all gathered facts
    # ------------------------------------------------------------------
    def synthesize_report(self, topic: str, sources: list[dict]) -> str:
        if not sources:
            return f"No relevant information found for '{topic}'."

        # Build a condensed facts block from the top sources
        facts_block = ""
        for i, src in enumerate(sources[:5], 1):  # Use top 5
            facts_block += f"\n--- Source {i}: {src['url']} ---\n"
            facts_block += src["content"][:800] + "\n"

        prompt = (
            f"You are JARVIS, a sophisticated AI assistant. Based on the following research sources, "
            f"write a comprehensive, well-structured report on the topic: '{topic}'.\n\n"
            f"SOURCES:\n{facts_block}\n\n"
            "Write a clear, factual report with key findings, important details, and a brief conclusion. "
            "Cite the source number (e.g., [Source 1]) where applicable."
        )
        print(f"[Researcher] Synthesizing final report from {len(sources)} sources...")
        return self._call_nim(prompt, max_tokens=2048) or f"Could not synthesize report for '{topic}'."

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    def perform_deep_dive(self, topic: str, max_depth: int = 1) -> str:
        """
        Full recursive research pipeline. Returns a synthesized report string.
        max_depth=1 means one level of recursion (enough for most queries).
        max_depth=2 for thorough research.
        """
        print(f"[Researcher] Starting recursive deep dive on: '{topic}'")
        sources = self._research_loop(topic, depth=0, max_depth=max_depth)

        if not sources:
            return f"[Researcher] No usable sources found for '{topic}'."

        return self.synthesize_report(topic, sources)
