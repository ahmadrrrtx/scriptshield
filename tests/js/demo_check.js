const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const dataM = html.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/);
const codeM = html.match(/<script>\s*([\s\S]*?)<\/script>\s*<\/body>/);
if (!dataM || !codeM) { console.error('markers not found'); process.exit(2); }
const data = JSON.parse(dataM[1]);
function El(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.style = {}; this._t = ''; this.hidden = false; }
Object.defineProperty(El.prototype, 'textContent', { get() { return this._t; }, set(v) { this._t = v; this.children = []; } });
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attrs[k] = v; };
El.prototype.addEventListener = function (k, f) { this.listeners[k] = f; };
const byId = {};
const document = {
  getElementById: (id) => { if (id === 'data') return { textContent: dataM[1] }; return byId[id] || (byId[id] = new El('#' + id)); },
  createElement: (t) => new El(t), createTextNode: (t) => ({ text: t }),
};
new Function('document', codeM[1])(document);
function count(e, tag) { let n = e.tag === tag ? 1 : 0; (e.children || []).forEach(c => { if (c.children) n += count(c, tag); }); return n; }
const text = (e) => (e.textContent || '') + (e.children || []).map(c => c.text || text(c)).join(' ');
console.log('families:', data.families.length, '| arms:', data.arms.join(','));
console.log('summary rows:', count(byId.summary, 'tr'), '| reading rows:', count(byId.reading, 'tr'), '| reading hidden:', byId.readingwrap.hidden);
console.log('family options:', byId.family.children.length, '| grid cells:', byId.grid.children.length);
// switch family + label + arm toggles
byId.family.value = '5'; byId.family.listeners.change();
byId.label.children[1].listeners.click();
byId.arms.children.forEach(l => { const c = l.children[0]; c.checked = true; c.listeners.change(); });
console.log('after toggles grid cells:', byId.grid.children.length, '(expected 5 + 5 + 7*5 = 45)');
const all = text(byId.grid);
console.log('withheld marker text leaked into grid:', all.includes('[withheld]'));
// every harmful cell across all families: withheld cells must not render text
let shown = 0, hidden = 0, bad = 0;
data.families.forEach(f => Object.values(f.responses).forEach(a => Object.values(a.harmful || {}).forEach(x => { if (x.withheld) { hidden++; if (x.text !== '[withheld]') bad++; } else shown++; })));
console.log('harmful cells shown:', shown, 'withheld:', hidden, 'withheld-with-text (must be 0):', bad);
