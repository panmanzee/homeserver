PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>taskbot</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f6f7fb; --card: #ffffff; --text: #1c1e21; --muted: #6b7280;
    --accent: #3b82f6; --border: #e5e7eb; --done: #9ca3af;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0f1115; --card: #1a1d23; --text: #e6e6e6; --muted: #9aa0aa;
            --accent: #5b9bff; --border: #2b2f37; --done: #6b7280; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI",
         system-ui, sans-serif; background: var(--bg); color: var(--text); }
  .wrap { max-width: 560px; margin: 0 auto; padding: 1rem 1rem 3rem; }
  header { position: sticky; top: 0; background: var(--bg); padding: .75rem 0; z-index: 5; }
  .datebar { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
  .datebar h1 { font-size: 1.1rem; margin: 0; font-weight: 600; }
  .navbtn { background: var(--card); border: 1px solid var(--border); color: var(--text);
            border-radius: 8px; padding: .5rem .75rem; font-size: 1rem; cursor: pointer; min-width: 44px; }
  .navbtn:active { transform: scale(.96); }
  .strip { display: flex; gap: .35rem; margin-top: .6rem; overflow-x: auto; }
  .strip button { flex: 1; min-width: 44px; padding: .5rem .3rem; border-radius: 8px;
                  border: 1px solid var(--border); background: var(--card); color: var(--text);
                  font-size: .8rem; cursor: pointer; }
  .strip button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .composer { display: flex; gap: .5rem; margin: 1rem 0; }
  .composer input { flex: 1; padding: .8rem .9rem; border-radius: 10px; border: 1px solid var(--border);
                     background: var(--card); color: var(--text); font: inherit; min-height: 44px; }
  .composer button { padding: .8rem 1.1rem; border-radius: 10px; border: none;
                      background: var(--accent); color: #fff; font: inherit; font-weight: 600;
                      cursor: pointer; min-height: 44px; }
  .composer button:disabled { opacity: .5; }
  .toast { font-size: .85rem; color: var(--muted); min-height: 1.2rem; margin: -.5rem 0 .75rem; }
  section.group { margin-bottom: 1.25rem; }
  section.group h2 { font-size: .75rem; text-transform: uppercase; letter-spacing: .04em;
                      color: var(--muted); margin: 0 0 .5rem; }
  .task { display: flex; align-items: center; gap: .6rem; background: var(--card);
          border: 1px solid var(--border); border-radius: 10px; padding: .7rem .8rem; margin-bottom: .5rem; }
  .task .time { font-variant-numeric: tabular-nums; color: var(--muted); font-size: .85rem; min-width: 3.2rem; }
  .task .title { flex: 1; }
  .task.done .title { text-decoration: line-through; color: var(--done); }
  .check { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--border);
           background: transparent; cursor: pointer; flex: none; }
  .check.checked { background: var(--accent); border-color: var(--accent); }
  .cal, .del { background: none; border: none; cursor: pointer; font-size: 1.05rem; flex: none;
               color: var(--muted); padding: .2rem; }
  .cal.on { color: var(--accent); }
  .empty { color: var(--muted); text-align: center; padding: 2rem 0; }
</style></head><body>
<div class="wrap">
  <header>
    <div class="datebar">
      <button class="navbtn" id="prev">‹</button>
      <h1 id="dateLabel">Today</h1>
      <button class="navbtn" id="next">›</button>
    </div>
    <div class="strip" id="strip"></div>
  </header>
  <div class="composer">
    <input id="msg" placeholder="Add a task or ask something…" autocomplete="off">
    <button id="send">Add</button>
  </div>
  <div class="toast" id="toast"></div>
  <div id="lists"></div>
</div>
<script>
function fmt(d) { const p = n => String(n).padStart(2, '0');
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()); }
function isToday(d) { return fmt(d) === fmt(new Date()); }
let current = new Date();

function renderStrip() {
  const strip = document.getElementById('strip');
  strip.innerHTML = '';
  for (let i = -3; i <= 3; i++) {
    const d = new Date(current); d.setDate(d.getDate() + i);
    const b = document.createElement('button');
    b.textContent = d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
    if (i === 0) b.classList.add('active');
    b.onclick = () => { current = d; load(); };
    strip.appendChild(b);
  }
}

function renderLabel() {
  document.getElementById('dateLabel').textContent = isToday(current)
    ? 'Today' : current.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

async function load() {
  renderLabel(); renderStrip();
  const day = fmt(current);
  const tasks = await (await fetch('/api/tasks?day=' + day)).json();
  const lists = document.getElementById('lists');
  lists.innerHTML = '';
  if (!tasks.length) {
    lists.innerHTML = '<div class="empty">Nothing here yet — try the box above.</div>';
    return;
  }
  const timed = tasks.filter(t => t.scheduled_start).sort((a, b) => a.scheduled_start.localeCompare(b.scheduled_start));
  const allday = tasks.filter(t => !t.scheduled_start);
  for (const [label, group] of [['Timed', timed], ['All day', allday]]) {
    if (!group.length) continue;
    const sec = document.createElement('section');
    sec.className = 'group';
    sec.innerHTML = '<h2>' + label + '</h2>';
    for (const t of group) sec.appendChild(taskRow(t));
    lists.appendChild(sec);
  }
}

function taskRow(t) {
  const row = document.createElement('div');
  row.className = 'task' + (t.status === 'done' ? ' done' : '');
  const check = document.createElement('button');
  check.className = 'check' + (t.status === 'done' ? ' checked' : '');
  check.onclick = async () => { await fetch('/api/tasks/' + t.id + '/complete', { method: 'POST' }); load(); };
  const time = document.createElement('span');
  time.className = 'time';
  time.textContent = t.scheduled_start ? new Date(t.scheduled_start).toLocaleTimeString(undefined,
    { hour: '2-digit', minute: '2-digit' }) : '';
  const title = document.createElement('span');
  title.className = 'title'; title.textContent = t.title;
  const cal = document.createElement('button');
  cal.className = 'cal' + (t.synced ? ' on' : '');
  cal.textContent = '📅';
  cal.onclick = async () => {
    if (t.synced) return;
    await fetch('/api/tasks/' + t.id + '/calendar', { method: 'POST' });
    load();
  };
  const del = document.createElement('button');
  del.className = 'del'; del.textContent = '×';
  del.onclick = async () => { await fetch('/api/tasks/' + t.id, { method: 'DELETE' }); load(); };
  row.append(check, time, title, cal, del);
  return row;
}

document.getElementById('prev').onclick = () => { current.setDate(current.getDate() - 1); load(); };
document.getElementById('next').onclick = () => { current.setDate(current.getDate() + 1); load(); };

const sendBtn = document.getElementById('send');
const input = document.getElementById('msg');
const toast = document.getElementById('toast');
async function send() {
  const text = input.value.trim();
  if (!text) return;
  sendBtn.disabled = true; toast.textContent = 'thinking…';
  try {
    const r = await fetch('/api/message', { method: 'POST', headers: { 'content-type': 'application/json' },
                                            body: JSON.stringify({ text }) });
    const d = await r.json();
    toast.textContent = d.reply || '';
    input.value = '';
  } catch (e) {
    toast.textContent = 'request failed';
  } finally {
    sendBtn.disabled = false;
    load();
  }
}
sendBtn.onclick = send;
input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

load();
</script></body></html>
"""
