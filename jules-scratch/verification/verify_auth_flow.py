from playwright.sync_api import sync_playwright, expect
import time

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # --- 1. Test First-Run Setup ---
            print("--- Testing First-Run Setup ---")
            page.goto("http://localhost:8080", timeout=10000)

            # Expect to be redirected to the setup page
            expect(page).to_have_url("http://localhost:8080/setup")
            print("Successfully redirected to /setup.")

            # Fill out the setup form
            page.get_by_label("Username").fill("testuser")
            page.get_by_label("Password").fill("testpassword")
            page.get_by_role("button", name="Save and Continue").click()

            # Expect to be redirected to the dashboard
            expect(page).to_have_url("http://localhost:8080/")
            print("Successfully redirected to dashboard after setup.")

            # Check for logged-in user display
            expect(page.get_by_text("Logado como: testuser")).to_be_visible()
            print("User is logged in on dashboard.")

            page.screenshot(path="jules-scratch/verification/setup_complete.png")
            print("Screenshot 'setup_complete.png' saved.")

            # --- 2. Test Logout ---
            print("\n--- Testing Logout ---")
            page.get_by_role("link", name="Sair").click()

            # Expect to be redirected to the login page
            expect(page).to_have_url("http://localhost:8080/login")
            print("Successfully redirected to /login after logout.")

            # --- 3. Test Route Protection ---
            print("\n--- Testing Route Protection ---")
            page.goto("http://localhost:8080/config")
            expect(page).to_have_url("http://localhost:8080/login")
            print("Successfully blocked from accessing /config and redirected to /login.")

            # --- 4. Test Login ---
            print("\n--- Testing Login ---")
            # Fill out the login form
            page.get_by_label("Username").fill("testuser")
            page.get_by_label("Password").fill("testpassword")
            page.get_by_role("button", name="Login").click()

            # Expect to be redirected back to the dashboard
            expect(page).to_have_url("http://localhost:8080/")
            print("Successfully redirected to dashboard after login.")

            expect(page.get_by_text("Logado como: testuser")).to_be_visible()
            print("User is logged in again.")

            page.screenshot(path="jules-scratch/verification/login_complete.png")
            print("Screenshot 'login_complete.png' saved.")

        except Exception as e:
            print(f"\nAn error occurred: {e}")
            page.screenshot(path="jules-scratch/verification/error.png")
            print("Error screenshot saved to jules-scratch/verification/error.png")

        finally:
            browser.close()

if __name__ == "__main__":
    run_verification()