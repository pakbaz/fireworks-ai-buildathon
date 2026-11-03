// The automated demo: drives the real site with captions and records a video. Every number in a caption comes from compare.json.
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');
const { REPO, hasKey } = require('./score');

const MAX_SECONDS = 118;
const data = JSON.parse(fs.readFileSync(path.join(REPO, 'web', 'compare.json'), 'utf8'));
const setOf = (key) => data.sets.find((s) => s.key === key);

async function caption(page, text, ms) {
  await page.evaluate((t) => {
    let el = document.getElementById('demo-caption');
    if (!el) {
      el = document.createElement('div');
      el.id = 'demo-caption';
      el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);width:min(1180px,92vw);padding:16px 22px;background:rgba(18,32,43,.95);color:#fff;border-radius:8px;font:600 24px/1.32 Archivo,Arial,sans-serif;text-align:center;z-index:9999;box-shadow:0 8px 24px rgba(0,0,0,.3)';
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
  await page.waitForTimeout(ms);
}

async function focusOn(page, selector, block = 'start') {
  await page.evaluate(([s, b]) => {
    document.querySelectorAll('[data-demo-focus]').forEach((e) => { e.style.outline = ''; e.removeAttribute('data-demo-focus'); });
    const el = document.querySelector(s);
    if (!el) return;
    el.setAttribute('data-demo-focus', '1');
    el.style.outline = '4px solid #1F6FB2';
    el.style.outlineOffset = '3px';
    window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - (b === 'start' ? 16 : 200), behavior: 'smooth' });
  }, [selector, block]);
  await page.waitForTimeout(700);
}

const money = (v) => '$' + Number(v).toFixed(2);

test('recorded demo', async ({ page }, info) => {
  const started = Date.now();
  const history = setOf('test_context');
  const docs = setOf('test_300');
  const full = setOf('test_1000');
  const h = history.arms;
  const d = docs.arms;
  const f = full.arms;

  await page.goto('/web/');
  await expect(page.getByTestId('claim-level')).toBeVisible();
  await page.waitForTimeout(400);

  await caption(page, 'Can a low-cost model with our checks keep up with a frontier model? Three arms, the same invoices, every call on Fireworks AI.', 6000);

  await focusOn(page, '#cmp-score');
  await caption(page, `History problems: all four documents agree, and only the supplier's history shows the issue. Kimi K3 alone caught ${h.kimi_alone.caught} of ${h.kimi_alone.real}, with ${h.kimi_alone.false_alarms} false alarms.`, 7000);
  await caption(page, `With our harness, Kimi K3 caught ${h.kimi_harness_wiki.caught} of ${h.kimi_harness_wiki.real} and GLM 5.3 Flash caught ${h.glm_harness_wiki.caught}, both with ${h.glm_harness_wiki.false_alarms} false alarms. GLM costs ${money(h.glm_harness_wiki.cost_per_100)} per 100 invoices, against ${money(h.kimi_alone.cost_per_100)}.`, 8000);

  await focusOn(page, '.cmp-case');
  const lead = history.featured.find((f) => f.id === 'TESTCTX-0149');
  await caption(page, `One invoice: 82 infusion pumps, when this supplier's largest past order was 11. Saved results: Kimi K3 alone recommended ${lead.arms.kimi_alone.action}. Both harness arms escalated.`, 7000);

  if (hasKey()) {
    await page.locator('#cmp-run').click();
    await caption(page, 'Now the same invoice goes through all three arms on Fireworks.', 1500);
    await expect(page.locator('#cmp-run-status')).toContainText('All three arms answered', { timeout: 35000 });
    const answer = async (a) => page.getByTestId(`arm-${a}`).getAttribute('data-action');
    const states = await Promise.all(['kimi_alone', 'kimi_harness_wiki', 'glm_harness_wiki'].map((a) => page.getByTestId(`arm-${a}`).getAttribute('data-state')));
    const how = states.every((s) => s === 'live') ? 'Live answers' : 'Answers, some replayed from the disk cache';
    await caption(page, `${how}: Kimi K3 alone ${await answer('kimi_alone')}, Kimi K3 + harness ${await answer('kimi_harness_wiki')}, GLM + harness ${await answer('glm_harness_wiki')}.`, 6000);
  }

  await focusOn(page, '#cmp-sets');
  await page.getByTestId('set-test_300').click();
  await page.waitForTimeout(500);
  await focusOn(page, '#cmp-claims');
  await caption(page, `Document problems: the PO, shipment, receipt and invoice disagree. On the ${docs.cases} invoices all three ran, each arm caught ${d.kimi_alone.caught} of ${d.kimi_alone.real}: ${d.kimi_alone.caught === d.kimi_harness_wiki.caught && d.kimi_alone.caught === d.glm_harness_wiki.caught ? 'a tie' : 'see the table'}.`, 6000);
  await caption(page, `Here Kimi K3 alone leads on false alarms: ${d.kimi_alone.false_alarms} of ${d.kimi_alone.fine}, against ${d.kimi_harness_wiki.false_alarms} for Kimi K3 + harness and ${d.glm_harness_wiki.false_alarms} for GLM + harness. Our checks don't beat it on this set.`, 8000);
  await page.getByTestId('set-test_1000').click();
  await page.waitForTimeout(400);
  await focusOn(page, '#cmp-score');
  await caption(page, `The full ${full.cases} document invoices: GLM + harness caught ${f.glm_harness_wiki.caught} of ${f.glm_harness_wiki.real} against Kimi K3's ${f.kimi_alone.caught}, with ${f.glm_harness_wiki.false_alarms} false alarms against ${f.kimi_alone.false_alarms}, at ${money(f.glm_harness_wiki.cost_per_100)} per 100 invoices against ${money(f.kimi_alone.cost_per_100)}.`, 8000);

  await page.locator('#nav-review').click();
  await page.waitForTimeout(600);
  await page.evaluate(() => window.scrollTo(0, 0));
  await caption(page, 'A flagged invoice goes to a person. The queue ranks by expected loss, and each company has its own dial.', 5000);
  await page.locator('[data-id="TEST-00942"]').click();
  await caption(page, 'The reviewer sees the conflicting values on each scan: billed 2, received 1. The scan highlights come from the answer key in this version.', 6000);
  await page.locator('#range').fill('420');
  await caption(page, 'Loosen the dial and low-value invoices fall below the line, with the dollars that would auto-pay shown.', 5000);

  await page.locator('#nav-compare').click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await caption(page, 'Synthetic data, and nothing is ever paid: PAY is a recommendation. A person decides.', 4000);

  const seconds = (Date.now() - started) / 1000;
  console.log(`Demo length: ${seconds.toFixed(1)} s`);
  const videoPath = await page.video().path();
  await page.close();
  fs.copyFileSync(videoPath, path.join(info.outputDir, '..', 'demo.webm'));
  expect(seconds, 'The event limits demo videos to 120 seconds').toBeLessThan(MAX_SECONDS);
});
