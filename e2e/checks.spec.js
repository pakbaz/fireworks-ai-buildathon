// UI checks that need no Fireworks key or API spend. Live responses are stubbed here and tested for real in live.spec.js.
const { test, expect } = require('@playwright/test');
const { ARMS, scoreSet } = require('./score');

const SETS = [
  { key: 'test_context', split: 'test_context', requires: ARMS, cases: 210 },
  { key: 'test_300', split: 'test', requires: ARMS, cases: 300 },
  { key: 'test_1000', split: 'test', requires: ['kimi_alone', 'glm_harness_wiki'], cases: 1000 },
];

test.describe('compare view', () => {
  test.beforeEach(async ({ page }) => {
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    page.errors = errors;
    await page.goto('/web/');
    await expect(page.getByTestId('claim-level')).toBeVisible();
  });

  test.afterEach(async ({ page }) => {
    expect(page.errors).toEqual([]);
  });

  for (const set of SETS) {
    test(`scoreboard for ${set.key} matches the saved runs`, async ({ page }) => {
      await page.getByTestId(`set-${set.key}`).click();
      await expect(page.locator('#cmp-score thead th').first()).toHaveText(`${set.cases} invoices`);
      const expected = scoreSet(set.split, set.requires);
      for (const arm of ARMS) {
        const caught = page.getByTestId(`score-caught-${arm}`);
        const falseAlarms = page.getByTestId(`score-false-${arm}`);
        if (expected[arm]) {
          await expect(caught).toHaveText(`${expected[arm].caught} / ${expected[arm].real}`);
          await expect(falseAlarms).toHaveText(`${expected[arm].falseAlarms} / ${expected[arm].fine}`);
        } else {
          await expect(caught).toHaveText('Not run');
        }
      }
    });

    test(`claims for ${set.key} follow the stated rules`, async ({ page }) => {
      await page.getByTestId(`set-${set.key}`).click();
      const s = scoreSet(set.split, set.requires);
      const base = s.kimi_alone;
      const rate = (a, b) => (100 * a) / b;
      const glm = s.glm_harness_wiki;
      const level = rate(glm.caught, glm.real) - rate(base.caught, base.real) >= -1 && rate(glm.falseAlarms, glm.fine) - rate(base.falseAlarms, base.fine) <= 1;
      await expect(page.getByTestId('claim-level')).toHaveAttribute('data-status', level ? 'holds' : 'falls_short');
      const kimi = s.kimi_harness_wiki;
      const beats = kimi && kimi.caught >= base.caught && kimi.falseAlarms <= base.falseAlarms && (kimi.caught > base.caught || kimi.falseAlarms < base.falseAlarms);
      await expect(page.getByTestId('claim-beats')).toHaveAttribute('data-status', !kimi ? 'not_tested' : beats ? 'holds' : 'falls_short');
    });
  }

  test('lead invoice shows each arm\'s saved decision against the answer key', async ({ page }) => {
    await expect(page.locator('#cmp-case')).toHaveValue('TESTCTX-0149');
    await expect(page.getByTestId('arm-kimi_alone')).toHaveAttribute('data-action', 'PAY');
    await expect(page.getByTestId('arm-kimi_alone')).toContainText('Wrong, answer key says ESCALATE');
    for (const arm of ['kimi_harness_wiki', 'glm_harness_wiki']) {
      await expect(page.getByTestId(`arm-${arm}`)).toHaveAttribute('data-action', 'ESCALATE');
      await expect(page.getByTestId(`arm-${arm}`)).toContainText('quantity_spike');
      await expect(page.getByTestId(`source-${arm}`)).toHaveText('Saved run');
    }
  });

  test('picking another invoice updates all three cards', async ({ page }) => {
    const options = await page.locator('#cmp-case option').evaluateAll((els) => els.map((e) => e.value));
    expect(options.length).toBeGreaterThan(1);
    await page.locator('#cmp-case').selectOption(options[1]);
    await expect(page.locator('#cmp-key')).not.toContainText('TESTCTX-0149');
    for (const arm of ARMS) await expect(page.getByTestId(`arm-${arm}`)).toBeVisible();
  });

  test('documents panel shows the invoice text', async ({ page }) => {
    await page.locator('.cmp-docs summary').click();
    await expect(page.locator('#cmp-docs')).toContainText('PO-092267');
  });
});

test.describe('live button', () => {
  const stub = async (page, respond) => {
    await page.route('**/api/status', (r) => r.fulfill({ json: { live: true } }));
    await page.route('**/api/analyze', respond);
    await page.goto('/web/');
    await expect(page.locator('#cmp-run')).toBeEnabled();
  };

  test('shows running cards, then labels live results', async ({ page }) => {
    await stub(page, async (route) => {
      await new Promise((r) => setTimeout(r, 300));
      await route.fulfill({ json: { action: 'ESCALATE', reason_code: 'quantity_spike', evidence: 'stubbed', calls: 1, cached_calls: 0, cost_usd: 0.001, latency_ms: 900, wall_ms: 900 } });
    });
    await page.locator('#cmp-run').click();
    await expect(page.getByTestId('arm-kimi_alone')).toHaveAttribute('data-state', 'running');
    await expect(page.locator('#cmp-run')).toBeDisabled();
    for (const arm of ARMS) await expect(page.getByTestId(`source-${arm}`)).toHaveText('Live on Fireworks');
    await expect(page.locator('#cmp-run-status')).toContainText('All three arms answered');
    await expect(page.locator('#cmp-run')).toBeEnabled();
  });

  test('labels a cached response as a replay', async ({ page }) => {
    await stub(page, (route) => route.fulfill({ json: { action: 'PAY', reason_code: 'none', evidence: 'stubbed', calls: 1, cached_calls: 1, cost_usd: 0.001, latency_ms: 900, wall_ms: 3 } }));
    await page.locator('#cmp-run').click();
    await expect(page.getByTestId('source-kimi_alone')).toHaveText('Replayed from disk cache');
  });

  test('shows a server error on the card, and never a decision', async ({ page }) => {
    await stub(page, (route) => route.fulfill({ status: 503, json: { error: 'No Fireworks key on the server.' } }));
    await page.locator('#cmp-run').click();
    await expect(page.getByTestId('arm-glm_harness_wiki')).toHaveAttribute('data-state', 'error');
    await expect(page.getByTestId('arm-glm_harness_wiki')).toContainText('No Fireworks key');
    await expect(page.getByTestId('arm-glm_harness_wiki').locator('.pill')).toHaveCount(0);
  });

  test('an arm API error reads as an error, not right or wrong', async ({ page }) => {
    await stub(page, (route) => route.fulfill({ json: { action: 'ERROR', reason_code: 'error', evidence: 'HTTP 500', calls: 0, cached_calls: 0, cost_usd: 0, latency_ms: 0, wall_ms: 5 } }));
    await page.locator('#cmp-run').click();
    await expect(page.getByTestId('arm-kimi_alone')).toHaveAttribute('data-state', 'error');
    await expect(page.getByTestId('arm-kimi_alone')).not.toContainText('answer key says');
  });
});

test.describe('review queue', () => {
  test('dial, queue, scans and undo work', async ({ page }) => {
    await page.goto('/web/#review');
    await expect(page.locator('#view-compare')).toBeHidden();
    await expect(page.locator('#above-count')).toHaveText('12');
    await page.locator('[data-id="TEST-00942"]').click();
    await expect(page.locator('#case-head h2')).toHaveText('Billed 2, received 1');
    const loaded = await page.locator('.scan img').evaluate((img) => img.decode().then(() => img.naturalWidth));
    expect(loaded).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Mark done' }).click();
    await expect(page.locator('#above-count')).toHaveText('11');
    await page.getByRole('button', { name: 'Undo' }).click();
    await expect(page.locator('#above-count')).toHaveText('12');
    await page.locator('#range').fill('400');
    await expect(page.locator('#below-count')).toHaveText('4');
    await expect(page.locator('#warn')).toBeVisible();
  });

  test('navigation switches between the two views', async ({ page }) => {
    await page.goto('/web/');
    await page.locator('#nav-review').click();
    await expect(page.locator('#view-review')).toBeVisible();
    await page.locator('#nav-compare').click();
    await expect(page.locator('#view-compare')).toBeVisible();
  });
});

test.describe('server', () => {
  for (const url of ['/.env', '/harness/config.py', '/data/test.jsonl', '/web/server.py', '/web/../.env', '/web/%2e%2e/.env', '/web/%2e%2e/%2e%2e/.env']) {
    test(`does not serve ${url}`, async ({ request }) => {
      expect((await request.get(url)).status()).toBe(404);
    });
  }

  test('status never includes the key', async ({ request }) => {
    const body = await (await request.get('/api/status')).text();
    expect(body).not.toMatch(/fw_|FIREWORKS_API_KEY/);
  });

  test('rejects unknown arms, splits and cases', async ({ request }) => {
    expect((await request.post('/api/analyze', { data: { split: 'test_context', case_id: 'TESTCTX-0149', arm: 'nope' } })).status()).toBe(400);
    expect((await request.post('/api/analyze', { data: { split: '../secrets', case_id: 'x', arm: 'kimi_alone' } })).status()).toBe(400);
    expect((await request.post('/api/analyze', { data: { split: 'test_context', case_id: 'nope', arm: 'kimi_alone' } })).status()).toBe(404);
  });
});
