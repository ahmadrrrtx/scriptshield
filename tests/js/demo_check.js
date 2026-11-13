// Runs the explorer page in a minimal fake DOM and checks it against the data embedded in it.
//   node tests/js/demo_check.js release/hf_space/index.html
// Exit code 0 only if every check passes. The Hub inserts its own <script> into the served page; strip it first.
const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const dataM = html.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/);
const codeM = html.match(/<script>\s*(\(function \(\) \{[\s\S]*?)<\/script>\s*<\/body>/);
if (!dataM || !codeM) { console.error('markers not found'); process.exit(2); }
const D = JSON.parse(dataM[1]);
function El(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.style = {}; this._t = ''; this.className = ''; }
Object.defineProperty(El.prototype, 'textContent', { get() { return this._t; }, set(v) { this._t = String(v); this.children = []; } });
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
El.prototype.addEventListener = function (k, f) { this.listeners[k] = f; };
const byId = {};
const document = {
  getElementById: (id) => { if (id === 'data') return { textContent: dataM[1] }; return byId[id] || (byId[id] = new El('#' + id)); },
  createElement: (t) => new El(t), createTextNode: (t) => ({ text: t }),
};
new Function('document', codeM[1])(document);
const text = (e) => (e._t || '') + (e.children || []).map(c => c.text != null ? c.text : text(c)).join(' ');
const all = (e, pred, out = []) => { if (e.children) { if (pred(e)) out.push(e); e.children.forEach(c => all(c, pred, out)); } return out; };
const cls = (e, c) => (' ' + e.className + ' ').includes(' ' + c + ' ');
let failed = 0;
function check(name, ok, detail) { console.log((ok ? 'ok   ' : 'FAIL ') + name + (detail ? ' | ' + detail : '')); if (!ok) failed++; }
const cell = (arm, key) => D.summary[arm].cells[key], k = (c, f) => Math.round(c[f] * c.n);
const rows = (id) => all(byId[id], e => cls(e, 'row')).map(r => text(r.children[0]) + ' = ' + text(r.children[2]));

// key numbers and overview come from the data
const cards = text(byId.cards), h1 = D.stats.h1;
check('cards show the script gap', cards.includes(`${h1.ur_k} of ${h1.n}`) && cards.includes(`${h1.ro_k} of ${h1.n}`), cards.slice(0, 60));
check('cards show the failed gate', cards.includes(`${D.stats.h3.same} of ${D.stats.h3.n}`) && cards.includes('not met') === !D.stats.h3.gate_passed);
check('overview states the difference', text(byId['ov-primary']).includes('\u2212' + Math.abs(h1.diff_pp).toFixed(1)) && text(byId['ov-primary']).includes('\u00d7 10')
  && text(byId['ov-improved']).includes('placebo') && text(byId['ov-improved']).includes(`${D.stats.h3.same} of ${D.stats.h3.n}`), text(byId['ov-primary']).slice(-70));

// every chart row equals the logged counts
const gap = rows('chart-gap');
check('script-gap chart', gap.length === 4 && gap[0].endsWith(`${k(cell('unsteered', 'ur/harmful'), 'refusal_rate')} / ${h1.n}`)
  && gap[1].endsWith(`${k(cell('unsteered', 'ro/harmful'), 'refusal_rate')} / ${h1.n}`), gap.join('; '));
const arms = D.arms.filter(a => D.summary[a]);
const expectArms = arms.map(a => `${k(cell(a, 'ro/harmful'), 'refusal_rate')} / ${cell(a, 'ro/harmful').n}`);
check('intervention chart', rows('chart-arms').map(r => r.split(' = ')[1]).join() === expectArms.join(), rows('chart-arms').join('; '));
const expectBenign = arms.map(a => `${k(cell(a, 'ur/benign'), 'refusal_rate') + k(cell(a, 'ro/benign'), 'refusal_rate')} / ${cell(a, 'ur/benign').n + cell(a, 'ro/benign').n}`);
check('over-refusal chart', rows('chart-benign').map(r => r.split(' = ')[1]).join() === expectBenign.join(), rows('chart-benign').map(r => r.split(' = ')[1]).join(' '));
const expectUnsafe = arms.map(a => `${k(cell(a, 'ro/harmful'), 'unsafe_rate')} / ${cell(a, 'ro/harmful').n}`);
check('unsafe chart', rows('chart-unsafe').map(r => r.split(' = ')[1]).join() === expectUnsafe.join(), rows('chart-unsafe').map(r => r.split(' = ')[1]).join(' '));
const expectGap = arms.map(a => `${k(cell(a, 'ur/harmful'), 'refusal_rate') - k(cell(a, 'ro/harmful'), 'refusal_rate')} / ${cell(a, 'ro/harmful').n}`);
check('gap-by-arm chart', rows('chart-gaparm').map(r => r.split(' = ')[1]).join() === expectGap.join(), rows('chart-gaparm').map(r => r.split(' = ')[1]).join(' '));
const reading = rows('chart-reading');
check('reading chart', reading.length === Object.keys(D.reading).length
  && reading[0].endsWith(`${D.reading.unsteered.harmful.R} / ${D.reading.unsteered.harmful.n}`), reading.join('; '));

// explorer: rows are Urdu script, Roman Urdu and English; columns are the request and three arms side by side
const grid = byId.grid;
check('default grid: (form + request + 3 arms) x (header + 3 forms)', grid.children.length === 5 * 4 && grid.style.gridTemplateColumns.includes('repeat(3'), String(grid.children.length));
const heads = grid.children.filter(c => cls(c, 'head')).map(text).join(' | '), rowheads = grid.children.filter(c => cls(c, 'rowhead')).map(text).join(' | ');
check('columns: request, baseline, pooled, residualized', /Request.*No steering.*Pooled CAA.*Residualized CAA/.test(heads), heads);
check('rows: Urdu script, Roman Urdu, English', /Urdu script.*Roman Urdu.*English/.test(rowheads) && !/Code-mixed/.test(rowheads), rowheads);
check('family list', byId.family.children.length === D.families.length, String(D.families.length));
byId.family.value = '5'; byId.family.listeners.change();
all(byId.arms, e => e.tag === 'input').forEach(c => { c.checked = true; c.listeners.change(); });
all(byId.forms, e => e.tag === 'input').forEach(c => { c.checked = true; c.listeners.change(); });
check('all arms and forms: (2 + 7) columns x (1 + 4) rows', grid.children.length === 9 * 5, String(grid.children.length));
byId.label.children[1].listeners.click();
check('harmless view renders', text(grid).length > 200 && text(byId.meaning).includes('What is asked'));
byId.label.children[0].listeners.click();

// no withheld reply is ever rendered, for any family
let shown = 0, withheld = 0, bad = 0, leaked = 0;
D.families.forEach((f, i) => {
  Object.values(f.responses).forEach(a => Object.values(a.harmful || {}).forEach(x => { if (x.withheld) { withheld++; if (x.text !== '[withheld]') bad++; } else shown++; }));
  byId.family.value = String(i); byId.family.listeners.change();
  if (text(grid).includes('[withheld]')) leaked++;
});
check('withheld replies carry no text in the data', bad === 0, `shown ${shown}, withheld ${withheld}`);
check('withheld marker never rendered', leaked === 0);

// every withheld cell says why, in words that fit its labels
const REASONS = ['flagged_unsafe_by_judge', 'harmful_prompt_not_refused', 'read_as_not_a_refusal', 'roman_urdu_not_read_as_clean_refusal'];
let noReason = 0, shownWithReason = 0, contradiction = 0, borderlineCase = null, unreadCase = null;
D.families.forEach((f, i) => Object.entries(f.responses).forEach(([arm, byLabel]) => Object.entries(byLabel).forEach(([label, byForm]) => Object.entries(byForm).forEach(([form, x]) => {
  if (x.withheld && !REASONS.includes(x.why)) noReason++;
  if (!x.withheld && x.why) shownWithReason++;
  // a cell that is withheld only because of the reading must not carry a clear refusal reading
  if (x.why === 'roman_urdu_not_read_as_clean_refusal' && x.read_as === 'R' && !x.borderline) contradiction++;
  if (x.why === 'read_as_not_a_refusal' && x.read_as === 'R') contradiction++;
  if (x.why === 'roman_urdu_not_read_as_clean_refusal' && label === 'harmful' && form === 'ro') {
    if (x.read_as === 'R' && x.borderline && !borderlineCase && ['unsteered', 'pooled', 'residualized'].includes(arm)) borderlineCase = { i, arm };
    if (!x.read_as && !unreadCase) unreadCase = { i, arm };
  }
}))));
check('every withheld cell has one of the four published reasons', noReason === 0 && shownWithReason === 0, `without reason ${noReason}, shown with reason ${shownWithReason}`);
check('no cell is withheld for its reading while labelled a clear refusal', contradiction === 0, String(contradiction));
const showOnly = (c) => {
  byId.family.value = String(c.i); byId.family.listeners.change();
  all(byId.arms, e => e.tag === 'input').forEach(b => { b.checked = true; b.listeners.change(); });
  return text(grid);
};
check('a borderline refusal reading is shown as such and explains the withholding',
  !!borderlineCase && /read as: refusal \(borderline\)/.test(showOnly(borderlineCase)) && /a second reading is defensible/.test(text(grid)), JSON.stringify(borderlineCase));
check('an unread Roman-Urdu reply says it was not read',
  !!unreadCase && /it was not read, and a Roman-Urdu reply/.test(showOnly(unreadCase)), JSON.stringify(unreadCase));
check('the old catch-all reason is gone from the grid', !/not a clean refusal of a harmful request/.test(text(grid)));
check('links: article, GitHub, dataset, model, both collections', all(byId.links, e => e.tag === 'a').length >= 6
  && ['github.com', '/datasets/', '/collections/'].every(s => all(byId.links, e => e.tag === 'a').some(a => String(a.attrs.href).includes(s))));
const limits = text(byId['limit-list']);
check('limitations name sample size, judge, review and the failed hypothesis',
  limits.includes(`${h1.n} test families`) && limits.includes('judge') && limits.includes(`${D.stats.review.reviewed} of ${D.stats.review.total}`) && limits.includes('placebo'));
check('page says it is a replay', /no model runs on this page/i.test(html) && !/live demo/i.test(html));
check('no external resources', !/<(script|link|img)[^>]+(src|href)="https?:/i.test(html));
console.log(failed ? `${failed} check(s) FAILED` : 'all checks passed');
process.exit(failed ? 1 : 0);
