PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>rag — study Q&A</title>
<style>
  :root { color-scheme: dark; }
  body { font: 16px/1.5 system-ui, sans-serif; max-width: 760px; margin: 2rem auto;
         padding: 0 1rem; background:#0f1115; color:#e6e6e6; }
  h1 { font-size: 1.2rem; } .muted { color:#8a8f98; font-size:.85rem; }
  textarea { width:100%; padding:.6rem; font:inherit; background:#1a1d23; color:inherit;
             border:1px solid #2b2f37; border-radius:6px; }
  button { margin-top:.5rem; padding:.5rem 1rem; font:inherit; border-radius:6px;
           border:0; background:#3b82f6; color:#fff; cursor:pointer; }
  button[disabled] { opacity:.5; cursor:default; }
  #answer { white-space:pre-wrap; margin-top:1.2rem; }
  #sources { margin-top:1rem; } #sources li { margin:.3rem 0; }
  code { background:#1a1d23; padding:.1rem .3rem; border-radius:4px; }
</style></head><body>
<h1>study Q&amp;A <span class="muted" id="stat"></span></h1>
<textarea id="q" rows="3" placeholder="Ask something about your material…"></textarea>
<button id="go">Ask</button>
<div id="answer"></div>
<ul id="sources"></ul>
<script>
async function stats(){
  try { const s = await (await fetch('/stats')).json();
    document.getElementById('stat').textContent =
      `· ${s.documents} docs / ${s.chunks} chunks · ${s.questions_today} asked today`;
  } catch(e){}
}
stats();
const go = document.getElementById('go');
go.onclick = async () => {
  const q = document.getElementById('q').value.trim();
  if(!q) return;
  go.disabled = true;
  document.getElementById('answer').textContent = 'thinking…';
  document.getElementById('sources').textContent = '';
  try {
    const r = await fetch('/ask', {method:'POST', headers:{'content-type':'application/json'},
                                   body: JSON.stringify({question:q})});
    if (!r.ok) {
      document.getElementById('answer').textContent = 'request failed (' + r.status + ')';
      return;
    }
    const d = await r.json();
    document.getElementById('answer').textContent = d.answer;
    const ul = document.getElementById('sources');
    ul.textContent = '';
    for (const s of (d.sources||[])) {
      const li = document.createElement('li');
      const code = document.createElement('code');
      code.textContent = s.filename + ' p.' + s.page;
      li.appendChild(code);
      li.appendChild(document.createTextNode(' — ' + s.snippet));
      ul.appendChild(li);
    }
  } catch(e) {
    document.getElementById('answer').textContent = 'request failed: ' + e;
  } finally { go.disabled = false; stats(); }
};
</script></body></html>
"""
