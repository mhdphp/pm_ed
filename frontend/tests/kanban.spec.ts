import { expect, test, type Page } from "@playwright/test";

const login = async (page: Page) => {
  await page.goto("/");
  await page.getByPlaceholder("user").fill("user");
  await page.getByPlaceholder("password").fill("password");
  await page.getByRole("button", { name: /sign in/i }).click();
};

const getColumnByTitle = (page: Page, title: string) =>
  page.locator('[data-testid^="column-"]').filter({
    has: page.locator(`input[aria-label="Column title"][value="${title}"]`),
  });

test("loads the kanban board", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: "Kanban Studio" })).toBeVisible();
  await expect(page.locator('[data-testid^="column-"]')).toHaveCount(5);
});

test("adds a card to a column", async ({ page }) => {
  await login(page);
  const firstColumn = getColumnByTitle(page, "Backlog");
  await firstColumn.getByRole("button", { name: /add a card/i }).click();
  await firstColumn.getByPlaceholder("Card title").fill("Playwright card");
  await firstColumn.getByPlaceholder("Details").fill("Added via e2e.");
  await firstColumn.getByRole("button", { name: /add card/i }).click();
  await expect(firstColumn.getByText("Playwright card").first()).toBeVisible();
});

test("moves a card between columns", async ({ page }) => {
  await login(page);
  const card = page.locator("article", { hasText: "Align roadmap themes" }).first();
  const targetColumn = getColumnByTitle(page, "Review");
  await expect(card).toBeVisible();
  const cardBox = await card.boundingBox();
  const columnBox = await targetColumn.boundingBox();
  if (!cardBox || !columnBox) {
    throw new Error("Unable to resolve drag coordinates.");
  }

  await page.mouse.move(
    cardBox.x + cardBox.width / 2,
    cardBox.y + cardBox.height / 2
  );
  await page.mouse.down();
  await page.mouse.move(
    columnBox.x + columnBox.width / 2,
    columnBox.y + 120,
    { steps: 12 }
  );
  await page.mouse.up();
  await expect(targetColumn.getByText("Align roadmap themes")).toBeVisible();
});

test("edits a card and keeps the change after reload", async ({ page }) => {
  await login(page);
  const column = getColumnByTitle(page, "Discovery");
  const title = `Edit me ${Date.now()}`;
  await column.getByRole("button", { name: /add a card/i }).click();
  await column.getByPlaceholder("Card title").fill(title);
  await column.getByRole("button", { name: /add card/i }).click();
  await expect(column.getByText(title)).toBeVisible();

  await column.getByRole("button", { name: `Edit ${title}`, exact: true }).click();
  await column.getByLabel("Card title").fill(`${title} edited`);
  await column.getByLabel("Card details").fill("Edited via e2e.");
  await column.getByRole("button", { name: "Save", exact: true }).click();
  await expect(column.getByText(`${title} edited`)).toBeVisible();

  await page.reload();
  await login(page);
  const reloaded = getColumnByTitle(page, "Discovery");
  await expect(reloaded.getByText(`${title} edited`)).toBeVisible();
  await expect(reloaded.getByText("Edited via e2e.").first()).toBeVisible();
  await reloaded.getByRole("button", { name: `Delete ${title} edited`, exact: true }).click();
  await expect(reloaded.getByText(`${title} edited`)).toHaveCount(0);
});

test("renames a column on blur and keeps it after reload", async ({ page }) => {
  await login(page);
  const input = getColumnByTitle(page, "Review").getByLabel("Column title");
  await input.fill("QA");
  await input.press("Enter");
  await expect(page.locator('input[aria-label="Column title"][value="QA"]')).toHaveCount(1);

  await page.reload();
  await login(page);
  const renamed = getColumnByTitle(page, "QA").getByLabel("Column title");
  await expect(renamed).toHaveValue("QA");
  await renamed.fill("Review");
  await renamed.press("Enter");
  await expect(page.locator('input[aria-label="Column title"][value="Review"]')).toHaveCount(1);
});
