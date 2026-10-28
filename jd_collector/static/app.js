/* JD Collector web UI - plain JavaScript, no build step, no dependencies.
 *
 * Views: Jobs (search + detail drawer), Saved, Insights (charts), Sources (manage + scrape),
 * Runs (history). All scraped text is rendered with textContent - never as HTML.
 */
"use strict";

// =================================================================== DOM helpers

const $ = (sel, root = document) => root.querySelector(sel);
const PROPS = new Set(["value", "checked", "selected", "disabled", "open", "indeterminate"]);

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false || c === true) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (PROPS.has(k)) el[k] = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
  }
  append(el, children);
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";
function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  append(el, children);
  return el;
}

const ICONS = {
  briefcase: [{ r: [3, 7, 18, 13, 2] }, "M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2", "M3 13h18"],
  search: [{ c: [11, 11, 7] }, "M20 20l-3.5-3.5"],
  bookmark: ["M6 3h12v18l-6-4-6 4z"],
  chart: ["M3 21h18", "M6 17v-6", "M11 17V6", "M16 17v-9", "M21 17v-3"],
  database: [{ e: [12, 5, 8, 3] }, "M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5", "M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"],
  activity: ["M3 12h4l3-8 4 16 3-8h4"],
  sliders: ["M4 6h9", "M17 6h3", "M4 12h3", "M11 12h9", "M4 18h11", "M19 18h1", { c: [15, 6, 2] }, { c: [9, 12, 2] }, { c: [17, 18, 2] }],
  sun: [{ c: [12, 12, 4] }, "M12 2v2", "M12 20v2", "M4.9 4.9l1.4 1.4", "M17.7 17.7l1.4 1.4", "M2 12h2", "M20 12h2", "M4.9 19.1l1.4-1.4", "M17.7 6.3l1.4-1.4"],
  moon: ["M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"],
  monitor: [{ r: [3, 4, 18, 12, 2] }, "M8 20h8", "M12 16v4"],
  x: ["M6 6l12 12", "M18 6L6 18"],
  external: ["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  refresh: ["M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7"],
  play: ["M7 4l13 8-13 8z"],
  plus: ["M12 5v14", "M5 12h14"],
  edit: ["M4 20h4L19 9l-4-4L4 16z", "M13.5 6.5l4 4"],
  trash: ["M4 7h16", "M9 7V4h6v3", "M6 7l1 13h10l1-13"],
  download: ["M12 4v11", "M7 10l5 5 5-5", "M4 20h16"],
  check: ["M5 12l5 5 9-10"],
  checkCircle: [{ c: [12, 12, 9] }, "M8 12l3 3 5-6"],
  xCircle: [{ c: [12, 12, 9] }, "M9 9l6 6", "M15 9l-6 6"],
  alert: ["M12 3l10 18H2z", "M12 10v4", "M12 17.5v.01"],
  info: [{ c: [12, 12, 9] }, "M12 11v6", "M12 7.5v.01"],
  link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
  chevL: ["M15 6l-6 6 6 6"],
  chevR: ["M9 6l6 6-6 6"],
  filter: ["M4 5h16l-6 8v6l-4-2v-4z"],
  pin: ["M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z", { c: [12, 10, 2.5] }],
  clock: [{ c: [12, 12, 9] }, "M12 7v5l3 2"],
  globe: [{ c: [12, 12, 9] }, "M3 12h18", "M12 3a14 14 0 0 1 0 18", "M12 3a14 14 0 0 0 0 18"],
  compass: [{ c: [12, 12, 9] }, "M16 8l-2.5 6.5L8 16l2.5-6.5z"],
  layers: ["M12 3l9 5-9 5-9-5z", "M3 13l9 5 9-5", "M3 18l9 5 9-5"],
  building: ["M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16", "M16 9h3a1 1 0 0 1 1 1v11", "M2 21h20", "M8 7h4", "M8 11h4", "M8 15h4"],
  key: [{ c: [8, 15, 4] }, "M11 12l9-9", "M17 6l3 3", "M15 8l2 2"],
  table: [{ r: [3, 4, 18, 16, 2] }, "M3 10h18", "M9 4v16"],
  skip: ["M5 5l10 7-10 7z", "M19 5v14"],
};

function icon(name, size = 16, extra = {}) {
  const svg = s("svg", {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", ...extra,
  });
  for (const part of ICONS[name] || []) {
    if (typeof part === "string") svg.append(s("path", { d: part }));
    else if (part.c) svg.append(s("circle", { cx: part.c[0], cy: part.c[1], r: part.c[2] }));
    else if (part.e) svg.append(s("ellipse", { cx: part.e[0], cy: part.e[1], rx: part.e[2], ry: part.e[3] }));
    else if (part.r) svg.append(s("rect", { x: part.r[0], y: part.r[1], width: part.r[2], height: part.r[3], rx: part.r[4] }));
  }
  return svg;
}

function button(label, { icon: ic, cls = "", onclick, title, type = "button", disabled } = {}) {
  return h("button", { class: `btn ${cls}`, type, onclick, title, disabled }, ic && icon(ic), label);
}
function iconButton(ic, label, onclick, { cls = "", disabled } = {}) {
  return h("button", { class: `icon-btn ${cls}`, type: "button", title: label, "aria-label": label, onclick, disabled }, icon(ic));
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function isTyping(e) {
  const t = e.target;
  return t && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));
}

// =================================================================== formatting

const nf = new Intl.NumberFormat();
const fmtNum = (n) => (n == null ? "–" : nf.format(n));
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

/** Server datetimes are naive UTC ("2026-10-16T17:53:49"); treat them as UTC. */
function toDate(v) {
  if (!v) return null;
  const str = String(v);
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(str) ? str : str + "Z");
  return isNaN(d) ? null : d;
}
function fmtDate(v, withTime = false) {
  const d = toDate(v);
  if (!d) return "–";
  const opts = { month: "short", day: "numeric" };
  if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
  if (withTime) Object.assign(opts, { hour: "numeric", minute: "2-digit" });
  return d.toLocaleString(undefined, opts);
}
function timeAgo(v) {
  const d = toDate(v);
  if (!d) return "–";
  const sec = (Date.now() - d.getTime()) / 1000;
  const future = sec < 0;
  const a = Math.abs(sec);
  let out;
  if (a < 45) return future ? "in a moment" : "just now";
  if (a < 3600) out = `${Math.round(a / 60)} min`;
  else if (a < 86400) out = `${Math.round(a / 3600)} h`;
  else if (a < 86400 * 30) out = `${Math.round(a / 86400)} d`;
  else return fmtDate(v);
  return future ? `in ${out}` : `${out} ago`;
}
function fmtDuration(sec) {
  if (sec == null) return "–";
  if (sec < 60) return `${sec.toFixed(sec < 10 ? 1 : 0)} s`;
  const m = Math.floor(sec / 60);
  return `${m} min ${Math.round(sec % 60)} s`;
}
function humanInterval(min) {
  if (min % 1440 === 0) return min === 1440 ? "Daily" : `Every ${min / 1440} days`;
  if (min % 60 === 0) return min === 60 ? "Hourly" : `Every ${min / 60} hours`;
  return `Every ${min} min`;
}
const isRecent = (v, days) => { const d = toDate(v); return d && Date.now() - d.getTime() < days * 864e5; };
const hostnameOf = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; } };
const slugify = (t) => t.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
const titleCase = (t) => t.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
const plural = (n, word) => `${fmtNum(n)} ${word}${n === 1 ? "" : "s"}`;

// =================================================================== storage (per-browser conveniences)

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem("jdc:" + key); return v == null ? fallback : JSON.parse(v); } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem("jdc:" + key, JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
};

const saved = {
  list() { return store.get("saved", []); },
  has(id) { return this.list().some((j) => j.job_id === id); },
  toggle(job) {
    const list = this.list();
    const i = list.findIndex((j) => j.job_id === job.job_id);
    if (i >= 0) list.splice(i, 1);
    else list.unshift({ job_id: job.job_id, title: job.title, company: job.company, saved_at: new Date().toISOString() });
    store.set("saved", list);
    document.dispatchEvent(new CustomEvent("saved-changed"));
    return i < 0;
  },
  remove(id) {
    store.set("saved", this.list().filter((j) => j.job_id !== id));
    document.dispatchEvent(new CustomEvent("saved-changed"));
  },
};

// =================================================================== API client

class ApiError extends Error {
  constructor(message, status, details) { super(message); this.status = status; this.details = details; }
}

function detailMessages(detail) {
  if (!detail) return [];
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "string" ? d : `${(d.loc || []).filter((x) => x !== "body").join(".")}: ${d.msg}`));
  }
  return [JSON.stringify(detail)];
}

async function api(path, { method = "GET", body, raw = false } = {}) {
  const headers = {};
  const key = store.get("apiKey", "");
  if (key) headers["X-API-Key"] = key;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let resp;
  try {
    resp = await fetch(path, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError("Can't reach the JD Collector server. Is it still running?", 0);
  }
  if (resp.status === 401) {
    if (!document.querySelector(".modal-root")) openSettings("This server requires an API key. Enter it to continue.");
    throw new ApiError("API key required - add it in Settings.", 401);
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try { detail = (await resp.json()).detail ?? detail; } catch { /* not JSON */ }
    const msgs = detailMessages(detail);
    throw new ApiError(msgs.join(" · ") || `Request failed (${resp.status})`, resp.status, msgs);
  }
  return raw ? resp : resp.json();
}

let facetsCache = { at: 0, data: null };
async function getFacets(force = false) {
  if (!force && facetsCache.data && Date.now() - facetsCache.at < 60_000) return facetsCache.data;
  facetsCache = { at: Date.now(), data: await api("/facets") };
  return facetsCache.data;
}
let typesCache = null;
async function getSourceTypes() {
  if (!typesCache) typesCache = await api("/source-types");
  return typesCache;
}

async function downloadCsv(params, filenameHint) {
  const resp = await api("/jobs/export.csv?" + params, { raw: true });
  const blob = await resp.blob();
  const name = /filename="([^"]+)"/.exec(resp.headers.get("Content-Disposition") || "")?.[1] || filenameHint;
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// =================================================================== toasts, tooltip, modal

function toast(title, { text, kind = "info", timeout = 5000 } = {}) {
  const icons = { info: "info", good: "checkCircle", crit: "xCircle", warn: "alert" };
  const el = h("div", { class: `toast ${kind}`, role: kind === "crit" ? "alert" : "status" },
    icon(icons[kind] || "info", 18),
    h("div", { class: "msg" }, h("strong", null, title), text && h("span", null, text)),
    iconButton("x", "Dismiss", () => el.remove()));
  $("#toasts").append(el);
  if (timeout) setTimeout(() => el.remove(), timeout);
}

const tip = () => $("#tooltip");
function showTip(e, content) {
  const el = tip();
  el.replaceChildren(...[content].flat());
  el.hidden = false;
  const pad = 14;
  const { innerWidth: W, innerHeight: H } = window;
  const r = el.getBoundingClientRect();
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + r.width > W - 8) x = e.clientX - r.width - pad;
  if (y + r.height > H - 8) y = e.clientY - r.height - pad;
  el.style.left = `${Math.max(8, x)}px`;
  el.style.top = `${Math.max(8, y)}px`;
}
function hideTip() { tip().hidden = true; }

function openModal({ title, body, footer, wide = false, onClose }) {
  const root = h("div", { class: "modal-root" });
  const dialog = h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true", "aria-label": title });
  const previous = document.activeElement;
  function close() {
    root.remove();
    document.removeEventListener("keydown", onKey, true);
    onClose?.();
    previous?.focus?.();
  }
  function onKey(e) {
    if (e.key === "Escape" && root === [...document.querySelectorAll(".modal-root")].pop()) { e.stopPropagation(); close(); }
  }
  dialog.append(
    h("div", { class: "modal-head" }, h("h2", null, title), iconButton("x", "Close", close)),
    h("div", { class: "modal-body" }, body),
    footer ? h("div", { class: "modal-foot" }, typeof footer === "function" ? footer(close) : footer) : null,
  );
  root.append(dialog);
  root.addEventListener("mousedown", (e) => { if (e.target === root) close(); });
  document.body.append(root);
  document.addEventListener("keydown", onKey, true);
  setTimeout(() => dialog.querySelector(".modal-body input, .modal-body select, .modal-body textarea, .modal-foot .primary")?.focus(), 0);
  return { close, dialog };
}

function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false, extra }) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok, m) => { if (done) return; done = true; m?.close(); resolve(ok); };
    const m = openModal({
      title,
      body: [h("p", { style: { margin: 0, color: "var(--text-2)" } }, message), extra],
      footer: (close) => [
        button("Cancel", { onclick: () => { finish(false); close(); } }),
        button(confirmLabel, { cls: danger ? "danger solid" : "primary", onclick: () => finish(true, m) }),
      ],
      onClose: () => finish(false),
    });
  });
}

function banner(kind, iconName, ...content) {
  return h("div", { class: `banner ${kind}` }, icon(iconName, 18), h("div", null, ...content));
}

function emptyState(iconName, title, text, actions = []) {
  return h("div", { class: "empty" },
    h("div", { class: "empty-icon" }, icon(iconName, 24)),
    h("h3", null, title), text && h("p", null, text),
    actions.length ? h("div", { class: "row" }, actions) : null);
}

const STATUS = {
  success: { kind: "good", icon: "checkCircle", label: "Success" },
  failed: { kind: "crit", icon: "xCircle", label: "Failed" },
  skipped: { kind: "warn", icon: "skip", label: "Skipped" },
};
function statusBadge(status) {
  if (status === "running") return h("span", { class: "status info" }, h("span", { class: "spinner" }), "Running");
  const st = STATUS[status] || { kind: "", icon: "info", label: status };
  return h("span", { class: `status ${st.kind}` }, icon(st.icon, 15), st.label);
}

function friendlyError(err) {
  if (!err) return null;
  if (/RobotsDisallowed/.test(err)) return "The site's robots.txt doesn't allow crawlers, and JD Collector respects it.";
  if (/HTTP 404/.test(err)) return "The board wasn't found (HTTP 404). Check the board / site name.";
  if (/HTTP 403/.test(err)) return "The site refused access (HTTP 403).";
  if (/Giving up|ConnectionError|Timeout/i.test(err)) return "The site couldn't be reached after several retries.";
  return null;
}

// =================================================================== settings & theme

function applyTheme(theme) {
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
  const btn = $("#theme-btn");
  const ic = { light: "sun", dark: "moon", system: "monitor" }[theme] || "monitor";
  btn.replaceChildren(icon(ic, 18));
  btn.title = `Theme: ${theme} (click to change)`;
}
function cycleTheme() {
  const order = ["system", "light", "dark"];
  const next = order[(order.indexOf(store.get("theme", "system")) + 1) % order.length];
  store.set("theme", next);
  applyTheme(next);
  toast(`Theme: ${next}`, { timeout: 1500 });
}

async function openSettings(reason) {
  const keyInput = h("input", { class: "input mono", type: "password", value: store.get("apiKey", ""), placeholder: "Leave empty if the server has no API_KEY", autocomplete: "off" });
  const show = h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => { keyInput.type = e.target.checked ? "text" : "password"; } }), "Show");
  const result = h("div");
  const themeSel = h("select", { class: "input" },
    ["system", "light", "dark"].map((t) => h("option", { value: t, selected: store.get("theme", "system") === t }, titleCase(t))));
  const info = h("p", { class: "help" }, "Checking server…");
  fetch("/health").then((r) => r.json()).then((hl) => {
    info.textContent = `Server version ${hl.version} · ${hl.auth_required ? "API key required" : "no API key required (open access)"}`;
  }).catch(() => { info.textContent = "Server unreachable."; });

  async function test() {
    store.set("apiKey", keyInput.value.trim());
    result.replaceChildren(h("span", { class: "muted" }, "Testing…"));
    try {
      const st = await api("/stats");
      result.replaceChildren(banner("good", "checkCircle", h("strong", null, "Connected. "), `${fmtNum(st.active_jobs)} open jobs in the database.`));
    } catch (e) {
      result.replaceChildren(banner("crit", "xCircle", e.message));
    }
  }
  openModal({
    title: "Settings",
    body: [
      reason ? banner("warn", "key", reason) : null,
      h("div", { class: "field" }, h("label", null, "API key"), h("div", { style: { display: "flex", gap: "10px", alignItems: "center" } }, keyInput, show),
        h("p", { class: "help" }, "Matches API_KEY in the server's .env. Stored only in this browser.")),
      h("div", { class: "field" }, h("label", null, "Theme"), themeSel),
      info, result,
    ],
    footer: (close) => [
      button("Test connection", { cls: "left", icon: "refresh", onclick: test }),
      button("Cancel", { onclick: close }),
      button("Save", {
        cls: "primary", onclick: () => {
          store.set("apiKey", keyInput.value.trim());
          store.set("theme", themeSel.value);
          applyTheme(themeSel.value);
          close();
          toast("Settings saved", { kind: "good", timeout: 2000 });
          poll();
          route();
        },
      }),
    ],
  });
}

// =================================================================== status polling

let lastStatus = null;
let prevRunning = new Set();
let pollTimer = null;
let polling = false;

async function poll() {
  clearTimeout(pollTimer);
  if (polling) return;
  polling = true;
  try {
    const st = await api("/status");
    const running = new Set(st.running);
    for (const name of prevRunning) if (!running.has(name)) announceFinished(name);
    prevRunning = running;
    lastStatus = st;
    renderStatusPill(st);
    current?.onStatus?.(st);
  } catch (e) {
    renderStatusPill(null, e);
  } finally {
    polling = false;
    pollTimer = setTimeout(poll, prevRunning.size ? 2500 : 10000);
  }
}
const pollSoon = () => setTimeout(poll, 500);

async function announceFinished(name) {
  facetsCache.at = 0;
  try {
    const [run] = await api(`/runs?source=${encodeURIComponent(name)}&limit=1`);
    if (!run) return;
    if (run.status === "success") {
      toast(`${name}: scrape finished`, { kind: "good", text: `${plural(run.new, "new job")} · ${fmtNum(run.updated)} updated · ${fmtNum(run.deactivated)} closed` });
    } else if (run.status === "failed") {
      toast(`${name}: scrape failed`, { kind: "crit", text: friendlyError(run.error) || run.error, timeout: 10000 });
    }
  } catch { /* ignore */ }
}

function renderStatusPill(st, err) {
  const el = $("#status-pill");
  if (!st) {
    el.replaceChildren(h("span", { class: "dot crit" }), h("span", null, err?.status === 401 ? "API key needed" : "Server unreachable"));
    return;
  }
  const parts = [];
  if (st.running.length) {
    parts.push(h("span", { class: "spinner" }), h("span", null, h("strong", null, `Scraping ${st.running.length === 1 ? st.running[0] : plural(st.running.length, "source")}`), h("br"), "Results update live"));
  } else {
    parts.push(h("span", { class: "dot good" }),
      h("span", null, st.data_freshness ? `Data updated ${timeAgo(st.data_freshness)}` : "No data collected yet", h("br"),
        h("span", { class: "muted" }, st.scheduler.running ? "Auto-scrape on" : "Auto-scrape off in this server")));
  }
  el.replaceChildren(...parts);
}

// =================================================================== router

const NAV = [
  { view: "jobs", label: "Jobs", icon: "briefcase" },
  { view: "saved", label: "Saved", icon: "bookmark" },
  { view: "insights", label: "Insights", icon: "chart" },
  { view: "sources", label: "Sources", icon: "database" },
  { view: "runs", label: "Runs", icon: "activity" },
];
const VIEWS = {};
let current = null;
let lastJobsQuery = "";

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  return { view: path || "jobs", params: new URLSearchParams(qs || "") };
}

function go(view, params) {
  const qs = params ? (params instanceof URLSearchParams ? params : new URLSearchParams(params)).toString() : "";
  location.hash = `#/${view}${qs ? "?" + qs : ""}`;
}

function renderNav(active) {
  const nav = $("#nav-links");
  nav.replaceChildren(...NAV.map((n) => {
    const a = h("a", {
      class: "nav-link" + (n.view === active ? " active" : ""), href: `#/${n.view}`,
      "aria-current": n.view === active ? "page" : null,
      onclick: (e) => {
        if (n.view === "jobs" && active !== "jobs" && lastJobsQuery) { e.preventDefault(); location.hash = `#/jobs?${lastJobsQuery}`; }
      },
    }, icon(n.icon, 18), h("span", { class: "label" }, n.label));
    if (n.view === "saved") {
      const count = saved.list().length;
      if (count) a.append(h("span", { class: "nav-count" }, count));
    }
    return a;
  }));
}

function route() {
  const { view, params } = parseHash();
  const name = VIEWS[view] ? view : "jobs";
  closeDrawer(true);
  hideTip();
  current?.destroy?.();
  renderNav(name);
  const main = $("#view");
  main.replaceChildren();
  main.scrollTop = 0;
  window.scrollTo(0, 0);
  current = VIEWS[name](main, params) || {};
  current.name = name;
  document.title = `${NAV.find((n) => n.view === name).label} · JD Collector`;
  if (lastStatus) current.onStatus?.(lastStatus);
}

// =================================================================== job card + drawer

function jobCard(job, { active, onOpen }) {
  const savedNow = saved.has(job.job_id);
  const saveBtn = iconButton("bookmark", savedNow ? "Remove from saved" : "Save job", (e) => {
    e.stopPropagation();
    const on = saved.toggle(job);
    toast(on ? "Saved" : "Removed from saved", { timeout: 1500 });
  }, { cls: savedNow ? "on" : "" });
  if (savedNow) saveBtn.querySelector("svg").setAttribute("fill", "currentColor");

  const skills = job.skills.slice(0, 6);
  const card = h("article", {
    class: "job-card" + (active ? " active" : "") + (job.is_active ? "" : " closed"),
    tabindex: "0", "aria-label": `${job.title} at ${job.company}`,
    onclick: onOpen, onkeydown: (e) => { if (e.key === "Enter" && e.target === card) onOpen(); },
  },
  h("div", { class: "job-body" },
    h("h3", null, job.title),
    h("div", { class: "job-meta" },
      h("span", null, icon("building", 14), job.company),
      job.location && h("span", { title: job.location }, icon("pin", 14), job.location.length > 70 ? job.location.slice(0, 68) + "…" : job.location),
      job.is_remote && h("span", null, icon("globe", 14), "Remote"),
      job.region && h("span", { title: "Region: " + job.region }, icon("compass", 14), job.region)),
    h("div", { class: "job-tags" },
      !job.is_active && h("span", { class: "badge closed" }, "Closed"),
      isRecent(job.posted_date, 3) && job.is_active && h("span", { class: "badge new" }, "New"),
      job.role_category && h("span", { class: "badge role" }, job.role_category),
      job.experience_level && h("span", { class: "badge" }, job.experience_level),
      job.job_type && h("span", { class: "badge" }, job.job_type),
      job.salary && h("span", { class: "badge salary" }, job.salary),
      skills.map((sk) => h("span", { class: "chip" }, sk)),
      job.skills.length > skills.length && h("span", { class: "chip" }, `+${job.skills.length - skills.length}`))),
  h("div", { class: "job-side" },
    saveBtn,
    h("span", { class: "job-when", title: job.posted_date ? `Posted ${fmtDate(job.posted_date)}` : "" },
      job.posted_date ? timeAgo(job.posted_date) : `seen ${timeAgo(job.first_seen_at)}`)));
  return card;
}

const HEADING_RX = /^(about|what|who|why|how|responsibilities|requirements|qualifications|benefits|perks|the role|your role|role|you will|you'll|you have|nice to have|bonus|preferred|minimum|basic|compensation|pay|salary|our|we offer|in this role|key)/i;
function renderDescription(text) {
  const root = h("div", { class: "description" });
  let list = null;
  for (const raw of (text || "").split("\n")) {
    const line = raw.trim();
    if (!line) { list = null; continue; }
    if (/^(• |[-*–] )/.test(line)) {
      if (!list) { list = h("ul"); root.append(list); }
      list.append(h("li", null, line.replace(/^(• |[-*–] )/, "")));
      continue;
    }
    list = null;
    const words = line.split(/\s+/).length;
    const heading = line.length <= 80 && words <= 10 && !/[.!?,;]$/.test(line) &&
      ((/^[A-Z][A-Z &/'’-]{2,}$/.test(line)) || line.endsWith(":") || HEADING_RX.test(line));
    root.append(h(heading ? "h4" : "p", null, line));
  }
  return root;
}

let drawerEl = null;
let drawerOpts = null;
let drawerReq = 0;

function openJobDrawer(jobId, opts = {}) {
  drawerOpts = opts;
  if (!drawerEl) {
    drawerEl = h("div", { class: "drawer-root" },
      h("div", { class: "drawer-backdrop", onclick: () => closeDrawer() }),
      h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": "Job details", tabindex: "-1" }));
    document.body.append(drawerEl);
    document.addEventListener("keydown", drawerKeys);
  }
  const panel = $(".drawer", drawerEl);
  panel.replaceChildren(drawerHead(opts), h("div", { class: "drawer-scroll" },
    h("div", { class: "skeleton", style: { height: "16px", width: "30%" } }),
    h("div", { class: "skeleton", style: { height: "26px", width: "80%", margin: "12px 0 24px" } }),
    h("div", { class: "skeleton", style: { height: "120px" } })));
  const req = ++drawerReq;
  api(`/jobs/${encodeURIComponent(jobId)}`).then((job) => {
    if (req !== drawerReq || !drawerEl) return;
    panel.replaceChildren(drawerHead(opts), jobDetail(job, opts));
    panel.focus();
  }).catch((e) => {
    if (req !== drawerReq || !drawerEl) return;
    panel.replaceChildren(drawerHead(opts), h("div", { class: "drawer-scroll" },
      banner("crit", "xCircle", e.status === 404 ? "This job is no longer in the database." : e.message)));
  });
}

function drawerHead(opts) {
  return h("div", { class: "drawer-head" },
    opts.onPrev && iconButton("chevL", "Previous job (k)", opts.onPrev, { disabled: !opts.hasPrev }),
    opts.onNext && iconButton("chevR", "Next job (j)", opts.onNext, { disabled: !opts.hasNext }),
    opts.position && h("span", { class: "pos" }, opts.position),
    h("span", { class: "spacer" }),
    iconButton("x", "Close (Esc)", () => closeDrawer()));
}

function citationBlock(job) {
  const host = hostnameOf(job.apply_link);
  return h("div", { class: "citation" },
    h("h3", { class: "section-title" }, "Source & citation"),
    h("dl", { class: "facts" },
      h("div", null, h("dt", null, "Collected from"), h("dd", null, host
        ? h("a", { href: job.apply_link, target: "_blank", rel: "noopener noreferrer" }, host, icon("external", 13))
        : "Unknown")),
      h("div", null, h("dt", null, "Source"), h("dd", null, job.company, h("span", { class: "muted" }, ` (${job.source})`))),
      h("div", null, h("dt", null, "Job ID"), h("dd", { class: "mono", style: { fontSize: "12.5px" } }, job.job_id))));
}

function jobDetail(job, opts) {
  const isSaved = saved.has(job.job_id);
  const saveBtn = button(isSaved ? "Saved" : "Save", {
    icon: "bookmark", onclick: () => {
      const on = saved.toggle(job);
      saveBtn.replaceChildren(icon("bookmark"), on ? "Saved" : "Save");
      if (on) saveBtn.querySelector("svg").setAttribute("fill", "currentColor");
    },
  });
  if (isSaved) saveBtn.querySelector("svg").setAttribute("fill", "currentColor");

  const copyBtn = button("Copy link", {
    icon: "link", onclick: async () => {
      const url = `${location.origin}${location.pathname}#/jobs?job=${encodeURIComponent(job.job_id)}`;
      try { await navigator.clipboard.writeText(url); toast("Link copied", { kind: "good", timeout: 1500 }); }
      catch { toast("Couldn't copy", { kind: "warn", text: url }); }
    },
  });

  const fact = (label, value) => value ? h("div", null, h("dt", null, label), h("dd", null, value)) : null;
  const factLink = (label, value, params) => value ? h("div", null, h("dt", null, label),
    h("dd", null, h("button", {
      class: "fact-link", type: "button", title: `Show jobs in ${value}`,
      onclick: () => { closeDrawer(); go("jobs", params); },
    }, value))) : null;
  const posted = job.posted_date ? `${fmtDate(job.posted_date)} (${timeAgo(job.posted_date)})` : "Not given";
  return h("div", { class: "drawer-scroll" },
    h("div", { class: "eyebrow" }, icon("building", 14), job.company, job.department && h("span", { class: "muted" }, `· ${job.department}`)),
    h("h2", null, job.title),
    h("div", { class: "job-tags" },
      !job.is_active && h("span", { class: "badge closed" }, "Closed - no longer listed"),
      isRecent(job.posted_date, 3) && job.is_active && h("span", { class: "badge new" }, "New"),
      job.role_category && h("span", { class: "badge role" }, job.role_category),
      job.experience_level && h("span", { class: "badge" }, job.experience_level),
      job.job_type && h("span", { class: "badge" }, job.job_type),
      job.is_remote && h("span", { class: "badge" }, "Remote"),
      job.salary && h("span", { class: "badge salary" }, job.salary)),
    h("div", { class: "drawer-actions" },
      h("a", { class: "btn primary", href: job.apply_link, target: "_blank", rel: "noopener noreferrer" }, "Apply on company site", icon("external")),
      saveBtn, copyBtn),
    h("dl", { class: "facts" },
      fact("Location", job.location || "Not given"),
      fact("Work mode", job.is_remote ? "Remote" : "On-site / hybrid"),
      factLink("Region", job.region, { region: job.region }),
      factLink("Role category", job.role_category, { role_category: job.role_category }),
      factLink("Experience needed", job.experience_level, { experience_level: job.experience_level }),
      fact("Job type", job.job_type || "Not given"),
      fact("Salary", job.salary || "Not given"),
      fact("Posted", posted),
      fact("First collected", fmtDate(job.first_seen_at, true)),
      fact("Last checked", `${timeAgo(job.last_seen_at)}`),
      fact("Status", job.is_active ? "Open" : "Closed")),
    job.skills.length ? h("div", { style: { marginBottom: "22px" } },
      h("h3", { class: "section-title" }, "Skills mentioned"),
      h("div", { class: "chips" }, job.skills.map((sk) => h("button", {
        class: "chip", type: "button", title: `Show jobs mentioning ${sk}`,
        onclick: () => { closeDrawer(); opts.onSkill ? opts.onSkill(sk) : go("jobs", { skill: sk }); },
      }, sk)))) : null,
    h("h3", { class: "section-title" }, "Job description"),
    renderDescription(job.description),
    citationBlock(job));
}

function closeDrawer(silent = false) {
  if (!drawerEl) return;
  drawerEl.remove();
  drawerEl = null;
  document.removeEventListener("keydown", drawerKeys);
  const cb = drawerOpts?.onClose;
  drawerOpts = null;
  drawerReq++;
  if (!silent) cb?.();
}
function drawerKeys(e) {
  if (e.key === "Escape" && !document.querySelector(".modal-root")) closeDrawer();
}

// =================================================================== Jobs view

const JOB_TYPES = ["Full-time", "Part-time", "Contract", "Internship", "Temporary"];
const SORTS = [["-posted_date", "Newest first"], ["-salary_max", "Highest salary"], ["-first_seen_at", "Recently collected"], ["company", "Company A–Z"], ["title", "Title A–Z"]];
const POSTED = [["", "Any time"], ["1", "24 hours"], ["7", "Week"], ["30", "Month"]];
const PAGE_SIZE = 20;

function readJobState(p) {
  return {
    q: p.get("q") || "", company: p.get("company") || "", location: p.get("location") || "",
    skills: p.getAll("skill"), job_type: p.get("job_type") || "", remote: p.get("remote") || "",
    region: p.get("region") || "", role_category: p.get("role_category") || "",
    experience_level: p.get("experience_level") || "",
    posted: p.get("posted") || "", min_salary: p.get("min_salary") || "", source: p.get("source") || "",
    include_inactive: p.get("include_inactive") === "true", sort: p.get("sort") || "-posted_date",
    page: Math.max(1, parseInt(p.get("page") || "1", 10) || 1), job: p.get("job") || "",
  };
}

function jobParams(st, forApi = false) {
  const p = new URLSearchParams();
  for (const k of ["q", "company", "location", "job_type", "remote", "region", "role_category", "experience_level", "min_salary", "source"])
    if (st[k]) p.set(k, st[k]);
  for (const sk of st.skills) p.append("skill", sk);
  if (st.include_inactive) p.set("include_inactive", "true");
  if (st.posted) {
    if (forApi) p.set("posted_after", new Date(Date.now() - Number(st.posted) * 864e5).toISOString().slice(0, 19));
    else p.set("posted", st.posted);
  }
  if (forApi || st.sort !== "-posted_date") p.set("sort", st.sort);
  if (!forApi) {
    if (st.page > 1) p.set("page", st.page);
    if (st.job) p.set("job", st.job);
  }
  return p;
}

const activeFilters = (st) =>
  ["q", "company", "location", "job_type", "remote", "region", "role_category", "experience_level", "posted", "min_salary", "source"]
    .filter((k) => st[k]).length + st.skills.length + (st.include_inactive ? 1 : 0);

function segmented(options, value, onChange) {
  const wrap = h("div", { class: "seg", role: "radiogroup" });
  const render = (val) => wrap.replaceChildren(...options.map(([v, label]) => h("button", {
    type: "button", class: v === val ? "on" : "", role: "radio", "aria-checked": String(v === val),
    onclick: () => { render(v); onChange(v); },
  }, label)));
  render(value);
  return wrap;
}

function tagInput({ values, listId, placeholder, onChange }) {
  const tags = [...values];
  const input = h("input", { type: "text", list: listId, placeholder, "aria-label": placeholder });
  const wrap = h("div", { class: "tag-input", onclick: () => input.focus() });
  function render() {
    wrap.replaceChildren(...tags.map((t) => h("span", { class: "chip accent" }, t,
      h("button", { class: "x", type: "button", "aria-label": `Remove ${t}`, onclick: (e) => { e.stopPropagation(); tags.splice(tags.indexOf(t), 1); render(); onChange([...tags]); } }, icon("x", 12)))), input);
  }
  function add(v) {
    v = v.trim();
    if (v && !tags.some((t) => t.toLowerCase() === v.toLowerCase())) { tags.push(v); render(); onChange([...tags]); }
    input.value = "";
    input.focus();
  }
  input.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === ",") && input.value.trim()) { e.preventDefault(); add(input.value); }
    else if (e.key === "Backspace" && !input.value && tags.length) { tags.pop(); render(); onChange([...tags]); }
  });
  // Picking a suggestion from the datalist fires "input" with the full option value.
  input.addEventListener("input", (e) => {
    const list = document.getElementById(listId);
    if (e.inputType === "insertReplacementText" || (list && [...list.options].some((o) => o.value === input.value) && !e.inputType)) add(input.value);
  });
  render();
  return wrap;
}

VIEWS.jobs = function JobsView(root, params) {
  let st = readJobState(params);
  let items = [], total = 0, pages = 1, selected = -1, reqId = 0;
  let dbEmpty = false;

  const setState = (patch, { reload = true } = {}) => {
    st = { ...st, ...patch };
    if (!("page" in patch)) st.page = 1;
    syncUrl();
    if (reload) load();
  };
  const syncUrl = () => {
    const qs = jobParams(st).toString();
    const withoutJob = new URLSearchParams(qs); withoutJob.delete("job");
    lastJobsQuery = withoutJob.toString();
    history.replaceState(null, "", `#/jobs${qs ? "?" + qs : ""}`);
  };

  // ---- filter controls
  const datalists = h("div", { hidden: true }, h("datalist", { id: "dl-skills" }), h("datalist", { id: "dl-locations" }));
  const qInput = h("input", { class: "input", type: "search", value: st.q, placeholder: "Title, skill, keyword…", "aria-label": "Search jobs", oninput: debounce((e) => setState({ q: e.target.value.trim() }), 350) });
  const companySel = h("select", { class: "input", "aria-label": "Company", onchange: (e) => setState({ company: e.target.value }) }, h("option", { value: "" }, "All companies"));
  const sourceSel = h("select", { class: "input", "aria-label": "Source", onchange: (e) => setState({ source: e.target.value }) }, h("option", { value: "" }, "All sources"));
  const locInput = h("input", { class: "input", type: "search", value: st.location, list: "dl-locations", placeholder: "City, country or 'Remote'", oninput: debounce((e) => setState({ location: e.target.value.trim() }), 400) });
  const regionSel = h("select", { class: "input", "aria-label": "Region", onchange: (e) => setState({ region: e.target.value }) }, h("option", { value: "" }, "All regions"));
  const roleSel = h("select", { class: "input", "aria-label": "Role category", onchange: (e) => setState({ role_category: e.target.value }) }, h("option", { value: "" }, "Any role"));
  const expSel = h("select", { class: "input", "aria-label": "Experience level", onchange: (e) => setState({ experience_level: e.target.value }) }, h("option", { value: "" }, "Any experience"));
  const salaryInput = h("input", { class: "input", type: "number", min: "0", step: "1000", value: st.min_salary, placeholder: "e.g. 100000", oninput: debounce((e) => setState({ min_salary: e.target.value }), 500) });
  const sortSel = h("select", { class: "input", "aria-label": "Sort", onchange: (e) => setState({ sort: e.target.value }) },
    SORTS.map(([v, l]) => h("option", { value: v, selected: v === st.sort }, l)));

  const field = (label, control, help) => h("div", { class: "field" }, h("span", { class: "field-label" }, label), control, help && h("p", { class: "help" }, help));
  const filters = h("aside", { class: "filters card", "aria-label": "Filters" },
    h("div", { class: "filters-head" }, h("h2", null, "Filters"),
      button("Clear all", { cls: "ghost sm", onclick: () => go("jobs") })),
    h("div", { class: "search-box" }, icon("search", 16), qInput),
    field("Company", companySel),
    field("Location", locInput),
    field("Region", regionSel, "Derived from each job's location"),
    field("Skills", tagInput({ values: st.skills, listId: "dl-skills", placeholder: st.skills.length ? "Add another…" : "Type a skill, press Enter", onChange: (skills) => setState({ skills }) }), "Jobs must mention every skill listed"),
    field("Job type", segmented([["", "Any"], ...JOB_TYPES.map((t) => [t, t])], st.job_type, (v) => setState({ job_type: v }))),
    field("Role category", roleSel, "Derived from the job title"),
    field("Experience needed", expSel, "Years of experience stated in the posting"),
    field("Work mode", segmented([["", "Any"], ["true", "Remote"], ["false", "On-site"]], st.remote, (v) => setState({ remote: v }))),
    field("Posted within", segmented(POSTED, st.posted, (v) => setState({ posted: v }))),
    field("Minimum salary", salaryInput, "Top of the range, in the posting's own currency"),
    field("Source", sourceSel),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: st.include_inactive, onchange: (e) => setState({ include_inactive: e.target.checked }) }), "Include closed jobs"),
    datalists);

  const countEl = h("span", { class: "results-count" });
  const filtersToggle = button("Filters", { cls: "filters-toggle", icon: "filter", onclick: () => filters.classList.toggle("open") });
  const list = h("div", { class: "job-list", "aria-live": "polite" });
  const pager = h("nav", { class: "pager", "aria-label": "Pages" });

  root.append(h("div", { class: "jobs-layout" }, filters,
    h("section", null,
      h("div", { class: "results-head" }, h("h1", null, "Jobs"), countEl, h("span", { class: "spacer" }), filtersToggle, sortSel,
        button("Export CSV", { icon: "download", title: "Download the matching jobs as a spreadsheet", onclick: exportCsv })),
      list, pager,
      h("p", { class: "kbd-hint" }, h("kbd", null, "/"), " search · ", h("kbd", null, "j"), " ", h("kbd", null, "k"), " next / previous · ", h("kbd", null, "s"), " save · ", h("kbd", null, "Esc"), " close"))));

  function updateFilterBadge() {
    const n = activeFilters(st);
    filtersToggle.replaceChildren(icon("filter"), n ? `Filters (${n})` : "Filters");
  }

  async function loadFacets() {
    try {
      const f = await getFacets();
      dbEmpty = f.companies.length === 0;
      const fill = (sel, rows, current) => {
        const names = new Set(rows.map((r) => r.name));
        sel.append(...rows.map((r) => h("option", { value: r.name, selected: r.name === current }, `${r.name} (${fmtNum(r.count)})`)));
        if (current && !names.has(current)) sel.append(h("option", { value: current, selected: true }, current));
      };
      fill(companySel, f.companies, st.company);
      fill(sourceSel, f.sources, st.source);
      fill(regionSel, f.regions, st.region);
      fill(roleSel, f.role_categories, st.role_category);
      fill(expSel, f.experience_levels, st.experience_level);
      $("#dl-skills", datalists).replaceChildren(...f.skills.map((x) => h("option", { value: x.name })));
      $("#dl-locations", datalists).replaceChildren(...f.locations.map((x) => h("option", { value: x.name })));
      if (dbEmpty && !items.length) renderResults();
    } catch { /* the job list shows the error */ }
  }

  function skeletons() {
    return Array.from({ length: 5 }, () => h("div", { class: "job-card", style: { cursor: "default" } },
      h("div", { class: "job-body" },
        h("div", { class: "skeleton", style: { height: "18px", width: "55%" } }),
        h("div", { class: "skeleton", style: { height: "13px", width: "35%" } }),
        h("div", { class: "skeleton", style: { height: "20px", width: "70%" } }))));
  }

  async function load() {
    const id = ++reqId;
    updateFilterBadge();
    if (!items.length) list.replaceChildren(...skeletons());
    else list.style.opacity = ".6";
    const p = jobParams(st, true);
    p.set("page", st.page);
    p.set("page_size", PAGE_SIZE);
    try {
      const data = await api("/jobs?" + p);
      if (id !== reqId) return;
      if (data.total && st.page > data.pages) { setState({ page: data.pages }); return; }
      items = data.items; total = data.total; pages = Math.max(1, data.pages);
      selected = items.findIndex((j) => j.job_id === st.job);
      renderResults();
    } catch (e) {
      if (id !== reqId) return;
      items = [];
      list.replaceChildren(banner("crit", "xCircle", e.message));
      countEl.textContent = "";
      pager.replaceChildren();
    } finally {
      if (id === reqId) list.style.opacity = "";
    }
  }

  function renderResults() {
    countEl.textContent = `${plural(total, "job")}${activeFilters(st) ? " match" : ""}`;
    if (!items.length) {
      if (activeFilters(st)) {
        list.replaceChildren(emptyState("search", "No jobs match these filters", "Try removing a filter or a skill.", [button("Clear all filters", { onclick: () => go("jobs") })]));
      } else if (dbEmpty || total === 0) {
        list.replaceChildren(emptyState("database", "No jobs collected yet",
          "Add a company's careers page in Sources, or scrape the sources that are already set up.",
          [button("Scrape all sources", { cls: "primary", icon: "play", onclick: scrapeAll }), button("Go to Sources", { onclick: () => go("sources") })]));
      }
      pager.replaceChildren();
      return;
    }
    list.replaceChildren(...items.map((job, i) => jobCard(job, { active: i === selected && !!drawerEl, onOpen: () => openAt(i) })));
    renderPager();
  }

  function renderPager() {
    if (pages <= 1) { pager.replaceChildren(); return; }
    const btn = (label, page, { on, disabled, aria } = {}) => h("button", {
      type: "button", class: on ? "on" : "", disabled, "aria-label": aria, "aria-current": on ? "page" : null,
      onclick: () => { setState({ page }); window.scrollTo({ top: 0 }); },
    }, label);
    const nums = new Set([1, pages, st.page - 1, st.page, st.page + 1].filter((n) => n >= 1 && n <= pages));
    const sorted = [...nums].sort((a, b) => a - b);
    const out = [btn(icon("chevL"), st.page - 1, { disabled: st.page <= 1, aria: "Previous page" })];
    sorted.forEach((n, i) => {
      if (i && n - sorted[i - 1] > 1) out.push(h("span", { class: "gap" }, "…"));
      out.push(btn(String(n), n, { on: n === st.page }));
    });
    out.push(btn(icon("chevR"), st.page + 1, { disabled: st.page >= pages, aria: "Next page" }));
    pager.replaceChildren(...out);
  }

  function openAt(i) {
    if (i < 0 || i >= items.length) return;
    selected = i;
    st.job = items[i].job_id;
    syncUrl();
    [...list.children].forEach((c, idx) => c.classList.toggle("active", idx === i));
    list.children[i]?.scrollIntoView({ block: "nearest" });
    openJobDrawer(st.job, {
      onClose: () => { st.job = ""; syncUrl(); [...list.children].forEach((c) => c.classList.remove("active")); list.children[selected]?.focus(); },
      onPrev: () => openAt(selected - 1), onNext: () => openAt(selected + 1),
      hasPrev: i > 0, hasNext: i < items.length - 1,
      position: `${(st.page - 1) * PAGE_SIZE + i + 1} of ${fmtNum(total)}`,
      onSkill: (sk) => { if (!st.skills.includes(sk)) go("jobs", jobParams({ ...st, skills: [...st.skills, sk], page: 1, job: "" })); },
    });
  }

  async function exportCsv() {
    try {
      toast("Preparing CSV…", { timeout: 1500 });
      await downloadCsv(jobParams(st, true), "jobs.csv");
    } catch (e) { toast("Export failed", { kind: "crit", text: e.message }); }
  }

  function onKey(e) {
    if (isTyping(e) || e.metaKey || e.ctrlKey || e.altKey || document.querySelector(".modal-root")) return;
    if (e.key === "/") { e.preventDefault(); qInput.focus(); qInput.select(); }
    else if (e.key === "j") openAt(Math.min(items.length - 1, selected + 1));
    else if (e.key === "k") openAt(Math.max(0, selected - 1));
    else if (e.key === "s" && items[selected]) {
      const on = saved.toggle(items[selected]);
      toast(on ? "Saved" : "Removed from saved", { timeout: 1200 });
    }
  }
  const onSaved = () => { renderNav("jobs"); if (items.length) list.replaceChildren(...items.map((job, i) => jobCard(job, { active: i === selected && !!drawerEl, onOpen: () => openAt(i) }))); };
  document.addEventListener("keydown", onKey);
  document.addEventListener("saved-changed", onSaved);

  syncUrl();
  loadFacets();
  load().then(() => { if (st.job) { const i = items.findIndex((j) => j.job_id === st.job); i >= 0 ? openAt(i) : openJobDrawer(st.job, { onClose: () => { st.job = ""; syncUrl(); } }); } });

  let lastRunning = null;
  return {
    destroy() { document.removeEventListener("keydown", onKey); document.removeEventListener("saved-changed", onSaved); },
    onStatus(status) {
      const key = status.running.join(",");
      // A scrape just finished: refresh the list quietly so new jobs appear.
      if (lastRunning !== null && key !== lastRunning && status.running.length < lastRunning.split(",").filter(Boolean).length) {
        facetsCache.at = 0;
        load();
      }
      lastRunning = key;
    },
  };
};

async function scrapeAll() {
  try {
    const r = await api("/scrape", { method: "POST" });
    if (r.queued.length) toast(`Scraping ${plural(r.queued.length, "source")}`, { text: "New jobs appear as each source finishes.", timeout: 4000 });
    else toast("Nothing to scrape", { kind: "warn", text: r.already_running.length ? "Those sources are already running." : "No sources are enabled." });
    pollSoon();
  } catch (e) { toast("Couldn't start scrape", { kind: "crit", text: e.message }); }
}

// =================================================================== Saved view

VIEWS.saved = function SavedView(root) {
  const list = h("div", { class: "job-list" });
  const head = h("div", { class: "page-head" });
  root.append(head, list);

  async function load() {
    const entries = saved.list();
    head.replaceChildren(
      h("div", null, h("h1", null, "Saved jobs"), h("p", null, entries.length ? `${plural(entries.length, "job")} saved in this browser` : "Jobs you bookmark appear here")),
      entries.length ? h("div", { class: "actions" },
        button("Export CSV", { icon: "download", onclick: () => { const p = new URLSearchParams(); entries.forEach((e) => p.append("ids", e.job_id)); p.set("include_inactive", "true"); downloadCsv(p, "saved-jobs.csv").catch((e) => toast("Export failed", { kind: "crit", text: e.message })); } }),
        button("Clear all", { cls: "danger", icon: "trash", onclick: async () => { if (await confirmDialog({ title: "Clear saved jobs?", message: `Remove all ${entries.length} saved jobs from this browser?`, confirmLabel: "Clear all", danger: true })) { store.set("saved", []); document.dispatchEvent(new CustomEvent("saved-changed")); } } })) : null);
    if (!entries.length) {
      list.replaceChildren(emptyState("bookmark", "Nothing saved yet", "Use the bookmark icon on any job to keep it here. Press s while viewing a job to save it.", [button("Browse jobs", { cls: "primary", onclick: () => go("jobs") })]));
      return;
    }
    const p = new URLSearchParams({ include_inactive: "true", page_size: "100" });
    entries.slice(0, 100).forEach((e) => p.append("ids", e.job_id));
    try {
      const data = await api("/jobs?" + p);
      const byId = new Map(data.items.map((j) => [j.job_id, j]));
      list.replaceChildren(...entries.map((entry) => {
        const job = byId.get(entry.job_id);
        if (!job) {
          return h("div", { class: "job-card closed", style: { cursor: "default" } },
            h("div", { class: "job-body" }, h("h3", null, entry.title), h("div", { class: "job-meta" }, entry.company, " · no longer in the database")),
            h("div", { class: "job-side" }, iconButton("trash", "Remove", () => saved.remove(entry.job_id))));
        }
        return jobCard(job, { onOpen: () => openJobDrawer(job.job_id, {}) });
      }));
    } catch (e) {
      list.replaceChildren(banner("crit", "xCircle", e.message));
    }
  }
  const onSaved = () => { renderNav("saved"); load(); };
  document.addEventListener("saved-changed", onSaved);
  load();
  return { destroy() { document.removeEventListener("saved-changed", onSaved); } };
};

// =================================================================== charts

function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}
function niceTicks(max, n = 4) {
  const step = Math.max(1, niceStep(max / n));
  const out = [0];
  while (out[out.length - 1] < max) out.push(out[out.length - 1] + step);
  return out;
}
const roundedTop = (x, y, w, hgt, r) =>
  `M${x},${y + hgt}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + hgt}Z`;

/** Single-series column chart (one hue), recessive grid, hover tooltip, peak label. */
function columnChart(box, data, { tipText, ariaLabel }) {
  function draw() {
    const W = Math.max(280, Math.floor(box.clientWidth));
    const H = 220, m = { t: 20, r: 6, b: 26, l: 38 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const max = Math.max(1, ...data.map((d) => d.count));
    const ticks = niceTicks(max, 4);
    const top = ticks[ticks.length - 1];
    const step = iw / data.length;
    const gap = Math.max(2, step * 0.22);
    const bw = Math.max(1, step - gap);
    const y = (v) => m.t + ih - (v / top) * ih;
    const svg = s("svg", { class: "chart", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": ariaLabel });
    for (const t of ticks) {
      svg.append(s("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), class: t === 0 ? "axis" : "grid" }));
      svg.append(s("text", { x: m.l - 8, y: y(t) + 4, class: "tick", "text-anchor": "end" }, fmtNum(t)));
    }
    const bars = [];
    data.forEach((d, i) => {
      const x = m.l + i * step + gap / 2;
      const bh = (d.count / top) * ih;
      const bar = d.count > 0 ? s("path", { class: "bar", d: roundedTop(x, y(d.count), bw, bh, Math.min(4, bw / 2, bh)) }) : null;
      if (bar) svg.append(bar);
      bars.push(bar);
      if ((data.length - 1 - i) % 7 === 0) {
        svg.append(s("text", { x: x + bw / 2, y: H - 8, class: "tick", "text-anchor": "middle" }, fmtDate(d.date + "T12:00:00")));
      }
    });
    const peak = data.reduce((bi, d, i) => (d.count > data[bi].count ? i : bi), 0);
    if (data[peak]?.count > 0) {
      svg.append(s("text", { x: m.l + peak * step + step / 2, y: y(data[peak].count) - 6, class: "direct-label", "text-anchor": "middle" }, fmtNum(data[peak].count)));
    }
    data.forEach((d, i) => {
      const hit = s("rect", { class: "hit", x: m.l + i * step, y: m.t, width: step, height: ih });
      hit.addEventListener("mousemove", (e) => {
        svg.classList.add("hovering");
        bars.forEach((b, bi) => b?.classList.toggle("active", bi === i));
        showTip(e, tipText(d));
      });
      hit.addEventListener("mouseleave", () => { svg.classList.remove("hovering"); hideTip(); });
      svg.append(hit);
    });
    box.replaceChildren(svg);
  }
  draw();
  let lastW = box.clientWidth;
  const ro = new ResizeObserver(() => { if (Math.abs(box.clientWidth - lastW) > 4) { lastW = box.clientWidth; draw(); } });
  ro.observe(box);
  return () => ro.disconnect();
}

/** Ranked horizontal bars (one hue). Rows are buttons that drill into the job list. */
function barList(rows, { total, onPick, unit = "open jobs" }) {
  if (!rows.length) return h("p", { class: "muted" }, "No data yet.");
  const max = Math.max(1, ...rows.map((r) => r.count));
  return h("div", { class: "barlist", role: "list" }, rows.map((r) => {
    const row = h("button", { class: "bar-row", type: "button", role: "listitem", onclick: () => onPick?.(r), "aria-label": `${r.label || r.name}: ${fmtNum(r.count)} ${unit}` },
      h("span", { class: "bar-label", title: r.label || r.name }, r.label || r.name),
      h("span", { class: "bar-track" }, h("span", { class: "bar-fill", style: { width: `${Math.max(0.5, (r.count / max) * 100)}%` } })),
      h("span", { class: "bar-value" }, fmtNum(r.count)));
    row.addEventListener("mousemove", (e) => showTip(e, [
      h("strong", null, r.label || r.name),
      h("div", null, `${fmtNum(r.count)} ${unit}${total ? ` · ${pct(r.count, total)}% of all` : ""}`),
      onPick ? h("div", { class: "muted" }, "Click to see these jobs") : null,
    ]));
    row.addEventListener("mouseleave", hideTip);
    return row;
  }));
}

// =================================================================== Insights view

VIEWS.insights = function InsightsView(root, params) {
  let company = params.get("company") || "";
  const cleanups = [];
  const companySel = h("select", { class: "input", "aria-label": "Company filter", onchange: (e) => { company = e.target.value; history.replaceState(null, "", `#/insights${company ? "?company=" + encodeURIComponent(company) : ""}`); loadScoped(); } },
    h("option", { value: "" }, "All companies"));
  const kpis = h("div", { class: "kpis" });
  const timelineBox = h("div", { class: "chart-box" });
  const timelineTable = h("div", { class: "table-scroll", hidden: true });
  const skillsBox = h("div");
  const companiesBox = h("div");
  const typesBox = h("div");
  const regionsBox = h("div");
  const rolesBox = h("div");
  const expBox = h("div");
  const locationsBox = h("div");
  const skillsTitle = h("h2", null, "Most requested skills");
  const timelineSub = h("p", { class: "sub" });
  let showTable = false;
  const tableBtn = button("Table", { cls: "ghost sm", icon: "table", onclick: () => { showTable = !showTable; timelineTable.hidden = !showTable; timelineBox.hidden = showTable; tableBtn.replaceChildren(icon(showTable ? "chart" : "table"), showTable ? "Chart" : "Table"); } });

  const card = (title, sub, body, { span, action } = {}) => h("section", { class: "chart-card card" + (span ? " span-2" : "") },
    h("div", { class: "chart-card-head" }, h("div", null, typeof title === "string" ? h("h2", null, title) : title, sub), action), body);

  root.append(
    h("div", { class: "page-head" }, h("div", null, h("h1", null, "Insights"), h("p", null, "What the collected job market looks like right now (open jobs only)."))),
    kpis,
    h("div", { class: "filter-row" }, h("span", { class: "field-label" }, "Company"), companySel, h("span", { class: "help" }, "Applies to posting activity and skills")),
    h("div", { class: "chart-grid" },
      card("Posting activity", timelineSub, [timelineBox, timelineTable], { span: true, action: tableBtn }),
      card(skillsTitle, h("p", { class: "sub" }, "Click a skill to see matching jobs"), skillsBox),
      card("Open jobs by company", h("p", { class: "sub" }, "Click a company to browse its jobs"), companiesBox),
      card("By region", h("p", { class: "sub" }, "Derived from each job's location"), regionsBox),
      card("By role category", h("p", { class: "sub" }, "Derived from each job's title"), rolesBox),
      card("By experience needed", h("p", { class: "sub" }, "Years of experience stated in the posting"), expBox),
      card("Job type", h("p", { class: "sub" }, "As stated by the posting or its title"), typesBox),
      card("Top locations", h("p", { class: "sub" }, "Exact location text from postings"), locationsBox)));

  const kpi = (label, value, sub) => h("div", { class: "kpi card" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value), sub && h("div", { class: "sub" }, sub));

  async function loadGlobal() {
    kpis.replaceChildren(...Array.from({ length: 5 }, () => h("div", { class: "kpi card" }, h("div", { class: "skeleton", style: { height: "14px", width: "50%" } }), h("div", { class: "skeleton", style: { height: "28px", width: "40%", marginTop: "8px" } }))));
    try {
      const [st, f] = await Promise.all([api("/stats"), getFacets(true)]);
      kpis.replaceChildren(
        kpi("Open jobs", fmtNum(st.active_jobs), `${fmtNum(st.total_jobs - st.active_jobs)} closed kept for history`),
        kpi("New in last 24 h", fmtNum(st.new_24h), "First collected in the past day"),
        kpi("Companies", fmtNum(st.companies), `${fmtNum(Object.keys(st.by_source).length)} sources`),
        kpi("Remote", `${pct(st.remote_jobs, st.active_jobs)}%`, `${fmtNum(st.remote_jobs)} jobs`),
        kpi("Salary listed", `${pct(st.with_salary, st.active_jobs)}%`, `${fmtNum(st.with_salary)} jobs`),
        kpi("Last updated", st.data_freshness ? timeAgo(st.data_freshness) : "Never", st.data_freshness ? fmtDate(st.data_freshness, true) : "Run a scrape in Sources"));
      companySel.append(...f.companies.map((c) => h("option", { value: c.name, selected: c.name === company }, c.name)));
      companiesBox.replaceChildren(barList(f.companies.slice(0, 15), { total: st.active_jobs, onPick: (r) => go("jobs", { company: r.name }) }));
      const types = Object.entries(st.by_job_type).map(([name, count]) => ({ name, count, label: name === "Unknown" ? "Not specified" : name })).sort((a, b) => b.count - a.count);
      typesBox.replaceChildren(barList(types, { total: st.active_jobs, onPick: (r) => r.name !== "Unknown" && go("jobs", { job_type: r.name }) }));
      regionsBox.replaceChildren(f.regions.length
        ? barList(f.regions, { total: st.active_jobs, onPick: (r) => go("jobs", { region: r.name }) })
        : h("p", { class: "muted" }, "No jobs with a recognizable location yet."));
      rolesBox.replaceChildren(f.role_categories.length
        ? barList(f.role_categories, { total: st.active_jobs, onPick: (r) => go("jobs", { role_category: r.name }) })
        : h("p", { class: "muted" }, "No jobs with a recognizable role yet."));
      expBox.replaceChildren(f.experience_levels.length
        ? barList(f.experience_levels, { total: st.active_jobs, onPick: (r) => go("jobs", { experience_level: r.name }) })
        : h("p", { class: "muted" }, "No jobs state a years-of-experience range yet."));
      locationsBox.replaceChildren(barList(f.locations.slice(0, 12), { total: st.active_jobs, onPick: (r) => go("jobs", { location: r.name }) }));
      if (!st.active_jobs) {
        kpis.after(banner("info", "info", h("strong", null, "No data yet. "), "Scrape your sources to fill these charts. ", h("a", { href: "#/sources" }, "Go to Sources")));
      }
    } catch (e) {
      kpis.replaceChildren(banner("crit", "xCircle", e.message));
    }
  }

  async function loadScoped() {
    const q = company ? `&company=${encodeURIComponent(company)}` : "";
    skillsTitle.textContent = company ? `Most requested skills at ${company}` : "Most requested skills";
    timelineSub.textContent = `Open jobs by the day they were posted, last 30 days${company ? ` · ${company}` : ""}`;
    try {
      const [timeline, skills] = await Promise.all([api(`/insights/timeline?days=30${q}`), api(`/skills?limit=20${q}`)]);
      cleanups.forEach((fn) => fn()); cleanups.length = 0;
      const sum = timeline.reduce((a, d) => a + d.count, 0);
      if (!sum) timelineBox.replaceChildren(h("p", { class: "muted" }, "No open jobs were posted in the last 30 days."));
      else cleanups.push(columnChart(timelineBox, timeline, {
        ariaLabel: `Jobs posted per day over the last 30 days, ${fmtNum(sum)} in total`,
        tipText: (d) => [h("strong", null, toDate(d.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })), h("div", null, `${plural(d.count, "job")} posted`)],
      }));
      timelineTable.replaceChildren(h("table", { class: "data-table" },
        h("thead", null, h("tr", null, h("th", null, "Date"), h("th", { class: "num" }, "Jobs posted"))),
        h("tbody", null, [...timeline].reverse().map((d) => h("tr", null, h("td", null, fmtDate(d.date + "T12:00:00")), h("td", { class: "num" }, fmtNum(d.count)))))));
      const totalScope = company ? undefined : (await getFacets()).companies.reduce((a, c) => a + c.count, 0);
      skillsBox.replaceChildren(barList(skills, { total: totalScope, onPick: (r) => go("jobs", company ? { skill: r.name, company } : { skill: r.name }) }));
    } catch (e) {
      timelineBox.replaceChildren(banner("crit", "xCircle", e.message));
    }
  }

  loadGlobal();
  loadScoped();
  return { destroy() { cleanups.forEach((fn) => fn()); } };
};

// =================================================================== Sources view

function detectSource(raw) {
  let u;
  const text = (raw || "").trim();
  if (!text) return null;
  try { u = new URL(/^https?:\/\//i.test(text) ? text : "https://" + text); } catch { return null; }
  const host = u.hostname.toLowerCase();
  const parts = u.pathname.split("/").filter(Boolean);
  if (/(^|\.)greenhouse\.io$/.test(host)) {
    const token = u.searchParams.get("for") || (parts[0] === "v1" && parts[1] === "boards" ? parts[2] : parts[0]);
    if (token && token !== "embed") return { type: "greenhouse", options: { board_token: token }, token };
  }
  if (/(^|\.)lever\.co$/.test(host)) {
    const site = parts[0] === "v0" && parts[1] === "postings" ? parts[2] : parts[0];
    if (site) return { type: "lever", options: { site, region: host.includes(".eu.") ? "eu" : "us" }, token: site };
  }
  if (/(^|\.)ashbyhq\.com$/.test(host)) {
    const board = parts[0] === "posting-api" ? parts[2] : parts[0];
    if (board) return { type: "ashby", options: { board }, token: board };
  }
  if (/(^|\.)smartrecruiters\.com$/.test(host)) {
    const cid = parts[0] === "v1" && parts[1] === "companies" ? parts[2] : parts[0];
    if (cid) return { type: "smartrecruiters", options: { company_id: cid, max_jobs: 200 }, token: cid };
  }
  const token = host.replace(/^(www|careers|jobs|join|work)\./, "").split(".")[0];
  return {
    type: "jsonld", token,
    options: { start_urls: [u.href], link_pattern: "/(jobs?|careers?|positions?|openings?|roles?|vacanc(y|ies))/[^/?#]+", max_pages: 50 },
  };
}

function scheduleText(src) {
  return src.cron ? `Cron: ${src.cron}` : humanInterval(src.interval_minutes);
}

VIEWS.sources = function SourcesView(root) {
  let sources = [], types = [], lastKey = null;
  const bannerBox = h("div", { style: { marginBottom: "14px" } });
  const list = h("div", { class: "source-list" });
  root.append(
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, "Sources"), h("p", null, "Company careers sites that jobs are collected from. Changes are saved to config/sources.yaml.")),
      h("div", { class: "actions" },
        button("Scrape all enabled", { icon: "play", onclick: scrapeAll }),
        button("Browse catalog", { icon: "layers", onclick: () => openCatalogBrowser(load) }),
        button("Add source", { cls: "primary", icon: "plus", onclick: () => openSourceEditor(null, { onSaved: load }) }))),
    bannerBox, list);

  function renderBanner(st) {
    if (!st) return;
    bannerBox.replaceChildren(st.scheduler.running
      ? banner("good", "clock", h("strong", null, "Automatic scraping is on. "), "Each enabled source runs on its schedule while this server is running.")
      : banner("info", "clock", h("strong", null, "Automatic scraping is off in this server. "),
        "Restart with ", h("code", null, "python -m jd_collector serve --with-scheduler"), " to scrape on schedule (or run ",
        h("code", null, "python -m jd_collector schedule"), " separately). You can always scrape manually here."));
  }

  async function load() {
    if (!sources.length) list.replaceChildren(...Array.from({ length: 4 }, () => h("div", { class: "source-row card" }, h("div", { class: "skeleton", style: { height: "34px", gridColumn: "1 / -1" } }))));
    try {
      [sources, types] = await Promise.all([api("/sources"), getSourceTypes()]);
      render();
    } catch (e) {
      list.replaceChildren(banner("crit", "xCircle", e.message));
    }
  }

  function lastRunCell(src) {
    const last = src.last_run;
    if (src.running) return [h("span", { class: "k" }, "Last run"), h("span", { class: "status info" }, h("span", { class: "spinner" }), "Running now…")];
    if (!last) return [h("span", { class: "k" }, "Last run"), h("span", { class: "s" }, "Never run")];
    const when = timeAgo(last.finished_at || last.started_at);
    let detail;
    if (last.status === "success") detail = `${fmtNum(last.fetched)} found · ${fmtNum(last.new)} new · ${fmtNum(last.updated)} updated · ${fmtNum(last.deactivated)} closed`;
    else detail = friendlyError(last.error) || last.error || "";
    return [h("span", { class: "k" }, "Last run"),
      h("span", { class: "v" }, statusBadge(last.status), h("span", { class: "s" }, ` · ${when}`)),
      h("div", { class: "s", title: last.error || "" }, detail.length > 140 ? detail.slice(0, 138) + "…" : detail)];
  }

  function render() {
    if (!sources.length) {
      list.replaceChildren(emptyState("database", "No sources yet", "Add a company by pasting its careers page URL, or pick from the curated catalog.", [
        button("Browse catalog", { cls: "primary", icon: "layers", onclick: () => openCatalogBrowser(load) }),
        button("Add source", { icon: "plus", onclick: () => openSourceEditor(null, { onSaved: load }) }),
      ]));
      return;
    }
    list.replaceChildren(...sources.map((src) => {
      const t = types.find((x) => x.type === src.type);
      const toggle = h("label", { class: "switch", title: src.enabled ? "Enabled - click to disable" : "Disabled - click to enable" },
        h("input", { type: "checkbox", checked: src.enabled, "aria-label": `${src.enabled ? "Disable" : "Enable"} ${src.name}`, onchange: (e) => setEnabled(src, e.target.checked, e.target) }), h("span"));
      return h("div", { class: "source-row card" + (src.enabled ? "" : " disabled") },
        h("div", { class: "src-main" },
          h("div", { class: "src-name" }, src.company),
          h("div", { class: "src-sub" }, h("code", null, src.name), h("span", { class: "badge" }, t?.label || src.type), !src.enabled && h("span", { class: "badge closed" }, "Disabled"))),
        h("div", { class: "src-col" }, h("span", { class: "k" }, "Schedule"), h("div", { class: "v" }, scheduleText(src)),
          h("div", { class: "s" }, src.enabled ? (src.next_run ? `Next run ${timeAgo(src.next_run)}` : "") : "Not scheduled")),
        h("div", { class: "src-col" }, h("span", { class: "k" }, "Open jobs"),
          src.active_jobs ? h("a", { href: `#/jobs?source=${encodeURIComponent(src.name)}` }, fmtNum(src.active_jobs)) : h("span", { class: "s" }, "0")),
        h("div", { class: "src-col" }, lastRunCell(src)),
        h("div", { class: "src-actions" }, toggle,
          button(src.running ? "Running…" : "Scrape now", { cls: "sm", icon: src.running ? null : "play", disabled: src.running, onclick: () => scrapeOne(src) }),
          iconButton("edit", `Edit ${src.name}`, () => openSourceEditor(src, { onSaved: load })),
          iconButton("trash", `Delete ${src.name}`, () => removeSource(src))));
    }));
  }

  async function scrapeOne(src) {
    try {
      const r = await api(`/scrape?source=${encodeURIComponent(src.name)}`, { method: "POST" });
      if (r.queued.length) { toast(`Scraping ${src.company}…`, { text: "You'll get a notification when it finishes.", timeout: 3000 }); src.running = true; render(); }
      else toast(`${src.name} is already running`, { kind: "warn" });
      pollSoon();
    } catch (e) { toast("Couldn't start scrape", { kind: "crit", text: e.message }); }
  }

  async function setEnabled(src, enabled, input) {
    try {
      await api(`/sources/${encodeURIComponent(src.name)}`, { method: "PUT", body: { ...sourceBody(src), enabled } });
      toast(`${src.company} ${enabled ? "enabled" : "disabled"}`, { kind: "good", timeout: 2000 });
      load();
    } catch (e) { input.checked = !enabled; toast("Couldn't update source", { kind: "crit", text: e.message }); }
  }

  async function removeSource(src) {
    const purge = h("input", { type: "checkbox" });
    const ok = await confirmDialog({
      title: `Delete ${src.company}?`, danger: true, confirmLabel: "Delete source",
      message: `This removes "${src.name}" from config/sources.yaml so it is no longer scraped.`,
      extra: src.active_jobs ? h("label", { class: "check" }, purge, `Also delete its ${plural(src.active_jobs, "collected job")}`) : null,
    });
    if (!ok) return;
    try {
      const r = await api(`/sources/${encodeURIComponent(src.name)}?delete_jobs=${purge.checked}`, { method: "DELETE" });
      toast(`Deleted ${src.name}`, { kind: "good", text: r.jobs_deleted ? `${plural(r.jobs_deleted, "job")} removed` : undefined });
      facetsCache.at = 0;
      load();
    } catch (e) { toast("Couldn't delete", { kind: "crit", text: e.message }); }
  }

  load();
  return {
    onStatus(st) {
      renderBanner(st);
      const key = st.running.join(",");
      if (lastKey !== null && key !== lastKey) load();
      lastKey = key;
    },
  };
};

const sourceBody = (src) => ({
  name: src.name, type: src.type, company: src.company, enabled: src.enabled,
  interval_minutes: src.interval_minutes, cron: src.cron, rate_limit_seconds: src.rate_limit_seconds, options: src.options || {},
});

const INTERVALS = [[60, "Every hour"], [180, "Every 3 hours"], [360, "Every 6 hours"], [720, "Every 12 hours"], [1440, "Daily"], [2880, "Every 2 days"], [10080, "Weekly"]];

async function openSourceEditor(existing, { onSaved } = {}) {
  let types;
  try { types = await getSourceTypes(); } catch (e) { toast("Couldn't load source types", { kind: "crit", text: e.message }); return; }
  const isEdit = !!existing;
  const src = existing ? sourceBody(existing) : { name: "", type: "greenhouse", company: "", enabled: true, interval_minutes: 360, cron: null, rate_limit_seconds: 1, options: {} };
  let nameTouched = isEdit;

  // ---- quick add from URL
  const urlInput = h("input", { class: "input", type: "url", placeholder: "https://boards.greenhouse.io/yourcompany", "aria-label": "Careers page URL",
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); detect(); } } });
  const quick = isEdit ? null : h("div", { class: "quick-add" },
    h("label", null, "Paste a careers page URL"),
    h("div", { class: "row" }, urlInput, button("Detect", { cls: "primary", icon: "search", onclick: detect })),
    h("p", { class: "help" }, "Recognises Greenhouse, Lever, Ashby and SmartRecruiters boards. Other sites are read through their structured job data (JSON-LD)."));

  // ---- form controls
  const companyIn = h("input", { class: "input", value: src.company, placeholder: "e.g. Stripe", oninput: () => { if (!nameTouched) nameIn.value = slugify(companyIn.value); } });
  const nameIn = h("input", { class: "input mono", value: src.name, placeholder: "e.g. stripe", oninput: () => { nameTouched = true; } });
  const typeSel = h("select", { class: "input", onchange: () => renderFields({}) }, types.map((t) => h("option", { value: t.type, selected: t.type === src.type }, t.label)));
  const typeHelp = h("p", { class: "help" });
  const fieldsBox = h("div", { class: "form-grid" });
  let inputs = {};

  function fieldInput(f, value) {
    const v = value ?? f.default;
    if (f.kind === "bool") return h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!v }), f.label);
    if (f.kind === "select") return h("select", { class: "input" }, f.choices.map((c) => h("option", { value: c, selected: c === v }, c)));
    if (f.kind === "urls") return h("textarea", { class: "input mono", rows: "3", value: Array.isArray(v) ? v.join("\n") : v || "", placeholder: "https://…" });
    return h("input", {
      class: "input" + (["selector", "regex", "url"].includes(f.kind) ? " mono" : ""), type: f.kind === "number" ? "number" : "text",
      min: f.kind === "number" ? "0" : null, value: v ?? "", placeholder: f.default != null ? String(f.default) : "",
    });
  }
  function renderFields(values) {
    const t = types.find((x) => x.type === typeSel.value);
    typeHelp.textContent = t?.description || "";
    inputs = {};
    fieldsBox.replaceChildren(...(t?.fields || []).map((f) => {
      const input = fieldInput(f, values[f.key]);
      inputs[f.key] = { f, input };
      const wide = ["urls", "url", "regex"].includes(f.kind) || (t.fields.length === 1);
      if (f.kind === "bool") return h("div", { class: "field" + (wide ? " full" : "") }, input, f.help && h("p", { class: "help" }, f.help));
      return h("div", { class: "field" + (wide ? " full" : "") }, h("label", null, f.label, f.required ? " *" : ""), input, f.help && h("p", { class: "help" }, f.help));
    }));
  }

  // ---- schedule
  let mode = src.cron ? "cron" : "interval";
  const intervals = [...INTERVALS];
  if (!intervals.some(([m]) => m === src.interval_minutes)) intervals.push([src.interval_minutes, humanInterval(src.interval_minutes)]);
  const intervalSel = h("select", { class: "input" }, intervals.map(([m, l]) => h("option", { value: m, selected: m === src.interval_minutes }, l)));
  const cronIn = h("input", { class: "input mono", value: src.cron || "", placeholder: "0 */6 * * *  (UTC)" });
  const schedWrap = h("div");
  const renderSched = () => schedWrap.replaceChildren(mode === "cron"
    ? h("div", { class: "field" }, cronIn, h("p", { class: "help" }, "minute hour day month weekday, in UTC. Example: 30 7 * * 1-5 = weekdays at 07:30."))
    : intervalSel);
  const radio = (val, label) => h("label", { class: "check" }, h("input", { type: "radio", name: "sched-mode", checked: mode === val, onchange: () => { mode = val; renderSched(); } }), label);
  renderSched();

  const rateIn = h("input", { class: "input", type: "number", min: "0.2", step: "0.1", value: src.rate_limit_seconds });
  const enabledIn = h("input", { type: "checkbox", checked: src.enabled });
  const errorsBox = h("div");
  const previewBox = h("div");

  function collect() {
    const options = {};
    for (const [key, { f, input }] of Object.entries(inputs)) {
      options[key] = f.kind === "bool" ? input.querySelector("input").checked : input.value;
    }
    return {
      name: nameIn.value.trim(), type: typeSel.value, company: companyIn.value.trim(), enabled: enabledIn.checked,
      interval_minutes: Number(intervalSel.value), cron: mode === "cron" ? cronIn.value.trim() || null : null,
      rate_limit_seconds: Number(rateIn.value) || 1, options,
    };
  }

  function showErrors(e) {
    const msgs = e.details?.length ? e.details : [e.message];
    errorsBox.replaceChildren(banner("crit", "xCircle", h("strong", null, msgs.length > 1 ? "Please fix these:" : "Please fix this:"), h("ul", null, msgs.map((m) => h("li", null, m)))));
  }

  function detect() {
    const d = detectSource(urlInput.value);
    if (!d) { errorsBox.replaceChildren(banner("warn", "alert", "That doesn't look like a URL.")); return; }
    errorsBox.replaceChildren();
    typeSel.value = d.type;
    renderFields(d.options);
    if (!companyIn.value) companyIn.value = titleCase(d.token);
    if (!nameTouched) nameIn.value = slugify(companyIn.value || d.token);
    const t = types.find((x) => x.type === d.type);
    previewBox.replaceChildren(banner("info", "info", h("strong", null, `Detected: ${t?.label || d.type}. `), "Check the company name, then test it."));
    test();
  }

  let testing = false;
  async function test() {
    if (testing) return;
    testing = true;
    errorsBox.replaceChildren();
    previewBox.replaceChildren(banner("info", "refresh", h("strong", null, "Testing… "), "Fetching a sample from the site. Nothing is saved yet."));
    const body = collect();
    body.name = body.name || "preview";
    try {
      const r = await api("/sources/preview", { method: "POST", body });
      renderPreview(r);
    } catch (e) {
      previewBox.replaceChildren();
      showErrors(e);
    } finally { testing = false; }
  }

  function renderPreview(r) {
    if (r.error) {
      previewBox.replaceChildren(banner("crit", "xCircle", h("strong", null, "Test failed. "), friendlyError(r.error) || "", h("div", { class: "mono", style: { fontSize: "12px", marginTop: "4px" } }, r.error)));
      return;
    }
    if (!r.valid) {
      previewBox.replaceChildren(banner("warn", "alert", h("strong", null, "No usable jobs found. "),
        r.scanned ? `${plural(r.scanned, "item")} found but none passed validation.` : "The page returned no jobs - check the settings (board name, URL or selectors).",
        r.issues.length ? h("ul", null, r.issues.map((i) => h("li", null, `${i.issue} (${i.count})`))) : null));
      return;
    }
    const summary = r.complete
      ? `Found ${plural(r.valid, "job")}${r.invalid ? `, ${fmtNum(r.invalid)} skipped as incomplete` : ""}.`
      : `Checked the first ${plural(r.scanned, "job")}: ${fmtNum(r.valid)} look good. The full scrape collects the rest.`;
    previewBox.replaceChildren(
      banner("good", "checkCircle", h("strong", null, "It works. "), summary, ` (${r.duration_seconds}s)`),
      h("div", { class: "preview-list" }, r.samples.map((j) => h("div", { class: "preview-item" },
        h("strong", null, j.title),
        h("div", { class: "sub" }, [j.company, j.location, j.is_remote ? "Remote" : null, j.job_type, j.salary].filter(Boolean).join(" · ")),
        j.skills.length ? h("div", { class: "chips", style: { marginTop: "6px" } }, j.skills.slice(0, 6).map((sk) => h("span", { class: "chip" }, sk))) : null))));
  }

  async function save(scrapeAfter) {
    errorsBox.replaceChildren();
    const body = collect();
    try {
      if (isEdit) await api(`/sources/${encodeURIComponent(existing.name)}`, { method: "PUT", body });
      else await api("/sources", { method: "POST", body });
      modal.close();
      toast(isEdit ? `Saved ${body.company}` : `Added ${body.company}`, { kind: "good", timeout: 2500 });
      if (scrapeAfter) {
        await api(`/scrape?source=${encodeURIComponent(slugify(body.name))}`, { method: "POST" });
        toast(`Scraping ${body.company}…`, { text: "You'll get a notification when it finishes.", timeout: 3000 });
        pollSoon();
      }
      onSaved?.();
    } catch (e) { showErrors(e); }
  }

  renderFields(src.options);
  const modal = openModal({
    title: isEdit ? `Edit ${existing.company}` : "Add source",
    wide: true,
    body: [
      quick,
      h("div", { class: "form-grid" },
        h("div", { class: "field" }, h("label", null, "Company *"), companyIn),
        h("div", { class: "field" }, h("label", null, "Source ID *"), nameIn, h("p", { class: "help" }, "Short unique name: lowercase letters, digits, - or _")),
        h("div", { class: "field full" }, h("label", null, "Site type *"), typeSel, typeHelp)),
      fieldsBox,
      h("div", { class: "field" }, h("span", { class: "field-label" }, "Schedule"), h("div", { class: "radio-row" }, radio("interval", "Repeat every"), radio("cron", "Cron expression")), schedWrap),
      h("details", { class: "advanced" }, h("summary", null, "Advanced"),
        h("div", { class: "form-grid" },
          h("div", { class: "field" }, h("label", null, "Seconds between requests"), rateIn, h("p", { class: "help" }, "Higher is gentler on the site. Minimum 0.2.")),
          h("div", { class: "field" }, h("span", { class: "field-label" }, "Status"), h("label", { class: "check" }, enabledIn, "Enabled (scraped on schedule and by “Scrape all”)")))),
      errorsBox, previewBox,
    ],
    footer: (close) => [
      button("Test source", { cls: "left", icon: "refresh", onclick: test }),
      button("Cancel", { onclick: close }),
      button("Save", { onclick: () => save(false) }),
      button(isEdit ? "Save & scrape now" : "Add & scrape now", { cls: "primary", icon: "play", onclick: () => save(true) }),
    ],
  });
  if (!isEdit) urlInput.focus();
}

// =================================================================== Catalog browser

async function openCatalogBrowser(onAdded) {
  let entries, meta;
  try {
    [entries, meta] = await Promise.all([api("/catalog"), api("/catalog/regions")]);
  } catch (e) {
    toast("Couldn't load the catalog", { kind: "crit", text: e.message });
    return;
  }
  if (!entries.length) {
    toast("Catalog is empty", { kind: "warn", text: "config/catalog.yaml has no entries." });
    return;
  }

  let region = "", query = "";
  const selected = new Set();

  const regionTabs = h("div", { class: "seg", role: "radiogroup", "aria-label": "Region" });
  const renderTabs = () => regionTabs.replaceChildren(
    ...[["", `All regions (${entries.length})`], ...meta.regions.map((r) => [r, r])].map(([v, label]) =>
      h("button", { type: "button", class: v === region ? "on" : "", role: "radio", "aria-checked": String(v === region),
        onclick: () => { region = v; renderTabs(); renderList(); } }, label)));

  const searchInput = h("input", {
    class: "input", type: "search", placeholder: "Search company or industry…", "aria-label": "Search catalog",
    oninput: debounce((e) => { query = e.target.value.trim().toLowerCase(); renderList(); }, 200),
  });
  const countLabel = h("span", { class: "help" });
  const listBox = h("div", { class: "catalog-list" });

  const visible = () => entries.filter((e) =>
    (!region || e.region === region) &&
    (!query || e.company.toLowerCase().includes(query) || e.industry.toLowerCase().includes(query) || e.name.includes(query)));

  function renderList() {
    const rows = visible();
    countLabel.textContent = `Showing ${rows.length} of ${entries.length}`;
    if (!rows.length) {
      listBox.replaceChildren(h("p", { class: "muted", style: { padding: "16px 4px" } }, "No matches - try a different search or region."));
      return;
    }
    listBox.replaceChildren(...rows.map((e) => {
      const id = "cat-" + e.name;
      return h("label", { class: "catalog-row" + (e.already_added ? " added" : ""), for: id },
        h("input", {
          type: "checkbox", id, disabled: e.already_added, checked: e.already_added || selected.has(e.name),
          onchange: (ev) => { ev.target.checked ? selected.add(e.name) : selected.delete(e.name); updateFooter(); },
        }),
        h("div", { class: "catalog-row-main" },
          h("span", { class: "catalog-row-name" }, e.company),
          h("span", { class: "catalog-row-sub" }, e.industry, " · ", e.region)),
        h("span", { class: "badge" }, e.type),
        e.already_added ? h("span", { class: "badge closed" }, "Already added") : null);
    }));
  }

  function updateFooter() {
    const n = selected.size;
    addBtn.disabled = addScrapeBtn.disabled = n === 0;
    addBtn.replaceChildren(n ? `Add ${plural(n, "source")}` : "Add selected");
    addScrapeBtn.replaceChildren(icon("play"), n ? `Add & scrape ${n}` : "Add & scrape");
  }

  async function doAdd(scrapeAfter) {
    const names = [...selected];
    if (!names.length) return;
    try {
      const r = await api("/catalog/add", { method: "POST", body: { names } });
      modal.close();
      if (r.added.length) {
        toast(`Added ${plural(r.added.length, "source")}`, {
          kind: "good", text: r.skipped.length ? `${plural(r.skipped.length, "source")} already existed, skipped` : undefined,
        });
      } else {
        toast("Nothing added", { kind: "warn", text: "Those sources already exist." });
      }
      if (scrapeAfter && r.added.length) {
        await api(`/scrape?${r.added.map((n) => `source=${encodeURIComponent(n)}`).join("&")}`, { method: "POST" });
        toast(`Scraping ${plural(r.added.length, "new source")}…`, { text: "You'll get a notification as each finishes.", timeout: 3500 });
        pollSoon();
      }
      onAdded?.();
    } catch (e) {
      toast("Couldn't add sources", { kind: "crit", text: e.message });
    }
  }

  const addBtn = button("Add selected", { onclick: () => doAdd(false) });
  const addScrapeBtn = button("Add & scrape", { cls: "primary", icon: "play", onclick: () => doAdd(true) });
  renderTabs();
  renderList();
  updateFooter();

  const modal = openModal({
    title: "Browse catalog", wide: true,
    body: [
      h("p", { class: "help", style: { margin: "0 0 2px" } },
        `${entries.length} companies, live-verified and ready to scrape. Pick as many as you like.`),
      regionTabs, searchInput, countLabel, listBox,
    ],
    footer: (close) => [button("Cancel", { onclick: close }), addBtn, addScrapeBtn],
  });
}

// =================================================================== Runs view

VIEWS.runs = function RunsView(root, params) {
  let source = params.get("source") || "", status = params.get("status") || "";
  let lastSig = null;
  const expanded = new Set();
  const sourceSel = h("select", { class: "input", "aria-label": "Source", onchange: (e) => { source = e.target.value; sync(); load(); } }, h("option", { value: "" }, "All sources"));
  const statusSel = h("select", { class: "input", "aria-label": "Status", onchange: (e) => { status = e.target.value; sync(); load(); } },
    [["", "Any status"], ["running", "Running"], ["success", "Success"], ["failed", "Failed"], ["skipped", "Skipped"]].map(([v, l]) => h("option", { value: v, selected: v === status }, l)));
  const summary = h("div", { class: "run-summary" });
  const tableWrap = h("div", { class: "card table-card" });
  const sync = () => {
    const p = new URLSearchParams();
    if (source) p.set("source", source);
    if (status) p.set("status", status);
    history.replaceState(null, "", `#/runs${p.toString() ? "?" + p : ""}`);
  };

  root.append(
    h("div", { class: "page-head" },
      h("div", null, h("h1", null, "Scrape runs"), h("p", null, "Every scrape: what it found, what changed, and any errors.")),
      h("div", { class: "actions" }, button("Refresh", { icon: "refresh", onclick: () => load() }), button("Scrape all enabled", { cls: "primary", icon: "play", onclick: scrapeAll }))),
    summary,
    h("div", { class: "filter-row" }, sourceSel, statusSel),
    tableWrap);

  api("/sources").then((srcs) => sourceSel.append(...srcs.map((x) => h("option", { value: x.name, selected: x.name === source }, x.name)))).catch(() => {});

  async function load() {
    const p = new URLSearchParams({ limit: "200" });
    if (source) p.set("source", source);
    if (status) p.set("status", status);
    try {
      const runs = await api("/runs?" + p);
      renderSummary(runs);
      renderTable(runs);
    } catch (e) {
      tableWrap.replaceChildren(h("div", { style: { padding: "14px" } }, banner("crit", "xCircle", e.message)));
    }
  }

  function renderSummary(runs) {
    const day = runs.filter((r) => isRecent(r.started_at, 1));
    const count = (st) => day.filter((r) => r.status === st).length;
    const tile = (label, value, sub) => h("div", { class: "kpi card" }, h("div", { class: "label" }, label), h("div", { class: "value" }, value), sub && h("div", { class: "sub" }, sub));
    summary.replaceChildren(
      tile("Runs, last 24 h", fmtNum(day.length)),
      tile("Succeeded", fmtNum(count("success"))),
      tile("Failed", fmtNum(count("failed")), count("failed") ? "See errors below" : "No errors"),
      tile("New jobs, last 24 h", fmtNum(day.reduce((a, r) => a + r.new, 0))),
      tile("Closed jobs, last 24 h", fmtNum(day.reduce((a, r) => a + r.deactivated, 0))));
  }

  function renderTable(runs) {
    if (!runs.length) {
      tableWrap.replaceChildren(emptyState("activity", "No runs yet", source || status ? "No runs match these filters." : "Start a scrape to see it here.",
        [button("Scrape all enabled", { cls: "primary", icon: "play", onclick: scrapeAll })]));
      return;
    }
    const num = (v) => h("td", { class: "num" + (v ? "" : " zero") }, fmtNum(v));
    const rows = [];
    for (const r of runs) {
      rows.push(h("tr", null,
        h("td", null, statusBadge(r.status)),
        h("td", null, h("a", { href: `#/runs?source=${encodeURIComponent(r.source)}`, onclick: (e) => { e.preventDefault(); source = r.source; sourceSel.value = r.source; sync(); load(); } }, r.source)),
        h("td", { title: fmtDate(r.started_at, true) }, timeAgo(r.started_at)),
        h("td", { class: "num" }, r.status === "running" ? "…" : fmtDuration(r.duration_seconds)),
        num(r.fetched), num(r.new), num(r.updated), num(r.unchanged), num(r.invalid), num(r.deactivated)));
      if (r.error && r.status !== "skipped") {
        const friendly = friendlyError(r.error);
        const long = r.error.length > 220;
        const open = expanded.has(r.id);
        rows.push(h("tr", { class: "err" }, h("td", { colspan: "10" }, h("div", { class: "errbox" }, icon("alert", 14),
          h("div", null, friendly && h("div", { style: { fontFamily: "var(--font)", fontWeight: 600, marginBottom: "2px" } }, friendly),
            open || !long ? r.error : r.error.slice(0, 220) + "…",
            long && h("button", { class: "btn ghost sm", type: "button", style: { marginLeft: "6px" }, onclick: () => { open ? expanded.delete(r.id) : expanded.add(r.id); renderTable(runs); } }, open ? "Show less" : "Show all"))))));
      }
    }
    tableWrap.replaceChildren(h("table", { class: "runs-table" },
      h("thead", null, h("tr", null, h("th", null, "Status"), h("th", null, "Source"), h("th", null, "Started"), h("th", { class: "num" }, "Duration"),
        h("th", { class: "num", title: "Postings returned by the site" }, "Found"), h("th", { class: "num" }, "New"), h("th", { class: "num" }, "Updated"),
        h("th", { class: "num" }, "Unchanged"), h("th", { class: "num", title: "Discarded by validation (e.g. missing title or link)" }, "Rejected"),
        h("th", { class: "num", title: "Jobs no longer listed, marked closed" }, "Closed"))),
      h("tbody", null, rows)));
  }

  load();
  return {
    onStatus(st) {
      const sig = `${st.running.join(",")}|${st.latest_run_id}`;
      if (lastSig !== null && (sig !== lastSig || st.running.length)) load();
      lastSig = sig;
    },
  };
};

// =================================================================== boot

function boot() {
  $("#brand-icon").append(icon("briefcase", 18, { "stroke-width": 2.2 }));
  $("#settings-btn").append(icon("sliders", 18));
  $("#settings-btn").addEventListener("click", () => openSettings());
  $("#theme-btn").addEventListener("click", cycleTheme);
  applyTheme(store.get("theme", "system"));
  window.addEventListener("hashchange", route);
  window.addEventListener("scroll", hideTip, { passive: true });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  route();
  poll();
}

boot();
