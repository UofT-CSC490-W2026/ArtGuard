/**
 * E2E tests for the history page: viewing, filtering, sorting, and deleting analyses.
 */
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

async function runAnalysis(page: import("@playwright/test").Page, artist = "Monet", artwork = "Lilies") {
  await page.locator('input[type="file"]').setInputFiles(tinyPng);
  await page.getByPlaceholder("Rembrandt van Rijn").fill(artist);
  await page.getByPlaceholder("The Night Watch").fill(artwork);
  await page.getByRole("button", { name: /analyze artwork/i }).click();
  await page.waitForURL("**/results", { timeout: 60_000 });
}

test.describe("History page", () => {
  test("shows empty state when no analyses exist", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await page.goto("/history");
    await expect(page.getByText(/no analysis history yet/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("link", { name: /upload artwork/i })).toBeVisible();
  });

  test("shows analysis after completing one", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await runAnalysis(page, "Rembrandt", "Night Watch");

    await page.goto("/history");
    await expect(page.getByText("Night Watch")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Rembrandt")).toBeVisible();
  });

  test("view details navigates to results page", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await runAnalysis(page, "Vermeer", "Pearl Earring");

    await page.goto("/history");
    await expect(page.getByText("Pearl Earring")).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: /view details/i }).first().click();
    await expect(page).toHaveURL(/\/results$/);
    await expect(page.getByText("AUTHENTICITY CONFIDENCE")).toBeVisible();
  });

  test("delete single analysis removes it from history", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await runAnalysis(page, "Da Vinci", "Mona Lisa");

    await page.goto("/history");
    await expect(page.getByText("Mona Lisa")).toBeVisible({ timeout: 5_000 });

    await page.getByRole("button", { name: /delete/i }).first().click();
    await expect(page.getByText("Mona Lisa")).not.toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/no analysis history yet/i)).toBeVisible();
  });

  test("search filters results by artist name", async ({ page }) => {
    await signUpAndGoToUpload(page);

    // Run two analyses with different artists
    await runAnalysis(page, "Monet", "Water Lilies");
    await page.goto("/upload");
    await runAnalysis(page, "Picasso", "Guernica");

    await page.goto("/history");
    await expect(page.getByText("Water Lilies")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Guernica")).toBeVisible();

    // Search for Monet
    await page.getByPlaceholder(/search artist/i).fill("Monet");
    await expect(page.getByText("Water Lilies")).toBeVisible();
    await expect(page.getByText("Guernica")).not.toBeVisible();
  });

  test("search filters results by artwork name", async ({ page }) => {
    await signUpAndGoToUpload(page);

    await runAnalysis(page, "Monet", "Water Lilies");
    await page.goto("/upload");
    await runAnalysis(page, "Picasso", "Guernica");

    await page.goto("/history");
    await expect(page.getByText("Guernica")).toBeVisible({ timeout: 5_000 });

    await page.getByPlaceholder(/search artist/i).fill("Guernica");
    await expect(page.getByText("Guernica")).toBeVisible();
    await expect(page.getByText("Water Lilies")).not.toBeVisible();
  });

  test("clear all history removes all analyses", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await runAnalysis(page, "Monet", "Water Lilies");

    await page.goto("/history");
    await expect(page.getByText("Water Lilies")).toBeVisible({ timeout: 5_000 });

    // Click Clear All button
    await page.getByRole("button", { name: /clear all/i }).click();

    // Confirm in dialog
    await page.getByRole("button", { name: /^clear all$/i }).last().click();

    await expect(page.getByText(/no analysis history yet/i)).toBeVisible({ timeout: 5_000 });
  });

  test("history page shows analysis count", async ({ page }) => {
    await signUpAndGoToUpload(page);
    await runAnalysis(page, "Monet", "Water Lilies");

    await page.goto("/history");
    await expect(page.getByText(/showing 1 of 1/i)).toBeVisible({ timeout: 5_000 });
  });
});
