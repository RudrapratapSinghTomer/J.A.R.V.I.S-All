import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

class WebBridgeBrowser:
    """
    High-Performance Browser / WebBridge Scraper.
    Aggregates web search queries without requiring API tokens (via DuckDuckGo HTML),
    scrapes full web articles, and strips boilerplate code to return clean markdown/JSON summaries.
    """
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

    def search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Performs an aggregated web search using DuckDuckGo's HTML search interface.
        Returns a list of dictionaries with 'title', 'link', and 'snippet'.
        """
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        
        print(f"[Browser] Aggregating search results for: '{query}'")
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, "html.parser")
            results = []
            
            # DuckDuckGo HTML uses the class 'result__body' for each result block
            blocks = soup.find_all("div", class_="result__body")
            
            for block in blocks[:limit]:
                title_el = block.find("a", class_="result__url")
                snippet_el = block.find("a", class_="result__snippet")
                
                if title_el and title_el.get("href"):
                    title = title_el.get_text().strip()
                    raw_href = title_el.get("href")
                    
                    # Parse duckduckgo redirect link if necessary
                    parsed_url = urllib.parse.urlparse(raw_href)
                    if parsed_url.netloc == "duckduckgo.com" and "uddg" in parsed_url.query:
                        queries = urllib.parse.parse_qs(parsed_url.query)
                        href = queries["uddg"][0]
                    else:
                        href = raw_href
                        
                    snippet = snippet_el.get_text().strip() if snippet_el else ""
                    
                    results.append({
                        "title": title,
                        "link": href,
                        "snippet": snippet
                    })
                    
            return results
        except Exception as e:
            print(f"[Browser Warning] DDG Search failed: {e}. Falling back to default mock results.")
            return self._get_fallback_search(query)

    def scrape_url(self, url: str) -> Dict[str, str]:
        """
        Fetches web page content, strips away boilerplates (nav, scripts, footers),
        and returns clean readable text.
        """
        print(f"[Browser] Scraping url: '{url}'")
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 1. Clean boilerplate elements
            for el in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                el.decompose()
                
            title = soup.title.get_text().strip() if soup.title else "Untitled Page"
            
            # 2. Extract content from body/main sections if available
            body = soup.find("main") or soup.find("article") or soup.find("body")
            if not body:
                body = soup
                
            # Extract plain lines and filter empty elements
            lines = (line.strip() for line in body.get_text().splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
            # Limit returned length to prevent context explosion
            trimmed_text = clean_text[:8000]
            if len(clean_text) > 8000:
                trimmed_text += "\n\n[Content Truncated due to size constraints]"
                
            return {
                "title": title,
                "content": trimmed_text,
                "url": url
            }
        except Exception as e:
            return {
                "title": "Error scraping page",
                "content": f"Failed to retrieve url: {e}",
                "url": url
            }

    def _get_fallback_search(self, query: str) -> List[Dict[str, str]]:
        """Safe fallback standard search metadata when network fails."""
        return [
            {
                "title": f"Official Hugging Face Hub for {query}",
                "link": f"https://huggingface.co/models?search={urllib.parse.quote(query)}",
                "snippet": f"Browse and download state of the art models matching {query} from the Hugging Face hub."
            },
            {
                "title": f"GitHub Repository matching {query}",
                "link": f"https://github.com/search?q={urllib.parse.quote(query)}",
                "snippet": f"Find open source libraries and tools for {query} on GitHub."
            }
        ]
