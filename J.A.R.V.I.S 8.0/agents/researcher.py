import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from tools.browser import web_search, extract_text_from_url


class AutoResearcher:
    def __init__(self):
        self.engine = "NVIDIA_NIM"

    def perform_deep_dive(self, topic: str) -> str:
        """
        1. Generate Search Queries (Simulated)
        2. Scrape results (Browser tool)
        3. Extract Key Insights (Simulated LLM)
        4. Synthesize final report
        """
        print(f"[Researcher] Starting deep dive on: {topic}")

        # Step 1: Search
        results = web_search(topic, max_results=2)

        if not results:
            return f"No results found for {topic}."

        # Step 2: Scrape
        report = f"Deep Dive Report for: {topic}\n\n"
        for i, res in enumerate(results):
            link = res["link"]
            print(f"[Researcher] Scraping {link}...")
            content = extract_text_from_url(link)

            # Step 3 & 4: Simulate Synthesis
            report += f"Source {i + 1}: {link}\n"
            report += f"Summary: Extracted {len(content)} characters of text.\n"
            report += f"Preview: {content[:200]}...\n\n"

        return report
