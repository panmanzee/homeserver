PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f6f4ef" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141311" media="(prefers-color-scheme: dark)">
<title>Tasks</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f6f4ef; --surface: #fffefb; --ink: #201e1a; --muted: #7a756b; --line: #e8e3d9;
    --accent: #2f6f5e; --accent-ink: #ffffff; --accent-soft: #e2eee9;
    --warn: #b3541b; --warn-soft: #f7e8dd; --danger: #b4372e;
    --shadow: 0 1px 2px rgba(32,30,26,.06), 0 8px 24px rgba(32,30,26,.06);
    --radius: 14px;
    --font: "Avenir Next", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", system-ui, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #141311; --surface: #1d1c19; --ink: #ece8df; --muted: #9a947f; --line: #2d2b26;
      --accent: #62b79c; --accent-ink: #0f1a16; --accent-soft: #1f2f29;
      --warn: #e58f58; --warn-soft: #35261b; --danger: #ef7a6f;
      --shadow: 0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
    }
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { scroll-padding-bottom: 180px; }
  body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.45 var(--font);
         -webkit-font-smoothing: antialiased; }
  button { font: inherit; color: inherit; }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 8px; }
  .app { max-width: 640px; margin: 0 auto; padding: 0 16px 190px; }

  /* ---------- header ---------- */
  .top { padding: max(18px, env(safe-area-inset-top)) 0 6px; position: sticky; top: 0; z-index: 10;
         background: linear-gradient(var(--bg) 82%, transparent); }
  .title-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; }
  h1 { margin: 0; font-size: 32px; line-height: 1.1; letter-spacing: -.025em; font-weight: 700; }
  .sub { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
  .nav { display: flex; gap: 6px; }
  .icon-btn { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 12px;
              border: 1px solid var(--line); background: var(--surface); cursor: pointer; color: var(--ink); }
  .icon-btn:hover { border-color: var(--muted); }
  .icon-btn:active { transform: scale(.95); }
  .icon-btn svg { width: 18px; height: 18px; }
  .text-btn { height: 40px; padding: 0 14px; border-radius: 12px; border: 1px solid var(--line);
              background: var(--surface); cursor: pointer; font-size: 14px; font-weight: 600; }
  .text-btn[hidden] { display: none; }

  .progress { margin-top: 14px; }
  .progress[hidden] { display: none; }
  .bar { height: 6px; border-radius: 99px; background: var(--line); overflow: hidden; }
  .bar > i { display: block; height: 100%; width: 0; background: var(--accent); border-radius: 99px;
             transition: width .45s cubic-bezier(.2,.8,.2,1); }
  .progress p { margin: 7px 0 0; font-size: 13px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .progress b { color: var(--ink); font-weight: 600; }

  .week { display: flex; gap: 6px; margin-top: 12px; }
  .day { flex: 1; min-width: 0; padding: 7px 0 8px; border-radius: 12px; border: 1px solid transparent;
         background: transparent; cursor: pointer; display: grid; gap: 1px; justify-items: center; }
  .day small { font-size: 11px; color: var(--muted); letter-spacing: .03em; text-transform: uppercase; }
  .day span { font-size: 17px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .day:hover { background: var(--surface); }
  .day[aria-current="date"] small::after { content: ""; display: inline-block; width: 4px; height: 4px; border-radius: 50%;
                                          background: var(--accent); margin-left: 4px; vertical-align: middle; }
  .day[aria-selected="true"] { background: var(--ink); color: var(--bg); }
  .day[aria-selected="true"] small { color: inherit; opacity: .7; }

  /* ---------- sections + rows ---------- */
  main { margin-top: 10px; }
  .sec { margin-top: 22px; }
  .sec-head { display: flex; align-items: baseline; gap: 8px; margin: 0 2px 8px; }
  .sec-head h2 { margin: 0; font-size: 12px; letter-spacing: .09em; text-transform: uppercase; font-weight: 700; color: var(--muted); }
  .sec-head .n { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .sec-head .hint { margin-left: auto; font-size: 12px; color: var(--muted); }
  .sec.late h2, .sec.late .n { color: var(--warn); }
  ul.list { list-style: none; margin: 0; padding: 0; background: var(--surface); border: 1px solid var(--line);
            border-radius: var(--radius); overflow: hidden; }
  .row { display: flex; align-items: center; gap: 4px; min-height: 56px; padding: 4px 6px 4px 4px;
         border-top: 1px solid var(--line); transition: opacity .2s, transform .2s; }
  .row:first-child { border-top: 0; }
  .row.leaving { opacity: 0; transform: translateX(14px); }
  .tick { width: 44px; height: 44px; flex: none; border: 0; background: transparent; cursor: pointer; display: grid; place-items: center; }
  .tick i { width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--muted); display: grid; place-items: center;
            transition: background .15s, border-color .15s, transform .15s; }
  .tick:hover i { border-color: var(--accent); }
  .tick:active i { transform: scale(.88); }
  .tick svg { width: 14px; height: 14px; stroke: var(--accent-ink); stroke-width: 3; fill: none; stroke-linecap: round; stroke-linejoin: round;
              stroke-dasharray: 20; stroke-dashoffset: 20; transition: stroke-dashoffset .25s ease .05s; }
  .tick[aria-checked="true"] i { background: var(--accent); border-color: var(--accent); }
  .tick[aria-checked="true"] svg { stroke-dashoffset: 0; }
  .body { flex: 1; min-width: 0; padding: 6px 4px; }
  .t { display: block; width: 100%; text-align: left; border: 0; background: none; padding: 0; cursor: text;
       overflow-wrap: anywhere; font-size: 16px; line-height: 1.35; }
  .row.done .t { color: var(--muted); text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--muted) 60%, transparent); cursor: default; }
  .edit { width: 100%; font: inherit; color: inherit; background: var(--bg); border: 1px solid var(--accent); border-radius: 8px; padding: 6px 8px; }
  .meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 3px; }
  .meta:empty { display: none; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; line-height: 1; padding: 4px 7px; border-radius: 99px;
          background: var(--bg); color: var(--muted); font-variant-numeric: tabular-nums; }
  .chip.late { background: var(--warn-soft); color: var(--warn); font-weight: 600; }
  .chip.time { color: var(--ink); font-weight: 600; }
  .chip.cal { color: var(--accent); background: var(--accent-soft); }
  .chip svg { width: 11px; height: 11px; }
  .more { width: 40px; height: 40px; flex: none; border: 0; background: transparent; border-radius: 10px; cursor: pointer; color: var(--muted); display: grid; place-items: center; }
  .more:hover { background: var(--bg); color: var(--ink); }
  .more svg { width: 18px; height: 18px; }

  details.done-sec { margin-top: 22px; }
  details.done-sec > summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 8px; margin: 0 2px 8px; color: var(--muted); }
  details.done-sec > summary::-webkit-details-marker { display: none; }
  details.done-sec > summary h2 { margin: 0; font-size: 12px; letter-spacing: .09em; text-transform: uppercase; font-weight: 700; }
  details.done-sec > summary svg { width: 14px; height: 14px; transition: transform .2s; }
  details.done-sec[open] > summary svg { transform: rotate(90deg); }

  .empty { text-align: center; padding: 56px 20px 24px; color: var(--muted); }
  .empty h3 { margin: 0 0 6px; color: var(--ink); font-size: 18px; letter-spacing: -.01em; }
  .empty p { margin: 0; font-size: 14px; }
  .soft { color: var(--muted); font-size: 14px; padding: 4px 2px 0; }
  .skel { height: 56px; border-top: 1px solid var(--line); background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--muted) 12%, transparent), transparent);
          background-size: 200% 100%; animation: shimmer 1.3s infinite; }
  .skel:first-child { border-top: 0; }
  @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
  .err { margin-top: 40px; text-align: center; color: var(--muted); }
  .err button { margin-top: 10px; }

  /* ---------- composer ---------- */
  .composer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; padding: 10px 16px max(12px, env(safe-area-inset-bottom));
              background: color-mix(in srgb, var(--bg) 92%, transparent); border-top: 1px solid var(--line);
              backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); }
  .composer-in { max-width: 608px; margin: 0 auto; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
  .chips { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; min-width: 0; padding: 1px 0; }
  .chips::-webkit-scrollbar { display: none; }
  .chips[hidden] { display: none; }
  .wchip { flex: none; border: 1px solid var(--line); background: var(--surface); border-radius: 99px; padding: 6px 12px; font-size: 13px; cursor: pointer; position: relative; white-space: nowrap; }
  .wchip[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); font-weight: 600; }
  .wchip input { position: absolute; inset: 0; opacity: 0; width: 100%; cursor: pointer; }
  .field { display: flex; gap: 8px; }
  .ask { flex: none; height: 48px; padding: 0 13px; border-radius: 12px; border: 1px solid var(--line); background: var(--surface);
         font-size: 14px; font-weight: 600; color: var(--muted); cursor: pointer; }
  .ask[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
  .field { min-width: 0; }
  .field input { flex: 1; min-width: 0; width: 0; height: 48px; padding: 0 14px; border-radius: 12px; border: 1px solid var(--line); background: var(--surface);
                 color: var(--ink); font: inherit; }
  .field input::placeholder { color: var(--muted); }
  .field input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .go { height: 48px; padding: 0 20px; border: 0; border-radius: 12px; background: var(--accent); color: var(--accent-ink); font-weight: 700; cursor: pointer; }
  .go:disabled { opacity: .5; cursor: default; }
  .go:active { transform: scale(.97); }

  /* ---------- toast + menu ---------- */
  .toast { position: fixed; left: 50%; bottom: 170px; transform: translate(-50%, 12px); z-index: 40; max-width: min(92vw, 520px);
           background: var(--ink); color: var(--bg); border-radius: 12px; padding: 11px 14px; font-size: 14px; display: flex; gap: 14px; align-items: center;
           box-shadow: var(--shadow); opacity: 0; pointer-events: none; transition: opacity .2s, transform .2s; white-space: pre-line; }
  .toast.show { opacity: 1; transform: translate(-50%, 0); pointer-events: auto; }
  .toast button { border: 0; background: none; color: var(--accent); font-weight: 700; cursor: pointer; padding: 0; flex: none;
                  filter: brightness(1.25) saturate(1.1); }
  .scrim { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,.28); }
  .scrim[hidden], .menu[hidden] { display: none; }
  .menu { position: fixed; z-index: 60; background: var(--surface); border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow);
          padding: 6px; min-width: 220px; }
  .menu button, .menu .mi { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; border: 0; background: none; padding: 11px 12px;
                 border-radius: 9px; cursor: pointer; font-size: 15px; position: relative; }
  .menu button:hover, .menu button:focus-visible, .menu .mi:hover, .menu .mi:focus-within { background: var(--bg); }
  .menu button.danger { color: var(--danger); }
  .menu hr { border: 0; border-top: 1px solid var(--line); margin: 5px 4px; }
  .menu input[type=date] { position: absolute; inset: 0; opacity: 0; width: 100%; height: 100%; cursor: pointer; }
  @media (max-width: 640px) {
    .menu { left: 8px !important; right: 8px; bottom: calc(8px + env(safe-area-inset-bottom)); top: auto !important; border-radius: 18px; }
    .menu button, .menu .mi { padding: 14px 14px; font-size: 16px; }
    .toast { bottom: 190px; }
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style></head>
<body>
<div class="app">
  <header class="top">
    <div class="title-row">
      <div><h1 id="title">Today</h1><p class="sub" id="sub">&nbsp;</p></div>
      <div class="nav">
        <button class="text-btn" id="todayBtn" hidden>Today</button>
        <button class="icon-btn" id="prev" aria-label="Previous day"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg></button>
        <button class="icon-btn" id="next" aria-label="Next day"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg></button>
      </div>
    </div>
    <div class="progress" id="progress" hidden><div class="bar"><i id="barFill"></i></div><p id="progressText"></p></div>
    <nav class="week" id="week" aria-label="Pick a day"></nav>
  </header>
  <main id="board" aria-live="polite"></main>
</div>

<form class="composer" id="composer" autocomplete="off">
  <div class="composer-in">
    <div class="chips" id="chips" role="group" aria-label="When"></div>
    <div class="field">
      <button type="button" class="ask" id="askBtn" aria-pressed="false" title="Talk to the assistant instead of adding directly">Ask AI</button>
      <input id="msg" type="text" enterkeyhint="send" placeholder="Add a task" aria-label="New task">
      <button class="go" id="go" type="submit">Add</button>
    </div>
  </div>
</form>

<div class="toast" id="toast" role="status"></div>
<div class="scrim" id="scrim" hidden></div>
<div class="menu" id="menu" role="menu" hidden></div>

<script>
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const ICON = {
  check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  dots: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>',
  cal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="15" rx="3"/><path d="M8 3v4M16 3v4M3.5 10h17"/></svg>',
  chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
};
const state = { day: null, today: null, tz: 'UTC', board: null, mode: 'add', when: 'today', picked: null, error: false };

/* ---------- date helpers (YYYY-MM-DD strings, no timezone surprises) ---------- */
const at = ymd => new Date(ymd + 'T12:00:00Z');
const addDays = (ymd, n) => { const d = at(ymd); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const fmt = (ymd, o) => new Intl.DateTimeFormat('en-GB', { ...o, timeZone: 'UTC' }).format(at(ymd));
function dayName(ymd) {
  if (ymd === state.today) return 'Today';
  if (ymd === addDays(state.today, 1)) return 'Tomorrow';
  if (ymd === addDays(state.today, -1)) return 'Yesterday';
  return fmt(ymd, { weekday: 'short', day: 'numeric', month: 'short' });
}
function clock(iso) {
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: state.tz }).format(new Date(iso));
}

/* ---------- api ---------- */
async function api(path, method = 'GET', body) {
  const r = await fetch(path, { method, headers: body ? { 'content-type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) throw new Error(path + ' ' + r.status);
  return r.json();
}
async function load() {
  try {
    state.board = await api('/api/board' + (state.day ? '?day=' + state.day : ''));
    state.day = state.board.day; state.today = state.board.today; state.tz = state.board.tz; state.error = false;
  } catch (e) { state.error = true; }
  render();
}

/* ---------- toast ---------- */
let toastTimer;
function toast(msg, action, ms = 5500) {
  const t = $('#toast'); t.replaceChildren(h('span', {}, msg));
  if (action) t.append(h('button', { type: 'button', onclick: () => { hideToast(); action.fn(); } }, action.label));
  t.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(hideToast, ms);
}
function hideToast() { $('#toast').classList.remove('show'); }

/* ---------- rendering ---------- */
function render() {
  renderHeader();
  const main = $('#board'); main.replaceChildren();
  if (state.error) {
    main.append(h('div', { class: 'err' }, h('p', {}, 'Can\\u2019t reach taskbot right now.'), h('button', { class: 'text-btn', onclick: load }, 'Try again')));
    return;
  }
  if (!state.board) {
    main.append(h('div', { class: 'sec' }, h('ul', { class: 'list' }, h('div', { class: 'skel' }), h('div', { class: 'skel' }), h('div', { class: 'skel' }))));
    return;
  }
  const b = state.board, isToday = state.day === state.today;
  const timed = b.day_tasks.filter(t => t.scheduled_start).sort((a, c) => a.scheduled_start.localeCompare(c.scheduled_start));
  const untimed = b.day_tasks.filter(t => !t.scheduled_start);
  const todays = [...timed, ...untimed];
  const nothing = !b.carried.length && !todays.length && !b.anytime.length && !b.done.length;
  if (nothing) {
    main.append(h('div', { class: 'empty' }, h('h3', {}, isToday ? 'A clear day' : 'Nothing planned'),
      h('p', {}, isToday ? 'Add what\\u2019s on your mind below. Anything you don\\u2019t finish stays here until you tick or remove it.' : 'Nothing is scheduled for this day.')));
    return;
  }
  if (b.carried.length) main.append(section('Overdue', b.carried, { cls: 'late', hint: 'stays until done' }));
  if (todays.length || (isToday && (b.carried.length || b.anytime.length))) {
    if (todays.length) main.append(section(isToday ? 'Today' : 'Scheduled', todays));
    else main.append(h('div', { class: 'sec' }, h('div', { class: 'sec-head' }, h('h2', {}, 'Today')), h('p', { class: 'soft' }, 'Nothing scheduled for today.')));
  }
  if (b.anytime.length) main.append(section('Anytime', b.anytime, { hint: 'no date, stays until done' }));
  if (b.done.length) {
    const d = h('details', { class: 'done-sec', open: false },
      h('summary', {}, h('span', { html: ICON.chev }), h('h2', {}, 'Done'), h('span', { class: 'n' }, String(b.done.length))),
      h('ul', { class: 'list' }, b.done.map(t => row(t, { done: true }))));
    if (state.doneOpen) d.open = true;
    d.addEventListener('toggle', () => { state.doneOpen = d.open; });
    main.append(d);
  }
}
function section(label, tasks, o = {}) {
  return h('section', { class: 'sec ' + (o.cls || '') },
    h('div', { class: 'sec-head' }, h('h2', {}, label), h('span', { class: 'n' }, String(tasks.length)), o.hint && h('span', { class: 'hint' }, o.hint)),
    h('ul', { class: 'list' }, tasks.map(t => row(t))));
}
function row(t, o = {}) {
  const done = !!o.done || t.status === 'done';
  const meta = [];
  if (t.scheduled_start) meta.push(h('span', { class: 'chip time' }, clock(t.scheduled_start)));
  if (t.late_days > 0) meta.push(h('span', { class: 'chip late' }, t.late_days === 1 ? 'yesterday' : t.late_days + ' days late'));
  if (t.synced) meta.push(h('span', { class: 'chip cal', html: ICON.cal + 'Calendar' }));
  const title = h('button', { type: 'button', class: 't', onclick: done ? null : () => startEdit(t, title) }, t.title);
  return h('li', { class: 'row' + (done ? ' done' : ''), 'data-id': t.id },
    h('button', { class: 'tick', role: 'checkbox', 'aria-checked': String(done), 'aria-label': (done ? 'Mark not done: ' : 'Mark done: ') + t.title,
                  onclick: e => done ? restore(t.id) : complete(t.id, e.currentTarget.closest('.row')), html: '<i>' + ICON.check + '</i>' }),
    h('div', { class: 'body' }, title, h('div', { class: 'meta' }, meta)),
    !done && h('button', { class: 'more', 'aria-label': 'More actions for ' + t.title, 'aria-haspopup': 'menu', html: ICON.dots, onclick: e => openMenu(t, e.currentTarget) }));
}
function renderHeader() {
  const day = state.day || state.today;
  $('#title').textContent = state.today ? dayName(day) : 'Tasks';
  $('#sub').textContent = state.today ? fmt(day, { weekday: 'long', day: 'numeric', month: 'long' }) : '\\u00a0';
  $('#todayBtn').hidden = !state.today || day === state.today;
  const wk = $('#week'); wk.replaceChildren();
  if (state.today) for (let i = -3; i <= 3; i++) {
    const d = addDays(day, i);
    wk.append(h('button', { class: 'day', type: 'button', 'aria-selected': String(i === 0), 'aria-current': d === state.today ? 'date' : false,
                            'aria-label': fmt(d, { weekday: 'long', day: 'numeric', month: 'long' }), onclick: () => go(d) },
      h('small', {}, fmt(d, { weekday: 'short' })), h('span', {}, fmt(d, { day: 'numeric' }))));
  }
  const b = state.board, p = $('#progress');
  if (b && day === state.today) {
    const open = b.carried.length + b.day_tasks.length + b.anytime.length, done = b.done.length, total = open + done;
    p.hidden = total === 0;
    $('#barFill').style.width = total ? Math.round(done / total * 100) + '%' : '0%';
    $('#progressText').replaceChildren(h('b', {}, String(done)), ' of ' + total + ' done' + (open === 0 && total ? ' \\u2013 all clear' : ''));
  } else p.hidden = true;
  renderComposer();
}
function go(ymd) { state.day = ymd; state.board = null; load(); render(); }

/* ---------- actions (optimistic, with undo) ---------- */
function find(id) { const b = state.board; return [...b.carried, ...b.day_tasks, ...b.anytime].find(t => t.id === id); }
function dropLocal(id) { const b = state.board; for (const k of ['carried', 'day_tasks', 'anytime']) b[k] = b[k].filter(t => t.id !== id); }
async function complete(id, rowEl) {
  const t = find(id); if (!t) return;
  rowEl && rowEl.classList.add('leaving');
  await new Promise(r => setTimeout(r, rowEl ? 190 : 0));
  dropLocal(id); if (state.day === state.today) state.board.done.unshift({ ...t, status: 'done' }); render();
  try { await api('/api/tasks/' + id + '/complete', 'POST'); toast('Marked done', { label: 'Undo', fn: () => restore(id) }); }
  catch (e) { toast('Couldn\\u2019t save that. Reloading.'); load(); }
}
async function remove(id) {
  const t = find(id); if (!t) return;
  dropLocal(id); render();
  try { await api('/api/tasks/' + id, 'DELETE'); toast('Removed \\u201c' + t.title + '\\u201d', { label: 'Undo', fn: () => restore(id) }); }
  catch (e) { toast('Couldn\\u2019t remove that. Reloading.'); load(); }
}
async function restore(id) { try { await api('/api/tasks/' + id + '/restore', 'POST'); } catch (e) { toast('Couldn\\u2019t undo.'); } load(); }
async function move(id, ymd) {
  try { await api('/api/tasks/' + id, 'PATCH', { due_date: ymd }); toast(ymd ? 'Moved to ' + dayName(ymd) : 'Moved to Anytime'); }
  catch (e) { toast('Couldn\\u2019t move that.'); }
  load();
}
async function calendarAdd(id) {
  try { await api('/api/tasks/' + id + '/calendar', 'POST'); toast('Added to Google Calendar'); } catch (e) { toast('Couldn\\u2019t add to calendar.'); }
  load();
}
function startEdit(t, titleEl) {
  const input = h('input', { class: 'edit', value: t.title, maxlength: '300', 'aria-label': 'Edit task' });
  let finished = false;
  const finish = async save => {
    if (finished) return; finished = true;
    const v = input.value.trim();
    if (save && v && v !== t.title) {
      t.title = v; try { await api('/api/tasks/' + t.id, 'PATCH', { title: v }); } catch (e) { toast('Couldn\\u2019t rename that.'); load(); return; }
    }
    render();
  };
  input.addEventListener('keydown', e => { if (e.key === 'Enter') finish(true); else if (e.key === 'Escape') finish(false); });
  input.addEventListener('blur', () => finish(true));
  titleEl.replaceWith(input); input.focus(); input.select();
}

/* ---------- popover / bottom-sheet menu ---------- */
function closeMenu() { $('#menu').hidden = true; $('#scrim').hidden = true; }
function openMenu(t, btn) {
  const m = $('#menu'); m.replaceChildren();
  const item = (label, fn, cls) => h('button', { type: 'button', role: 'menuitem', class: cls || false, onclick: () => { closeMenu(); fn(); } }, label);
  const timed = !!t.scheduled_start, items = [];
  if (!timed) {
    if (t.due_date !== state.today) items.push(item('Move to today', () => move(t.id, state.today)));
    if (t.due_date !== addDays(state.today, 1)) items.push(item('Move to tomorrow', () => move(t.id, addDays(state.today, 1))));
    items.push(h('label', { class: 'mi', role: 'menuitem' }, 'Pick a date\\u2026',
      h('input', { type: 'date', 'aria-label': 'Pick a date', min: state.today, onchange: e => { closeMenu(); if (e.target.value) move(t.id, e.target.value); } })));
    if (t.due_date) items.push(item('Make it anytime (no date)', () => move(t.id, null)));
    items.push(h('hr'));
  }
  if (!t.synced) items.push(item('Add to Google Calendar', () => calendarAdd(t.id)));
  items.push(item('Delete', () => remove(t.id), 'danger'));
  m.append(...items);
  $('#scrim').hidden = false; m.hidden = false;
  if (matchMedia('(min-width: 641px)').matches) {
    const r = btn.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
    m.style.left = Math.max(8, Math.min(innerWidth - mw - 8, r.right - mw)) + 'px';
    m.style.top = (r.bottom + 6 + mh > innerHeight ? Math.max(8, r.top - mh - 6) : r.bottom + 6) + 'px';
  }
  (m.querySelector('button') || m).focus();
}
$('#scrim').addEventListener('click', closeMenu);

/* ---------- composer: instant add, or ask the assistant ---------- */
function whenLabel() {
  if (state.when === 'today') return 'Today';
  if (state.when === 'tomorrow') return 'Tomorrow';
  if (state.when === 'anytime') return 'Anytime';
  return state.picked ? dayName(state.picked) : 'Pick a date';
}
function whenValue() {
  if (state.when === 'today') return state.today;
  if (state.when === 'tomorrow') return addDays(state.today, 1);
  if (state.when === 'anytime') return null;
  return state.picked;
}
function renderComposer() {
  const add = state.mode === 'add';
  $('#askBtn').setAttribute('aria-pressed', String(!add));
  $('#msg').placeholder = add ? 'Add a task' : 'Tell me what to do, e.g. \\u201cgym at 7pm\\u201d or \\u201cwhat\\u2019s open?\\u201d';
  $('#go').textContent = add ? 'Add' : 'Send';
  const chips = $('#chips'); chips.hidden = !add; chips.replaceChildren();
  if (!add || !state.today) return;
  for (const [key, label] of [['today', 'Today'], ['tomorrow', 'Tomorrow'], ['anytime', 'Anytime']])
    chips.append(h('button', { type: 'button', class: 'wchip', 'aria-pressed': String(state.when === key), onclick: () => { state.when = key; renderComposer(); $('#msg').focus(); } }, label));
  chips.append(h('span', { class: 'wchip', 'aria-pressed': String(state.when === 'date') }, state.when === 'date' && state.picked ? dayName(state.picked) : 'Pick date',
    h('input', { type: 'date', 'aria-label': 'Pick a date', min: state.today, value: state.picked || '',
                 onchange: e => { if (e.target.value) { state.picked = e.target.value; state.when = 'date'; renderComposer(); $('#msg').focus(); } } })));
}
$('#askBtn').onclick = () => { state.mode = state.mode === 'ask' ? 'add' : 'ask'; renderComposer(); $('#msg').focus(); };
$('#composer').addEventListener('submit', async e => {
  e.preventDefault();
  const input = $('#msg'), text = input.value.trim(), btn = $('#go');
  if (!text || !state.today) return;
  btn.disabled = true;
  try {
    if (state.mode === 'add') {
      if (state.when === 'date' && !state.picked) { toast('Pick a date first.'); return; }
      const due = whenValue();
      await api('/api/tasks', 'POST', { title: text, due_date: due });
      input.value = '';
      const visible = due === null ? state.day === state.today : due === state.day || (due === state.today && state.day === state.today);
      toast('Added to ' + whenLabel(), visible ? null : { label: 'View', fn: () => go(due || state.today) });
    } else {
      toast('Thinking\\u2026', null, 30000);
      const r = await api('/api/message', 'POST', { text });
      input.value = ''; toast(r.reply || 'Done.', null, 9000);
    }
  } catch (err) { toast('That didn\\u2019t go through. Try again.'); }
  finally { btn.disabled = false; input.focus(); load(); }
});

/* ---------- keyboard ---------- */
addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeMenu(); hideToast(); return; }
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === 'n' || e.key === '/') { e.preventDefault(); $('#msg').focus(); }
  else if (e.key === 't' && state.today) go(state.today);
  else if (e.key === 'ArrowLeft' && state.day) go(addDays(state.day, -1));
  else if (e.key === 'ArrowRight' && state.day) go(addDays(state.day, 1));
});
$('#prev').onclick = () => state.day && go(addDays(state.day, -1));
$('#next').onclick = () => state.day && go(addDays(state.day, 1));
$('#todayBtn').onclick = () => state.today && go(state.today);

render(); load();
</script>
</body></html>
"""
