/**
 * Full-stack E2E tests: frontend UI → real FastAPI backend → DynamoDB/S3 (mocked via moto).
 *
 * These tests run when VITE_API_URL is set (pointing to a live backend).
 * In CI, the backend is started with mocked AWS before Playwright runs.
 * In mock-only mode (no VITE_API_URL), all tests are skipped.
 *
 * Flow covered:
 *   signup → login → upload image → inference pipeline → results page
 *   → history list → delete → profile update → change password → logout
 */
import path from "path";
import { fileURLToPath } from "url";
import { expect, test } from "@playwright/test";

const e2eDir = path.dirname(fileURLToPath(import.meta.url));
const tinyPng = path.join(e2eDir, "fixtures", "tiny.png");

const BACKEND_URL = process.env.VITE_API_URL || process.env.E2E_BACKEND_URL || "";
const hasBackend = BACKEND_URL.length > 0;

function uniqueUser() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    username: `e2e${suffix}`,
    email: `e2e-${suffix}@test.com`,
    password: "Password123!",
  };
}

test.describe("Full-stack: auth → inference → history pipeline", () => {
  test.skip(!hasBackend, "Skipped: no backend URL set (set VITE_API_URL or E2E_BACKEND_URL)");

  test("signup creates account via real API and returns JWT", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();

    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Verify JWT was stored in localStorage
    const token = await page.evaluate(() => localStorage.getItem("artguard_access_token"));
    expect(token).toBeTruthy();
    expect(token!.split(".")).toHaveLength(3); // valid JWT structure

    // Verify backend /auth/me responds with correct user
    const me = await request.get(`${BACKEND_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(me.ok()).toBe(true);
    const meData = await me.json();
    expect(meData.username).toBe(username);
    expect(meData.email).toBe(email.toLowerCase());
  });

  test("login with correct credentials returns JWT and user", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    // Create account via API directly
    const signup = await request.post(`${BACKEND_URL}/auth/signup`, {
      data: { username, email, password },
    });
    expect(signup.ok()).toBe(true);

    // Login via UI
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^log in$/i }).click();

    await page.waitForURL("**/upload", { timeout: 10_000 });

    const token = await page.evaluate(() => localStorage.getItem("artguard_access_token"));
    expect(token).toBeTruthy();
  });

  test("wrong password returns 401 and shows error in UI", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    // Create account
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.evaluate(() => localStorage.clear());
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("wrongpassword");
    await page.getByRole("button", { name: /^log in$/i }).click();

    await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 5_000 });
  });

  test("full inference pipeline: upload → backend processes → results page shows score", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    // Sign up
    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Upload image
    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Claude Monet");
    await page.getByPlaceholder("The Night Watch").fill("Water Lilies");
    await page.getByRole("button", { name: /analyze artwork/i }).click();

    // Wait for inference to complete (backend + Modal mock)
    await page.waitForURL("**/results", { timeout: 60_000 });

    // Results page must show score
    await expect(page.getByText("AUTHENTICITY CONFIDENCE")).toBeVisible();
    await expect(page.locator("main")).toContainText("%");

    // Verify inference was stored in backend
    const token = await page.evaluate(() => localStorage.getItem("artguard_access_token"));
    const stats = await request.get(`${BACKEND_URL}/inferences/stats`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(stats.ok()).toBe(true);
    const statsData = await stats.json();
    expect(statsData.count).toBeGreaterThanOrEqual(1);
  });

  test("inference appears in history page after analysis", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Vermeer");
    await page.getByPlaceholder("The Night Watch").fill("Pearl Earring");
    await page.getByRole("button", { name: /analyze artwork/i }).click();
    await page.waitForURL("**/results", { timeout: 60_000 });

    // Navigate to history
    await page.goto("/history");
    await expect(page.getByText("Pearl Earring")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Vermeer")).toBeVisible();
  });

  test("delete inference removes it from backend and history page", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Da Vinci");
    await page.getByPlaceholder("The Night Watch").fill("Mona Lisa");
    await page.getByRole("button", { name: /analyze artwork/i }).click();
    await page.waitForURL("**/results", { timeout: 60_000 });

    await page.goto("/history");
    await expect(page.getByText("Mona Lisa")).toBeVisible({ timeout: 10_000 });

    // Delete via UI
    await page.getByRole("button", { name: /delete/i }).first().click();
    await expect(page.getByText("Mona Lisa")).not.toBeVisible({ timeout: 5_000 });

    // Verify deleted in backend
    const token = await page.evaluate(() => localStorage.getItem("artguard_access_token"));
    const stats = await request.get(`${BACKEND_URL}/inferences/stats`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const statsData = await stats.json();
    expect(statsData.count).toBe(0);
  });

  test("profile update persists to backend", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.goto("/profile");
    await expect(page.getByDisplayValue(username)).toBeVisible({ timeout: 5_000 });

    const newUsername = `updated${Date.now()}`;
    await page.getByDisplayValue(username).fill(newUsername);
    await page.getByRole("button", { name: /save changes/i }).click();

    // Verify backend reflects the update
    const token = await page.evaluate(() => localStorage.getItem("artguard_access_token"));
    const me = await request.get(`${BACKEND_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const meData = await me.json();
    expect(meData.username).toBe(newUsername);
  });

  test("change password invalidates old password on backend", async ({ page, request }) => {
    const { username, email, password } = uniqueUser();

    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.goto("/profile");
    await page.getByLabel(/current password/i).fill(password);
    await page.getByLabel(/^new password$/i).fill("NewPassword456!");
    await page.getByLabel(/confirm new password/i).fill("NewPassword456!");
    await page.getByRole("button", { name: /change password/i }).click();

    // Wait for success (fields clear)
    await expect(page.getByLabel(/current password/i)).toHaveValue("", { timeout: 5_000 });

    // Old password should now fail on backend
    const loginOld = await request.post(`${BACKEND_URL}/auth/login`, {
      data: { email, password },
    });
    expect(loginOld.status()).toBe(401);

    // New password should work
    const loginNew = await request.post(`${BACKEND_URL}/auth/login`, {
      data: { email, password: "NewPassword456!" },
    });
    expect(loginNew.ok()).toBe(true);
  });

  test("logout clears JWT and redirects protected routes to login", async ({ page }) => {
    const { username, email, password } = uniqueUser();

    await page.goto("/signup");
    await page.getByLabel("Username").fill(username);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: /^sign up$/i }).click();
    await page.waitForURL("**/upload", { timeout: 20_000 });

    // Open user dropdown and click logout
    await page.getByText(username).click();
    await page.getByText(/log out/i).click();

    // Should redirect to home or login
    await page.waitForURL(/\/(login|)$/, { timeout: 5_000 });

    // JWT should be gone
    const token = await page.evaluate(() => localStorage.getItem("artguard_access_token"));
    expect(token).toBeNull();

    // Protected routes should redirect
    await page.goto("/upload");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("backend health check is reachable", async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/health`);
    expect(resp.ok()).toBe(true);
    expect((await resp.json()).status).toBe("ok");
  });

  test("unauthenticated API calls return 401", async ({ request }) => {
    const resp = await request.get(`${BACKEND_URL}/inferences`);
    expect(resp.status()).toBe(401);
  });

  test("duplicate email signup returns 409 from backend", async ({ request }) => {
    const { username, email, password } = uniqueUser();

    await request.post(`${BACKEND_URL}/auth/signup`, {
      data: { username, email, password },
    });

    const dup = await request.post(`${BACKEND_URL}/auth/signup`, {
      data: { username: `${username}2`, email, password },
    });
    expect(dup.status()).toBe(409);
  });
});
