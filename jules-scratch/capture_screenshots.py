from playwright.sync_api import sync_playwright, expect
import time

def run_capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # --- 1. Capture Setup Page ---
            print("Navigating to capture Setup page...")
            page.goto("http://localhost:8080", timeout=10000)
            expect(page).to_have_url("http://localhost:8080/setup")
            page.screenshot(path="docs/images/setup-page.png")
            print("Captured setup-page.png")

            # --- 2. Complete Setup and Capture Dashboard ---
            print("Completing setup...")
            page.get_by_label("Username").fill("admin")
            page.get_by_label("Password").fill("admin_password_123")
            page.get_by_role("button", name="Save and Continue").click()

            expect(page).to_have_url("http://localhost:8080/")
            print("Navigating to capture Dashboard page...")
            page.screenshot(path="docs/images/dashboard-page.png")
            print("Captured dashboard-page.png")

            # --- 3. Capture Arbitrage Page ---
            print("Navigating to capture Arbitrage page...")
            page.get_by_role("link", name="Arbitragem").click()
            expect(page).to_have_url("http://localhost:8080/arbitrage")
            # Wait for the content to load
            loading_indicator = page.locator("#loading-indicator")
            expect(loading_indicator).to_be_hidden(timeout=15000)
            page.screenshot(path="docs/images/arbitrage-page.png")
            print("Captured arbitrage-page.png")

            # --- 4. Capture Login Page ---
            print("Logging out to capture Login page...")
            page.get_by_role("link", name="Sair").click()
            expect(page).to_have_url("http://localhost:8080/login")
            page.screenshot(path="docs/images/login-page.png")
            print("Captured login-page.png")

        except Exception as e:
            print(f"\nAn error occurred during screenshot capture: {e}")
            page.screenshot(path="jules-scratch/error_capture.png")

        finally:
            browser.close()

if __name__ == "__main__":
    run_capture()