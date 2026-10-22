PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newsfeed</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    color-scheme: dark;
    --bg: #0b0d10;
    --bg-elevated: #121519;
    --surface: #15181d;
    --surface-hover: #1a1e24;
    --ink: #eae6dd;
    --ink-dim: #8b8f98;
    --ink-faint: #565a63;
    --rule: #232730;
    --rule-soft: #1b1e24;
    --amber: #d4a15e;
    --amber-dim: #8a6d43;
    --breaking: #d9573f;
    --notable: #d4a15e;
    --positive: #5fa87c;
    --negative: #c25a5a;
    --focus: #d4a15e;
    --rail-w: 220px;
    --side-w: 320px;
  }
  * { box-sizing: border-box; }
  html { scrollbar-color: var(--rule) transparent; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.55 "Inter", -apple-system, "Segoe UI", "Noto Sans Thai", "Leelawadee UI", sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  ::selection { background: var(--amber-dim); color: var(--bg); }
  a { color: inherit; }

  /* ---------- Top bar (full width) ---------- */
  .topbar {
    position: sticky; top: 0; z-index: 20;
    background: color-mix(in srgb, var(--bg) 94%, transparent);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--rule);
    padding: 0 24px;
  }
  .topbar-inner {
    max-width: 1600px; margin: 0 auto;
    display: flex; align-items: center; gap: 24px; height: 58px;
  }
  .brand {
    font-family: "Fraunces", Georgia, serif; font-size: 1.25rem; font-weight: 600;
    letter-spacing: -0.01em; white-space: nowrap;
  }
  .search-row { position: relative; flex: 1; max-width: 480px; }
  .search {
    width: 100%; padding: 8px 12px 8px 32px; font: 400 0.86rem "Inter", sans-serif; color: var(--ink);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 7px;
    transition: border-color .15s ease, background .15s ease;
  }
  .search::placeholder { color: var(--ink-faint); }
  .search:focus { outline: none; border-color: var(--amber-dim); background: var(--bg-elevated); }
  .search-icon {
    position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
    width: 13px; height: 13px; color: var(--ink-faint); pointer-events: none;
  }
  .topbar-tabs { display: flex; gap: 4px; margin-left: auto; }
  .tab {
    font: 500 0.82rem "Inter", sans-serif; padding: 6px 4px; color: var(--ink-faint);
    background: transparent; border: none; border-bottom: 2px solid transparent;
    cursor: pointer; transition: color .15s ease, border-color .15s ease; white-space: nowrap;
  }
  .tab:hover { color: var(--ink-dim); }
  .tab[aria-pressed="true"] { color: var(--ink); border-bottom-color: var(--amber); }
  .tab:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 2px; }
  .date {
    font-family: "JetBrains Mono", monospace; font-size: 0.7rem; color: var(--ink-faint);
    letter-spacing: 0.02em; text-transform: uppercase; white-space: nowrap;
  }
  .kbd-hint {
    width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--rule);
    background: transparent; color: var(--ink-faint); font: 600 0.7rem "JetBrains Mono", monospace;
    cursor: pointer; flex-shrink: 0; transition: all .15s ease;
  }
  .kbd-hint:hover { border-color: var(--amber-dim); color: var(--amber); }
  .tab-count {
    display: inline-block; font: 700 0.65rem "JetBrains Mono", monospace; color: var(--bg);
    background: var(--amber); border-radius: 999px; padding: 1px 6px; margin-left: 4px;
  }
  .tab-count[hidden] { display: none; }

  /* ---------- Pulse strip: glanceable daily summary ---------- */
  .pulse-strip {
    max-width: 1600px; margin: 0 auto; padding: 10px 24px;
    display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
    font: 500 0.76rem "Inter", sans-serif; color: var(--ink-dim);
    border-bottom: 1px solid var(--rule-soft);
  }
  .pulse-item { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
  .pulse-num { font: 700 0.82rem "JetBrains Mono", monospace; color: var(--ink); }
  .pulse-num.breaking { color: var(--breaking); }
  .pulse-num.notable { color: var(--notable); }
  .pulse-num.positive { color: var(--positive); }
  .pulse-num.negative { color: var(--negative); }
  .pulse-sep { width: 1px; height: 12px; background: var(--rule); }
  .pulse-new {
    margin-left: auto; font: 600 0.74rem "Inter", sans-serif; color: var(--amber);
    display: flex; align-items: center; gap: 5px; cursor: pointer; background: none; border: none;
    padding: 0;
  }
  .pulse-new:hover { text-decoration: underline; }

  /* ---------- Keyboard shortcuts overlay ---------- */
  .kbd-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,.6); z-index: 100;
    display: flex; align-items: center; justify-content: center;
  }
  .kbd-overlay[hidden] { display: none; }
  .kbd-panel {
    background: var(--bg-elevated); border: 1px solid var(--rule); border-radius: 12px;
    padding: 24px 28px; max-width: 340px; width: 90%;
  }
  .kbd-panel h3 {
    font: 600 0.9rem "Inter", sans-serif; margin: 0 0 16px; color: var(--ink);
  }
  .kbd-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; font-size: 0.84rem; color: var(--ink-dim); }
  .kbd-key {
    font: 600 0.74rem "JetBrains Mono", monospace; color: var(--ink);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 5px;
    padding: 2px 7px; min-width: 20px; text-align: center;
  }
  .kbd-close {
    display: block; margin: 18px auto 0; padding: 7px 16px; font: 500 0.8rem "Inter", sans-serif;
    color: var(--ink-dim); background: var(--surface); border: 1px solid var(--rule); border-radius: 7px; cursor: pointer;
  }

  /* ---------- 3-column grid ---------- */
  .layout {
    max-width: 1600px; margin: 0 auto; padding: 0 24px;
    display: grid; grid-template-columns: var(--rail-w) minmax(0,1fr) var(--side-w);
    gap: 24px; align-items: start;
  }

  /* ---------- Left rail: filters ---------- */
  .rail {
    position: sticky; top: 82px; padding: 20px 0;
    max-height: calc(100vh - 82px); overflow-y: auto;
  }
  .rail-section { margin-bottom: 22px; }
  .rail-title {
    font: 600 0.68rem "JetBrains Mono", monospace; color: var(--ink-faint);
    text-transform: uppercase; letter-spacing: 0.07em; margin: 0 0 10px;
  }
  .rail-chips { display: flex; flex-direction: column; gap: 2px; }
  .rail-chip {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    padding: 6px 8px; font: 500 0.82rem "Inter", sans-serif; color: var(--ink-dim);
    background: transparent; border: none; border-radius: 6px; cursor: pointer;
    text-align: left; transition: all .15s ease; width: 100%;
  }
  .rail-chip:hover { background: var(--surface); color: var(--ink); }
  .rail-chip[aria-pressed="true"] { background: color-mix(in srgb, var(--amber) 14%, transparent); color: var(--amber); font-weight: 600; }
  .rail-chip .count { font: 500 0.7rem "JetBrains Mono", monospace; color: var(--ink-faint); }
  .rail-chip[aria-pressed="true"] .count { color: var(--amber-dim); }
  .rail-chip:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
  .range-chips { flex-direction: row; flex-wrap: wrap; }
  .range-chips .rail-chip { width: auto; border: 1px solid var(--rule); border-radius: 999px; padding: 5px 11px; }

  .rail select, .rail input {
    width: 100%; padding: 7px 9px; font: 400 0.82rem "Inter", sans-serif; color: var(--ink);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; margin-bottom: 8px;
  }
  .rail select:focus, .rail input:focus { outline: none; border-color: var(--amber-dim); }
  .rail label {
    font: 500 0.66rem "JetBrains Mono", monospace; color: var(--ink-faint); display: block; margin-bottom: 4px;
    text-transform: uppercase; letter-spacing: 0.04em;
  }

  /* ---------- Center: stream ---------- */
  main { min-width: 0; padding: 20px 0 60px; }

  .day {
    margin: 0 0 10px; font: 600 0.7rem "JetBrains Mono", monospace; color: var(--ink-faint);
    text-transform: uppercase; letter-spacing: 0.08em;
    display: flex; align-items: center; gap: 10px;
  }
  .day:not(:first-child) { margin-top: 26px; }
  .day::after { content: ''; flex: 1; height: 1px; background: var(--rule-soft); }

  /* Dense two-column feed grid on wide screens */
  .feed-grid {
    display: grid; grid-template-columns: 1fr; gap: 8px;
  }
  @media (min-width: 1280px) {
    .feed-grid { grid-template-columns: 1fr 1fr; }
    .feed-grid .day-break { grid-column: 1 / -1; }
  }
  .saved-stream { grid-column: 2; padding: 20px 0; }
  @media (max-width: 1180px) { .saved-stream { grid-column: 2; } }
  @media (max-width: 860px) { .saved-stream { grid-column: 1; padding: 14px 0 40px; } }

  article {
    background: var(--surface); border-radius: 10px; padding: 14px 16px;
    border: 1px solid transparent;
    transition: border-color .15s ease, background .15s ease;
    position: relative; overflow: hidden;
  }
  article::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2.5px;
    background: transparent; transition: background .15s ease;
  }
  article:hover { background: var(--surface-hover); border-color: var(--rule); }
  article.breaking::before { background: var(--breaking); }
  article.notable::before { background: var(--notable); }
  article.is-read { opacity: 0.52; }
  article.is-read:hover { opacity: 0.85; }
  article.kbd-focus { border-color: var(--amber-dim); background: var(--surface-hover); }

  .row1 { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .row1-badges { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
  .save-btn {
    width: 22px; height: 22px; border-radius: 5px; border: 1px solid var(--rule);
    background: transparent; color: var(--ink-faint); cursor: pointer; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; transition: all .15s ease;
    margin-top: 2px;
  }
  .save-btn:hover { border-color: var(--amber-dim); color: var(--amber); }
  .save-btn.saved { color: var(--amber); border-color: var(--amber-dim); background: color-mix(in srgb, var(--amber) 10%, transparent); }
  .save-btn svg { width: 11px; height: 11px; }
  .badge {
    font: 700 0.6rem "JetBrains Mono", monospace; text-transform: uppercase; letter-spacing: 0.06em;
    padding: 2px 6px; border-radius: 4px; white-space: nowrap; margin-top: 3px; flex-shrink: 0;
  }
  .badge.breaking { color: var(--breaking); background: color-mix(in srgb, var(--breaking) 14%, transparent); }
  .badge.notable { color: var(--notable); background: color-mix(in srgb, var(--notable) 14%, transparent); }

  article a.title {
    color: var(--ink); text-decoration: none; font: 600 0.98rem/1.38 "Fraunces", Georgia, serif;
    letter-spacing: -0.005em;
  }
  article a.title:hover { color: var(--amber); }
  article a.title:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 3px; }

  .summary {
    margin: 7px 0 0; font: 400 0.84rem/1.6 "Inter", sans-serif; color: var(--ink-dim);
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }

  .meta {
    display: flex; flex-wrap: wrap; align-items: center; gap: 7px;
    margin-top: 10px; font: 500 0.72rem "Inter", sans-serif; color: var(--ink-faint);
  }
  .feed-name { color: var(--ink-faint); }
  .dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
  .dot.positive { background: var(--positive); }
  .dot.negative { background: var(--negative); }
  .dot.neutral { background: var(--ink-faint); }
  .pill {
    font: 500 0.68rem "JetBrains Mono", monospace; color: var(--ink-dim);
    border: 1px solid var(--rule); border-radius: 5px; padding: 1px 6px;
  }
  .time { margin-left: auto; color: var(--ink-faint); white-space: nowrap; }

  .empty, .end {
    text-align: center; color: var(--ink-faint); padding: 56px 20px; font-size: 0.88rem;
    grid-column: 1 / -1;
  }
  .loadmore {
    display: block; margin: 20px auto 0; padding: 10px 22px; font: 500 0.84rem "Inter", sans-serif;
    color: var(--ink-dim); background: var(--surface); border: 1px solid var(--rule);
    border-radius: 8px; cursor: pointer; transition: all .15s ease; grid-column: 1 / -1;
  }
  .loadmore:hover { border-color: var(--amber-dim); color: var(--ink); }
  .loadmore[disabled] { opacity: .4; cursor: default; }
  .loadmore[hidden] { display: none; }

  /* ---------- Right sidebar: Picks / watchlist ---------- */
  .sidebar {
    position: sticky; top: 82px; padding: 20px 0;
    max-height: calc(100vh - 82px); overflow-y: auto;
  }
  .sidebar h2 {
    font: 600 0.7rem "JetBrains Mono", monospace; color: var(--ink-faint); margin: 0 0 10px;
    text-transform: uppercase; letter-spacing: 0.08em;
    display: flex; align-items: center; gap: 10px;
  }
  .sidebar h2::after { content: ''; flex: 1; height: 1px; background: var(--rule-soft); }
  .sidebar-section { margin-bottom: 22px; }
  .disclaimer {
    color: var(--ink-faint); font-size: 0.72rem; margin: 0 0 16px; padding: 8px 10px;
    background: var(--surface); border-radius: 8px; border: 1px solid var(--rule-soft); line-height: 1.5;
  }

  .pickRow {
    display: flex; flex-direction: column; gap: 4px; background: var(--surface);
    border: 1px solid transparent; border-radius: 8px; padding: 10px 12px; margin-bottom: 6px;
    transition: all .15s ease;
  }
  .pickRow:hover { background: var(--surface-hover); border-color: var(--rule); }
  .pickTop { display: flex; align-items: center; gap: 8px; }
  .pickSymbol { font: 700 0.84rem "JetBrains Mono", monospace; min-width: 4rem; letter-spacing: 0.01em; }
  .pickName {
    color: var(--ink-faint); font: 400 0.76rem "Inter", sans-serif; flex: 1; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap;
  }
  .pickChange { font: 700 0.8rem "JetBrains Mono", monospace; color: var(--positive); }
  .pickMeta { font: 400 0.72rem "Inter", sans-serif; color: var(--ink-faint); }
  .pickSub { font: 400 0.72rem "Inter", sans-serif; color: var(--ink-faint); }
  .pickEmpty { color: var(--ink-faint); font-size: 0.8rem; padding: 4px 0; }

  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }

  /* ---------- Responsive breakpoints ---------- */
  @media (max-width: 1500px) {
    :root { --side-w: 280px; }
  }
  /* ---------- Trading tab ---------- */
  .trading-view {
    grid-column: 1 / -1; display: grid;
    grid-template-columns: 1fr var(--side-w); grid-template-rows: auto 1fr;
    gap: 16px; padding: 18px 0 40px; min-height: 0;
  }
  .trading-toolbar {
    grid-column: 1 / -1; display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
    padding-bottom: 14px; border-bottom: 1px solid var(--rule);
  }
  .symbol-search { position: relative; width: 260px; flex-shrink: 0; }
  .symbol-search input {
    width: 100%; padding: 9px 12px; font: 500 0.88rem "JetBrains Mono", monospace; color: var(--ink);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 8px;
  }
  .symbol-search input:focus { outline: none; border-color: var(--amber-dim); }
  .symbol-dropdown {
    position: absolute; top: calc(100% + 4px); left: 0; right: 0; max-height: 320px; overflow-y: auto;
    background: var(--bg-elevated); border: 1px solid var(--rule); border-radius: 8px; z-index: 20;
    box-shadow: 0 12px 28px rgba(0,0,0,.4);
  }
  .symbol-option {
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    padding: 8px 12px; cursor: pointer; font-size: 0.84rem;
  }
  .symbol-option:hover, .symbol-option.kbd-focus { background: var(--surface-hover); }
  .symbol-option .sym { font: 700 0.82rem "JetBrains Mono", monospace; color: var(--amber); }
  .symbol-option .nm { color: var(--ink-dim); font-size: 0.78rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .trading-symbol-info { display: flex; align-items: baseline; gap: 10px; flex-shrink: 0; }
  .trading-symbol-info .sym { font: 700 1.2rem "JetBrains Mono", monospace; color: var(--ink); }
  .trading-symbol-info .nm { color: var(--ink-faint); font-size: 0.82rem; }
  .trading-symbol-info .px { font: 700 1.05rem "JetBrains Mono", monospace; color: var(--ink); }
  .trading-symbol-info .chg { font: 600 0.86rem "JetBrains Mono", monospace; }
  .trading-symbol-info .chg.positive { color: var(--positive); }
  .trading-symbol-info .chg.negative { color: var(--negative); }
  .trading-controls { display: flex; align-items: center; gap: 18px; margin-left: auto; flex-wrap: wrap; }
  .trading-range { flex-direction: row; }
  .trading-range .rail-chip { width: auto; border: 1px solid var(--rule); border-radius: 999px; padding: 5px 12px; font-size: 0.76rem; }
  .overlay-toggles { display: flex; align-items: center; gap: 14px; }
  .overlay-toggle {
    display: flex; align-items: center; gap: 6px; font: 500 0.78rem "Inter", sans-serif; color: var(--ink-dim);
    cursor: pointer; user-select: none;
  }
  .overlay-toggle input { accent-color: var(--amber); cursor: pointer; }

  .trading-main { display: flex; flex-direction: column; min-width: 0; }
  .chart-panel {
    position: relative; background: var(--surface); border: 1px solid var(--rule-soft); border-radius: 10px 10px 0 0;
    height: 420px; padding: 10px;
  }
  .chart-panel canvas { width: 100%; height: 100%; display: block; }
  .chart-empty {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    color: var(--ink-faint); font-size: 0.86rem;
  }
  .chart-empty[hidden] { display: none; }
  .volume-panel {
    background: var(--surface); border: 1px solid var(--rule-soft); border-top: none; border-radius: 0 0 10px 10px;
    height: 90px; padding: 6px 10px;
  }
  .volume-panel canvas { width: 100%; height: 100%; display: block; }

  .analysis-panel { min-width: 0; }
  .analysis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .analysis-cell {
    background: var(--surface); border: 1px solid var(--rule-soft); border-radius: 8px; padding: 9px 11px;
  }
  .analysis-cell .lbl { font: 500 0.66rem "JetBrains Mono", monospace; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 0.05em; }
  .analysis-cell .val { font: 700 0.94rem "JetBrains Mono", monospace; color: var(--ink); margin-top: 3px; }
  .analysis-cell .val.support { color: var(--positive); }
  .analysis-cell .val.resistance { color: var(--negative); }
  #symbolNews .sn-item { padding: 9px 0; border-bottom: 1px solid var(--rule-soft); }
  #symbolNews .sn-item:last-child { border-bottom: none; }
  #symbolNews .sn-item a { font: 500 0.82rem "Inter", sans-serif; color: var(--ink); text-decoration: none; line-height: 1.4; }
  #symbolNews .sn-item a:hover { color: var(--amber); }
  #symbolNews .sn-empty { color: var(--ink-faint); font-size: 0.8rem; padding: 6px 0; }

  .verdict-loading { color: var(--ink-faint); font-size: 0.8rem; margin: 0; }
  .verdict-error { color: var(--negative); font-size: 0.8rem; margin: 0; }
  .verdict-body { display: flex; flex-direction: column; gap: 10px; }
  .verdict-read {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--surface); border: 1px solid var(--rule-soft); border-radius: 8px; padding: 10px 12px;
  }
  .verdict-read .read-label {
    font: 700 0.92rem "JetBrains Mono", monospace; text-transform: uppercase; letter-spacing: 0.03em;
  }
  .verdict-read .read-label.bullish { color: var(--positive); }
  .verdict-read .read-label.bearish { color: var(--negative); }
  .verdict-read .read-label.neutral { color: var(--ink-faint); }
  .verdict-read .read-confidence { font: 500 0.72rem "JetBrains Mono", monospace; color: var(--ink-faint); }
  .verdict-risk { display: flex; align-items: center; gap: 8px; font-size: 0.78rem; color: var(--ink-faint); }
  .verdict-risk .risk-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .verdict-risk .risk-dot.low { background: var(--positive); }
  .verdict-risk .risk-dot.moderate { background: var(--amber); }
  .verdict-risk .risk-dot.elevated { background: #e0883a; }
  .verdict-risk .risk-dot.high { background: var(--negative); }
  .verdict-probs { display: flex; gap: 4px; height: 6px; border-radius: 3px; overflow: hidden; }
  .verdict-probs .p-bull { background: var(--positive); }
  .verdict-probs .p-neutral { background: var(--rule); }
  .verdict-probs .p-bear { background: var(--negative); }
  .verdict-disclaimer { font-size: 0.68rem; color: var(--ink-faint); line-height: 1.4; margin: 0; }

  @media (max-width: 1180px) {
    .trading-view { grid-template-columns: 1fr; }
    .analysis-panel { grid-column: 1; }
  }
  @media (max-width: 860px) {
    .trading-toolbar { flex-direction: column; align-items: stretch; }
    .symbol-search { width: 100%; }
    .trading-controls { margin-left: 0; justify-content: space-between; }
    .chart-panel { height: 300px; }
  }

  @media (max-width: 1180px) {
    :root { --side-w: 280px; }
  }
  @media (max-width: 1180px) {
    .layout { grid-template-columns: var(--rail-w) minmax(0,1fr); }
    .sidebar { display: none; }
    .sidebar.mobile-visible { display: block; }
  }
  @media (max-width: 860px) {
    .layout { grid-template-columns: 1fr; padding: 0 14px; }
    .rail { position: static; max-height: none; padding: 14px 0; border-bottom: 1px solid var(--rule); margin-bottom: 6px; }
    .rail-chips { flex-direction: row; flex-wrap: wrap; }
    .rail-chip { width: auto; border: 1px solid var(--rule); border-radius: 999px; padding: 5px 11px; }
    .rail-section:has(select), .rail-section:has(input) { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .rail-section:has(select) .rail-title, .rail-section:has(input) .rail-title { grid-column: 1 / -1; }
    main { padding: 14px 0 40px; }
    .topbar { padding: 0 14px; }
    .topbar-inner { height: auto; flex-wrap: wrap; padding: 10px 0; gap: 10px; }
    .brand { font-size: 1.1rem; }
    .search-row { order: 3; max-width: none; width: 100%; }
    .topbar-tabs { order: 2; margin-left: 0; }
    .date { display: none; }
    .pulse-strip { padding: 8px 14px; gap: 10px; font-size: 0.7rem; overflow-x: auto; flex-wrap: nowrap; }
    .pulse-new { margin-left: 12px; }
  }
  @media (max-width: 480px) {
    article { padding: 12px 14px; }
    article a.title { font-size: 0.92rem; }
  }
</style></head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <span class="brand">Newsfeed</span>
      <div class="search-row">
        <svg class="search-icon" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M11 11L14.5 14.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        <input class="search" id="q" type="search" placeholder='Search titles and topics — try "thailand"'>
      </div>
      <div class="topbar-tabs">
        <button type="button" class="tab" id="tabNews" aria-pressed="true">News</button>
        <button type="button" class="tab" id="tabSaved" aria-pressed="false">Saved <span class="tab-count" id="savedCount" hidden></span></button>
        <button type="button" class="tab" id="tabPicks" aria-pressed="false">Today's Picks</button>
        <button type="button" class="tab" id="tabTrading" aria-pressed="false">Trading</button>
      </div>
      <span class="date" id="todayDate"></span>
      <button type="button" class="kbd-hint" id="kbdHint" title="Keyboard shortcuts">?</button>
    </div>
  </div>

  <div class="pulse-strip" id="pulseStrip"></div>

  <div class="layout">
    <aside class="rail" id="rail">
      <div class="rail-section">
        <p class="rail-title">Time range</p>
        <div class="rail-chips range-chips" id="rangeChips">
          <button type="button" class="rail-chip" data-range="today" aria-pressed="false">Today</button>
          <button type="button" class="rail-chip" data-range="week" aria-pressed="false">This week</button>
          <button type="button" class="rail-chip" data-range="month" aria-pressed="false">This month</button>
          <button type="button" class="rail-chip" data-range="all" aria-pressed="true">All time</button>
        </div>
      </div>
      <div class="rail-section">
        <p class="rail-title">Category</p>
        <div class="rail-chips" id="catChips"></div>
      </div>
      <div class="rail-section">
        <div class="rail-title">Filters</div>
        <label for="importance">Importance</label>
        <select id="importance">
          <option value="">Any</option>
          <option value="breaking">Breaking</option>
          <option value="notable">Notable</option>
          <option value="routine">Routine</option>
        </select>
        <label for="sentiment">Sentiment</label>
        <select id="sentiment">
          <option value="">Any</option>
          <option value="positive">Positive</option>
          <option value="negative">Negative</option>
          <option value="neutral">Neutral</option>
        </select>
        <label for="ticker">Ticker</label>
        <input id="ticker" placeholder="e.g. AAPL">
        <label for="tag">Tag</label>
        <input id="tag" placeholder="e.g. ai-chips" list="tagList">
        <datalist id="tagList"></datalist>
      </div>
    </aside>

    <main>
      <div class="feed-grid" id="stream"></div>
      <button class="loadmore" id="loadmore" hidden>Load more</button>
    </main>

    <div class="feed-grid saved-stream" id="savedStream" hidden></div>

    <div class="trading-view" id="tradingView" hidden>
      <div class="trading-toolbar">
        <div class="symbol-search">
          <input type="text" id="symbolSearch" placeholder="Search symbol — try NVDA, AAPL" autocomplete="off">
          <div class="symbol-dropdown" id="symbolDropdown" hidden></div>
        </div>
        <div class="trading-symbol-info" id="tradingSymbolInfo"></div>
        <div class="trading-controls">
          <div class="range-chips trading-range" id="chartRangeChips">
            <button type="button" class="rail-chip" data-days="30">1M</button>
            <button type="button" class="rail-chip" data-days="90" aria-pressed="true">3M</button>
            <button type="button" class="rail-chip" data-days="180">6M</button>
            <button type="button" class="rail-chip" data-days="365">1Y</button>
          </div>
          <div class="overlay-toggles">
            <label class="overlay-toggle"><input type="checkbox" id="toggleEMA20" checked><span>EMA 20</span></label>
            <label class="overlay-toggle"><input type="checkbox" id="toggleEMA50" checked><span>EMA 50</span></label>
            <label class="overlay-toggle"><input type="checkbox" id="toggleSR" checked><span>Support / Resistance</span></label>
          </div>
        </div>
      </div>

      <div class="trading-main">
        <div class="chart-panel">
          <canvas id="priceCanvas"></canvas>
          <div class="chart-empty" id="chartEmpty" hidden>No price history for this symbol yet.</div>
        </div>
        <div class="volume-panel">
          <canvas id="volumeCanvas"></canvas>
        </div>
      </div>

      <aside class="analysis-panel" id="analysisPanel">
        <p class="disclaimer">Computed directly from price history — not investment advice.</p>
        <section class="sidebar-section">
          <p class="sidebar-title">Levels</p>
          <div class="analysis-grid" id="levelsGrid"></div>
        </section>
        <section class="sidebar-section">
          <p class="sidebar-title">Momentum</p>
          <div class="analysis-grid" id="momentumGrid"></div>
        </section>
        <section class="sidebar-section" id="verdictSection">
          <p class="sidebar-title">AI read (Jev)</p>
          <div id="verdictBody" class="verdict-body">
            <p class="verdict-loading">Loading AI read…</p>
          </div>
        </section>
        <section class="sidebar-section">
          <p class="sidebar-title">Recent news for this symbol</p>
          <div id="symbolNews"></div>
        </section>
      </aside>
    </div>

    <aside class="sidebar" id="picksView" hidden>
      <p class="disclaimer">Ranked by recent price movement and news attention — not financial advice.</p>
      <section class="sidebar-section">
        <h2>Tech</h2>
        <div id="picksTech" class="pickList"></div>
      </section>
      <section class="sidebar-section">
        <h2>Healthcare</h2>
        <div id="picksHealthcare" class="pickList"></div>
      </section>
      <section class="sidebar-section">
        <h2>Other</h2>
        <div id="picksOther" class="pickList"></div>
      </section>
    </aside>
  </div>

  <div class="kbd-overlay" id="kbdOverlay" hidden>
    <div class="kbd-panel">
      <h3>Keyboard shortcuts</h3>
      <div class="kbd-row"><span>Next / previous article</span><span><span class="kbd-key">j</span> <span class="kbd-key">k</span></span></div>
      <div class="kbd-row"><span>Open focused article</span><span class="kbd-key">Enter</span></div>
      <div class="kbd-row"><span>Save / unsave focused article</span><span class="kbd-key">s</span></div>
      <div class="kbd-row"><span>Jump to search</span><span class="kbd-key">/</span></div>
      <div class="kbd-row"><span>Close this panel</span><span class="kbd-key">Esc</span></div>
      <button class="kbd-close" id="kbdClose">Got it</button>
    </div>
  </div>

<script>
document.getElementById('todayDate').textContent = new Date().toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });

const state = { offset: 0, limit: 40, items: [], hasMore: false, focusIdx: -1, range: 'all' };
const STORE_KEY = 'newsfeed:v1';
function loadStore() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || { read: {}, saved: {}, lastVisit: 0 }; }
  catch { return { read: {}, saved: {}, lastVisit: 0 }; }
}
function saveStore() { localStorage.setItem(STORE_KEY, JSON.stringify(store)); }
const store = loadStore();
const previousVisit = store.lastVisit || 0;

const els = {
  q: document.getElementById('q'),
  catChips: document.getElementById('catChips'),
  rangeChips: document.getElementById('rangeChips'),
  importance: document.getElementById('importance'),
  sentiment: document.getElementById('sentiment'),
  ticker: document.getElementById('ticker'),
  tag: document.getElementById('tag'),
  tagList: document.getElementById('tagList'),
  stream: document.getElementById('stream'),
  savedStream: document.getElementById('savedStream'),
  loadmore: document.getElementById('loadmore'),
  tabNews: document.getElementById('tabNews'),
  tabSaved: document.getElementById('tabSaved'),
  savedCount: document.getElementById('savedCount'),
  tabPicks: document.getElementById('tabPicks'),
  rail: document.getElementById('rail'),
  picksView: document.getElementById('picksView'),
  pulseStrip: document.getElementById('pulseStrip'),
  kbdHint: document.getElementById('kbdHint'),
  kbdOverlay: document.getElementById('kbdOverlay'),
  kbdClose: document.getElementById('kbdClose'),
  tabTrading: document.getElementById('tabTrading'),
  tradingView: document.getElementById('tradingView'),
  symbolSearch: document.getElementById('symbolSearch'),
  symbolDropdown: document.getElementById('symbolDropdown'),
  tradingSymbolInfo: document.getElementById('tradingSymbolInfo'),
  chartRangeChips: document.getElementById('chartRangeChips'),
  priceCanvas: document.getElementById('priceCanvas'),
  volumeCanvas: document.getElementById('volumeCanvas'),
  chartEmpty: document.getElementById('chartEmpty'),
  levelsGrid: document.getElementById('levelsGrid'),
  momentumGrid: document.getElementById('momentumGrid'),
  symbolNews: document.getElementById('symbolNews'),
  verdictBody: document.getElementById('verdictBody'),
  toggleEMA20: document.getElementById('toggleEMA20'),
  toggleEMA50: document.getElementById('toggleEMA50'),
  toggleSR: document.getElementById('toggleSR'),
};
let activeCategory = '';
let currentTab = 'news';

function rangeSince(range) {
  const now = new Date();
  if (range === 'today') {
    const d = new Date(now); d.setHours(0, 0, 0, 0);
    return d.toISOString();
  }
  if (range === 'week') return new Date(now.getTime() - 7 * 86400000).toISOString();
  if (range === 'month') return new Date(now.getTime() - 30 * 86400000).toISOString();
  return null;
}

function currentParams(offset) {
  const p = new URLSearchParams();
  if (els.q.value.trim()) p.set('q', els.q.value.trim());
  if (activeCategory) p.set('category', activeCategory);
  if (els.importance.value) p.set('importance', els.importance.value);
  if (els.sentiment.value) p.set('sentiment', els.sentiment.value);
  if (els.ticker.value.trim()) p.set('ticker', els.ticker.value.trim());
  if (els.tag.value.trim()) p.set('tag', els.tag.value.trim());
  const since = rangeSince(state.range);
  if (since) p.set('since', since);
  p.set('limit', state.limit);
  p.set('offset', offset);
  return p;
}

function timeAgo(iso) {
  if (!iso) return '';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  const days = Math.floor(hrs / 24);
  if (days < 7) return days + 'd ago';
  return new Date(iso).toLocaleDateString();
}

function dayLabel(iso) {
  if (!iso) return 'Undated';
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date(today); yest.setDate(today.getDate() - 1);
  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  if (sameDay(d, today)) return 'Today';
  if (sameDay(d, yest)) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
}

function articleId(item) {
  // Articles have no stable server ID exposed to this page; use URL as the identity key.
  return item.url || item.title;
}

function articleEl(item) {
  const art = document.createElement('article');
  const id = articleId(item);
  art.dataset.id = id;
  const classes = [];
  if (item.importance === 'breaking' || item.importance === 'notable') classes.push(item.importance);
  if (store.read[id]) classes.push('is-read');
  art.className = classes.join(' ');

  const row1 = document.createElement('div');
  row1.className = 'row1';
  const a = document.createElement('a');
  a.className = 'title'; a.href = item.url; a.target = '_blank'; a.rel = 'noopener';
  a.textContent = item.title;
  a.addEventListener('click', () => markRead(id, art));
  row1.appendChild(a);

  const badges = document.createElement('div');
  badges.className = 'row1-badges';
  if (item.importance === 'breaking' || item.importance === 'notable') {
    const b = document.createElement('span');
    b.className = 'badge ' + item.importance;
    b.textContent = item.importance;
    badges.appendChild(b);
  }
  const saveBtn = document.createElement('button');
  saveBtn.type = 'button'; saveBtn.className = 'save-btn' + (store.saved[id] ? ' saved' : '');
  saveBtn.title = store.saved[id] ? 'Remove from saved' : 'Save for later';
  saveBtn.innerHTML = '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 2h8a1 1 0 011 1v11l-5-3-5 3V3a1 1 0 011-1z"/></svg>';
  saveBtn.addEventListener('click', (e) => {
    e.preventDefault(); e.stopPropagation();
    toggleSaved(id, item, saveBtn);
  });
  badges.appendChild(saveBtn);
  row1.appendChild(badges);
  art.appendChild(row1);

  if (item.summary) {
    const p = document.createElement('p');
    p.className = 'summary';
    p.textContent = item.summary;
    art.appendChild(p);
  }

  const meta = document.createElement('div');
  meta.className = 'meta';
  const feed = document.createElement('span');
  feed.className = 'feed-name';
  feed.textContent = item.feed_name || '';
  meta.appendChild(feed);

  if (item.sentiment) {
    const dot = document.createElement('span');
    dot.className = 'dot ' + item.sentiment;
    dot.title = item.sentiment;
    meta.appendChild(dot);
  }
  (item.tickers || []).forEach(sym => {
    const pill = document.createElement('span');
    pill.className = 'pill'; pill.textContent = sym;
    meta.appendChild(pill);
  });
  const time = document.createElement('span');
  time.className = 'time'; time.textContent = timeAgo(item.published_at);
  meta.appendChild(time);
  art.appendChild(meta);

  return art;
}

function render(items, { append }) {
  if (!append) els.stream.innerHTML = '';
  if (!append && items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    const rangeLabels = { today: 'today', week: 'this week', month: 'this month', all: 'all time' };
    const hasOtherFilters = els.q.value.trim() || activeCategory || els.importance.value || els.sentiment.value || els.ticker.value.trim() || els.tag.value.trim();
    empty.textContent = hasOtherFilters
      ? 'No articles match — try a different search or clear filters.'
      : 'No articles published in the "' + rangeLabels[state.range] + '" range yet — try "This week" or "All time" to see more.';
    els.stream.appendChild(empty);
    return;
  }
  let lastDay = append && state.items.length ? dayLabel(state.items[state.items.length - 1].published_at) : null;
  items.forEach(item => {
    const label = dayLabel(item.published_at);
    if (label !== lastDay) {
      const h = document.createElement('div');
      h.className = 'day day-break'; h.textContent = label;
      els.stream.appendChild(h);
      lastDay = label;
    }
    els.stream.appendChild(articleEl(item));
  });
}

async function load({ reset }) {
  const offset = reset ? 0 : state.offset;
  els.loadmore.disabled = true;
  const res = await fetch('/api/articles?' + currentParams(offset));
  const body = await res.json();
  state.items = reset ? body.items : state.items.concat(body.items);
  render(body.items, { append: !reset });
  state.offset = offset + body.items.length;
  state.hasMore = body.has_more;
  els.loadmore.hidden = !body.has_more;
  els.loadmore.disabled = false;
  state.focusIdx = -1;
  updatePulse();
}

// ---------- Read state, saved articles, unread badge ----------
function markRead(id, artEl) {
  if (store.read[id]) return;
  store.read[id] = Date.now();
  saveStore();
  if (artEl) artEl.classList.add('is-read');
}

function toggleSaved(id, item, btnEl) {
  if (store.saved[id]) {
    delete store.saved[id];
  } else {
    store.saved[id] = { title: item.title, url: item.url, feed_name: item.feed_name, published_at: item.published_at, summary: item.summary, tickers: item.tickers, importance: item.importance, sentiment: item.sentiment };
  }
  saveStore();
  if (btnEl) {
    const isSaved = !!store.saved[id];
    btnEl.classList.toggle('saved', isSaved);
    btnEl.title = isSaved ? 'Remove from saved' : 'Save for later';
  }
  updateSavedCount();
  if (currentTab === 'saved') renderSaved();
}

function updateSavedCount() {
  const n = Object.keys(store.saved).length;
  els.savedCount.textContent = String(n);
  els.savedCount.hidden = n === 0;
}

function renderSaved() {
  els.savedStream.innerHTML = '';
  const items = Object.values(store.saved).sort((a, b) => new Date(b.published_at || 0) - new Date(a.published_at || 0));
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'Nothing saved yet — click the bookmark icon on any article to keep it here.';
    els.savedStream.appendChild(empty);
    return;
  }
  items.forEach(item => els.savedStream.appendChild(articleEl(item)));
}

// ---------- Pulse strip: glanceable daily summary over the loaded set ----------
function updatePulse() {
  const items = state.items;
  const breaking = items.filter(i => i.importance === 'breaking').length;
  const notable = items.filter(i => i.importance === 'notable').length;
  const positive = items.filter(i => i.sentiment === 'positive').length;
  const negative = items.filter(i => i.sentiment === 'negative').length;
  const newSince = previousVisit ? items.filter(i => i.published_at && new Date(i.published_at).getTime() > previousVisit).length : 0;
  const rangeLabels = { today: 'today', week: 'this week', month: 'this month', all: 'all time' };

  els.pulseStrip.innerHTML = '';
  const rangeTag = document.createElement('span');
  rangeTag.className = 'pulse-item';
  const countLabel = state.hasMore ? items.length + '+' : String(items.length);
  rangeTag.innerHTML = '<span class="pulse-num">' + countLabel + '</span> articles &middot; ' + rangeLabels[state.range];
  els.pulseStrip.appendChild(rangeTag);
  els.pulseStrip.appendChild((() => { const s = document.createElement('span'); s.className = 'pulse-sep'; return s; })());

  const mk = (label, num, cls) => {
    const wrap = document.createElement('span'); wrap.className = 'pulse-item';
    const n = document.createElement('span'); n.className = 'pulse-num' + (cls ? ' ' + cls : ''); n.textContent = num;
    wrap.appendChild(n);
    const l = document.createElement('span'); l.textContent = label;
    wrap.appendChild(l);
    return wrap;
  };
  const sep = () => { const s = document.createElement('span'); s.className = 'pulse-sep'; return s; };

  els.pulseStrip.appendChild(mk('breaking', breaking, 'breaking'));
  els.pulseStrip.appendChild(sep());
  els.pulseStrip.appendChild(mk('notable', notable, 'notable'));
  els.pulseStrip.appendChild(sep());
  els.pulseStrip.appendChild(mk('positive', positive, 'positive'));
  els.pulseStrip.appendChild(sep());
  els.pulseStrip.appendChild(mk('negative', negative, 'negative'));

  if (newSince > 0) {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'pulse-new';
    btn.textContent = newSince + (newSince === 1 ? ' new article since your last visit ↑' : ' new articles since your last visit ↑');
    btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
    els.pulseStrip.appendChild(btn);
  }
  document.title = breaking > 0 ? '(' + breaking + ') Newsfeed' : 'Newsfeed';
}

// ---------- Keyboard navigation ----------
function setFocus(idx) {
  const cards = [...els.stream.querySelectorAll('article')];
  if (!cards.length) return;
  cards.forEach(c => c.classList.remove('kbd-focus'));
  state.focusIdx = Math.max(0, Math.min(idx, cards.length - 1));
  const card = cards[state.focusIdx];
  card.classList.add('kbd-focus');
  card.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

document.addEventListener('keydown', (e) => {
  const tag = (e.target.tagName || '').toLowerCase();
  const typing = tag === 'input' || tag === 'select' || tag === 'textarea';
  if (e.key === 'Escape') { els.kbdOverlay.hidden = true; if (typing) e.target.blur(); return; }
  if (typing) return;
  if (currentTab !== 'news') return;

  if (e.key === '/') { e.preventDefault(); els.q.focus(); return; }
  if (e.key === '?') { els.kbdOverlay.hidden = !els.kbdOverlay.hidden; return; }
  if (e.key === 'j') { e.preventDefault(); setFocus(state.focusIdx + 1); return; }
  if (e.key === 'k') { e.preventDefault(); setFocus(state.focusIdx - 1); return; }
  if (e.key === 'Enter') {
    const cards = [...els.stream.querySelectorAll('article')];
    const card = cards[state.focusIdx];
    const link = card && card.querySelector('a.title');
    if (link) { markRead(articleId({url: link.href}), card); window.open(link.href, '_blank'); }
    return;
  }
  if (e.key === 's') {
    const cards = [...els.stream.querySelectorAll('article')];
    const card = cards[state.focusIdx];
    if (card) card.querySelector('.save-btn')?.click();
    return;
  }
});
els.kbdHint.addEventListener('click', () => { els.kbdOverlay.hidden = false; });
els.kbdClose.addEventListener('click', () => { els.kbdOverlay.hidden = true; });
els.kbdOverlay.addEventListener('click', (e) => { if (e.target === els.kbdOverlay) els.kbdOverlay.hidden = true; });

let picksLoaded = false;

function formatMarketCap(v) {
  if (v == null) return null;
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(2) + 'T';
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B';
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M';
  return '$' + v.toFixed(0);
}

function valuationText(f) {
  if (!f) return null;
  const parts = [];
  if (f.trailing_pe != null) parts.push('P/E ' + f.trailing_pe.toFixed(1));
  else if (f.forward_pe != null) parts.push('Fwd P/E ' + f.forward_pe.toFixed(1));
  const cap = formatMarketCap(f.market_cap);
  if (cap) parts.push(cap + ' cap');
  if (f.revenue_growth_pct != null) {
    const sign = f.revenue_growth_pct >= 0 ? '+' : '';
    parts.push('rev ' + sign + f.revenue_growth_pct.toFixed(0) + '%');
  }
  if (f.analyst_rating) {
    let s = 'Wall St.: ' + f.analyst_rating;
    if (f.analyst_target_price != null) s += ' (target $' + f.analyst_target_price.toFixed(0) + ')';
    parts.push(s);
  }
  return parts.length ? parts.join(' · ') : null;
}

function eventTypesText(counts) {
  if (!counts) return null;
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return null;
  return 'Recent: ' + entries.map(([type, n]) => type + (n > 1 ? ' ×' + n : '')).join(', ');
}

function pickRow(p) {
  const row = document.createElement('div');
  row.className = 'pickRow';

  const top = document.createElement('div');
  top.className = 'pickTop';

  const sym = document.createElement('span');
  sym.className = 'pickSymbol'; sym.textContent = p.symbol;
  top.appendChild(sym);

  const name = document.createElement('span');
  name.className = 'pickName'; name.textContent = p.name || '';
  top.appendChild(name);

  const change = document.createElement('span');
  change.className = 'pickChange';
  change.textContent = '+' + p.price_change_pct.toFixed(1) + '%';
  top.appendChild(change);
  row.appendChild(top);

  const meta = document.createElement('div');
  meta.className = 'pickMeta';
  const articleWord = p.article_count === 1 ? 'article' : 'articles';
  const tags = (p.matched_tags || []).slice(0, 3).join(', ');
  meta.textContent = p.article_count + ' ' + articleWord + (tags ? ' · ' + tags : '');
  row.appendChild(meta);

  const valuation = valuationText(p.fundamentals);
  if (valuation) {
    const sub = document.createElement('div');
    sub.className = 'pickSub'; sub.textContent = valuation;
    row.appendChild(sub);
  }

  const events = eventTypesText(p.event_type_counts);
  if (events) {
    const sub = document.createElement('div');
    sub.className = 'pickSub'; sub.textContent = events;
    row.appendChild(sub);
  }

  return row;
}

function renderPickList(containerId, items) {
  const el = document.getElementById(containerId);
  el.innerHTML = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'pickEmpty';
    empty.textContent = 'No tickers clear the bar right now.';
    el.appendChild(empty);
    return;
  }
  items.forEach(p => el.appendChild(pickRow(p)));
}

async function loadPicks() {
  const res = await fetch('/api/picks');
  const body = await res.json();
  renderPickList('picksTech', body.tech);
  renderPickList('picksHealthcare', body.healthcare);
  renderPickList('picksOther', body.other);
  picksLoaded = true;
}

function showTab(tab) {
  currentTab = tab;
  const isNews = tab === 'news';
  const isSaved = tab === 'saved';
  const isPicks = tab === 'picks';
  const isTrading = tab === 'trading';
  els.tabNews.setAttribute('aria-pressed', String(isNews));
  els.tabSaved.setAttribute('aria-pressed', String(isSaved));
  els.tabPicks.setAttribute('aria-pressed', String(isPicks));
  els.tabTrading.setAttribute('aria-pressed', String(isTrading));

  const narrow = window.matchMedia('(max-width: 1180px)').matches;

  // Rail (filters) only makes sense on the News tab
  els.rail.style.display = isNews ? '' : 'none';

  // Center column: News stream vs Saved stream vs Trading view
  document.querySelector('main').hidden = !isNews;
  els.savedStream.hidden = !isSaved;
  els.tradingView.hidden = !isTrading;
  if (isSaved) renderSaved();
  if (isTrading && !tradingInitialized) initTrading();

  // Right sidebar (Picks): always visible on wide screens; tab-controlled on narrow screens
  if (narrow) {
    els.picksView.hidden = !isPicks || isTrading;
    els.picksView.classList.toggle('mobile-visible', isPicks);
  } else {
    els.picksView.hidden = isTrading ? true : false;
  }
  if (!picksLoaded && !isTrading) loadPicks();
}

let debounceTimer;
function scheduleReload() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => load({ reset: true }), 300);
}

async function initFacets() {
  const res = await fetch('/api/facets');
  const facets = await res.json();
  els.catChips.innerHTML = '';
  const makeChip = (label, value) => {
    const chip = document.createElement('button');
    chip.type = 'button'; chip.className = 'rail-chip'; chip.setAttribute('aria-pressed', 'false');
    const span = document.createElement('span'); span.textContent = label;
    chip.appendChild(span);
    chip.addEventListener('click', () => {
      activeCategory = (activeCategory === value) ? '' : value;
      [...els.catChips.children].forEach(c => c.setAttribute('aria-pressed', 'false'));
      if (activeCategory) chip.setAttribute('aria-pressed', 'true');
      load({ reset: true });
    });
    return chip;
  };
  facets.categories.forEach(cat => els.catChips.appendChild(makeChip(cat, cat)));
  const breakingChip = document.createElement('button');
  breakingChip.type = 'button'; breakingChip.className = 'rail-chip'; breakingChip.setAttribute('aria-pressed', 'false');
  const bspan = document.createElement('span'); bspan.textContent = 'breaking';
  breakingChip.appendChild(bspan);
  breakingChip.addEventListener('click', () => {
    const on = breakingChip.getAttribute('aria-pressed') === 'true';
    breakingChip.setAttribute('aria-pressed', on ? 'false' : 'true');
    els.importance.value = on ? '' : 'breaking';
    load({ reset: true });
  });
  els.catChips.appendChild(breakingChip);

  els.tagList.innerHTML = '';
  facets.top_tags.slice(0, 25).forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.tag;
    els.tagList.appendChild(opt);
  });
}

els.q.addEventListener('input', scheduleReload);
[els.importance, els.sentiment].forEach(el => el.addEventListener('change', () => load({ reset: true })));
[els.ticker, els.tag].forEach(el => el.addEventListener('input', scheduleReload));
els.loadmore.addEventListener('click', () => load({ reset: false }));
els.tabNews.addEventListener('click', () => showTab('news'));
els.tabSaved.addEventListener('click', () => showTab('saved'));
els.tabPicks.addEventListener('click', () => showTab('picks'));
els.tabTrading.addEventListener('click', () => showTab('trading'));
els.rangeChips.addEventListener('click', (e) => {
  const btn = e.target.closest('.rail-chip');
  if (!btn) return;
  state.range = btn.dataset.range;
  [...els.rangeChips.querySelectorAll('.rail-chip')].forEach(c => c.setAttribute('aria-pressed', String(c === btn)));
  load({ reset: true });
});

updateSavedCount();
initFacets();
load({ reset: true });
loadPicks();
els.picksView.hidden = false;

// Record this visit's timestamp AFTER computing "new since last visit" for this
// session, so the pulse strip stays accurate until the page is reloaded/revisited.
window.addEventListener('beforeunload', () => {
  store.lastVisit = Date.now();
  saveStore();
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    store.lastVisit = Date.now();
    saveStore();
  }
});

// =====================================================================
// Trading tab — candlestick chart, indicators, support/resistance, RSI
// All numbers computed client-side from real /api/chart OHLCV data.
// Canvas-drawn (no chart library) to stay dependency-free and match the
// page's own visual language exactly.
// =====================================================================
let tradingInitialized = false;
let allSymbols = [];
let tradingSymbol = null;
let tradingDays = 90;
let tradingCandles = [];

async function initTrading() {
  tradingInitialized = true;
  const res = await fetch('/api/symbols');
  const body = await res.json();
  allSymbols = body.symbols || [];
  const defaultSym = allSymbols.find(s => s.symbol === 'NVDA') || allSymbols[0];
  if (defaultSym) loadSymbol(defaultSym.symbol);
  window.addEventListener('resize', () => { if (tradingCandles.length) drawCharts(); });
}

function ema(values, period) {
  const k = 2 / (period + 1);
  const out = [];
  let prev = null;
  for (const v of values) {
    if (v == null) { out.push(prev); continue; }
    prev = prev == null ? v : v * k + prev * (1 - k);
    out.push(prev);
  }
  return out;
}

function rsi(closes, period = 14) {
  if (closes.length < period + 1) return null;
  let gains = 0, losses = 0;
  for (let i = closes.length - period; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gains += diff; else losses -= diff;
  }
  const avgGain = gains / period, avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function supportResistance(candles) {
  if (candles.length < 5) return { support: null, resistance: null };
  const highs = candles.map(c => c.high).filter(v => v != null);
  const lows = candles.map(c => c.low).filter(v => v != null);
  return { support: Math.min(...lows), resistance: Math.max(...highs) };
}

async function loadSymbol(symbol) {
  tradingSymbol = symbol.toUpperCase();
  els.symbolSearch.value = tradingSymbol;
  const res = await fetch('/api/chart?symbol=' + encodeURIComponent(tradingSymbol) + '&days=' + tradingDays);
  const body = await res.json();
  tradingCandles = body.candles || [];
  const meta = allSymbols.find(s => s.symbol === tradingSymbol);

  if (!tradingCandles.length) {
    els.chartEmpty.hidden = false;
    els.tradingSymbolInfo.innerHTML = '<span class="sym">' + tradingSymbol + '</span>' + (meta ? ' <span class="nm">' + meta.name + '</span>' : '');
    els.levelsGrid.innerHTML = ''; els.momentumGrid.innerHTML = '';
    return;
  }
  els.chartEmpty.hidden = true;

  const last = tradingCandles[tradingCandles.length - 1];
  const prev = tradingCandles.length > 1 ? tradingCandles[tradingCandles.length - 2] : null;
  const chg = prev ? last.close - prev.close : 0;
  const chgPct = prev ? (chg / prev.close) * 100 : 0;
  const chgCls = chg >= 0 ? 'positive' : 'negative';
  const chgSign = chg >= 0 ? '+' : '';
  els.tradingSymbolInfo.innerHTML =
    '<span class="sym">' + tradingSymbol + '</span>' +
    (meta ? '<span class="nm">' + meta.name + '</span>' : '') +
    '<span class="px">$' + last.close.toFixed(2) + '</span>' +
    '<span class="chg ' + chgCls + '">' + chgSign + chg.toFixed(2) + ' (' + chgSign + chgPct.toFixed(2) + '%)</span>';

  renderAnalysis();
  drawCharts();
  loadSymbolNews(tradingSymbol);
  loadVerdict(tradingSymbol);
}

function renderAnalysis() {
  const closes = tradingCandles.map(c => c.close).filter(v => v != null);
  const { support, resistance } = supportResistance(tradingCandles);
  const last = closes[closes.length - 1];
  const emaArr20 = ema(closes, 20);
  const emaArr50 = ema(closes, 50);
  const rsiVal = rsi(closes, 14);
  const high90 = Math.max(...tradingCandles.map(c => c.high).filter(v => v != null));
  const low90 = Math.min(...tradingCandles.map(c => c.low).filter(v => v != null));

  const cell = (label, value, cls) => '<div class="analysis-cell"><div class="lbl">' + label + '</div><div class="val' + (cls ? ' ' + cls : '') + '">' + value + '</div></div>';

  els.levelsGrid.innerHTML =
    cell('Support', support != null ? '$' + support.toFixed(2) : '—', 'support') +
    cell('Resistance', resistance != null ? '$' + resistance.toFixed(2) : '—', 'resistance') +
    cell('Period high', '$' + high90.toFixed(2)) +
    cell('Period low', '$' + low90.toFixed(2));

  const rsiLabel = rsiVal == null ? '—' : rsiVal.toFixed(1) + (rsiVal >= 70 ? ' (overbought)' : rsiVal <= 30 ? ' (oversold)' : '');
  const emaTrend = emaArr20[emaArr20.length - 1] > emaArr50[emaArr50.length - 1] ? 'Bullish (EMA20 > EMA50)' : 'Bearish (EMA20 < EMA50)';
  els.momentumGrid.innerHTML =
    cell('RSI (14)', rsiLabel) +
    cell('EMA 20', emaArr20[emaArr20.length - 1] ? '$' + emaArr20[emaArr20.length - 1].toFixed(2) : '—') +
    cell('EMA 50', emaArr50[emaArr50.length - 1] ? '$' + emaArr50[emaArr50.length - 1].toFixed(2) : '—') +
    cell('Trend', emaTrend, emaTrend.startsWith('Bullish') ? 'support' : 'resistance');
}

async function loadSymbolNews(symbol) {
  els.symbolNews.innerHTML = '<p class="sn-empty">Loading…</p>';
  const res = await fetch('/api/articles?ticker=' + encodeURIComponent(symbol) + '&limit=6');
  const body = await res.json();
  if (!body.items.length) {
    els.symbolNews.innerHTML = '<p class="sn-empty">No recent articles mention ' + symbol + '.</p>';
    return;
  }
  els.symbolNews.innerHTML = body.items.map(item =>
    '<div class="sn-item"><a href="' + item.url + '" target="_blank" rel="noopener">' + item.title + '</a></div>'
  ).join('');
}

async function loadVerdict(symbol) {
  els.verdictBody.innerHTML = '<p class="verdict-loading">Loading AI read…</p>';
  let body;
  try {
    const res = await fetch('/api/verdict?symbol=' + encodeURIComponent(symbol));
    if (!res.ok) throw new Error('http ' + res.status);
    body = await res.json();
  } catch (err) {
    els.verdictBody.innerHTML = '<p class="verdict-error">Could not load AI read right now.</p>';
    return;
  }

  if (body.jev_error || !body.jev) {
    els.verdictBody.innerHTML = '<p class="verdict-error">' + (body.jev_error || 'AI read unavailable right now.') + '</p>';
    return;
  }

  const jev = body.jev;
  const readCls = jev.read; // bullish | neutral | bearish
  const probs = jev.read_probabilities || {};
  const riskLabels = ['low', 'moderate', 'elevated', 'high'];
  const riskLabel = riskLabels[Math.round(jev.risk_level)] || 'moderate';

  els.verdictBody.innerHTML =
    '<div class="verdict-read">' +
      '<span class="read-label ' + readCls + '">' + readCls + '</span>' +
      '<span class="read-confidence">' + Math.round(jev.read_confidence * 100) + '% confidence</span>' +
    '</div>' +
    '<div class="verdict-probs">' +
      '<span class="p-bull" style="flex:' + (probs.bullish || 0) + '"></span>' +
      '<span class="p-neutral" style="flex:' + (probs.neutral || 0) + '"></span>' +
      '<span class="p-bear" style="flex:' + (probs.bearish || 0) + '"></span>' +
    '</div>' +
    '<div class="verdict-risk"><span class="risk-dot ' + riskLabel + '"></span>Risk: ' + riskLabel + '</div>' +
    '<p class="verdict-disclaimer">Synthesized by Jev from real price trend, RSI, fundamentals (when available), and recent news for this symbol. Decision support only — not investment advice, no automated trading.</p>';
}

function drawCharts() {
  drawPriceChart();
  drawVolumeChart();
}

function drawPriceChart() {
  const canvas = els.priceCanvas;
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = (rect.height - 20) * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height - 20;
  ctx.clearRect(0, 0, W, H);

  const candles = tradingCandles.filter(c => c.close != null);
  if (!candles.length) return;
  const closes = candles.map(c => c.close);
  const highs = candles.map(c => c.high);
  const lows = candles.map(c => c.low);
  const emaArr20 = ema(closes, 20);
  const emaArr50 = ema(closes, 50);
  const { support, resistance } = supportResistance(candles);

  const padL = 54, padR = 10, padT = 10, padB = 4;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  let dataMin = Math.min(...lows), dataMax = Math.max(...highs);
  const pad = (dataMax - dataMin) * 0.08 || 1;
  dataMin -= pad; dataMax += pad;
  const yFor = v => padT + plotH * (1 - (v - dataMin) / (dataMax - dataMin));
  const xStep = plotW / candles.length;
  const xFor = i => padL + xStep * i + xStep / 2;

  // gridlines + y-axis labels
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.fillStyle = getCss('--ink-faint');
  ctx.font = '10px "JetBrains Mono", monospace';
  ctx.textAlign = 'right';
  const steps = 5;
  for (let i = 0; i <= steps; i++) {
    const v = dataMin + (dataMax - dataMin) * (i / steps);
    const y = yFor(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillText('$' + v.toFixed(0), padL - 6, y + 3);
  }

  // support / resistance lines
  if (els.toggleSR.checked && support != null) {
    ctx.strokeStyle = getCss('--positive'); ctx.setLineDash([4, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, yFor(support)); ctx.lineTo(W - padR, yFor(support)); ctx.stroke();
    ctx.strokeStyle = getCss('--negative');
    ctx.beginPath(); ctx.moveTo(padL, yFor(resistance)); ctx.lineTo(W - padR, yFor(resistance)); ctx.stroke();
    ctx.setLineDash([]);
  }

  // candlesticks
  const bodyW = Math.max(2, xStep * 0.6);
  candles.forEach((c, i) => {
    const x = xFor(i);
    const up = c.close >= c.open;
    ctx.strokeStyle = ctx.fillStyle = up ? getCss('--positive') : getCss('--negative');
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, yFor(c.high)); ctx.lineTo(x, yFor(c.low)); ctx.stroke();
    const yOpen = yFor(c.open), yClose = yFor(c.close);
    const top = Math.min(yOpen, yClose), h = Math.max(1, Math.abs(yClose - yOpen));
    ctx.fillRect(x - bodyW / 2, top, bodyW, h);
  });

  // EMA overlays
  const drawLine = (arr, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
    let started = false;
    arr.forEach((v, i) => {
      if (v == null) return;
      const x = xFor(i), y = yFor(v);
      if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };
  if (els.toggleEMA20.checked) drawLine(emaArr20, getCss('--amber'));
  if (els.toggleEMA50.checked) drawLine(emaArr50, '#7a9fd4');
}

function drawVolumeChart() {
  const canvas = els.volumeCanvas;
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height;
  ctx.clearRect(0, 0, W, H);

  const candles = tradingCandles.filter(c => c.volume != null);
  if (!candles.length) return;
  const padL = 54, padR = 10;
  const plotW = W - padL - padR;
  const maxVol = Math.max(...candles.map(c => c.volume));
  const xStep = plotW / candles.length;
  const barW = Math.max(1, xStep * 0.6);

  candles.forEach((c, i) => {
    const x = padL + xStep * i + xStep / 2;
    const h = maxVol ? (c.volume / maxVol) * (H - 4) : 0;
    const up = c.close >= c.open;
    ctx.fillStyle = up ? 'rgba(95,168,124,0.5)' : 'rgba(194,90,90,0.5)';
    ctx.fillRect(x - barW / 2, H - h, barW, h);
  });
}

function getCss(varName) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
}

// Symbol search dropdown
els.symbolSearch.addEventListener('input', () => {
  const q = els.symbolSearch.value.trim().toUpperCase();
  if (!q) { els.symbolDropdown.hidden = true; return; }
  const matches = allSymbols.filter(s => s.symbol.includes(q) || s.name.toUpperCase().includes(q)).slice(0, 12);
  if (!matches.length) { els.symbolDropdown.hidden = true; return; }
  els.symbolDropdown.innerHTML = matches.map(s =>
    '<div class="symbol-option" data-symbol="' + s.symbol + '"><span class="sym">' + s.symbol + '</span><span class="nm">' + s.name + '</span></div>'
  ).join('');
  els.symbolDropdown.hidden = false;
});
els.symbolDropdown.addEventListener('click', (e) => {
  const opt = e.target.closest('.symbol-option');
  if (!opt) return;
  els.symbolDropdown.hidden = true;
  loadSymbol(opt.dataset.symbol);
});
els.symbolSearch.addEventListener('focus', () => { if (els.symbolSearch.value.trim()) els.symbolDropdown.hidden = false; });
document.addEventListener('click', (e) => {
  if (!els.symbolSearch.contains(e.target) && !els.symbolDropdown.contains(e.target)) els.symbolDropdown.hidden = true;
});

// Chart range chips
els.chartRangeChips.addEventListener('click', (e) => {
  const btn = e.target.closest('.rail-chip');
  if (!btn) return;
  tradingDays = parseInt(btn.dataset.days, 10);
  [...els.chartRangeChips.querySelectorAll('.rail-chip')].forEach(c => c.setAttribute('aria-pressed', String(c === btn)));
  if (tradingSymbol) loadSymbol(tradingSymbol);
});

// Overlay toggles just redraw, no refetch
[els.toggleEMA20, els.toggleEMA50, els.toggleSR].forEach(cb => cb.addEventListener('change', () => { if (tradingCandles.length) drawCharts(); }));
</script>
</body></html>
"""
