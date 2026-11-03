// Real Fireworks calls through the UI. Needs a key in .env. Spends about $0.02 the first time per invoice, then replays from the disk cache.
const { test, expect } = require('@playwright/test');
const { ARMS, hasKey } = require('./score');

test.skip(!hasKey(), 'No Fireworks key in .env');

test('all three arms answer the lead invoice on Fireworks', async ({ page }) => {
  await page.goto('/web/');
  await expect(page.locator('#cmp-run')).toBeEnabled();
  await page.locator('#cmp-run').click();
  await expect(page.locator('#cmp-run-status')).toContainText('All three arms answered', { timeout: 300000 });
  for (const arm of ARMS) {
    const card = page.getByTestId(`arm-${arm}`);
    await expect(card, `${arm} should finish without an error`).not.toHaveAttribute('data-state', 'error');
    expect(['live', 'cached']).toContain(await card.getAttribute('data-state'));
    console.log(`${arm}: ${await card.getAttribute('data-action')}, ${await card.locator('.arm-meta').innerText()}, ${await page.getByTestId(`source-${arm}`).innerText()}`);
  }
  // The harness decision comes from a code check on the quantity, so both readers must reach it. Kimi alone is reported, not asserted.
  await expect(page.getByTestId('arm-glm_harness_wiki')).toHaveAttribute('data-action', 'ESCALATE');
  await expect(page.getByTestId('arm-kimi_harness_wiki')).toHaveAttribute('data-action', 'ESCALATE');
});
