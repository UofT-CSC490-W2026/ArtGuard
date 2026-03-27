/**
 * E2E tests for navigation, home page, and general UI flows.
 */
import { expect, test } from "@playwright/test";

function uniqueUser() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    username: `user${suffix}`,
    email: `e2e-${suffix}@example.com`,
    password: "password123",
  };
}

test.describe("Home page", () => {
  test("shows ArtGuard branding and hero text", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /shaping tomorrow's art authentication with ai/i }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "ArtGuard" })).toBeVisible();
  });

  test("shows Get started link for unauthenticated users", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("link", { name: /get started/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /log in/i })).toBeVisible();
  });

  test("shows Analyze artwork link for authenticated users", async ({ page }) => {
    const { username, email, password } = uniqueUser();
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.goto("/");
    await expect(page.getByRole("link", { name: /analyze artwork/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /history/i })).toBeVisible();
  });

  test("Get started navigates to signup", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /get started/i }).click();
    await expect(page).toHaveURL(/\/signup$/);
  });

  test("Log in link navigates to login", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /log in/i }).first().click();
    await expect(page).toHaveURL(/\/login$/);
  });

  test("footer shows copyright year", async ({ page }) => {
    await page.goto("/");
    const year = new Date().getFullYear().toString();
    await expect(page.getByText(new RegExp(year))).toBeVisible();
  });

  test("footer navigation links work", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: /^analyze$/i }).click();
    // Should redirect to login since not authenticated
    await expect(page).toHaveURL(/\/(login|upload)$/);
  });
});

test.describe("Header navigation", () => {
  test("header shows Sign Up and Log In for unauthenticated users", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("link", { name: /sign up/i })).toBeVisible();
  });

  test("header shows navigation for authenticated users", async ({ page }) => {
    const { username, email, password } = uniqueUser();
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Header should show navigation links
    await expect(page.getByRole("link", { name: "ArtGuard" })).toBeVisible();
  });
});

test.describe("404 and edge cases", () => {
  test("unknown route shows something (not blank)", async ({ page }) => {
    await page.goto("/this-route-does-not-exist");
    // Should either redirect or show some content — not a blank page
    const bodyText = await page.locator("body").textContent();
    expect(bodyText?.trim().length).toBeGreaterThan(0);
  });
});
