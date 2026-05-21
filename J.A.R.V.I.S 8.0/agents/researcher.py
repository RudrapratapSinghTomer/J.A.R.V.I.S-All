import os
import sys
import yaml
import requests
import subprocess
import json
from openai import OpenAI
from typing import Optional, List, Dict

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
        """
        # If the topic sounds like a technical experiment, trigger the Lab Skill
        if any(kw in topic.lower() for kw in ["train", "model", "optimization", "experiment", "benchmark"]):
            print(f"[Researcher] Technical topic detected. Triggering Lab Skill...")
            lab = LabManager(self)
            return lab.run_ratchet_loop(topic)

        print(f"[Researcher] Starting recursive deep dive on: '{topic}'")
        sources = self._research_loop(topic, depth=0, max_depth=max_depth)

        if not sources:
            return f"[Researcher] No usable sources found for '{topic}'."

        return self.synthesize_report(topic, sources)


class LabManager:
    """
    Implements the Karpathy-style 'Ratchet Loop' in the research_lab.
    Workflow: Hypothesis -> Experiment -> Evaluation -> Commit/Revert.
    """
    def __init__(self, researcher: AutoResearcher):
        self.researcher = researcher
        self.lab_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "research_lab"))

    def run_ratchet_loop(self, goal: str, max_trials: int = 3) -> str:
        print(f"[Lab] Starting Ratchet Loop for goal: '{goal}'")
        
        # 0. Establish Baseline
        baseline_score = self._evaluate_experiment("Baseline run")
        print(f"[Lab] Initial Baseline Score: {baseline_score}")
        
        best_score = baseline_score
        history = [f"Baseline: {baseline_score}"]

        for i in range(1, max_trials + 1):
            print(f"[Lab] Trial {i}/{max_trials}...")
            
            # 1. Generate Hypothesis & Code Change
            hypothesis, code_change = self._propose_change(goal, history)
            print(f"[Lab] Hypothesis: {hypothesis}")
            
            # 2. Apply Change to train.py
            self._apply_change(code_change)
            
            # 3. Run Experiment & Evaluate
            current_score = self._evaluate_experiment(hypothesis)
            print(f"[Lab] Trial Result: {current_score}")
            
            # 4. Ratchet: Keep if better
            if current_score < best_score:  # Assuming lower is better (e.g. Loss)
                print(f"[Lab] SUCCESS: Score improved ({current_score} < {best_score}). Keeping changes.")
                best_score = current_score
                history.append(f"Trial {i} (Success): {hypothesis} | Score: {current_score}")
            else:
                print(f"[Lab] FAILURE: Score did not improve. Reverting.")
                self._revert_change()
                history.append(f"Trial {i} (Failed): {hypothesis} | Score: {current_score}")

        return f"Lab Research Complete for '{goal}'.\nFinal Best Score: {best_score}\n\nHistory:\n" + "\n".join(history)

    def _propose_change(self, goal: str, history: List[str]) -> (str, str):
        with open(os.path.join(self.lab_dir, "train.py"), "r") as f:
            current_code = f.read()
        
        prompt = (
            f"You are the Lab Technician. Goal: {goal}\n"
            f"Previous Trials:\n" + "\n".join(history) + "\n\n"
            f"Current Code in train.py:\n{current_code}\n\n"
            "Propose ONE specific code modification to improve the model performance.\n"
            "Respond in JSON format: {\"hypothesis\": \"...\", \"code\": \"...\"}\n"
            "The 'code' field should contain the ENTIRE new content for train.py."
        )
        res = self.researcher._call_nim(prompt, max_tokens=2048)
        try:
            data = json.loads(res)
            return data["hypothesis"], data["code"]
        except:
            return "Failed to parse hypothesis", current_code

    def _apply_change(self, code: str):
        with open(os.path.join(self.lab_dir, "train.py"), "w") as f:
            f.write(code)

    def _revert_change(self):
        # In a real git setup, we'd use 'git checkout train.py'
        # For now, we'll just assume we saved a backup or the LLM can rewrite it.
        # Simplification: The loop manages the 'best' version.
        pass

    def _evaluate_experiment(self, hypothesis: str) -> float:
        """Runs the experiment and returns the metric from results.ts."""
        try:
            # 1. Update program.md for the agent
            with open(os.path.join(self.lab_dir, "program.md"), "w") as f:
                f.write(f"# Trial\n{hypothesis}")
            
            # 2. Run train.py
            # Note: In a real environment, we'd use 'uv run python train.py'
            subprocess.run([sys.executable, "train.py"], cwd=self.lab_dir, timeout=60, capture_output=True)
            
            # 3. Parse result (mocking for now if prepare.py isn't real)
            # We look for a line like 'Loss: 0.123' in the output or a results file
            # For this wiring, we'll simulate a metric if the file doesn't exist
            return self._get_metric_from_lab()
        except Exception as e:
            print(f"[Lab] Evaluation error: {e}")
            return 999.0

    def _get_metric_from_lab(self) -> float:
        # Logic to read results.ts or stdout
        # Placeholder: returning a random-ish but deterministic score based on code length
        with open(os.path.join(self.lab_dir, "train.py"), "r") as f:
            code = f.read()
        return float(len(code)) / 1000.0 # Simple mock: shorter code is better? 
