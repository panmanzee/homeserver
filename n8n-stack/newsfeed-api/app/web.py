PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Newsfeed</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #10141b; --surface: #171d27; --text: #e9e6de; --text-dim: #8992a3;
    --rule: #232b38; --breaking: #e2543d; --notable: #d9a441;
    --positive: #4fa97a; --negative: #c24b62; --accent: #5b8def;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans Thai",
          "Leelawadee UI", sans-serif;
  }
  .wrap { max-width: 680px; margin: 0 auto; padding: 0 1rem 3rem; }

  header {
    position: sticky; top: 0; z-index: 5; background: var(--bg);
    padding: 1rem 0 .75rem; border-bottom: 1px solid var(--rule);
  }
  header h1 { font-size: 1.05rem; font-weight: 600; margin: 0 0 .7rem; }
  .search {
    width: 100%; padding: .6rem .8rem; font: inherit; color: var(--text);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 8px;
  }
  .search:focus { outline: 2px solid var(--accent); outline-offset: 1px; }

  .chips { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .6rem; }
  .chip {
    padding: .35rem .7rem; font: inherit; font-size: .85rem; color: var(--text-dim);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 999px;
    cursor: pointer;
  }
  .chip[aria-pressed="true"] { color: var(--bg); background: var(--accent); border-color: var(--accent); }
  .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

  details.more { margin-top: .6rem; }
  details.more summary {
    color: var(--text-dim); font-size: .85rem; cursor: pointer; list-style: none;
  }
  details.more summary::-webkit-details-marker { display: none; }
  .more-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: .6rem;
  }
  .more-grid label { font-size: .78rem; color: var(--text-dim); display: block; margin-bottom: .2rem; }
  .more-grid select, .more-grid input {
    width: 100%; padding: .4rem .5rem; font: inherit; font-size: .85rem; color: var(--text);
    background: var(--surface); border: 1px solid var(--rule); border-radius: 6px;
  }

  .day { margin: 1.4rem 0 .5rem; font-size: .8rem; color: var(--text-dim); font-weight: 600; }

  article {
    background: var(--surface); border-left: 3px solid var(--rule);
    border-radius: 0 8px 8px 0; padding: .75rem .9rem; margin-bottom: .6rem;
  }
  article.breaking { border-left-color: var(--breaking); }
  article.notable { border-left-color: var(--notable); }

  .row1 { display: flex; align-items: baseline; justify-content: space-between; gap: .6rem; }
  .badge { font-size: .72rem; font-weight: 600; }
  .badge.breaking { color: var(--breaking); }
  .badge.notable { color: var(--notable); }

  article a.title {
    color: var(--text); text-decoration: none; font-weight: 600; font-size: .98rem;
  }
  article a.title:hover { text-decoration: underline; }

  .summary { margin: .45rem 0 0; font-size: .92rem; line-height: 1.7; color: var(--text); }

  .meta {
    display: flex; flex-wrap: wrap; align-items: center; gap: .5rem;
    margin-top: .5rem; font-size: .78rem; color: var(--text-dim);
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .dot.positive { background: var(--positive); }
  .dot.negative { background: var(--negative); }
  .dot.neutral { background: var(--text-dim); }
  .pill {
    font-size: .72rem; color: var(--text-dim); border: 1px solid var(--rule);
    border-radius: 5px; padding: .05rem .4rem;
  }
  .time { margin-left: auto; }

  .empty, .end {
    text-align: center; color: var(--text-dim); padding: 2.5rem 1rem; font-size: .9rem;
  }
  .loadmore {
    display: block; margin: 1.2rem auto 0; padding: .55rem 1.4rem; font: inherit;
    color: var(--text); background: var(--surface); border: 1px solid var(--rule);
    border-radius: 8px; cursor: pointer;
  }
  .loadmore:hover { border-color: var(--accent); }
  .loadmore[disabled] { opacity: .5; cursor: default; }

  @media (max-width: 480px) {
    .more-grid { grid-template-columns: 1fr; }
  }
</style></head>
<body>
<div class="wrap">
  <header>
    <h1>Newsfeed</h1>
    <input class="search" id="q" type="search" placeholder="Search titles and topics — try &quot;thailand&quot;">
    <div class="chips" id="catChips"></div>
    <details class="more">
      <summary>+ filters</summary>
      <div class="more-grid">
        <div>
          <label for="importance">Importance</label>
          <select id="importance">
            <option value="">Any</option>
            <option value="breaking">Breaking</option>
            <option value="notable">Notable</option>
            <option value="routine">Routine</option>
          </select>
        </div>
        <div>
          <label for="sentiment">Sentiment</label>
          <select id="sentiment">
            <option value="">Any</option>
            <option value="positive">Positive</option>
            <option value="negative">Negative</option>
            <option value="neutral">Neutral</option>
          </select>
        </div>
        <div>
          <label for="ticker">Ticker</label>
          <input id="ticker" placeholder="e.g. AAPL">
        </div>
        <div>
          <label for="tag">Tag</label>
          <input id="tag" placeholder="e.g. ai-chips" list="tagList">
          <datalist id="tagList"></datalist>
        </div>
      </div>
    </details>
  </header>

  <div id="stream"></div>
  <button class="loadmore" id="loadmore" hidden>Load more</button>
</div>

<script>
const state = { offset: 0, limit: 30, items: [] };
const els = {
  q: document.getElementById('q'),
  catChips: document.getElementById('catChips'),
  importance: document.getElementById('importance'),
  sentiment: document.getElementById('sentiment'),
  ticker: document.getElementById('ticker'),
  tag: document.getElementById('tag'),
  tagList: document.getElementById('tagList'),
  stream: document.getElementById('stream'),
  loadmore: document.getElementById('loadmore'),
};
let activeCategory = '';

function currentParams(offset) {
  const p = new URLSearchParams();
  if (els.q.value.trim()) p.set('q', els.q.value.trim());
  if (activeCategory) p.set('category', activeCategory);
  if (els.importance.value) p.set('importance', els.importance.value);
  if (els.sentiment.value) p.set('sentiment', els.sentiment.value);
  if (els.ticker.value.trim()) p.set('ticker', els.ticker.value.trim());
  if (els.tag.value.trim()) p.set('tag', els.tag.value.trim());
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

function articleEl(item) {
  const art = document.createElement('article');
  if (item.importance === 'breaking' || item.importance === 'notable') {
    art.className = item.importance;
  }

  const row1 = document.createElement('div');
  row1.className = 'row1';
  const a = document.createElement('a');
  a.className = 'title'; a.href = item.url; a.target = '_blank'; a.rel = 'noopener';
  a.textContent = item.title;
  row1.appendChild(a);
  if (item.importance === 'breaking' || item.importance === 'notable') {
    const b = document.createElement('span');
    b.className = 'badge ' + item.importance;
    b.textContent = item.importance;
    row1.appendChild(b);
  }
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
    empty.textContent = 'No articles match — try a different search or clear filters.';
    els.stream.appendChild(empty);
    return;
  }
  let lastDay = append && state.items.length ? dayLabel(state.items[state.items.length - 1].published_at) : null;
  items.forEach(item => {
    const label = dayLabel(item.published_at);
    if (label !== lastDay) {
      const h = document.createElement('div');
      h.className = 'day'; h.textContent = label;
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
  els.loadmore.hidden = !body.has_more;
  els.loadmore.disabled = false;
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
    chip.type = 'button'; chip.className = 'chip'; chip.textContent = label;
    chip.setAttribute('aria-pressed', 'false');
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
  breakingChip.type = 'button'; breakingChip.className = 'chip'; breakingChip.textContent = 'breaking';
  breakingChip.setAttribute('aria-pressed', 'false');
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

initFacets();
load({ reset: true });
</script>
</body></html>
"""
