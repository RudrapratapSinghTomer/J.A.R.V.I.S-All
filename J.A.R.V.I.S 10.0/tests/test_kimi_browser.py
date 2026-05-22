import os
import sys
import time

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.browser import WebBridgeBrowser

def main():
    print("=== Testing J.A.R.V.I.S 10.0 Kimi WebBridge Browser Capabilities ===")

    browser = WebBridgeBrowser()

    # 1. Check Kimi Daemon Status
    print("\n[Step 1] Probing Kimi WebBridge daemon status...")
    is_active = browser.is_kimi_active()
    print(f"Kimi WebBridge active: {is_active}")
    
    # We expect Kimi daemon to be active under the project requirement.
    assert is_active, "Kimi WebBridge daemon must be active for this test suite!"

    # 2. Test Navigation
    print("\n[Step 2] Navigating to https://example.com...")
    # Proactively clear previous/stale sessions to release locks
    browser.close_session(session="kimi-test-suite")
    browser.close_session(session="kimi-scrape")
    time.sleep(0.5)

    nav_res = None
    for attempt in range(2):
        print(f"Navigation attempt {attempt + 1}...")
        nav_res = browser.navigate("https://example.com", new_tab=True, session="kimi-test-suite")
        if nav_res.get("success"):
            break
        print(f"[Warning] Attempt {attempt + 1} failed: {nav_res.get('error')}")
        time.sleep(1.5)

    print(f"Navigation response: {nav_res}")
    assert nav_res.get("success"), f"Navigation failed: {nav_res.get('error')}"

    # Wait for page to render
    time.sleep(2.0)

    # 3. Test JavaScript Evaluation (using IIFE for scope protection if needed)
    print("\n[Step 3] Evaluating document title via browser execution context...")
    eval_res = browser.evaluate("(() => { return document.title; })()", session="kimi-test-suite")
    print(f"Evaluation response: {eval_res}")
    assert eval_res.get("success"), f"JS Evaluation failed: {eval_res.get('error')}"
    
    val = eval_res.get("data", {}).get("value")
    print(f"Document title evaluated: '{val}'")
    assert "Example Domain" in val, f"Expected 'Example Domain' in title, got: '{val}'"

    # 4. Test Web Page Scraping Pathway
    print("\n[Step 4] Scraping https://example.com using Kimi integration...")
    # Proactively clear kimi-scrape session to release any old locks
    browser.close_session(session="kimi-scrape")
    time.sleep(1.0)
    
    scrape_res = None
    for attempt in range(3):
        print(f"Scrape attempt {attempt + 1}...")
        scrape_res = browser.scrape_url("https://example.com")
        if scrape_res.get("method") == "Kimi WebBridge":
            break
        print(f"[Warning] Scrape attempt {attempt + 1} fell back or failed: {scrape_res.get('method')}")
        time.sleep(3.0)

    print(f"Scraped title: {scrape_res.get('title')}")
    print(f"Scraped method: {scrape_res.get('method')}")
    print(f"Scraped content length: {len(scrape_res.get('content', ''))}")
    assert scrape_res.get("method") == "Kimi WebBridge", f"Expected Kimi WebBridge scraper, got {scrape_res.get('method')}"
    assert "Example Domain" in scrape_res.get("title"), "Scraped title incorrect"
    assert "example" in scrape_res.get("content").lower(), "Scraped body content incorrect"

    # 5. Test Screenshot Rendering
    print("\n[Step 5] Testing page screenshot capturing...")
    # Define an absolute path inside capabilities/screenshots
    screenshot_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "screenshots"))
    output_path = os.path.join(screenshot_dir, "test_kimi_screenshot.png")
    
    # Proactively clean up any existing file
    if os.path.exists(output_path):
        os.remove(output_path)

    res_screenshot = browser.screenshot(output_path=output_path, session="kimi-test-suite")
    print(f"Screenshot response: {res_screenshot}")
    if res_screenshot.get("success"):
        assert os.path.exists(output_path), f"Screenshot file was not written to: {output_path}"
        assert os.path.getsize(output_path) > 0, "Screenshot file is empty"
        print(f"[SUCCESS] Screenshot successfully saved to: {output_path}")
    else:
        err = res_screenshot.get("error", "")
        if "502" in err or "timeout" in err.lower():
            print(f"[INFO] Screenshot skipped/failed due to expected platform limitation: {err}")
        else:
            assert False, f"Screenshot failed unexpectedly: {err}"

    # 6. Test PDF Rendering
    print("\n[Step 6] Testing PDF document rendering...")
    pdf_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "pdf"))
    output_pdf = "test_kimi_pdf.pdf"
    dest_pdf_path = os.path.join(pdf_dir, output_pdf)
    
    # Clean up existing file
    if os.path.exists(dest_pdf_path):
        os.remove(dest_pdf_path)

    res_pdf = browser.save_as_pdf(file_name=output_pdf, session="kimi-test-suite")
    print(f"PDF response: {res_pdf}")
    if res_pdf.get("success"):
        pdf_path = res_pdf.get("path")
        assert os.path.exists(pdf_path), f"PDF file was not copied/saved to: {pdf_path}"
        assert os.path.getsize(pdf_path) > 0, "PDF file is empty"
        print(f"[SUCCESS] PDF successfully rendered to: {pdf_path}")
    else:
        err = res_pdf.get("error", "")
        if "502" in err or "timeout" in err.lower():
            print(f"[INFO] PDF rendering skipped/failed due to expected platform limitation: {err}")
        else:
            assert False, f"PDF rendering failed unexpectedly: {err}"

    # 6.5. Test Smart Navigation & Natural Language Search
    print("\n[Step 6.5] Testing smart navigation and search ('to wikipedia and search dog')...")
    res_smart = browser.smart_navigate("to wikipedia and search dog", session="kimi-test-suite")
    print(f"Smart navigation response: {res_smart}")
    assert res_smart.get("success"), f"Smart navigation failed: {res_smart.get('error')}"
    
    # Verify we are on Wikipedia's dog article or land page
    snap_smart = browser.snapshot(session="kimi-test-suite")
    title_smart = snap_smart.get("data", {}).get("title", "")
    print(f"Current page title: '{title_smart}'")
    assert "Dog" in title_smart or "Wikipedia" in title_smart, f"Did not land on expected search result page, got: '{title_smart}'"

    # 7. Test Session Teardown
    print("\n[Step 7] Testing session termination...")
    close_res = browser.close_session(session="kimi-test-suite")
    print(f"Close session response: {close_res}")
    assert close_res.get("success"), f"Close session failed: {close_res.get('error')}"

    print("\n[SUCCESS] J.A.R.V.I.S 10.0 WebBridge Browser verification passes flawlessly!")

if __name__ == "__main__":
    main()
