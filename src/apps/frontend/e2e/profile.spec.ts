/**
 * E2E tests for the profile page: update username/email, change password.
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

async function signUpAndGoToProfile(page: import("@playwright/test").Page) {
  const creds = uniqueUser();
  await page.goto("/signup");
  await page.getByLabel("Username").fill(creds.username);
  await page.getByLabel("Email").fill(creds.email);
  await page.getByLabel("Password", { exact: true }).fill(creds.password);
  await page.getByRole("button", { name: /^sign up$/i }).click();
  await page.waitForURL("**/upload", { timeout: 20_000 });
  await page.goto("/profile");
  return creds;
}

test.describe("Profile page", () => {
  test("shows user info pre-filled", async ({ page }) => {
    const { username, email } = await signUpAndGoToProfile(page);
    await expect(page.getByDisplayValue(username)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByDisplayValue(email)).toBeVisible();
  });

  test("save changes button is disabled when nothing changed", async ({ page }) => {
    await signUpAndGoToProfile(page);
    await expect(page.getByRole("button", { name: /save changes/i })).toBeDisabled({ timeout: 5_000 });
  });

  test("save changes button enables when username is modified", async ({ page }) => {
    const { username } = await signUpAndGoToProfile(page);
    const usernameInput = page.getByDisplayValue(username);
    await usernameInput.fill("newusername123");
    await expect(page.getByRole("button", { name: /save changes/i })).toBeEnabled();
  });

  test("shows error for too-short username on save", async ({ page }) => {
    const { username } = await signUpAndGoToProfile(page);
    await page.getByDisplayValue(username).fill("ab");
    await page.getByRole("button", { name: /save changes/i }).click();
    await expect(page.getByText(/at least 3 characters/i)).toBeVisible({ timeout: 5_000 });
  });

  test("shows error when new passwords do not match", async ({ page }) => {
    await signUpAndGoToProfile(page);
    await page.getByLabel(/current password/i).fill("password123");
    await page.getByLabel(/^new password$/i).fill("newpass123");
    await page.getByLabel(/confirm new password/i).fill("differentpass");
    await page.getByRole("button", { name: /change password/i }).click();
    await expect(page.getByText(/passwords do not match/i)).toBeVisible({ timeout: 5_000 });
  });

  test("shows error when new password is too short", async ({ page }) => {
    await signUpAndGoToProfile(page);
    await page.getByLabel(/current password/i).fill("password123");
    await page.getByLabel(/^new password$/i).fill("12345");
    await page.getByLabel(/confirm new password/i).fill("12345");
    await page.getByRole("button", { name: /change password/i }).click();
    await expect(page.getByText(/at least 6 characters/i)).toBeVisible({ timeout: 5_000 });
  });

  test("shows error when current password is wrong", async ({ page }) => {
    await signUpAndGoToProfile(page);
    await page.getByLabel(/current password/i).fill("wrongpassword");
    await page.getByLabel(/^new password$/i).fill("newpass123");
    await page.getByLabel(/confirm new password/i).fill("newpass123");
    await page.getByRole("button", { name: /change password/i }).click();
    await expect(page.getByText(/incorrect/i)).toBeVisible({ timeout: 5_000 });
  });

  test("successful password change clears password fields", async ({ page }) => {
    await signUpAndGoToProfile(page);
    await page.getByLabel(/current password/i).fill("password123");
    await page.getByLabel(/^new password$/i).fill("newpassword456");
    await page.getByLabel(/confirm new password/i).fill("newpassword456");
    await page.getByRole("button", { name: /change password/i }).click();
    // Fields should be cleared after success
    await expect(page.getByLabel(/current password/i)).toHaveValue("", { timeout: 5_000 });
  });

  test("shows account statistics section", async ({ page }) => {
    await signUpAndGoToProfile(page);
    await expect(page.getByText(/account statistics/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/total analyses/i)).toBeVisible();
  });

  test("profile page is protected — redirects unauthenticated users", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/login$/);
    await context.close();
  });
});
