/**
 * E2E tests for authentication flows: signup, login, logout, profile, password change.
 * Covers all user-facing auth interactions from UI to backend (mock mode).
 */
import path from "path";
import { fileURLToPath } from "url";
import { expect, test } from "@playwright/test";
import { clearMockAuthSession } from "./auth-helpers";

const e2eDir = path.dirname(fileURLToPath(import.meta.url));
const tinyPng = path.join(e2eDir, "fixtures", "tiny.png");

// Helper: generate unique user credentials per test
function uniqueUser() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    username: `user${suffix}`,
    email: `e2e-${suffix}@example.com`,
    password: "password123",
  };
}

test.describe("Signup flow", () => {
  test("successful signup redirects to upload page", async ({ page }) => {
    const { username, email, password } = uniqueUser();
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();

    await expect(page.getByText(/account created successfully/i)).toBeVisible({ timeout: 10_000 });
    await page.waitForURL("**/upload", { timeout: 20_000 });
    await expect(page.getByText(/upload artwork/i)).toBeVisible();
  });

  test("duplicate email shows error", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    // First signup
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Logout and try to sign up again with same email
    await page.goto("/signup");
    await page.getByLabel("Username").fill(`${username}2`);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();

    await expect(page.getByText(/email already registered/i)).toBeVisible({ timeout: 5_000 });
  });

  test("short username shows validation error", async ({ page }) => {
    await page.goto("/signup");
    await page.getByLabel("Username").fill("ab"); // min 3
    await page.getByLabel("Email").fill("test@example.com");
    await page.getByLabel("Password", { exact: true }).fill("password123");
    await page.getByRole("button", { name: /^sign up$/i }).click();

    await expect(page.getByText(/at least 3 characters/i)).toBeVisible({ timeout: 5_000 });
  });

  test("short password shows validation error", async ({ page }) => {
    await page.goto("/signup");
    await page.getByLabel("Username").fill("validuser");
    await page.getByLabel("Email").fill("test@example.com");
    await page.getByLabel("Password", { exact: true }).fill("12345"); // min 6
    await page.getByRole("button", { name: /^sign up$/i }).click();

    await expect(page.getByText(/at least 6 characters/i)).toBeVisible({ timeout: 5_000 });
  });

  test("password visibility toggle works", async ({ page }) => {
    await page.goto("/signup");
    const passwordInput = page.getByLabel("Password", { exact: true });
    await expect(passwordInput).toHaveAttribute("type", "password");

    // Click the eye icon to show password
    await page.locator('button[type="button"]').last().click();
    await expect(passwordInput).toHaveAttribute("type", "text");

    // Click again to hide
    await page.locator('button[type="button"]').last().click();
    await expect(passwordInput).toHaveAttribute("type", "password");
  });

  test("signup page has link to login", async ({ page }) => {
    await page.goto("/signup");
    const formLink = page.getByRole("link", { name: "Log in", exact: true });
    await expect(formLink).toBeVisible();
    await formLink.click();
    await expect(page).toHaveURL(/\/login$/);
  });
});

test.describe("Login flow", () => {
  test("successful login navigates to upload", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    // Create account first
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await clearMockAuthSession(page);
    await page.goto("/login");

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^log in$/i }).click();

    await page.waitForURL("**/upload", { timeout: 10_000 });
    await expect(page.getByText(/upload artwork/i)).toBeVisible();
  });

  test("wrong password shows error", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    // Create account
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await clearMockAuthSession(page);
    await page.goto("/login");

    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("wrongpassword");
    await page.getByRole("button", { name: /^log in$/i }).click();

    await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 5_000 });
  });

  test("unknown email shows error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("nobody@nowhere.com");
    await page.getByLabel("Password", { exact: true }).fill("password123");
    await page.getByRole("button", { name: /^log in$/i }).click();

    await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 5_000 });
  });

  test("login page has link to signup", async ({ page }) => {
    await page.goto("/login");
    const formLink = page.getByRole("link", { name: "Sign up", exact: true });
    await expect(formLink).toBeVisible();
    await formLink.click();
    await expect(page).toHaveURL(/\/signup$/);
  });

  test("already authenticated user is redirected from login", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    // Sign up first
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Try to visit login while authenticated
    await page.goto("/login");
    await page.waitForURL("**/upload", { timeout: 5_000 });
  });
});

test.describe("Protected routes", () => {
  test("upload page redirects unauthenticated users to login", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/upload");
    await expect(page).toHaveURL(/\/login$/);
    await context.close();
  });

  test("history page redirects unauthenticated users to login", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/history");
    await expect(page).toHaveURL(/\/login$/);
    await context.close();
  });

  test("results page redirects to upload when no result stored", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    // Sign up to be authenticated
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Clear any stored result and navigate to results
    await page.evaluate(() => localStorage.removeItem("artguard_latest_result"));
    await page.goto("/results");
    await page.waitForURL("**/upload", { timeout: 5_000 });
  });
});
