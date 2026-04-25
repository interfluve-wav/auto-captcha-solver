import sys
import json
sys.path.insert(0, "/Users/suhaas/Documents/GitHub/auto-captcha-solver/src")

from playwright.sync_api import sync_playwright
from auto_captcha_solver import CaptchaSolver

# Use a dummy key (won't solve, but detection should still work)
solver = CaptchaSolver(api_key="test-key")

def test_detection_on_real_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        # Use the official hCaptcha demo page
        page.goto("https://accounts.hcaptcha.com/demo", timeout=30000)
        page.wait_for_load_state("networkidle")

        # Detect captchas
        found = solver.detect(page)

        print("DETECTED:", json.dumps(found, indent=2, default=str))

        # Assert
        assert len(found) >= 1, "Expected at least one hCaptcha on demo page"
        assert any(c["type"] == "hcaptcha" for c in found), "hCaptcha not detected"

        browser.close()
        print("✓ Browser detection test PASSED")

if __name__ == "__main__":
    test_detection_on_real_page()
