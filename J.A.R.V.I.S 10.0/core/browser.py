import re
import os
import urllib.parse
import requests
from bs4 import BeautifulSoup
from typing import List, Dict

SITE_MAP = {
    "wikipedia": "https://www.wikipedia.org",
    "wikipedia.org": "https://www.wikipedia.org",
    "google": "https://www.google.com",
    "google.com": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "youtube.com": "https://www.youtube.com",
    "github": "https://github.com",
    "github.com": "https://github.com",
    "huggingface": "https://huggingface.co",
    "huggingface.co": "https://huggingface.co",
    "reddit": "https://www.reddit.com",
    "reddit.com": "https://www.reddit.com",
}

SITE_SEARCH_CONFIGS = {
    "wikipedia": {
        "input": "input#searchInput",
        "submit_js": "document.querySelector('input#searchInput').form.submit()",
        "url_pattern": "wikipedia.org"
    },
    "google": {
        "input": "input[name='q']",
        "submit_js": "document.querySelector('input[name=\"q\"]').form.submit()",
        "url_pattern": "google.com"
    },
    "youtube": {
        "input": "input#search",
        "submit_js": "document.querySelector('input#search').form.submit()",
        "url_pattern": "youtube.com"
    },
    "github": {
        "input": "input[name='q']",
        "submit_js": "document.querySelector('input[name=\"q\"]').form.submit()",
        "url_pattern": "github.com"
    }
}

class WebBridgeBrowser:
    """
    High-Performance Browser / WebBridge Scraper.
    Detects and interfaces with the Kimi WebBridge local daemon at http://127.0.0.1:10086
    to control a real browser session (navigate, click, fill, screenshot, PDF).
    Falls back to DuckDuckGo HTML scraping when the daemon is offline.
    """
    def __init__(self, llm_client=None, model=None):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/119.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }
        self.kimi_url = "http://127.0.0.1:10086/command"
        self.llm_client = llm_client
        self.model = model or "meta/llama-3.3-70b-instruct"

    def _check_active_endpoint(self) -> bool:
        """Helper to probe endpoint status directly without attempting to start it"""
        try:
            payload = {"action": "list_tabs", "args": {}, "session": "kimi-probe"}
            res = requests.post(self.kimi_url, json=payload, headers={"Content-Type": "application/json"}, timeout=1.0)
            if res.status_code == 200:
                return res.json().get("ok", False)
            return False
        except Exception:
            return False

    def ensure_kimi_active(self) -> bool:
        """Ensures that the Kimi WebBridge daemon is active, starting it automatically if offline"""
        if self._check_active_endpoint():
            return True
            
        print("[Browser] Kimi WebBridge local daemon is offline. Attempting to start daemon automatically...")
        binary_path = os.path.normpath(os.path.expanduser("~/.kimi-webbridge/bin/kimi-webbridge.exe"))
        if not os.path.exists(binary_path):
            print(f"[Browser Warning] Kimi WebBridge executable not found at: {binary_path}")
            return False
            
        # Clean up stale pid file to prevent launch blocks
        pid_file = os.path.normpath(os.path.expanduser("~/.kimi-webbridge/daemon.pid"))
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except Exception:
                pass
                
        try:
            import subprocess
            creationflags = 0
            if os.name == 'nt':
                creationflags = 0x08000000 # CREATE_NO_WINDOW
                
            subprocess.Popen(
                [binary_path, "run"],
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Poll status for up to 3 seconds
            import time
            for _ in range(6):
                time.sleep(0.5)
                if self._check_active_endpoint():
                    print("[Browser] Kimi WebBridge daemon started successfully!")
                    return True
            return False
        except Exception as e:
            print(f"[Browser Warning] Failed to start Kimi daemon process: {e}")
            return False

    def is_kimi_active(self) -> bool:
        """Checks if the Kimi WebBridge local daemon is active and responsive, starting it if necessary"""
        return self.ensure_kimi_active()

    def send_command(self, action: str, args: dict = None, session: str = "kimi") -> dict:
        """Sends a JSON action request to the Kimi WebBridge local daemon"""
        if args is None:
            args = {}
        payload = {
            "action": action,
            "args": args,
            "session": session
        }
        try:
            res = requests.post(self.kimi_url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
            if res.status_code == 200:
                resp_data = res.json()
                if resp_data.get("ok"):
                    return {"success": True, "data": resp_data.get("data")}
                else:
                    return {"success": False, "error": resp_data.get("error", "Unknown WebBridge error")}
            return {"success": False, "error": f"HTTP status code: {res.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Failed to communicate with Kimi daemon: {e}"}

    def find_and_fill_search(self, term: str, session: str = "kimi") -> bool:
        """Dynamically finds a search input element on the current page, fills it, and submits it."""
        snap = self.snapshot(session=session)
        if not snap.get("success"):
            return False
        
        current_url = snap.get("data", {}).get("url", "").lower()
        
        # 1. Check against known search configs
        for site, config in SITE_SEARCH_CONFIGS.items():
            if config["url_pattern"] in current_url:
                print(f"[Browser] Matches known config for {site}. Filling search field...")
                fill_res = self.fill(config["input"], term, session=session)
                if fill_res.get("success"):
                    self.evaluate(config["submit_js"], session=session)
                    return True
        
        # 2. Dynamic heuristics if not a known site
        search_selectors = [
            "input[type='search']",
            "input[name='search']",
            "input[name='q']",
            "input[id*='search']",
            "input[class*='search']",
            "input[placeholder*='search' i]",
            "input[placeholder*='Search' i]",
            "input[type='text']"
        ]
        
        for sel in search_selectors:
            check_js = f"document.querySelector(\"{sel}\") !== null"
            check_res = self.evaluate(check_js, session=session)
            if check_res.get("success") and check_res.get("data", {}).get("value") is True:
                print(f"[Browser] Found search input using selector: '{sel}'. Filling...")
                fill_res = self.fill(sel, term, session=session)
                if fill_res.get("success"):
                    submit_js = f"document.querySelector(\"{sel}\").form.submit()"
                    self.evaluate(submit_js, session=session)
                    return True
        
        return False

    def smart_navigate(self, query: str, session: str = "kimi") -> dict:
        """
        Intelligently resolves and navigates the browser based on query input.
        Handles raw URLs, simple domains, and natural language instructions.
        """
        query_lower = query.lower().strip()
        
        # Clean up "browser navigate " prefix if present
        if query_lower.startswith("browser navigate "):
            query = query[len("browser navigate "):].strip()
            query_lower = query.lower()
        elif query_lower.startswith("browser "):
            query = query[len("browser "):].strip()
            query_lower = query.lower()
            
        site_name = None
        search_term = None
        
        # Pattern A: "to <site> and search <term>" or "navigate to <site> and search <term>"
        match_a = re.search(r"(?:navigate\s+to\s+|go\s+to\s+|open\s+)?(\w+(?:\.\w+)?)\s+and\s+search\s+(?:for\s+)?(.+)", query_lower)
        if match_a:
            site_name = match_a.group(1).strip()
            search_term = match_a.group(2).strip()
        else:
            # Pattern B: "search (for) <term> on <site>"
            match_b = re.search(r"search\s+(?:for\s+)?(.+)\s+on\s+(\w+(?:\.\w+)?)", query_lower)
            if match_b:
                search_term = match_b.group(1).strip()
                site_name = match_b.group(2).strip()
                
        if site_name and search_term:
            print(f"[Browser] Detected natural language search query. Site: '{site_name}', Term: '{search_term}'")
            
            target_url = None
            for key, val in SITE_MAP.items():
                if key in site_name:
                    target_url = val
                    break
            
            if not target_url:
                if "." in site_name:
                    target_url = f"https://{site_name}"
                else:
                    print(f"[Browser] Site '{site_name}' not in pre-defined map. Performing web search to find it...")
                    search_results = self.search(site_name, limit=1)
                    if search_results:
                        target_url = search_results[0]["link"]
                        print(f"[Browser] Found domain for '{site_name}': {target_url}")
                    else:
                        target_url = f"https://www.google.com"
            
            nav_res = self.navigate(target_url, new_tab=True, session=session)
            if not nav_res.get("success"):
                return nav_res
                
            import time
            time.sleep(2)
            
            fill_success = self.find_and_fill_search(search_term, session=session)
            if fill_success:
                time.sleep(2)
                return {"success": True, "message": f"Successfully navigated to {site_name} and searched for '{search_term}'."}
            else:
                return {"success": False, "error": f"Failed to locate search input on {target_url}."}
                
        url = query
        for prefix in ["to ", "go to ", "navigate to ", "open "]:
            if url.lower().startswith(prefix):
                url = url[len(prefix):].strip()
                
        url_lower = url.lower()
        target_url = None
        for key, val in SITE_MAP.items():
            if url_lower == key:
                target_url = val
                break
                
        if not target_url:
            if " " not in url:
                if url.startswith("http://") or url.startswith("https://") or url.startswith("chrome://") or url.startswith("localhost") or url.startswith("127.0.0.1"):
                    target_url = url
                elif "." in url:
                    target_url = f"https://{url}"
                    
        if not target_url:
            print(f"[Browser] Query '{url}' is not a raw URL. Performing DuckDuckGo search...")
            search_results = self.search(url, limit=1)
            if search_results:
                target_url = search_results[0]["link"]
                print(f"[Browser] Navigating to first search result: '{target_url}'")
            else:
                target_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(url)}"
                
        return self.navigate(target_url, new_tab=True, session=session)

    def navigate(self, url: str, new_tab: bool = True, session: str = "kimi") -> dict:
        """Instructs browser to navigate to target URL, with self-healing for stale tabs"""
        res = self.send_command("navigate", {"url": url, "newTab": new_tab}, session=session)
        
        # Check if the response indicates a stale tab ID error
        error = res.get("error", "")
        error_msg = ""
        if isinstance(error, dict):
            error_msg = error.get("message", "")
        elif isinstance(error, str):
            error_msg = error
            
        if not res.get("success") and ("no tab with given id" in error_msg.lower() or "tab closed" in error_msg.lower() or "invalid session" in error_msg.lower()):
            print(f"[Browser Warning] Stale/closed session tab detected. Re-initializing session '{session}'...")
            # Silently force close the session to clear the old tab mapping
            self.close_session(session=session)
            # Re-attempt navigation with newTab=True to force open a fresh working tab
            res = self.send_command("navigate", {"url": url, "newTab": True}, session=session)
            
        return res

    def find_tab(self, url: str, active: bool = True, session: str = "kimi") -> dict:
        """Finds an already-open tab matching the target domain/URL"""
        return self.send_command("find_tab", {"url": url, "active": active}, session=session)

    def click(self, selector: str, session: str = "kimi") -> dict:
        """Simulates a synthetic element click using an accessibility @e ref or CSS selector"""
        return self.send_command("click", {"selector": selector}, session=session)

    def fill(self, selector: str, value: str, session: str = "kimi") -> dict:
        """Fills an input, textarea, or contenteditable element with the target value"""
        return self.send_command("fill", {"selector": selector, "value": value}, session=session)

    def evaluate(self, code: str, session: str = "kimi") -> dict:
        """Runs dynamic JavaScript in the browser console"""
        return self.send_command("evaluate", {"code": code}, session=session)

    def snapshot(self, session: str = "kimi") -> dict:
        """Retrieves page title, URL, and accessibility tree representation"""
        return self.send_command("snapshot", {}, session=session)

    def screenshot(self, output_path: str = None, selector: str = None, session: str = "kimi") -> dict:
        """Captures a screenshot of the current page or a specific element"""
        args = {"format": "png"}
        if selector:
            args["selector"] = selector
        res = self.send_command("screenshot", args, session=session)
        if not res.get("success"):
            return res
            
        data = res.get("data", {})
        base64_data = data.get("data", "")
        if not base64_data:
            return {"success": False, "error": "No screenshot data returned"}
            
        import base64
        if not output_path:
            import time
            timestamp = int(time.time())
            output_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "screenshots", f"screenshot_{timestamp}.png"))
            
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(base64_data))
            return {"success": True, "path": output_path}
        except Exception as e:
            return {"success": False, "error": f"Failed to save screenshot file: {e}"}

    def save_as_pdf(self, file_name: str = None, paper_format: str = "letter", landscape: bool = False, session: str = "kimi") -> dict:
        """Renders current browser window into a PDF document"""
        args = {
            "paper_format": paper_format,
            "landscape": landscape,
            "print_background": True
        }
        if file_name:
            args["file_name"] = file_name
        res = self.send_command("save_as_pdf", args, session=session)
        if not res.get("success"):
            return res
        
        data = res.get("data", {})
        pdf_path = data.get("path")
        if pdf_path and os.path.exists(pdf_path):
            import shutil
            dest_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "pdf"))
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, os.path.basename(pdf_path))
            try:
                shutil.copy2(pdf_path, dest_path)
                return {"success": True, "path": dest_path}
            except Exception as e:
                return {"success": True, "path": pdf_path, "warning": f"Could not copy PDF file: {e}"}
        return {"success": False, "error": "No PDF path returned by daemon"}

    def close_session(self, session: str = "kimi") -> dict:
        """Terminates and closes all tabs active under this session name"""
        return self.send_command("close_session", {}, session=session)

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
            
            blocks = soup.find_all("div", class_="result__body")
            
            for block in blocks[:limit]:
                title_el = block.find("a", class_="result__url")
                snippet_el = block.find("a", class_="result__snippet")
                
                if title_el and title_el.get("href"):
                    title = title_el.get_text().strip()
                    raw_href = title_el.get("href")
                    
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
        Fetches web page content. If Kimi WebBridge is active, renders with a real browser session;
        otherwise, falls back to requests + BeautifulSoup scraping.
        """
        if self.is_kimi_active():
            print(f"[Browser] Kimi WebBridge active. Navigating via real browser to: '{url}'")
            nav_res = self.navigate(url, new_tab=True, session="kimi-scrape")
            if nav_res.get("success"):
                import time
                time.sleep(2.0)  # Allow page JS and ajax resources to render
                
                # Get document title and inner text via evaluate
                title_res = self.evaluate("document.title", session="kimi-scrape")
                text_res = self.evaluate("document.body.innerText", session="kimi-scrape")
                
                title = "Kimi Scraped Page"
                if title_res.get("success") and title_res.get("data"):
                    title = title_res.get("data", {}).get("value") or title
                    
                content = ""
                if text_res.get("success") and text_res.get("data"):
                    content = text_res.get("data", {}).get("value") or ""
                    
                self.close_session(session="kimi-scrape")
                
                trimmed_text = content[:8000]
                if len(content) > 8000:
                    trimmed_text += "\n\n[Content Truncated due to size constraints]"
                    
                return {
                    "title": title,
                    "content": trimmed_text,
                    "url": url,
                    "method": "Kimi WebBridge"
                }
            else:
                print(f"[Browser Warning] Kimi navigation failed: {nav_res.get('error')}. Falling back...")
                
        # Standard fallback to requests and BeautifulSoup
        print(f"[Browser] Falling back to standard requests scraping for: '{url}'")
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, "html.parser")
            
            for el in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                el.decompose()
                
            title = soup.title.get_text().strip() if soup.title else "Untitled Page"
            
            body = soup.find("main") or soup.find("article") or soup.find("body")
            if not body:
                body = soup
                
            lines = (line.strip() for line in body.get_text().splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
            trimmed_text = clean_text[:8000]
            if len(clean_text) > 8000:
                trimmed_text += "\n\n[Content Truncated due to size constraints]"
                
            return {
                "title": title,
                "content": trimmed_text,
                "url": url,
                "method": "Requests"
            }
        except Exception as e:
            return {
                "title": "Error scraping page",
                "content": f"Failed to retrieve url: {e}",
                "url": url,
                "method": "Failed"
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
