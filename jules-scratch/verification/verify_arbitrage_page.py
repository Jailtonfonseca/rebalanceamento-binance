from playwright.sync_api import sync_playwright, expect

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Navigate to the homepage
            page.goto("http://localhost:8080", timeout=10000)

            # Find and click the "Arbitragem" link in the navigation
            arbitrage_link = page.get_by_role("link", name="Arbitragem")
            expect(arbitrage_link).to_be_visible()
            arbitrage_link.click()

            # Wait for the new page to load and check for the title
            expect(page).to_have_title("Rebalanceador de Cripto")

            # Check for the presence of the main card title
            card_title = page.get_by_role("heading", name="Arbitrage Opportunities")
            expect(card_title).to_be_visible()

            # Wait for the loading indicator to disappear, which means data has been fetched
            loading_indicator = page.locator("#loading-indicator")
            expect(loading_indicator).to_be_hidden(timeout=15000) # Increased timeout for API call

            # Take a screenshot of the arbitrage page
            page.screenshot(path="jules-scratch/verification/verification.png")
            print("Screenshot saved to jules-scratch/verification/verification.png")

        except Exception as e:
            print(f"An error occurred: {e}")
            page.screenshot(path="jules-scratch/verification/error.png")
            print("Error screenshot saved to jules-scratch/verification/error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    run_verification()