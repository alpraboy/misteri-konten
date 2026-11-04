// Uji dashboard tanpa browser: stub DOM + fetch palsu. Dijalankan oleh tests/test_v11.py
const fs = require("fs"), path = require("path"), assert = require("assert");
const site = path.join(__dirname, "..", "site");
const C = require(path.join(site, "dashboard-core.js"));

// ---- logika murni
assert.deepStrictEqual(C.buildDispatchBody("main", {theme: "kriptid", style: "MYSTERY_WAYANG", post: "tidak", topic: "  Orang   Pendek \n Kerinci "}),
  {ref: "main", inputs: {theme: "kriptid", style: "MYSTERY_WAYANG", post: "tidak", topic: "Orang Pendek Kerinci"}});
const bad = C.buildDispatchBody(undefined, {theme: "ngawur", style: "ngawur", post: "x", topic: "a".repeat(500)});
assert.strictEqual(bad.ref, "main"); assert.strictEqual(bad.inputs.theme, "horor_nusantara");
assert.strictEqual(bad.inputs.style, "auto"); assert.strictEqual(bad.inputs.post, "ya"); assert.strictEqual(bad.inputs.topic.length, 200);
assert.strictEqual(C.statusInfo({status: "in_progress"}).active, true);
assert.strictEqual(C.statusInfo({status: "completed", conclusion: "success"}).label, "Selesai");
assert.strictEqual(C.statusInfo({status: "completed", conclusion: "failure"}).cls, "bad");
assert.strictEqual(C.relTime("2026-11-03T10:00:00Z", Date.parse("2026-11-03T10:05:00Z")), "5 mnt lalu");
assert.ok(C.explain(403, {message: "Resource not accessible"}).includes("Read and write"));
assert.ok(C.explain(404).includes("akses ke repo"));
assert.strictEqual(C.validateConfig({owner: "budi", repo: "misteri-konten", token: "github_pat_" + "x".repeat(30)}).length, 0);
assert.ok(C.validateConfig({owner: "", repo: "r", token: ""}).length >= 2);
// tema & style di dashboard harus sama dengan workflow
const wf = fs.readFileSync(path.join(__dirname, "..", ".github", "workflows", "make-video.yml"), "utf8");
for (const [k] of C.THEMES) assert.ok(wf.includes(k), "tema tidak ada di workflow: " + k);
for (const [k] of C.STYLES) assert.ok(wf.includes(k), "style tidak ada di workflow: " + k);

// ---- simulasi UI: stub DOM
function el(id) {
  const o = {id, value: "", textContent: "", innerHTML: "", style: {}, children: [], disabled: false, open: false, className: "",
    appendChild(c) { this.children.push(c); return c; }, addEventListener() {}, set onclick(f) { this._click = f; }, get onclick() { return this._click; }};
  return o;
}
const els = {};
global.window = global; global.AMCore = C;   // meniru <script src="dashboard-core.js">
global.document = {getElementById: (id) => els[id] || (els[id] = el(id)), createElement: (t) => el(t),
  addEventListener() {}, hidden: false};
const store = {am_owner: "budi", am_repo: "misteri-konten", am_token: "github_pat_" + "x".repeat(30)};
global.localStorage = {getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; }};
const calls = [];
global.fetch = async (url, opts = {}) => {
  calls.push({url, method: opts.method || "GET", body: opts.body, auth: (opts.headers || {}).Authorization});
  const json = (status, body) => ({status, json: async () => body});
  if (url.endsWith("/repos/budi/misteri-konten")) return json(200, {full_name: "budi/misteri-konten", private: true, default_branch: "main"});
  if (url.includes("/dispatches")) return {status: 204, json: async () => ({})};
  if (url.includes("/runs?")) return json(200, {workflow_runs: [{id: 9, run_number: 12, status: "in_progress", conclusion: null, created_at: new Date().toISOString(), html_url: "https://github.com/x/y/actions/runs/9"}]});
  return json(404, {});
};
global.setTimeout = (f) => 0; global.clearTimeout = () => {};
const html = fs.readFileSync(path.join(site, "dashboard.html"), "utf8");
const inline = html.match(/<script>([\s\S]*?)<\/script>/g).pop().replace(/<\/?script>/g, "");
(async () => {
  eval(inline);                                           // tidak boleh melempar error saat dimuat
  await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  assert.ok(els.theme.children.length === 12 && els.style.children.length === 4, "dropdown terisi");
  assert.ok(calls.some(c => c.url.includes("/runs?")), "status dimuat saat dibuka");
  assert.strictEqual(calls[0].auth, "Bearer " + store.am_token);
  assert.ok(els.runs.children.length === 1, "satu run ditampilkan");
  // tekan 'Buat Video'
  els.theme.value = "kriptid"; els.style.value = "MYSTERY_VHS"; els.post.value = "ya"; els.topic.value = "Orang Pendek";
  calls.length = 0;
  await els.go.onclick(); await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r)); await new Promise(r => setImmediate(r));
  const d = calls.find(c => c.url.includes("/dispatches"));
  assert.ok(d && d.method === "POST", "dispatch terkirim");
  assert.ok(d.url.endsWith("/repos/budi/misteri-konten/actions/workflows/make-video.yml/dispatches"));
  assert.deepStrictEqual(JSON.parse(d.body), {ref: "main", inputs: {theme: "kriptid", style: "MYSTERY_VHS", post: "ya", topic: "Orang Pendek"}});
  assert.ok(els.msg.textContent.startsWith("Dimulai"), "pesan sukses: " + els.msg.textContent);
  console.log("DASHBOARD_OK");
})().catch(e => { console.error("GAGAL:", e.message); process.exit(1); });
