import path from "path";
import { fileURLToPath } from "url";
import { expect, test } from "@playwright/test";

const e2eDir = path.dirname(fileURLToPath(import.meta.url));
const tinyPng = path.join(e2eDir, "fixtures", "tiny.png");

test.describe("mock mode (no VITE_API_URL)", () => {
  test("home page shows hero and ArtGuard branding", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", {
        name: /authenticate art\. understand why\./i,
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "ArtGuard" })).toBeVisible();
  });

  test("signup then analysis flow reaches results with score UI", async ({
    page,
  }) => {
    const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const email = `e2e-${suffix}@example.com`;

    await page.goto("/signup");
    await page.getByLabel("Username").fill(`user${suffix}`);
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password", { exact: true }).fill("password1");
    await page.getByRole("button", { name: /^sign up$/i }).click();

    await expect(
      page.getByText(/account created successfully/i),
    ).toBeVisible({ timeout: 15_000 });

    await page.waitForURL("**/upload", { timeout: 20_000 });

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Test Artist");
    await page.getByPlaceholder("The Night Watch").fill("Test Artwork");
    await page.getByRole("button", { name: /analyze artwork/i }).click();

    await page.waitForURL("**/results", { timeout: 60_000 });
    await expect(page.getByText("PREDICTION CONFIDENCE", { exact: true })).toBeVisible();
    await expect(page.locator("main")).toContainText("%");
  });

  test("visiting upload while logged out redirects to login", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto("/upload");
    await expect(page).toHaveURL(/\/login$/);
    await context.close();
  });
});
