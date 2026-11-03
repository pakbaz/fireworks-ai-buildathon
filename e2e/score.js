// Scores the saved runs directly from runs/ and data/, separately from web/build_compare.py, so the tests can catch a wrong page.
const fs = require('fs');
const path = require('path');

const REPO = path.dirname(__dirname);
const ARMS = ['kimi_alone', 'kimi_harness_wiki', 'glm_harness_wiki'];
const RUN_DIR = { kimi_alone: 'kimi_alone', kimi_harness_wiki: 'kimi_harness_wiki', glm_harness_wiki: 'glm_harness_wiki_low' };

function readRows(rel) {
  const full = path.join(REPO, rel);
  if (!fs.existsSync(full)) return new Map();
  const rows = fs.readFileSync(full, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l));
  return new Map(rows.map((r) => [r.case_id, r]));
}

function scoreSet(split, requires) {
  const cases = readRows(`data/${split}.jsonl`);
  const runs = Object.fromEntries(ARMS.map((a) => [a, readRows(`runs/${RUN_DIR[a]}/${split}.jsonl`)]));
  const ok = (p) => p && p.action !== 'ERROR' && p.reason_code !== 'error';
  const ids = [...cases.keys()].filter((i) => requires.every((a) => ok(runs[a].get(i))));
  const out = {};
  for (const arm of ARMS) {
    if (!ids.every((i) => ok(runs[arm].get(i)))) {
      out[arm] = null;
      continue;
    }
    const label = (i) => cases.get(i).label;
    const real = ids.filter((i) => label(i).real_discrepancy);
    const fine = ids.filter((i) => !label(i).real_discrepancy && label(i).stratum !== 'in_transit');
    out[arm] = {
      real: real.length,
      caught: real.filter((i) => runs[arm].get(i).action === 'ESCALATE').length,
      fine: fine.length,
      falseAlarms: fine.filter((i) => runs[arm].get(i).action === 'ESCALATE').length,
    };
  }
  return out;
}

function hasKey() {
  if (process.env.FIREWORKS_API_KEY) return true;
  const env = path.join(REPO, '.env');
  return fs.existsSync(env) && /^FIREWORKS_API_KEY=\S+/m.test(fs.readFileSync(env, 'utf8'));
}

module.exports = { ARMS, REPO, scoreSet, hasKey };
