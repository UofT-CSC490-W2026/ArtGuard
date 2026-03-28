import type { Page } from "@playwright/test";

/** Clears session only; keeps `artguard_users` so mock-mode login still finds accounts. */
export async function clearMockAuthSession(page: Page) {
  await page.evaluate(() => {
    localStorage.removeItem("artguard_user");
    localStorage.removeItem("artguard_access_token");
  });
}
