// Review site: a threshold dial, a queue ranked by expected loss, and the scans with the disputed values highlighted.
// Ported from dashboard/Main.dc.html. Data comes from cases.json (web/build_data.py).

const DOC_NAMES = { po: 'Purchase order', shipping_notice: 'Shipping notice', gr: 'Goods receipt', invoice: 'Invoice' };
const DOC_ORDER = ['po', 'shipping_notice', 'gr', 'invoice'];
const REASON_NAMES = {
  short_shipped: 'short shipment', lost_in_transit: 'lost in transit', qty_mismatch: 'quantity mismatch',
  price_mismatch: 'price above PO', wrong_po: 'wrong PO', duplicate_invoice: 'duplicate invoice'
};
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

let data = null;
const state = {
  company: 'northside', pos: {}, sel: {}, doc: null, removed: {}, history: [], added: {},
  files: [], status: '', resultId: null, showUpload: false, showWhy: false
};

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// The dial is logarithmic: position 0 is $1M and position 1 is $1.
const tAt = (p) => Math.pow(10, 6 - 6 * p);
const pAt = (t) => (6 - Math.log10(t)) / 6;

function fmt(v) {
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
  if (v >= 1000) return '$' + (v / 1000).toFixed(v >= 1e4 ? 0 : 1).replace(/\.0$/, '') + 'k';
  if (v >= 10) return '$' + Math.round(v);
  return '$' + v.toFixed(1).replace(/\.0$/, '');
}
const whole = (n) => '$' + Math.round(n).toLocaleString('en-US');
function date(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return MONTHS[m - 1] + ' ' + d + ', ' + y;
}

function polar(r, a) {
  const t = a * Math.PI / 180;
  return [140 + r * Math.sin(t), 145 - r * Math.cos(t)];
}
function arc(r, a0, a1) {
  const s = polar(r, a0), e = polar(r, a1);
  return 'M' + s[0].toFixed(2) + ' ' + s[1].toFixed(2) + 'A' + r + ' ' + r + ' 0 ' + (a1 - a0 > 180 ? 1 : 0) + ' 1 ' + e[0].toFixed(2) + ' ' + e[1].toFixed(2);
}
function radial(r0, r1, a) {
  const s = polar(r0, a), e = polar(r1, a);
  return 'M' + s[0].toFixed(2) + ' ' + s[1].toFixed(2) + 'L' + e[0].toFixed(2) + ' ' + e[1].toFixed(2);
}

const says = (c, doc) => (c.marks.find((m) => m.doc === doc) || {}).says || '';

function verdict(c) {
  if (c.rc === 'duplicate_invoice') return 'Already paid on ' + date(c.paid);
  if (c.rc === 'wrong_po') return 'Invoice ' + says(c, 'invoice').toLowerCase().replace('po-', 'PO-') + ', goods arrived on ' + c.po;
  if (c.rc === 'price_mismatch') return says(c, 'invoice') + ', PO says ' + says(c, 'po').replace('PO price ', '');
  return says(c, 'invoice') + ', ' + says(c, 'gr').toLowerCase();
}
function short(c) {
  if (c.rc === 'duplicate_invoice') return 'Already paid';
  if (c.rc === 'wrong_po') return 'Wrong PO';
  if (c.rc === 'price_mismatch') return 'Price above PO';
  return says(c, 'invoice') + ', ' + says(c, 'gr').toLowerCase();
}
function action(c) {
  const a = whole(c.atRisk);
  if (c.rc === 'lost_in_transit') return 'Lost in transit. Claim ' + a + ' from ' + c.car + '.';
  if (c.rc === 'short_shipped') return 'Never shipped. Dispute ' + a + ' with the supplier.';
  if (c.rc === 'qty_mismatch') return 'No shipping notice. Investigate ' + a + '.';
  if (c.rc === 'price_mismatch') return 'Dispute ' + a + ' with the supplier.';
  if (c.rc === 'wrong_po') return 'Investigate before paying ' + a + '.';
  return 'Do not pay ' + a + ' twice.';
}

function guessType(name) {
  const n = name.toLowerCase();
  if (/(^|[^a-z])(po|purchase)/.test(n)) return 'PO';
  if (/inv/.test(n)) return 'Invoice';
  if (/(^|[^a-z])gr([^a-z]|$)|receipt|received/.test(n)) return 'Goods receipt';
  if (/asn|ship|notice|packing/.test(n)) return 'Shipping notice';
  return 'Type unknown';
}

function activeRows() {
  return data.cases
    .filter((c) => c.co === state.company && !state.removed[c.id] && (!c.sample || state.added[c.id]))
    .sort((a, b) => b.loss - a.loss);
}

// Replace a container only when its markup changed, so scans do not reload while the dial moves. Keeps keyboard focus.
const rendered = new WeakMap();
function setHTML(el, html) {
  if (rendered.get(el) === html) return;
  const active = el.contains(document.activeElement) ? document.activeElement.dataset.key : null;
  el.innerHTML = html;
  rendered.set(el, html);
  if (active) {
    const again = el.querySelector('[data-key="' + CSS.escape(active) + '"]');
    if (again) again.focus();
  }
}

function setP(p) {
  state.pos[state.company] = Math.min(1, Math.max(0, p));
  render();
}

function cropHTML(c, mark) {
  const size = c.docs[mark.doc], b = mark.box, label = DOC_NAMES[mark.doc];
  const cw = Math.max(320, b[2] - b[0] + 120), ch = Math.max(cw * 0.3, b[3] - b[1] + 40);
  const x0 = Math.max(0, Math.min(size.w - cw, (b[0] + b[2]) / 2 - cw / 2));
  const y0 = Math.max(0, Math.min(size.h - ch, (b[1] + b[3]) / 2 - ch / 2));
  const pct = (v, of) => (v / of * 100).toFixed(2) + '%';
  return `<button class="crop${mark.bad ? ' bad' : ''}" data-act="openDoc" data-doc="${mark.doc}" data-key="crop-${mark.doc}" aria-label="${esc(mark.says + ' on the ' + label.toLowerCase() + '. Open the full page.')}">
    <span class="crop-head"><span class="crop-says">${esc(mark.says)}</span><span class="crop-label">${label}</span></span>
    <span class="crop-view" style="aspect-ratio:${(cw / ch).toFixed(3)}">
      <img src="${esc(size.url)}" alt="${esc(label + ' for ' + c.inv + ', zoomed in: ' + mark.says)}" style="width:${pct(size.w, cw)};left:${pct(-x0, cw)};top:${pct(-y0, ch)}">
      <span class="crop-box" aria-hidden="true" style="left:${pct(b[0] - 3 - x0, cw)};top:${pct(b[1] - 3 - y0, ch)};width:${pct(b[2] - b[0] + 6, cw)};height:${pct(b[3] - b[1] + 6, ch)}"></span>
    </span>
    ${mark.note ? `<span class="crop-note">${esc(mark.note)}</span>` : ''}
  </button>`;
}

function docsHTML(c) {
  const firstBad = c.marks.find((m) => m.bad) || c.marks[0];
  const docKey = state.doc && c.docs[state.doc] ? state.doc : firstBad.doc;
  const flagged = new Set(c.marks.filter((m) => m.bad).map((m) => m.doc));
  const size = c.docs[docKey], mark = c.marks.find((m) => m.doc === docKey);
  const tabs = DOC_ORDER.filter((d) => c.docs[d]).map((d) => `<button class="tab" data-act="openDoc" data-doc="${d}" data-key="tab-${d}" aria-pressed="${d === docKey}">${flagged.has(d) ? '<span class="tab-dot" aria-hidden="true"></span>' : ''}${DOC_NAMES[d]}</button>`).join('');
  const box = mark ? `<span class="scan-box" aria-hidden="true" style="left:${((mark.box[0] - 4) / size.w * 100).toFixed(2)}%;top:${((mark.box[1] - 4) / size.h * 100).toFixed(2)}%;width:${((mark.box[2] - mark.box[0] + 8) / size.w * 100).toFixed(2)}%;height:${((mark.box[3] - mark.box[1] + 8) / size.h * 100).toFixed(2)}%"></span>` : '';
  return `<div class="tabs" role="group" aria-label="Document">${tabs}</div>
    <div class="scan-wrap"><div class="scan" style="max-width:${size.w}px">
      <img src="${esc(size.url)}" width="${size.w}" height="${size.h}" alt="${esc('Full scan of the ' + DOC_NAMES[docKey].toLowerCase() + ' for invoice ' + c.inv)}">${box}
    </div></div>`;
}

function renderCase(current, rows, T) {
  const head = $('case-head');
  [$('case-crops'), $('case-docs'), $('case-why-wrap')].forEach((el) => { el.hidden = !current; });
  if (!current) {
    setHTML(head, '<div class="case-clear">Queue is clear.</div>');
    $('case-autopay').hidden = true;
    $('case-disagree').hidden = true;
    return;
  }
  setHTML(head, `<div class="case-top">
    <div class="case-title">
      <div class="case-sup">${esc(current.sup)} · ${esc(current.inv)}</div>
      <h2>${esc(verdict(current))}</h2>
      <div class="case-action">${esc(action(current))}</div>
    </div>
    <div class="case-buttons">
      <button class="btn btn-line" data-act="review" data-id="${current.id}" data-key="fine">Not a problem</button>
      <button class="btn btn-dark" data-act="review" data-id="${current.id}" data-key="done">Mark done</button>
    </div>
  </div>`);
  const below = current.loss <= T;
  $('case-autopay').hidden = !below;
  if (below) $('case-autopay').textContent = 'This one auto-pays at ' + fmt(T) + '.';

  const m = current.model, disagree = m.reason !== current.rc;
  $('case-disagree').hidden = !disagree;
  if (disagree) $('case-disagree').textContent = 'Kimi K3 read this as ' + REASON_NAMES[m.reason] + ' with ' + whole(current.atRisk) + ' at risk. The answer key says ' + REASON_NAMES[current.rc] + ' with ' + whole(m.keyAtRisk) + ' at risk, so its rank here may be too low.';

  const paid = current.paid ? `<div class="paid"><span class="paid-label">Payment history</span><span class="paid-inv">${esc(current.inv)}</span><span class="paid-when">Paid ${date(current.paid)} on ${esc(current.po)}</span></div>` : '';
  setHTML($('case-crops'), current.marks.map((x) => cropHTML(current, x)).join('') + paid);
  setHTML($('case-docs'), docsHTML(current));

  const weight = current.loss / (current.atRisk * current.risk);
  $('case-why-title').textContent = 'Why it ranks #' + (rows.indexOf(current) + 1);
  setHTML($('case-why'), `<p class="formula">${whole(current.atRisk)} at risk × ${(current.risk * 100).toFixed(1)}% risk × ${weight.toFixed(1)} item and supplier weight = ${whole(current.loss)}</p>
    <p>harness/dial.py also escalates this one: ${whole(current.loss)} expected loss against $${m.reviewCost.toFixed(2)} expected review cost.</p>
    <p><strong>Kimi K3’s explanation:</strong> ${esc(m.evidence)}</p>`);
}

function render() {
  const co = data.companies[state.company];
  const p = state.pos[state.company], T = tAt(p), ps = pAt(co.suggested);
  const moved = Math.abs(p - ps) > 0.002;
  const rows = activeRows();
  const above = rows.filter((r) => r.loss > T), below = rows.filter((r) => r.loss <= T);
  const tLabel = fmt(T), suggestedLabel = fmt(co.suggested);
  const ang = -135 + 270 * p;

  setHTML($('companies'), Object.keys(data.companies).map((id) => `<button class="segment" data-act="pickCompany" data-id="${id}" data-key="co-${id}" aria-pressed="${state.company === id}">${esc(data.companies[id].name)}</button>`).join(''));

  $('knob-track').setAttribute('d', arc(106, -135, 135));
  $('knob-value').setAttribute('d', arc(106, -135, Math.max(ang, -134.9)));
  $('knob-suggested').setAttribute('d', radial(94, 118, -135 + 270 * ps));
  $('knob-pointer').setAttribute('d', radial(62, 76, ang));
  $('knob-label').textContent = tLabel;
  $('range').value = Math.round(p * 1000);
  $('range').setAttribute('aria-valuetext', 'Send to a person above ' + tLabel + ' expected loss. ' + above.length + ' invoices go to a person.');
  $('above-count').textContent = above.length;
  $('below-count').textContent = below.length;

  const ratio = T > co.suggested ? T / co.suggested : co.suggested / T;
  const ratioText = ratio >= 10 ? Math.round(ratio).toLocaleString('en-US') : ratio.toFixed(1).replace(/\.0$/, '');
  $('offset-label').textContent = !moved ? 'Suggested ' + suggestedLabel : T < co.suggested ? ratioText + '× more cautious' : ratioText + '× looser';

  $('warn').hidden = below.length === 0;
  $('warn-label').textContent = whole(below.reduce((a, r) => a + r.atRisk, 0)) + (co.gate ? ' in real problems would auto-pay' : ' written off');
  $('reset').hidden = !moved;
  $('reset').textContent = 'Back to ' + suggestedLabel;
  $('why-toggle').textContent = 'Why ' + suggestedLabel + '?';
  $('why-toggle').setAttribute('aria-expanded', state.showWhy);
  $('why').hidden = !state.showWhy;
  setHTML($('why'), `<p>${esc(co.posture)}</p><dl>${co.why.map((w) => `<div><dt>${esc(w.label)}</dt><dd>${esc(w.value)}</dd></div>`).join('')}</dl>`);

  const current = rows.find((r) => r.id === state.sel[state.company]) || rows[0] || null;
  const line = `<div class="line">Escalation line · ${tLabel}</div>`;
  setHTML($('rows'), rows.map((r, i) => {
    const isAbove = r.loss > T, selected = current && current.id === r.id;
    const tag = state.resultId === r.id ? 'Sample' : isAbove ? '' : 'Auto-pay';
    return `<li>${i === above.length ? line : ''}<button class="row${isAbove ? '' : ' below'}" data-act="pickRow" data-id="${r.id}" data-key="row-${r.id}"${selected ? ' aria-current="true"' : ''}>
      <span class="row-rank">${i + 1}</span><span class="row-short">${esc(short(r))}</span><span class="row-amount">${whole(r.atRisk)}</span>
      <span></span><span class="row-sup">${esc(r.sup)}</span><span class="row-tag">${tag}</span>
    </button></li>`;
  }).join('') + (rows.length && above.length === rows.length ? `<li>${line}</li>` : ''));
  $('rest').textContent = co.passed + ' passed every check · ' + co.waiting + ' in transit';

  const reviewed = state.history.filter((id) => data.cases.find((c) => c.id === id).co === state.company);
  setHTML($('reviewed'), reviewed.length ? `<div class="reviewed"><span>Reviewed ${reviewed.length}</span><button class="undo" data-act="undo" data-key="undo">Undo</button></div>` : '');

  renderCase(current, rows, T);

  $('upload').hidden = !state.showUpload;
  $('upload-toggle').setAttribute('aria-expanded', state.showUpload);
  setHTML($('upload-files'), state.files.map((f) => `<div class="file"><span class="file-type">${esc(f.type)}</span><span class="file-name">${esc(f.name)}</span></div>`).join(''));
  const result = rows.find((r) => r.id === state.resultId);
  $('upload-status').textContent = result ? result.inv + ' from the saved test run landed at rank ' + (rows.indexOf(result) + 1) + '.' : state.status;
}

function takeFiles(list) {
  const files = Array.from(list || []).map((f) => ({ name: f.name, type: guessType(f.name) }));
  if (!files.length) return;
  state.files = files;
  state.resultId = null;
  state.status = 'Live checks are not connected yet, so these files were not read or sent anywhere. Try a sample to see a result.';
  render();
}

const actions = {
  toggleUpload() { state.showUpload = !state.showUpload; },
  toggleWhy() { state.showWhy = !state.showWhy; },
  pickCompany(el) {
    state.company = el.dataset.id;
    state.doc = null;
    state.resultId = null;
    state.files = [];
    state.status = '';
  },
  pickRow(el) { state.sel[state.company] = el.dataset.id; state.doc = null; },
  openDoc(el) { state.doc = el.dataset.doc; },
  stepUp() { state.pos[state.company] = Math.min(1, state.pos[state.company] + 0.025); },
  stepDown() { state.pos[state.company] = Math.max(0, state.pos[state.company] - 0.025); },
  reset() { state.pos[state.company] = pAt(data.companies[state.company].suggested); },
  review(el) {
    const rows = activeRows(), i = rows.findIndex((r) => r.id === el.dataset.id);
    const next = rows[i + 1] || rows[i - 1];
    state.removed[el.dataset.id] = el.dataset.key;
    state.history.push(el.dataset.id);
    state.sel[state.company] = next ? next.id : null;
    state.doc = null;
  },
  undo() {
    const inCompany = state.history.filter((id) => data.cases.find((c) => c.id === id).co === state.company);
    const last = inCompany[inCompany.length - 1];
    state.history.splice(state.history.lastIndexOf(last), 1);
    delete state.removed[last];
    state.sel[state.company] = last;
    state.doc = null;
  },
  useSample() {
    const sample = data.cases.find((c) => c.co === state.company && c.sample);
    state.added[sample.id] = true;
    delete state.removed[sample.id];
    state.history = state.history.filter((id) => id !== sample.id);
    state.sel[state.company] = sample.id;
    state.doc = null;
    state.files = [];
    state.status = '';
    state.resultId = sample.id;
  }
};

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  actions[el.dataset.act](el);
  render();
  // Below this width the invoice sits under the queue, out of sight.
  if (el.dataset.act === 'pickRow' && matchMedia('(max-width: 1064px)').matches) document.querySelector('.detail').scrollIntoView();
});

function wireKnob() {
  const knob = $('knob');
  let dragging = false;
  const knobP = (e) => {
    const rect = knob.getBoundingClientRect();
    const cx = rect.left + rect.width / 2, cy = rect.top + rect.height * 145 / 270;
    const deg = Math.atan2(e.clientX - cx, cy - e.clientY) * 180 / Math.PI;
    return (Math.max(-135, Math.min(135, deg)) + 135) / 270;
  };
  knob.addEventListener('pointerdown', (e) => {
    dragging = true;
    knob.setPointerCapture(e.pointerId);
    setP(knobP(e));
  });
  knob.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const next = knobP(e);
    // Ignore a jump across the gap at the bottom of the dial.
    if (Math.abs(next - state.pos[state.company]) <= 0.4) setP(next);
  });
  const stop = () => { dragging = false; };
  knob.addEventListener('pointerup', stop);
  knob.addEventListener('pointercancel', stop);
  $('range').addEventListener('input', (e) => setP(Number(e.target.value) / 1000));
}

function wireUpload() {
  const drop = $('upload');
  drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('dragging'); });
  drop.addEventListener('dragleave', () => drop.classList.remove('dragging'));
  drop.addEventListener('drop', (e) => {
    e.preventDefault();
    drop.classList.remove('dragging');
    takeFiles(e.dataTransfer.files);
  });
  $('file-input').addEventListener('change', (e) => {
    takeFiles(e.target.files);
    e.target.value = '';
  });
}

async function start() {
  try {
    const res = await fetch('cases.json');
    if (!res.ok) throw new Error('cases.json returned ' + res.status);
    data = await res.json();
  } catch (err) {
    $('load-error').hidden = false;
    $('load-error').innerHTML = 'Could not load the cases. Run <code>python3 -m http.server</code> from the repo root and open <code>/web/</code>.';
    return;
  }
  Object.keys(data.companies).forEach((id) => { state.pos[id] = pAt(data.companies[id].suggested); });
  wireKnob();
  wireUpload();
  render();
}

start();
