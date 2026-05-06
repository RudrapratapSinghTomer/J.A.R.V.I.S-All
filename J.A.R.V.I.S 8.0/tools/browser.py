import requests
from bs4 import BeautifulSoup
import urllib.parse


def web_search(query: str, max_results: int = 5) -> list:
    """
    Performs a basic web search (using duckduckgo html version as a simple free alternative)
    and returns a list of dictionaries with 'title' and 'link'.
    """
    try:
        url = "https://html.duckduckgo.com/html/"
        data = {"q": query}
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        response = requests.post(url, data=data, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for a in soup.find_all("a", class_="result__url", limit=max_results):
            link = a.get("href")
            # Extract actual url from duckduckgo redirect
            if link and "uddg=" in link:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                if "uddg" in parsed:
                    actual_link = parsed["uddg"][0]
                    results.append({"link": actual_link})
        return results
    except Exception as e:
        print(f"[Browser] Search error: {e}")
        return []


def extract_text_from_url(url: str) -> str:
    """
    Scrapes the text content from a given URL.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()

        text = soup.get_text(separator=" ")
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text[:5000]  # Limit to 5000 chars to avoid overwhelming models
    except Exception as e:
        return f"[Browser] Scrape error for {url}: {e}"
