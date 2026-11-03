// Compare view: the three arms on the same invoices, from compare.json (web/build_compare.py), plus live runs through web/server.py.

const cmp = { data: null, set: 0, caseId: null, live: false, results: {}, running: false };

const num = (v, d = 2) => (v === null || v === undefined ? '-' : Number(v).toFixed(d));
const STATUS_LABEL = { holds: 'Holds', falls_short: 'Falls short', not_tested: 'Not tested yet' };

function setView() {
  const review = location.hash === '#review';
  $('view-review').hidden = !review;
  $('view-compare').hidden = review;
  $('review-actions').hidden = !review;
  $('nav-review').toggleAttribute('aria-current', review);
  $('nav-compare').toggleAttribute('aria-current', !review);
  if (review) $('nav-review').setAttribute('aria-current', 'page'); else $('nav-compare').setAttribute('aria-current', 'page');
}

function renderClaims(set) {
  $('cmp-claims').innerHTML = set.claims.map((c) => {
    const p = c.mcnemar ? ` Paired McNemar p = ${c.mcnemar.p < 0.001 ? c.mcnemar.p.toExponential(0) : c.mcnemar.p.toFixed(3)}.` : '';
    return `<article class="claim ${c.status}" data-testid="claim-${c.id}" data-status="${c.status}">
      <span class="claim-status">${STATUS_LABEL[c.status]}</span>
      <div class="claim-title">${esc(c.title)}</div>
      <div class="claim-detail">${esc(c.detail)}${p}</div>
      <div class="claim-rule">Test: ${esc(c.rule)}</div>
    </article>`;
  }).join('');
}

function renderScore(set) {
  const arms = cmp.data.arms;
  const rows = [
    { label: 'Real problems caught', show: (a) => `${a.caught} / ${a.real}`, val: (a) => a.caught, better: 'high', id: 'caught' },
    { label: 'False alarms on fine invoices', show: (a) => `${a.false_alarms} / ${a.fine}`, val: (a) => a.false_alarms, better: 'low', id: 'false' },
  ];
  if (set.arms.kimi_alone.in_transit) rows.push({ label: 'Goods in transit held correctly', show: (a) => `${a.wait_ok} / ${a.in_transit}`, val: (a) => a.wait_ok, better: 'high', id: 'wait' });
  rows.push(
    { label: 'Right reason on caught problems', show: (a) => `${a.reason_ok} / ${a.caught}`, val: (a) => (a.caught ? a.reason_ok / a.caught : 0), better: 'high', id: 'reason' },
    { label: 'API errors', show: (a) => `${a.errors} / ${a.cases}`, val: (a) => a.errors, better: 'low', id: 'errors' },
    { label: 'Model cost per 100 invoices', show: (a) => '$' + num(a.cost_per_100), val: (a) => a.cost_per_100, better: 'low', id: 'cost' },
    { label: 'Median time per invoice', show: (a) => num(a.latency_p50_s, 1) + ' s', val: (a) => a.latency_p50_s, better: 'low', id: 'p50' },
    { label: '95th percentile time', show: (a) => num(a.latency_p95_s, 1) + ' s', val: (a) => a.latency_p95_s, better: 'low', id: 'p95' }
  );
  const head = `<thead><tr><th scope="col">${set.cases} invoices</th>${arms.map((a) => `<th scope="col">${esc(a.name)}<small>${esc(a.role)}</small></th>`).join('')}</tr></thead>`;
  const body = rows.map((r) => {
    const ran = arms.map((a) => set.arms[a.key]).filter((a) => a.status === 'run');
    const vals = ran.map(r.val);
    const best = r.better === 'high' ? Math.max(...vals) : Math.min(...vals);
    const tied = vals.every((v) => v === best);
    const cells = arms.map((a) => {
      const s = set.arms[a.key];
      if (s.status !== 'run') return `<td class="none" data-testid="score-${r.id}-${a.key}">Not run</td>`;
      return `<td class="${!tied && r.val(s) === best ? 'best' : ''}" data-testid="score-${r.id}-${a.key}">${esc(r.show(s))}</td>`;
    }).join('');
    return `<tr><td>${r.label}</td>${cells}</tr>`;
  }).join('');
  $('cmp-score').innerHTML = head + `<tbody>${body}</tbody>`;
}

function renderTypes(set) {
  const arms = cmp.data.arms;
  const head = `<thead><tr><th scope="col">Type (share handled correctly)</th><th scope="col">Invoices</th>${arms.map((a) => `<th scope="col">${esc(a.name)}</th>`).join('')}</tr></thead>`;
  const body = set.types.map((t) => {
    const vals = arms.filter((a) => t.arms[a.key] !== undefined).map((a) => t.arms[a.key]);
    const best = Math.max(...vals), tied = vals.every((v) => v === best);
    return `<tr><td>${esc(t.type)}</td><td>${t.cases}</td>${arms.map((a) => (t.arms[a.key] === undefined ? '<td class="none">Not run</td>' : `<td class="${!tied && t.arms[a.key] === best ? 'best' : ''}">${t.arms[a.key]}</td>`)).join('')}</tr>`;
  }).join('');
  $('cmp-types').innerHTML = head + `<tbody>${body}</tbody>`;
}

function currentCase() {
  return cmp.data.sets[cmp.set].featured.find((f) => f.id === cmp.caseId);
}

function armCard(arm, c) {
  const live = (cmp.results[c.id] || {})[arm.key];
  const saved = c.arms[arm.key];
  const head = `<div><div class="arm-name">${esc(arm.name)}</div><div class="arm-role">${esc(arm.role)}</div></div>`;
  if (live === 'running') {
    return `<article class="arm" data-testid="arm-${arm.key}" data-state="running">${head}<div>Calling Fireworks</div><div class="arm-wait"><div></div></div></article>`;
  }
  const r = live && live.action ? live : saved;
  if (live && live.error) {
    return `<article class="arm" data-testid="arm-${arm.key}" data-state="error">${head}<div class="arm-evidence">${esc(live.error)}</div></article>`;
  }
  if (!r) {
    return `<article class="arm" data-testid="arm-${arm.key}" data-state="empty">${head}<div class="arm-evidence">No saved run for this invoice yet.</div></article>`;
  }
  const isLive = r === live;
  const fromCache = isLive && r.calls > 0 && r.cached_calls === r.calls;
  const source = !isLive ? 'Saved run' : fromCache ? 'Replayed from disk cache' : 'Live on Fireworks';
  const state = r.action === 'ERROR' ? 'error' : isLive ? (fromCache ? 'cached' : 'live') : 'saved';
  const right = r.action === c.want;
  const time = isLive && !fromCache ? r.wall_ms : r.latency_ms;
  const atRisk = r.at_risk_usd ? ` · $${Math.round(r.at_risk_usd).toLocaleString('en-US')} at risk` : '';
  return `<article class="arm ${r.action === 'ERROR' ? '' : right ? 'right' : 'wrong'}" data-testid="arm-${arm.key}" data-state="${state}" data-action="${esc(r.action)}">
    ${head}
    <div class="arm-row"><span class="pill">${esc(r.action)}</span>${r.action === 'ERROR' ? '' : `<span class="verdict">${right ? 'Right' : 'Wrong'}, answer key says ${esc(c.want)}</span>`}</div>
    <div class="arm-reason">${esc(r.reason_code || 'none')}${atRisk}</div>
    <div class="arm-evidence">${esc(r.evidence || '')}</div>
    <div class="arm-meta">${r.calls} call${r.calls === 1 ? '' : 's'} · $${num(r.cost_usd, 4)} · ${num((time || 0) / 1000, 1)} s</div>
    <div class="arm-source ${isLive && !fromCache ? 'live' : ''}" data-testid="source-${arm.key}">${source}</div>
  </article>`;
}

function renderArmCards() {
  const c = currentCase();
  $('cmp-results').innerHTML = c ? cmp.data.arms.map((a) => armCard(a, c)).join('') : '';
  $('cmp-key').textContent = c ? `${c.company} · ${c.supplier} · answer key: ${c.want} (${c.group}). No arm sees the answer key. PAY is a recommendation, and nothing is paid.` : '';
  $('cmp-docs').innerHTML = c ? Object.entries(c.documents).map(([k, v]) => `<div><h3>${DOC_NAMES[k]}</h3><pre>${esc(v)}</pre></div>`).join('') : '';
  const run = $('cmp-run');
  run.disabled = !cmp.live || cmp.running || !c;
  run.title = cmp.live ? '' : 'Start web/server.py with a Fireworks key in .env';
  run.textContent = cmp.running ? 'Running' : 'Run live on Fireworks';
}

function renderCompare() {
  const set = cmp.data.sets[cmp.set];
  $('cmp-sets').innerHTML = cmp.data.sets.map((s, i) => `<button class="segment" data-set="${i}" data-testid="set-${s.key}" aria-pressed="${i === cmp.set}">${esc(s.name)} · ${s.cases}</button>`).join('');
  $('cmp-blurb').textContent = set.blurb + (set.cases < set.total ? ` First ${set.cases} of ${set.total} invoices, the same mix.` : '');
  renderClaims(set);
  renderScore(set);
  renderTypes(set);
  $('cmp-case').innerHTML = set.featured.map((f) => {
    const answers = cmp.data.arms.filter((a) => f.arms[a.key]).map((a) => f.arms[a.key].action).join(' / ');
    return `<option value="${f.id}"${f.id === cmp.caseId ? ' selected' : ''}>${f.id} · ${esc(f.group)} · ${answers}</option>`;
  }).join('');
  renderArmCards();
}

async function runLive() {
  const c = currentCase();
  if (!c || cmp.running) return;
  cmp.running = true;
  const started = Date.now();
  cmp.results[c.id] = Object.fromEntries(cmp.data.arms.map((a) => [a.key, 'running']));
  $('cmp-run-status').textContent = `Sending ${c.id} to all three arms on Fireworks.`;
  renderArmCards();
  await Promise.all(cmp.data.arms.map(async (a) => {
    try {
      const res = await fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ split: c.split, case_id: c.id, arm: a.key }) });
      const body = await res.json();
      cmp.results[c.id][a.key] = res.ok ? body : { error: body.error || 'Request failed' };
    } catch (err) {
      cmp.results[c.id][a.key] = { error: 'The server did not answer.' };
    }
    renderArmCards();
  }));
  cmp.running = false;
  $('cmp-run-status').textContent = `All three arms answered in ${((Date.now() - started) / 1000).toFixed(1)} s.`;
  renderArmCards();
}

function wireCompare() {
  $('cmp-sets').addEventListener('click', (e) => {
    const b = e.target.closest('[data-set]');
    if (!b) return;
    cmp.set = Number(b.dataset.set);
    cmp.caseId = (cmp.data.sets[cmp.set].featured[0] || {}).id || null;
    $('cmp-run-status').textContent = '';
    renderCompare();
  });
  $('cmp-case').addEventListener('change', (e) => {
    cmp.caseId = e.target.value;
    $('cmp-run-status').textContent = '';
    renderArmCards();
  });
  $('cmp-run').addEventListener('click', runLive);
  window.addEventListener('hashchange', setView);
}

async function startCompare() {
  setView();
  try {
    const res = await fetch('compare.json');
    if (!res.ok) throw new Error('compare.json returned ' + res.status);
    cmp.data = await res.json();
  } catch (err) {
    $('cmp-blurb').textContent = 'Could not load compare.json. Run python3 web/build_compare.py, then python3 web/server.py.';
    return;
  }
  try {
    const res = await fetch('/api/status');
    if (res.ok) cmp.live = (await res.json()).live;
  } catch (err) {
    cmp.live = false;
  }
  cmp.caseId = (cmp.data.sets[0].featured[0] || {}).id || null;
  $('cmp-foot').textContent = 'Synthetic test data. The history set covers the seven anomaly types the checks were written for, on new examples. Kimi K3 alone on the document sets ran before its prompt gained the history instruction. All arms here read document text, not scans. Risk values are heuristic, not calibrated. Dollars at risk are exposure, not proven loss.';
  wireCompare();
  renderCompare();
}

startCompare();
