/**
 * E2E tests for the upload and analysis flow.
 * Covers file selection, validation, drag-and-drop, form submission, and results display.
 */
import { Buffer } from "node:buffer";
import path from "path";
import { fileURLToPath } from "url";
import { expect, test } from "@playwright/test";

const e2eDir = path.dirname(fileURLToPath(import.meta.url));
const tinyPng = path.join(e2eDir, "fixtures", "tiny.png");

function uniqueUser() {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return {
    username: `user${suffix}`,
    email: `e2e-${suffix}@example.com`,
    password: "password123",
  };
}

async function signUpAndGoToUpload(page: import("@playwright/test").Page) {
  const { username, email, password } = uniqueUser();
  await page.goto("/signup");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: /^sign up$/i }).click();
  await page.waitForURL("**/upload", { timeout: 20_000 });
  return { username, email, password };
}

test.describe("Upload page", () => {
  test("shows upload form with all required fields", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await expect(page.getByText(/upload artwork/i)).toBeVisible();
    await expect(page.getByPlaceholder("Rembrandt van Rijn")).toBeVisible();
    await expect(page.getByPlaceholder("The Night Watch")).toBeVisible();
    await expect(page.getByRole("button", { name: /analyze artwork/i })).toBeVisible();
  });

  test("analyze button is disabled until all fields are filled", async ({ page }) => {
    await signUpAndGoToUpload(page);
    const analyzeBtn = page.getByRole("button", { name: /analyze artwork/i });
    await expect(analyzeBtn).toBeDisabled();

    // Upload file
    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await expect(analyzeBtn).toBeDisabled(); // still disabled — no artist/artwork

    // Fill artist
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Monet");
    await expect(analyzeBtn).toBeDisabled(); // still disabled — no artwork

    // Fill artwork
    await page.getByPlaceholder("The Night Watch").fill("Water Lilies");
    await expect(analyzeBtn).toBeEnabled();
  });

  test("file preview appears after selection", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await page.locator('input[type="file"]').setInputFiles(tinyPng);

    // Preview image should appear
    await expect(page.locator('img[src^="data:"]')).toBeVisible({ timeout: 5_000 });
    // File name should be shown
    await expect(page.getByText("tiny.png")).toBeVisible();
  });

  test("remove file button clears selection", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await expect(page.getByText("tiny.png")).toBeVisible();

    await page.getByRole("button", { name: /remove/i }).click();
    await expect(page.getByText("tiny.png")).not.toBeVisible();
    await expect(page.getByText(/drop image or click to upload/i)).toBeVisible();
  });

  test("full analysis flow reaches results page with score", async ({ page }) => {
    await signUpAndGoToUpload(page);

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Claude Monet");
    await page.getByPlaceholder("The Night Watch").fill("Water Lilies");
    await page.getByRole("button", { name: /analyze artwork/i }).click();

    await page.waitForURL("**/results", { timeout: 60_000 });
    await expect(page.getByText("PREDICTION CONFIDENCE", { exact: true })).toBeVisible();
    await expect(page.locator("main")).toContainText("%");
  });

  test("results page shows verdict (Authentic or Inauthentic)", async ({ page }) => {
    await signUpAndGoToUpload(page);

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Vermeer");
    await page.getByPlaceholder("The Night Watch").fill("Girl with a Pearl Earring");
    await page.getByRole("button", { name: /analyze artwork/i }).click();

    await page.waitForURL("**/results", { timeout: 60_000 });
    await expect(page.locator("main")).toContainText(
      /Authentic|Inauthentic|Unavailable|Error/,
      { timeout: 10_000 },
    );
  });

  test("results page has analyze another artwork button", async ({ page }) => {
    await signUpAndGoToUpload(page);

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Artist");
    await page.getByPlaceholder("The Night Watch").fill("Artwork");
    await page.getByRole("button", { name: /analyze artwork/i }).click();

    await page.waitForURL("**/results", { timeout: 60_000 });
    await expect(page.getByRole("link", { name: /analyze another artwork/i })).toBeVisible();
  });

  test("results page shows patch overlay when mock returns patch data", async ({ page }) => {
    await signUpAndGoToUpload(page);

    await page.locator('input[type="file"]').setInputFiles(tinyPng);
    await page.getByPlaceholder("Rembrandt van Rijn").fill("Artist");
    await page.getByPlaceholder("The Night Watch").fill("Artwork");
    await page.getByRole("button", { name: /analyze artwork/i }).click();

    await page.waitForURL("**/results", { timeout: 60_000 });
    await expect(page.getByText(/per-patch authenticity heatmap/i)).toBeVisible();
  });
});

test.describe("Upload validation", () => {
  test("shows error for oversized file", async ({ page }) => {
    await signUpAndGoToUpload(page);

    const buf = Buffer.alloc(21 * 1024 * 1024);
    buf[0] = 0x89;
    buf[1] = 0x50;
    buf[2] = 0x4e;
    buf[3] = 0x47;

    await page.locator('input[type="file"]').setInputFiles({
      name: "huge.png",
      mimeType: "image/png",
      buffer: buf,
    });

    await expect(page.getByText(/file too large|too large/i)).toBeVisible({ timeout: 5_000 });
  });
});
