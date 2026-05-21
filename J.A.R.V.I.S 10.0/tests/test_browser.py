import os
import sys

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.browser import WebBridgeBrowser

def main():
    print("=== Testing J.A.R.V.I.S 10.0 WebBridge Browser ===")

    browser = WebBridgeBrowser()

    # 1. Test Aggregated Search
    print("\n[Test 1] Testing DuckDuckGo HTML Search for 'huggingface pyannote'...")
    search_res = browser.search("huggingface pyannote", limit=3)
    
    print(f"Search returned {len(search_res)} results:")
    for i, res in enumerate(search_res):
        print(f"Result {i+1}:")
        print(f"  Title: {res.get('title')}")
        print(f"  Link: {res.get('link')}")
        print(f"  Snippet: {res.get('snippet')[:100]}...")

    if len(search_res) > 0:
        print("[SUCCESS] WebBridge search completed successfully!")
    else:
        print("[FAILED] Search returned zero results.")

    # 2. Test Boilerplate-free Scraping
    print("\n[Test 2] Scraping test URL (https://huggingface.co)...")
    scrape_res = browser.scrape_url("https://huggingface.co")
    
    print(f"Scraped Title: {scrape_res.get('title')}")
    print(f"Scraped Content length: {len(scrape_res.get('content'))} characters")
    
    if len(scrape_res.get("content")) > 100:
        print("[SUCCESS] Scraping completed and pulled clean text!")
        # Print a short snippet of content
        snippet = scrape_res.get('content').replace('\n', ' ')[:200]
        print(f"Content Snippet: {snippet}...")
    else:
        print("[FAILED] Scraping failed or pulled empty text.")

if __name__ == "__main__":
    main()
