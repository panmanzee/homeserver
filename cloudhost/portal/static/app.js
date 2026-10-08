// pandeploy portal — vanilla ES module. User-supplied strings are only ever inserted as text nodes.

// ───────────────────────── helpers
const $ = (s, el = document) => el.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}

const ICONS = {
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  apps: '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  ext: '<path d="M14 3h7v7M21 3l-9 9M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
  play: '<path d="M7 4l13 8-13 8z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  redo: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8M21 3v5h-5"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  logs: '<path d="M4 6h16M4 12h10M4 18h16"/>',
  eye: '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  term: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  dice: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8.5 8.5h.01M15.5 15.5h.01M12 12h.01"/>',
};
function icon(name) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'icon'); s.setAttribute('fill', 'none');
  s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2');
  s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round'); s.setAttribute('aria-hidden', 'true');
  s.innerHTML = ICONS[name] || '';
  return s;
}

async function api(path, opts = {}) {
  const r = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: opts.body ? { 'Content-Type': 'application/json' } : {},
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: 'same-origin',
  });
  let data = null;
  try { data = await r.json(); } catch (_) { /* empty */ }
  if (!r.ok) {
    const d = data && data.detail;
    const e = new Error(typeof d === 'string' ? d : Array.isArray(d) ? 'Check the highlighted fields and try again.' : 'Something went wrong. Try again.');
    e.status = r.status;
    throw e;
  }
  return data;
}

function toast(msg, bad) {
  const t = h('div', { class: 'toast' + (bad ? ' bad' : ''), role: bad ? 'alert' : 'status' }, msg);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), bad ? 6000 : 3600);
}

const money = (n) => '$' + (Number.isInteger(n) ? n : n.toFixed(2));
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
async function copyText(t) {
  try { await navigator.clipboard.writeText(t); toast('Copied'); }
  catch (_) { toast('Copy failed — select the text manually.', true); }
}

// ───────────────────────── state
const S = { me: null, config: { invite_required: false }, plans: null, plansAt: 0, timers: [], apps: [], ui: { open: {}, logs: {}, compare: false } };
const stopTimers = () => { S.timers.forEach(clearInterval); S.timers = []; };
const isDark = () => document.documentElement.dataset.theme === 'dark';
function toggleTheme() {
  const t = isDark() ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('pd_theme', t); } catch (_) { /* private mode */ }
  document.querySelectorAll('[data-themebtn]').forEach((b) => b.replaceChildren(icon(isDark() ? 'sun' : 'moon')));
}
async function loadPlans(force) {
  if (!force && S.plans && Date.now() - S.plansAt < 30000) return S.plans;
  S.plans = await api('/plans'); S.plansAt = Date.now();
  return S.plans;
}
async function loadMe() {
  try { S.me = await api('/me'); } catch (e) { S.me = null; }
  return S.me;
}
const planOf = (id) => (S.plans?.plans || []).find((p) => p.id === id);

// ───────────────────────── shared chrome
function themeBtn() {
  return h('button', { class: 'iconbtn', 'data-themebtn': '', 'aria-label': 'Toggle light and dark theme', onclick: toggleTheme }, icon(isDark() ? 'sun' : 'moon'));
}
function logo() { return h('a', { class: 'logo', href: '#/' }, h('i'), 'pandeploy'); }

function marketingNav() {
  return h('header', { class: 'wrap nav' },
    logo(),
    h('a', { class: 'link hide-s', href: '#/pricing' }, 'Pricing'),
    themeBtn(),
    S.me
      ? h('a', { class: 'btn sm', href: '#/apps' }, 'Open dashboard')
      : [h('a', { class: 'link', href: '#/login' }, 'Sign in'), h('a', { class: 'btn sm', href: '#/signup' }, 'Get started')],
  );
}

function appShell(active, ...content) {
  const link = (id, href, label, ic) => h('a', { href, 'aria-current': active === id ? 'page' : null }, icon(ic), label);
  return h('div', {},
    h('header', { class: 'wrap nav' },
      logo(),
      h('button', { class: 'btn ghost sm', onclick: openPalette, 'aria-label': 'Open command palette' }, icon('search'), 'Search', h('kbd', {}, navigator.platform.includes('Mac') ? '⌘K' : 'Ctrl K')),
      themeBtn()),
    h('div', { class: 'wrap shell' },
      h('nav', { class: 'side', 'aria-label': 'Dashboard' },
        link('apps', '#/apps', 'Apps', 'apps'), link('machines', '#/machines', 'Machines', 'cpu'), link('billing', '#/billing', 'Billing', 'card'), link('account', '#/account', 'Account', 'user')),
      h('main', { id: 'main', tabindex: '-1' }, ...content)));
}

// ───────────────────────── plans UI (shared by landing + billing)
function planCard(p, opts = {}) {
  const current = opts.currentId === p.id;
  const maxUs = 33;
  const cmp = p.aws ? h('div', { class: 'cmp', 'aria-hidden': S.ui.compare ? null : 'true' },
    h('div', { class: 'row' }, h('span', {}, 'pandeploy'), h('div', { class: 'bar' }, h('i', { class: 'us', style: `--w:${Math.max(p.price ? (p.price / maxUs) * 100 : 1.5, 1.5)}%` })), h('b', {}, money(p.price))),
    h('div', { class: 'row' }, h('span', {}, 'AWS'), h('div', { class: 'bar' }, h('i', { class: 'aws', style: `--w:${(p.aws.usd / maxUs) * 100}%` })), h('b', {}, '≈ ' + money(p.aws.usd))),
    h('div', { class: 'cap' }, 'AWS: ' + p.aws.label)) : null;
  return h('article', { class: 'plan' + (current ? ' current' : '') },
    h('div', { class: 'pname' }, p.name, current ? h('span', { class: 'badge', style: 'margin-left:10px' }, 'Your plan') : null),
    h('div', { class: 'price' }, money(p.price), h('small', {}, p.price ? ' / month' : ' forever')),
    h('ul', {},
      h('li', {}, plural(p.max_apps, 'app')),
      h('li', {}, `${p.cpu} CPU and ${p.memory_mb} MB RAM per app`),
      h('li', {}, 'Your own https:// address'),
      h('li', {}, 'Images from Docker Hub, ghcr.io, quay.io')),
    cmp,
    opts.cta ? opts.cta(p, current) : null);
}
function compareSwitch() {
  const sw = h('button', { class: 'switch', role: 'switch', 'aria-checked': String(S.ui.compare), onclick: () => {
    S.ui.compare = !S.ui.compare;
    sw.setAttribute('aria-checked', String(S.ui.compare));
    document.querySelectorAll('.plans').forEach((el) => el.classList.toggle('compare', S.ui.compare));
    document.querySelectorAll('.cmp').forEach((el) => el.setAttribute('aria-hidden', S.ui.compare ? 'false' : 'true'));
  } }, 'Compare with AWS', h('span', { class: 'track' }));
  return sw;
}
const awsNote = () => h('p', { class: 'fine' }, `AWS figures are approximate list prices for an always-on container, checked ${S.plans?.aws_checked || ''}. AWS also gives you multiple regions, support and an uptime promise that one home server can't match.`);

// ───────────────────────── landing
const WORDS_A = ['quiet', 'brisk', 'amber', 'lunar', 'tiny', 'swift', 'mellow', 'bright', 'calm', 'nimble'];
const WORDS_B = ['otter', 'comet', 'harbor', 'maple', 'pixel', 'falcon', 'orbit', 'lotus', 'ember', 'moss'];
const randomName = () => `${WORDS_A[Math.floor(Math.random() * 10)]}-${WORDS_B[Math.floor(Math.random() * 10)]}`;

function heroConsole(plans) {
  const rack = plans.rack;
  const free = planOf('free') || { cpu: '0.25', memory_mb: 256, name: 'Free' };
  const leds = Array.from({ length: rack.slots_total }, (_, i) =>
    h('span', { class: 'led boot' + (i < rack.slots_total - rack.slots_free ? ' on' : ''), style: `animation-delay:${200 + i * 90}ms` }));
  let image = 'nginx:alpine', name = randomName(), busy = false, check = { ok: true };
  const avail = h('span', { class: 'avail' });
  const input = h('input', { value: name, maxlength: '30', 'aria-label': 'App name', spellcheck: 'false', autocomplete: 'off',
    style: 'width:' + Math.max(8, name.length + 1) + 'ch' });
  const log = h('div', { class: 'log', 'aria-live': 'polite' });
  const go = h('button', { class: 'btn sm', type: 'button' }, 'Deploy preview');
  const chips = ['nginx:alpine', 'traefik/whoami', 'nginxdemos/hello'].map((img) =>
    h('button', { class: 'chip', type: 'button', 'aria-pressed': String(img === image), onclick: (e) => {
      image = img; chips.forEach((c) => c.setAttribute('aria-pressed', String(c === e.currentTarget)));
    } }, img));
  let t;
  async function validate() {
    clearTimeout(t);
    t = setTimeout(async () => {
      try { check = await api('/slug-check?slug=' + encodeURIComponent(input.value)); } catch (_) { check = { ok: true }; }
      avail.className = 'avail ' + (check.ok ? 'ok' : 'no');
      avail.textContent = check.ok ? '✓ available' : check.reason;
    }, 250);
  }
  input.addEventListener('input', () => { input.style.width = Math.max(8, input.value.length + 1) + 'ch'; avail.textContent = ''; validate(); });
  validate();

  const say = (cls, text) => { log.append(h('div', { class: cls }, text)); };
  async function run() {
    if (busy) return;
    if (!check.ok) { input.focus(); return; }
    busy = true; go.disabled = true; log.replaceChildren();
    const nm = input.value.trim().toLowerCase();
    const next = leds.find((l) => !l.classList.contains('on'));
    const steps = [
      ['dim', `$ pandeploy deploy ${image} --name ${nm}`, 250],
      ['hot', `pulling ${image}`, 650],
      ['hot', `limits: ${free.cpu} CPU · ${free.memory_mb} MB RAM (${free.name} plan)`, 600],
      ['hot', 'issuing https certificate', 650],
      ['hot', `routing ${nm}.pandeploy.dev`, 600],
    ];
    if (next) next.className = 'led build';
    for (const [c, t2, d] of steps) { say(c, t2); await sleep(reduceMotion ? 10 : d); }
    if (next) next.className = 'led on';
    say('ok', '✓ live');
    log.append(h('div', { class: 'livechip' }, `https://${nm}.pandeploy.dev`));
    log.append(h('div', { class: 'dim', style: 'margin-top:10px' }, 'This was a preview. Create an account to deploy it for real.'));
    sessionStorage.setItem('pd_prefill', JSON.stringify({ name: nm, image }));
    log.append(h('div', { class: 'console-actions' }, h('a', { class: 'btn sm', href: S.me ? '#/apps' : '#/signup' }, S.me ? 'Deploy it for real' : 'Make it real — create account')));
    busy = false; go.disabled = false; go.textContent = 'Run again';
  }
  go.addEventListener('click', run);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') run(); });

  const chassis = h('div', { class: 'chassis' },
    h('div', { class: 'sheen' }),
    h('div', { class: 'bezel' }, h('span', { class: 'tag' }, 'rack-01 · preview'), leds),
    h('div', { class: 'screen' },
      h('div', { class: 'prompt' }, h('span', { class: 'sym' }, '$'), 'deploy ', input, h('span', { class: 'dom' }, '.pandeploy.dev'), avail),
      h('div', { class: 'chips', role: 'group', 'aria-label': 'Image' }, chips),
      h('div', { class: 'console-actions' }, go, h('span', { class: 'dim', style: 'color:#6D77A6;font-size:13px' }, `${rack.slots_free} of ${rack.slots_total} slots free right now`)),
      log));
  if (!reduceMotion && matchMedia('(pointer:fine)').matches) {
    chassis.addEventListener('pointermove', (e) => {
      const r = chassis.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
      chassis.style.setProperty('--ry', ((x - 0.5) * 7).toFixed(2) + 'deg');
      chassis.style.setProperty('--rx', ((0.5 - y) * 6).toFixed(2) + 'deg');
      chassis.style.setProperty('--mx', (x * 100) + '%'); chassis.style.setProperty('--my', (y * 100) + '%');
    });
    chassis.addEventListener('pointerleave', () => { chassis.style.setProperty('--rx', '0deg'); chassis.style.setProperty('--ry', '0deg'); });
  }
  return chassis;
}

async function viewLanding(scrollTo) {
  const plans = await loadPlans();
  const root = h('div', {},
    marketingNav(),
    h('main', { id: 'main', tabindex: '-1', class: 'wrap' },
      h('div', { class: 'hero' },
        h('div', {},
          h('h1', {}, 'Your app, online in a minute.'),
          h('p', { class: 'lede' }, 'Give us a container image. It runs on a real server in a home lab, and you get back a https address you can share.'),
          h('div', { class: 'cta-row' },
            h('a', { class: 'btn', href: S.me ? '#/apps' : '#/signup' }, S.me ? 'Open dashboard' : 'Create free account'),
            h('a', { class: 'btn ghost', href: '#/pricing' }, 'See plans')),
          h('p', { class: 'fine' }, 'Early access. Payments are in test mode, so nothing is ever charged.')),
        heroConsole(plans)),
      h('section', { class: 'block', id: 'how' },
        h('div', { class: 'sechead' }, h('div', {}, h('h2', {}, 'From image to link in three steps'))),
        h('div', { class: 'steps' },
          h('div', { class: 'step' }, h('h3', {}, 'Make an account'), h('p', {}, 'Email and a password. No card needed for the Free plan.')),
          h('div', { class: 'step' }, h('h3', {}, 'Name it and point at an image'), h('p', {}, 'Pick a name for your address and an image like nginx:alpine. We set the CPU and memory limits for your plan.')),
          h('div', { class: 'step' }, h('h3', {}, 'Share the link'), h('p', {}, 'Watch it go live, read its logs, restart or stop it any time from your dashboard.')))),
      h('section', { class: 'block', id: 'pricing' },
        h('div', { class: 'sechead' },
          h('div', {}, h('h2', {}, 'Simple plans'), h('p', { class: 'sub' }, 'Limits apply to each app. Upgrade or downgrade whenever you like.')),
          compareSwitch()),
        h('div', { class: 'plans' + (S.ui.compare ? ' compare' : '') }, plans.plans.map((p) => planCard(p, {
          cta: () => h('a', { class: 'btn' + (p.price ? '' : ' ghost'), href: S.me ? '#/billing' : '#/signup' }, p.price ? `Choose ${p.name}` : 'Start free') }))),
        awsNote()),
      h('section', { class: 'block' },
        h('div', { class: 'honest' },
          h('span', { class: 'led on', style: 'margin-top:2px' }),
          h('p', {}, h('strong', {}, 'Early access, honestly. '), 'pandeploy runs on one server in a home lab with a home internet connection. There is no uptime guarantee yet, so it suits side projects, demos and learning — not anything critical.'))),
      h('footer', { class: 'foot' }, h('span', {}, '© pandeploy'), h('span', {}, 'Built in a home lab in Thailand'))));
  mount(root);
  if (scrollTo) $('#' + scrollTo)?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
}

// ───────────────────────── auth
function viewAuth(mode) {
  const signup = mode === 'signup';
  const errBox = h('div', { class: 'formerr', role: 'alert', hidden: true });
  const fields = {};
  const mk = (id, label, type, extra = {}) => {
    const input = h('input', { class: 'input', id, name: id, type, autocomplete: extra.ac, required: true, 'aria-describedby': id + '-e', ...extra.attrs });
    const err = h('div', { class: 'err', id: id + '-e' });
    fields[id] = { input, err };
    return h('div', { class: 'field' }, h('label', { for: id }, label), extra.wrap ? extra.wrap(input) : input, extra.hint ? h('div', { class: 'hint' }, extra.hint) : null, err);
  };
  const rules = {
    name: (v) => (v.trim() ? '' : 'Enter your name.'),
    email: (v) => (/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(v.trim()) ? '' : 'Enter a valid email address.'),
    password: (v) => (!signup || v.length >= 10 ? (v ? '' : 'Enter your password.') : 'Use at least 10 characters.'),
  };
  const show = h('button', { class: 'btn quiet sm', type: 'button', 'aria-label': 'Show password', onclick: () => {
    const p = fields.password.input; p.type = p.type === 'password' ? 'text' : 'password';
    show.setAttribute('aria-label', p.type === 'password' ? 'Show password' : 'Hide password');
  } }, icon('eye'));
  const bar = h('div', { class: 'meter', 'aria-hidden': 'true' }, h('i'));
  const form = h('form', { novalidate: true },
    signup ? mk('name', 'Your name', 'text', { ac: 'name' }) : null,
    mk('email', 'Email', 'email', { ac: 'email', attrs: { inputmode: 'email' } }),
    mk('password', 'Password', 'password', { ac: signup ? 'new-password' : 'current-password',
      hint: signup ? 'At least 10 characters. A short sentence works well.' : null, wrap: (i) => h('div', { class: 'input-row' }, i, show) }),
    signup ? bar : null,
    signup && S.config.invite_required ? mk('invite', 'Invite code', 'text', { ac: 'off' }) : null,
    errBox,
    h('div', { style: 'margin-top:22px' }, h('button', { class: 'btn', style: 'width:100%', type: 'submit' }, signup ? 'Create account' : 'Sign in')));
  fields.password.input.addEventListener('input', () => { $('i', bar).style.setProperty('--w', Math.min(100, (fields.password.input.value.length / 16) * 100) + '%'); $('i', bar).style.background = fields.password.input.value.length >= 10 ? 'var(--run)' : 'var(--fail)'; });
  for (const k of Object.keys(rules)) fields[k]?.input.addEventListener('blur', () => validateField(k));
  function validateField(k) {
    const f = fields[k]; if (!f) return true;
    const msg = rules[k](f.input.value); f.err.textContent = msg; f.input.setAttribute('aria-invalid', msg ? 'true' : 'false');
    return !msg;
  }
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); errBox.hidden = true;
    const ok = Object.keys(rules).map(validateField).every(Boolean);
    if (!ok) { form.querySelector('[aria-invalid=true]')?.focus(); return; }
    const btn = $('button[type=submit]', form); btn.disabled = true; btn.replaceChildren(h('span', { class: 'spin' }), 'One moment');
    try {
      const body = { email: fields.email.input.value, password: fields.password.input.value };
      if (signup) { body.name = fields.name.input.value; body.invite = fields.invite?.input.value || ''; }
      await api(signup ? '/signup' : '/login', { method: 'POST', body });
      await loadMe();
      toast(signup ? 'Welcome to pandeploy' : 'Signed in');
      location.hash = '#/apps';
    } catch (err) {
      errBox.textContent = err.message; errBox.hidden = false;
      btn.disabled = false; btn.replaceChildren(signup ? 'Create account' : 'Sign in');
    }
  });
  mount(h('div', {}, marketingNav(),
    h('main', { id: 'main', tabindex: '-1', class: 'wrap authwrap' },
      h('div', { class: 'card' },
        h('h1', {}, signup ? 'Create your account' : 'Welcome back'),
        h('p', { class: 'muted' }, signup ? 'Free plan included. No card needed.' : 'Sign in to manage your apps.'),
        form,
        h('p', { class: 'swap' }, signup ? 'Already have an account? ' : 'New here? ', h('a', { href: signup ? '#/login' : '#/signup' }, signup ? 'Sign in' : 'Create an account'))))));
  (signup ? fields.name : fields.email).input.focus();
}

// ───────────────────────── dialogs
function dialog(content, cls = 'dlg') {
  const d = h('dialog', {}, h('div', { class: cls }, content));
  d.addEventListener('close', () => d.remove());
  document.body.append(d); d.showModal();
  return d;
}
function confirmDialog({ title, body, confirm, danger, typed }) {
  return new Promise((resolve) => {
    let result = false;
    const input = typed ? h('input', { class: 'input', 'aria-label': `Type ${typed} to confirm`, autocomplete: 'off' }) : null;
    const ok = h('button', { class: 'btn ' + (danger ? 'danger' : ''), disabled: !!typed, onclick: () => { result = true; d.close(); } }, confirm);
    if (input) input.addEventListener('input', () => { ok.disabled = input.value.trim() !== typed; });
    const d = dialog([h('h2', {}, title), h('p', { class: 'muted' }, body),
      typed ? h('div', { class: 'field' }, h('label', {}, `Type ${typed} to confirm`), input) : null,
      h('div', { class: 'actions' }, h('button', { class: 'btn ghost', onclick: () => d.close() }, 'Cancel'), ok)]);
    d.addEventListener('close', () => resolve(result));
  });
}

// ───────────────────────── apps
const STATE_LABEL = { running: 'Running', building: 'Starting…', failed: 'Failed', stopped: 'Stopped', unknown: 'Unknown' };
const ledClass = (s) => ({ running: 'on', building: 'build', failed: 'fail' }[s] || 'off');

async function refreshApps(rerender = true) {
  const { apps } = await api('/apps');
  const changed = JSON.stringify(apps) !== JSON.stringify(S.apps);
  S.apps = apps;
  if (S.me && S.me.apps_used !== apps.length) { S.me.apps_used = apps.length; drawStats(); }
  const open = Object.keys(S.ui.logs).filter((id) => S.ui.open[id]);
  await Promise.all(open.map(async (id) => {
    const l = S.ui.logs[id];
    try { l.text = (await api(`/apps/${id}/logs?kind=${l.kind}`)).logs; } catch (_) { /* keep old */ }
  }));
  if (rerender && (changed || open.length)) drawRack();
}

async function appAction(a, action) {
  try { await api(`/apps/${a.id}/${action}`, { method: 'POST' }); toast(({ restart: 'Restarting', stop: 'Stopping', start: 'Starting' })[action] + ` ${a.name}…`); }
  catch (e) { toast(e.message, true); }
  setTimeout(() => refreshApps(), 1500);
}
async function removeApp(a) {
  if (!(await confirmDialog({ title: `Delete ${a.name}?`, body: 'This stops the app and frees its slot. It can’t be undone.', confirm: 'Delete app', danger: true, typed: a.name }))) return;
  try { await api(`/apps/${a.id}`, { method: 'DELETE' }); toast(`Deleted ${a.name}`); delete S.ui.open[a.id]; await refreshApps(); await loadMe(); drawStats(); }
  catch (e) { toast(e.message, true); }
}

function unit(a) {
  const open = !!S.ui.open[a.id];
  const logs = S.ui.logs[a.id];
  const stopStart = a.state === 'running' || a.state === 'building'
    ? h('button', { class: 'btn ghost sm', onclick: () => appAction(a, 'stop') }, icon('stop'), 'Stop')
    : h('button', { class: 'btn ghost sm', onclick: () => appAction(a, 'start') }, icon('play'), 'Start');
  return h('article', { class: 'unit' },
    h('div', { class: 'ear' }, h('span', { class: 'led ' + ledClass(a.state), title: STATE_LABEL[a.state] })),
    h('div', { class: 'unit-main' },
      h('div', { class: 'unit-top' },
        h('span', { class: 'nm' }, a.name), h('span', { class: 'state ' + a.state }, STATE_LABEL[a.state] || a.state),
        h('a', { class: 'url', href: a.url, target: '_blank', rel: 'noopener' }, a.url.replace('https://', ''))),
      h('div', { class: 'unit-actions' },
        h('a', { class: 'btn sm', href: a.url, target: '_blank', rel: 'noopener' }, icon('ext'), 'Open'),
        h('button', { class: 'btn ghost sm', onclick: () => copyText(a.url) }, icon('copy'), 'Copy link'),
        h('button', { class: 'btn ghost sm', onclick: () => appAction(a, 'restart') }, icon('redo'), 'Restart'), stopStart,
        h('button', { class: 'btn ghost sm', onclick: () => openEnv(a) }, icon('key'), 'Variables'),
        h('button', { class: 'btn ghost sm', 'aria-expanded': String(open), onclick: () => {
          S.ui.open[a.id] = !open; if (!S.ui.logs[a.id]) S.ui.logs[a.id] = { kind: 'runtime', text: 'Loading…' };
          drawRack(); if (!open) refreshApps(); } }, icon('logs'), open ? 'Hide logs' : 'Logs'),
        h('button', { class: 'btn quiet sm', onclick: () => removeApp(a), 'aria-label': `Delete ${a.name}` }, icon('trash'))),
      a.state === 'failed' && a.error_tail ? h('div', { class: 'errtail' }, a.error_tail) : null,
      open ? h('div', {},
        h('div', { class: 'tabs', role: 'tablist' }, ['runtime', 'build'].map((k) =>
          h('button', { role: 'tab', 'aria-selected': String(logs.kind === k), onclick: () => { logs.kind = k; logs.text = 'Loading…'; drawRack(); refreshApps(); } }, k === 'runtime' ? 'App output' : 'Build'))),
        h('pre', { class: 'logbox', tabindex: '0', 'aria-label': 'Logs' }, logs.text)) : null,
      h('div', { class: 'muted', style: 'font-size:13px;margin-top:10px' }, `${a.image} · port ${a.port}`)));
}
function emptyUnit(label, onclick) {
  return h('button', { class: 'unit empty', style: 'text-align:left;font:inherit;color:inherit', onclick },
    h('div', { class: 'ear' }, h('span', { class: 'led off' })),
    h('div', { class: 'unit-main' }, icon('plus'), label));
}
function drawStats() {
  const el = $('#stats'); if (!el || !S.me) return;
  const l = S.me.limits;
  el.replaceChildren(
    h('div', { class: 'stat' }, h('b', {}, `${S.me.apps_used} of ${l.max_apps}`), h('span', {}, 'apps used')),
    h('div', { class: 'stat' }, h('b', {}, `${l.cpu_limit} CPU`), h('span', {}, 'per app')),
    h('div', { class: 'stat' }, h('b', {}, `${l.memory_limit_mb} MB`), h('span', {}, 'RAM per app')));
}
function drawRack() {
  const el = $('#rack'); if (!el) return;
  const max = S.me.limits.max_apps;
  const nodes = S.apps.map(unit);
  const empties = Math.min(Math.max(0, max - S.apps.length), 4);
  for (let i = 0; i < empties; i++) nodes.push(emptyUnit('Empty slot — deploy an app', () => openDeploy()));
  if (S.apps.length >= max) nodes.push(emptyUnit(`All ${plural(max, 'slot')} used — upgrade for more`, () => { location.hash = '#/billing'; }));
  el.replaceChildren(...nodes);
  if (!S.apps.length) el.replaceChildren(h('div', { class: 'empty-state' },
    h('h2', {}, 'Nothing running yet'),
    h('p', {}, 'Deploy your first app. Pick a name, point at an image, and it gets its own https address.'),
    h('button', { class: 'btn', onclick: () => openDeploy() }, icon('plus'), 'Deploy your first app')));
}

async function viewApps() {
  await Promise.all([loadMe(), loadPlans()]);
  if (!S.me) return;
  S.apps = [];
  mount(appShell('apps',
    h('div', { class: 'pagehead' },
      h('div', {}, h('h1', {}, 'Your apps'), h('p', { class: 'muted' }, `Hi ${S.me.user.name.split(' ')[0]} — you’re on the `, h('span', { class: 'badge' }, planOf(S.me.plan)?.name || S.me.plan), ' plan.')),
      h('button', { class: 'btn', onclick: () => openDeploy() }, icon('plus'), 'Deploy app')),
    h('div', { class: 'usage', id: 'stats' }),
    h('div', { class: 'rack', id: 'rack', 'aria-live': 'polite' })));
  drawStats();
  await refreshApps(false); drawRack();
  const pre = sessionStorage.getItem('pd_prefill');
  if (pre) { sessionStorage.removeItem('pd_prefill'); try { openDeploy(JSON.parse(pre)); } catch (_) { /* ignore */ } }
  S.timers.push(setInterval(async () => {
    if (document.hidden) return;
    try { await refreshApps(); } catch (e) { if (e.status === 401) { S.me = null; location.hash = '#/login'; } }
  }, 4000));
}

// ───────────────────────── virtual machines
const MSTATE = { creating: 'building', deleting: 'building', running: 'running', stopped: 'stopped', error: 'failed' };
const MLABEL = { creating: 'Creating…', deleting: 'Deleting…', running: 'Running', stopped: 'Stopped', error: 'Failed' };
let M = { machines: [], plan: 'free', rule: { max_machines: 0, sizes: [] }, sizes: {} };

async function loadMachines() { Object.assign(M, await api('/machines')); }
function sizeText(s) { return `${s.vcpu} vCPU · ${s.memory_mb} MB RAM · ${s.disk_gb} GB disk`; }

async function viewMachines() {
  await Promise.all([loadMe(), loadPlans()]);
  if (!S.me) return;
  await loadMachines();
  mount(appShell('machines',
    h('div', { class: 'pagehead' },
      h('div', {}, h('h1', {}, 'Virtual machines'),
        h('p', { class: 'muted' }, 'A whole Ubuntu computer of your own: log in, install anything, run any server. Open a terminal right here in the browser.')),
      h('button', { class: 'btn', onclick: openCreateMachine }, icon('plus'), 'Create machine')),
    h('div', { class: 'rack', id: 'mrack', 'aria-live': 'polite' })));
  drawMachines();
  S.timers.push(setInterval(async () => {
    if (document.hidden) return;
    try { await loadMachines(); drawMachines(); } catch (e) { if (e.status === 401) { S.me = null; location.hash = '#/login'; } }
  }, 3000));
}

function drawMachines() {
  const rack = $('#mrack'); if (!rack) return;
  const r = M.rule;
  const nodes = M.machines.map(machineUnit);
  if (!M.machines.length) {
    nodes.push(r.max_machines === 0
      ? h('div', { class: 'unit empty', style: 'display:block' }, h('h3', {}, 'Machines come with the Hobby and Pro plans'),
          h('p', { class: 'muted', style: 'margin:8px 0 14px' }, `You are on the ${M.plan} plan. Upgrade to rent a machine.`),
          h('a', { class: 'btn', href: '#/billing' }, 'See plans'))
      : emptyUnit('No machines yet. Create one', openCreateMachine));
  } else if (M.machines.length < r.max_machines) {
    nodes.push(emptyUnit('Empty slot. Create a machine', openCreateMachine));
  }
  rack.replaceChildren(...nodes);
}

function machineUnit(m) {
  const busy = m.state === 'creating' || m.state === 'deleting';
  const st = MSTATE[m.state] || 'unknown';
  return h('article', { class: 'unit' },
    h('div', { class: 'ear' }, h('span', { class: 'led ' + ledClass(st), title: MLABEL[m.state] || m.state })),
    h('div', { class: 'unit-main' },
      h('div', { class: 'unit-top' },
        h('span', { class: 'nm' }, m.name), h('span', { class: 'state ' + st }, MLABEL[m.state] || m.state),
        m.public ? h('a', { class: 'url', href: m.public.url, target: '_blank', rel: 'noopener' }, m.public.url.replace('https://', '')) : null),
      h('div', { class: 'unit-actions' },
        m.state === 'running' ? h('button', { class: 'btn sm', onclick: () => openTerminal(m) }, icon('term'), 'Terminal') : null,
        m.state === 'running' ? h('button', { class: 'btn ghost sm', onclick: () => machineAct(m, 'reboot') }, icon('redo'), 'Reboot') : null,
        m.state === 'running' ? h('button', { class: 'btn ghost sm', onclick: () => machineAct(m, 'stop') }, icon('stop'), 'Stop') : null,
        m.state === 'stopped' ? h('button', { class: 'btn ghost sm', onclick: () => machineAct(m, 'start') }, icon('play'), 'Start') : null,
        (m.state === 'running' || m.state === 'stopped') ? h('button', { class: 'btn ghost sm', onclick: () => openPublic(m) }, icon('ext'), 'Web address') : null,
        h('button', { class: 'btn quiet sm', disabled: m.state === 'deleting', onclick: () => removeMachine(m), 'aria-label': `Delete ${m.name}` }, icon('trash'))),
      m.state === 'error' ? h('div', { class: 'errtail' }, m.error || 'This machine could not be created. Delete it and try again.') : null,
      h('div', { class: 'muted', style: 'font-size:13px;margin-top:10px' }, `${m.image_label} · ${sizeText(m.specs)} · private address ${m.ip}${busy ? '' : ' · login: ' + m.user}`)));
}

async function machineAct(m, action) {
  try { await api(`/machines/${m.id}/${action}`, { method: 'POST' }); toast(action === 'stop' ? 'Shutting down…' : action === 'start' ? 'Starting…' : 'Rebooting…'); await loadMachines(); drawMachines(); }
  catch (ex) { toast(ex.message, true); }
}

async function removeMachine(m) {
  const ok = await confirmDialog({ title: `Delete ${m.name}?`, body: 'The machine and everything on its disk is destroyed. This cannot be undone.', confirm: 'Delete machine', danger: true, typed: m.name });
  if (!ok) return;
  try { await api(`/machines/${m.id}`, { method: 'DELETE' }); toast('Machine deleted'); await loadMachines(); drawMachines(); }
  catch (ex) { toast(ex.message, true); }
}

function openCreateMachine() {
  const r = M.rule;
  if (r.max_machines === 0) { toast(`Machines are not part of the ${M.plan} plan.`, true); location.hash = '#/billing'; return; }
  if (M.machines.length >= r.max_machines) { toast(`Your plan includes ${r.max_machines} machine${r.max_machines === 1 ? '' : 's'}. Upgrade to rent more.`, true); location.hash = '#/billing'; return; }
  const name = h('input', { class: 'input', id: 'mn', maxlength: '30', autocomplete: 'off', spellcheck: 'false', placeholder: 'my-server' });
  const sizes = r.sizes.map((k, i) => h('label', { class: 'sizepick' },
    h('input', { type: 'radio', name: 'msize', value: k, checked: i === 0 }),
    h('span', {}, h('strong', {}, M.sizes[k].label), h('small', {}, sizeText(M.sizes[k])))));
  const key = h('textarea', { class: 'input mono-area', id: 'mk', rows: '2', placeholder: 'ssh-ed25519 AAAA… (optional)', autocomplete: 'off', spellcheck: 'false' });
  const err = h('div', { class: 'formerr', role: 'alert', hidden: true });
  const submit = h('button', { class: 'btn', type: 'submit' }, 'Create machine');
  const form = h('form', { novalidate: true },
    h('div', { class: 'field' }, h('label', { for: 'mn' }, 'Machine name'), name),
    h('div', { class: 'field' }, h('label', {}, 'Size'), h('div', { class: 'sizes' }, sizes)),
    h('div', { class: 'field' }, h('label', { for: 'mk' }, 'SSH public key ', h('span', { class: 'muted', style: 'font-weight:400' }, '(optional)')), key,
      h('div', { class: 'hint' }, 'You can always log in with the terminal in your browser. A key is only needed if you want your own tools to connect from inside the machine network.')),
    h('p', { class: 'hint', style: 'margin-top:16px' }, 'Ubuntu 24.04 LTS. Ready in about a minute. It can reach the internet, nothing else on our network.'),
    err, h('div', { class: 'actions' }, h('button', { class: 'btn ghost', type: 'button', onclick: () => d.close() }, 'Cancel'), submit));
  const d = dialog(h('div', {}, h('h2', {}, 'Create a machine'), form));
  name.focus();
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); err.hidden = true;
    if (!name.value.trim()) { name.focus(); return; }
    submit.disabled = true; submit.replaceChildren(h('span', { class: 'spin' }), 'Creating');
    try {
      await api('/machines', { method: 'POST', body: { name: name.value, size: form.querySelector('input[name=msize]:checked').value, public_key: key.value } });
      d.close(); toast('Creating your machine…'); await loadMachines(); drawMachines();
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false; submit.disabled = false; submit.replaceChildren('Create machine');
      if (ex.status === 402) err.append(' ', h('a', { href: '#/billing', onclick: () => d.close() }, 'See plans'));
    }
  });
}

function loadScript(src) {
  return new Promise((res, rej) => { const el = document.createElement('script'); el.src = src; el.onload = res; el.onerror = rej; document.head.append(el); });
}
async function loadXterm() {
  if (window.Terminal && window.FitAddon) return;
  if (!document.getElementById('xterm-css')) document.head.append(h('link', { id: 'xterm-css', rel: 'stylesheet', href: '/static/vendor/xterm.css' }));
  await loadScript('/static/vendor/xterm.js'); await loadScript('/static/vendor/addon-fit.js');
}

async function openTerminal(m) {
  await loadXterm();
  const box = h('div', { class: 'termbox' });
  const d = dialog(h('div', {}, h('div', { class: 'termhead' }, h('h2', {}, m.name), h('button', { class: 'btn ghost sm', onclick: () => d.close() }, 'Close')), box), 'dlg termdlg');
  const term = new window.Terminal({ cursorBlink: true, fontSize: 14, fontFamily: 'ui-monospace, "Spline Sans Mono", monospace', theme: { background: '#0B1020' } });
  const fit = new window.FitAddon.FitAddon();
  term.loadAddon(fit); term.open(box); fit.fit(); term.focus();
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/machines/${m.id}/terminal`);
  ws.binaryType = 'arraybuffer';
  const enc = new TextEncoder();
  const sendSize = () => { try { fit.fit(); if (ws.readyState === 1) ws.send(`resize:${term.cols}x${term.rows}`); } catch (_) { /* closing */ } };
  ws.onopen = sendSize;
  ws.onmessage = (e) => term.write(typeof e.data === 'string' ? e.data : new Uint8Array(e.data));
  ws.onclose = () => term.write('\r\n\x1b[90m[connection closed]\x1b[0m\r\n');
  term.onData((data) => { if (ws.readyState === 1) ws.send(enc.encode(data)); });
  const ro = new ResizeObserver(sendSize); ro.observe(box);
  d.addEventListener('close', () => { ro.disconnect(); ws.close(); term.dispose(); });
}

function openPublic(m) {
  const on = h('input', { type: 'checkbox', id: 'pw', checked: !!m.public });
  const port = h('input', { class: 'input', id: 'pp', type: 'number', min: '1', max: '65535', value: String(m.public ? m.public.port : 80) });
  const link = h('div', { class: 'hint' }, m.public ? m.public.url : 'Off. Only you can reach the machine, through the terminal.');
  const err = h('div', { class: 'formerr', role: 'alert', hidden: true });
  const save = h('button', { class: 'btn', type: 'submit' }, 'Save');
  const form = h('form', { novalidate: true },
    h('div', { class: 'field' }, h('label', { class: 'switchrow' }, on, h('span', {}, 'Give this machine a public https address'))),
    h('div', { class: 'field' }, h('label', { for: 'pp' }, 'Port your web server listens on'), port, link),
    h('p', { class: 'hint', style: 'margin-top:14px' }, 'Start a web server on that port inside the machine (for example nginx or python3 -m http.server 8080). Anyone on the internet can open the address.'),
    err, h('div', { class: 'actions' }, h('button', { class: 'btn ghost', type: 'button', onclick: () => d.close() }, 'Close'), save));
  const d = dialog(h('div', {}, h('h2', {}, `Web address for ${m.name}`), form));
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); err.hidden = true; save.disabled = true;
    try {
      const res = await api(`/machines/${m.id}/public`, { method: 'PUT', body: { enabled: on.checked, port: Number(port.value) } });
      m.public = res.public; link.textContent = res.public ? res.public.url : 'Off. Only you can reach the machine, through the terminal.';
      toast(res.public ? 'Web address is live' : 'Web address removed'); await loadMachines(); drawMachines();
    } catch (ex) { err.textContent = ex.message; err.hidden = false; }
    save.disabled = false;
  });
}

// environment variables
function parseEnvText(text) {
  const env = {};
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq < 1) return { error: `Line ${i + 1}: write it as NAME=value.` };
    let value = line.slice(eq + 1).trim();
    if (value.length >= 2 && ((value[0] === '"' && value.endsWith('"')) || (value[0] === "'" && value.endsWith("'")))) value = value.slice(1, -1);
    env[line.slice(0, eq).trim()] = value;
  }
  return { env };
}
async function openEnv(a) {
  const list = h('div', { class: 'envlist' }, h('p', { class: 'muted' }, 'Loading…'));
  const key = h('input', { class: 'input', id: 'ek', placeholder: 'NAME', autocomplete: 'off', spellcheck: 'false', maxlength: '64' });
  const val = h('input', { class: 'input', id: 'ev', type: 'password', placeholder: 'value', autocomplete: 'new-password', spellcheck: 'false' });
  const err = h('div', { class: 'formerr', role: 'alert', hidden: true });
  const note = h('p', { class: 'hint', hidden: true }, 'Saved. Restart the app so it picks up the change.');
  const save = h('button', { class: 'btn', type: 'submit' }, 'Save');
  const draw = (keys) => list.replaceChildren(...(keys.length
    ? keys.map((k) => h('div', { class: 'envrow' }, h('code', {}, k),
        h('span', { class: 'muted' }, '••••••••'),
        h('button', { class: 'btn quiet sm', type: 'button', 'aria-label': `Delete ${k}`, onclick: async () => {
          try { await api(`/apps/${a.id}/env/${encodeURIComponent(k)}`, { method: 'DELETE' }); note.hidden = false; load(); }
          catch (ex) { toast(ex.message, true); } } }, icon('trash'))))
    : [h('p', { class: 'muted' }, 'No variables yet.')]));
  const load = async () => {
    try { draw((await api(`/apps/${a.id}/env`)).env.map((e) => e.key)); }
    catch (ex) { list.replaceChildren(h('p', { class: 'muted' }, ex.message)); }
  };
  const form = h('form', { novalidate: true, class: 'envform' },
    h('div', { class: 'field' }, h('label', { for: 'ek' }, 'Add or replace a variable'), h('div', { class: 'input-row' }, key, val)), err, h('div', { class: 'actions' }, save));
  const d = dialog(h('div', {},
    h('h2', {}, `Variables for ${a.name}`),
    h('p', { class: 'muted' }, 'Passwords, database addresses and API keys go here. Values are write-only: you can replace or delete them, but they are never shown again.'),
    list, form, note,
    h('div', { class: 'actions' },
      h('button', { class: 'btn ghost', type: 'button', onclick: () => d.close() }, 'Close'),
      h('button', { class: 'btn', type: 'button', onclick: async () => { await appAction(a, 'restart'); d.close(); } }, icon('redo'), 'Restart to apply'))));
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); err.hidden = true;
    if (!key.value.trim()) { key.focus(); return; }
    save.disabled = true;
    try { await api(`/apps/${a.id}/env`, { method: 'PUT', body: { key: key.value, value: val.value } }); key.value = ''; val.value = ''; note.hidden = false; await load(); }
    catch (ex) { err.textContent = ex.message; err.hidden = false; }
    save.disabled = false;
  });
  load();
}

// deploy dialog
function openDeploy(prefill = {}) {
  const l = S.me.limits;
  if (S.me.apps_used >= l.max_apps) {
    toast(`Your ${l.name} plan includes ${plural(l.max_apps, 'app')}. Upgrade to deploy more.`, true); location.hash = '#/billing'; return;
  }
  let check = { ok: false };
  const name = h('input', { class: 'input', id: 'dn', value: prefill.name || '', maxlength: '30', autocomplete: 'off', spellcheck: 'false', 'aria-describedby': 'dn-m' });
  const msg = h('div', { class: 'hint', id: 'dn-m' }, 'This becomes your address.');
  const image = h('input', { class: 'input', id: 'di', value: prefill.image || 'nginx:alpine', autocomplete: 'off', spellcheck: 'false' });
  const port = h('input', { class: 'input', id: 'dp', type: 'number', min: '1', max: '65535', value: '80' });
  const envBox = h('textarea', { class: 'input mono-area', id: 'de', rows: '3', placeholder: 'KEY=value', autocomplete: 'off', spellcheck: 'false' });
  const err = h('div', { class: 'formerr', role: 'alert', hidden: true });
  let t;
  const validate = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      if (!name.value) { msg.textContent = 'This becomes your address.'; msg.style.color = ''; check = { ok: false }; return; }
      try { check = await api('/slug-check?slug=' + encodeURIComponent(name.value)); } catch (_) { check = { ok: false, reason: 'Could not check the name.' }; }
      msg.textContent = check.ok ? `✓ ${name.value.toLowerCase()}.pandeploy.dev is available` : check.reason;
      msg.style.color = check.ok ? 'var(--run)' : 'var(--fail)';
      name.setAttribute('aria-invalid', String(!check.ok));
    }, 250);
  };
  name.addEventListener('input', validate);
  const picks = [['nginx:alpine', '80'], ['traefik/whoami', '80'], ['nginxdemos/hello', '80']].map(([img, p]) =>
    h('button', { class: 'chip', type: 'button', style: 'color:var(--ink);border-color:var(--line)', onclick: () => { image.value = img; port.value = p; } }, img));
  const submit = h('button', { class: 'btn', type: 'submit' }, 'Deploy');
  const body = h('div', {});
  const form = h('form', { novalidate: true },
    h('div', { class: 'field' }, h('label', { for: 'dn' }, 'App name'),
      h('div', { class: 'input-row' }, name, h('button', { class: 'btn quiet sm', type: 'button', 'aria-label': 'Suggest a name', onclick: () => { name.value = randomName(); validate(); name.focus(); } }, icon('dice'))), msg),
    h('div', { class: 'field' }, h('label', { for: 'di' }, 'Container image'), image,
      h('div', { class: 'chips', style: 'margin:4px 0 0' }, picks), h('div', { class: 'hint' }, 'From Docker Hub, ghcr.io or quay.io. Add a tag like :1.0 if you need one.')),
    h('div', { class: 'field' }, h('label', { for: 'dp' }, 'Port your app listens on'), port),
    h('div', { class: 'field' }, h('label', { for: 'de' }, 'Environment variables ', h('span', { class: 'muted', style: 'font-weight:400' }, '(optional)')), envBox,
      h('div', { class: 'hint' }, 'One per line, like DATABASE_URL=postgres://… Values are write-only: you can replace or delete them later, but not read them back. No single quotes or line breaks in values.')),
    h('p', { class: 'hint', style: 'margin-top:16px' }, `Runs with ${l.cpu_limit} CPU and ${l.memory_limit_mb} MB RAM on the ${l.name} plan.`),
    err,
    h('div', { class: 'actions' }, h('button', { class: 'btn ghost', type: 'button', onclick: () => d.close() }, 'Cancel'), submit));
  body.append(h('h2', {}, 'Deploy an app'), h('p', { class: 'muted' }, 'It will be live at its own https address in about a minute.'), form);
  const d = dialog(body);
  name.focus();
  if (prefill.name) validate();
  form.addEventListener('submit', async (e) => {
    e.preventDefault(); err.hidden = true;
    if (!name.value.trim()) { name.focus(); msg.textContent = 'Enter a name for your app.'; msg.style.color = 'var(--fail)'; return; }
    const parsed = parseEnvText(envBox.value);
    if (parsed.error) { err.textContent = parsed.error; err.hidden = false; envBox.focus(); return; }
    submit.disabled = true; submit.replaceChildren(h('span', { class: 'spin' }), 'Deploying');
    try {
      const res = await api('/apps', { method: 'POST', body: { name: name.value, image: image.value, port: Number(port.value), env: parsed.env } });
      await loadMe();
      showProgress(d, body, res.app);
    } catch (ex) {
      err.textContent = ex.message; err.hidden = false; submit.disabled = false; submit.replaceChildren('Deploy');
      if (ex.status === 402) err.append(' ', h('a', { href: '#/billing', onclick: () => d.close() }, 'See plans'));
    }
  });
}
function showProgress(d, body, app) {
  const steps = [['Created your app', 'done'], ['Pulling the image and starting', 'now'], ['Going live', '']];
  const list = h('div', { class: 'steps-live' });
  const paint = () => list.replaceChildren(...steps.map(([t, c]) => h('div', { class: 'sl ' + c }, h('span', { class: 'led' }), t)));
  paint();
  const footer = h('div', { class: 'actions' }, h('button', { class: 'btn ghost', onclick: () => d.close() }, 'Close — it keeps deploying'));
  body.replaceChildren(h('h2', {}, `Deploying ${app.name}`), h('p', { class: 'muted' }, 'First starts can take a minute while the image downloads.'), list, footer);
  let tries = 0;
  const poll = setInterval(async () => {
    tries++;
    if (!d.isConnected) { clearInterval(poll); return; }
    try {
      const a = await api(`/apps/${app.id}`);
      if (a.state === 'running') {
        clearInterval(poll); steps[1][1] = 'done'; steps[2][1] = 'done'; paint();
        body.replaceChildren(h('div', { class: 'paid pop' }, h('span', { class: 'led on', style: 'width:22px;height:22px' }), h('h2', {}, 'Your app is live'),
          h('a', { class: 'livechipLight', href: a.url, target: '_blank', rel: 'noopener', style: 'font:500 15px var(--mono)' }, a.url)),
          h('div', { class: 'actions' }, h('button', { class: 'btn ghost', onclick: () => d.close() }, 'Done'), h('a', { class: 'btn', href: a.url, target: '_blank', rel: 'noopener' }, icon('ext'), 'Open app')));
        refreshApps();
      } else if (a.state === 'failed') {
        clearInterval(poll); steps[1][1] = ''; paint();
        body.replaceChildren(h('h2', {}, 'It didn’t start'), h('p', { class: 'muted' }, 'The image downloaded or started with an error. Check the name, tag and port, then try again.'),
          a.error_tail ? h('div', { class: 'errtail' }, a.error_tail) : null,
          h('div', { class: 'actions' }, h('button', { class: 'btn', onclick: () => d.close() }, 'Back to my apps')));
        refreshApps();
      } else if (tries > 90) { clearInterval(poll); }
    } catch (_) { /* transient */ }
  }, 2500);
  d.addEventListener('close', () => clearInterval(poll));
}

// ───────────────────────── billing
async function viewBilling() {
  await Promise.all([loadMe(), loadPlans(true)]);
  if (!S.me) return;
  const cur = S.me.plan;
  const cta = (p, current) => current ? h('button', { class: 'btn ghost', disabled: true }, 'Current plan')
    : p.price === 0 ? h('button', { class: 'btn ghost', onclick: () => downgrade(p) }, 'Switch to Free')
    : h('button', { class: 'btn', onclick: () => openCheckout(p) }, `Choose ${p.name}`);
  const inv = S.me.invoices;
  mount(appShell('billing',
    h('div', { class: 'pagehead' }, h('div', {}, h('h1', {}, 'Billing'), h('p', { class: 'muted' }, 'Pick the plan that fits. Limits apply to each app.')), compareSwitch()),
    h('p', {}, h('span', { class: 'badge test' }, 'Test mode'), h('span', { class: 'muted' }, '  Payments here are simulated. No card is charged and no card details are collected.')),
    h('div', { class: 'plans' + (S.ui.compare ? ' compare' : ''), style: 'margin-top:22px' }, S.plans.plans.map((p) => planCard(p, { currentId: cur, cta }))),
    awsNote(),
    h('div', { class: 'panel' }, h('h2', {}, 'Invoices'),
      inv.length ? h('table', { class: 'inv' }, h('thead', {}, h('tr', {}, h('th', {}, 'Date'), h('th', {}, 'Description'), h('th', {}, 'Amount'))),
        h('tbody', {}, inv.map((i) => h('tr', {}, h('td', {}, new Date(i.created_at).toLocaleDateString()), h('td', {}, i.description), h('td', {}, money(i.amount_usd))))))
        : h('p', { class: 'muted' }, 'No invoices yet. They appear here after you choose a paid plan.'))));
}
async function downgrade(p) {
  if (!(await confirmDialog({ title: 'Switch to Free?', body: 'You keep your apps up to the Free limit, and your plan changes right away.', confirm: 'Switch to Free' }))) return;
  try { await api('/subscribe', { method: 'POST', body: { tier: p.id } }); toast('You’re on the Free plan'); viewBilling(); }
  catch (e) { toast(e.message, true); }
}
function openCheckout(p) {
  const card = h('div', { class: 'cc' }, h('div', { class: 'cc-in' },
    h('div', { class: 'cc-face' }, h('div', { class: 'cc-chip' }), h('div', { class: 'cc-num' }, '4242 4242 4242 4242'), h('div', { class: 'cc-meta' }, h('span', {}, 'TEST CARD'), h('span', {}, '12 / 34'))),
    h('div', { class: 'cc-face cc-back' }, h('div', { class: 'cc-stripe' }), h('div', { class: 'cc-meta' }, h('span', {}, 'CVC'), h('span', {}, '123')))));
  const flip = h('button', { class: 'btn quiet sm', type: 'button', onclick: () => card.classList.toggle('flip') }, 'Flip card');
  const err = h('div', { class: 'formerr', role: 'alert', hidden: true });
  const pay = h('button', { class: 'btn', onclick: async () => {
    pay.disabled = true; pay.replaceChildren(h('span', { class: 'spin' }), 'Processing'); err.hidden = true;
    try {
      await Promise.all([api('/subscribe', { method: 'POST', body: { tier: p.id } }), sleep(reduceMotion ? 10 : 1300)]);
      await loadMe();
      body.replaceChildren(h('div', { class: 'paid' },
        (() => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 80 80'); s.innerHTML = '<circle cx="40" cy="40" r="32"/><path d="M26 41l10 10 19-21"/>'; return s; })(),
        h('h2', {}, `You’re on ${p.name}`), h('p', { class: 'muted' }, 'Test payment complete. Your new limits apply right away.')),
        h('div', { class: 'actions' }, h('button', { class: 'btn ghost', onclick: () => d.close() }, 'Stay here'), h('a', { class: 'btn', href: '#/apps', onclick: () => d.close() }, 'Go deploy something')));
      d.addEventListener('close', () => { if (location.hash === '#/billing') viewBilling(); });
    } catch (e) { err.textContent = e.message; err.hidden = false; pay.disabled = false; pay.replaceChildren(`Pay ${money(p.price)} (test)`); }
  } }, `Pay ${money(p.price)} (test)`);
  const body = h('div', {}, h('h2', {}, `Upgrade to ${p.name}`), h('p', { class: 'muted' }, `${money(p.price)} per month · ${plural(p.max_apps, 'app')} · ${p.cpu} CPU and ${p.memory_mb} MB per app`),
    card, h('div', { style: 'display:flex;justify-content:space-between;align-items:center' }, h('span', { class: 'badge test' }, 'Test mode — no real charge'), flip),
    h('p', { class: 'hint muted', style: 'margin-top:10px;font-size:13px' }, 'This is a demo card. Nothing you do here is stored or sent to a payment company.'),
    err, h('div', { class: 'actions' }, h('button', { class: 'btn ghost', onclick: () => d.close() }, 'Cancel'), pay));
  const d = dialog(body);
}

// ───────────────────────── account
async function viewAccount() {
  await loadMe(); if (!S.me) return;
  mount(appShell('account',
    h('div', { class: 'pagehead' }, h('h1', {}, 'Account')),
    h('div', { class: 'panel', style: 'margin-top:0' }, h('h2', {}, 'Your details'),
      h('p', {}, h('strong', {}, S.me.user.name)), h('p', { class: 'muted' }, S.me.user.email),
      h('div', { style: 'margin-top:20px;display:flex;gap:10px;flex-wrap:wrap' },
        h('button', { class: 'btn ghost', onclick: toggleTheme }, 'Switch theme'),
        h('button', { class: 'btn ghost', onclick: signOut }, icon('out'), 'Sign out')))));
}
async function signOut() {
  try { await api('/logout', { method: 'POST' }); } catch (_) { /* already out */ }
  S.me = null; S.apps = []; location.hash = '#/'; toast('Signed out');
}

// ───────────────────────── command palette
function openPalette() {
  if (!S.me) { location.hash = '#/login'; return; }
  const items = [
    { label: 'Deploy a new app', ic: 'plus', run: () => { location.hash = '#/apps'; setTimeout(() => openDeploy(), 150); } },
    { label: 'Go to Apps', ic: 'apps', run: () => { location.hash = '#/apps'; } },
    { label: 'Go to Billing and plans', ic: 'card', run: () => { location.hash = '#/billing'; } },
    { label: 'Go to Account', ic: 'user', run: () => { location.hash = '#/account'; } },
    { label: isDark() ? 'Switch to light theme' : 'Switch to dark theme', ic: isDark() ? 'sun' : 'moon', run: toggleTheme },
    ...S.apps.map((a) => ({ label: `Open ${a.name}`, ic: 'ext', run: () => window.open(a.url, '_blank', 'noopener') })),
    { label: 'Sign out', ic: 'out', run: signOut },
  ];
  let sel = 0, shown = items;
  const input = h('input', { 'aria-label': 'Type a command', placeholder: 'Type a command…', role: 'combobox', 'aria-expanded': 'true', autocomplete: 'off' });
  const list = h('ul', { role: 'listbox' });
  const d = dialog([input, list], 'palette');
  const draw = () => {
    list.replaceChildren(...(shown.length ? shown.map((it, i) => h('li', { role: 'option', 'aria-selected': String(i === sel), onclick: () => run(it), onmousemove: () => { sel = i; draw(); } }, icon(it.ic), it.label))
      : [h('li', { class: 'none' }, 'No matches')]));
  };
  const run = (it) => { d.close(); it.run(); };
  input.addEventListener('input', () => { const q = input.value.toLowerCase(); shown = items.filter((i) => i.label.toLowerCase().includes(q)); sel = 0; draw(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); draw(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(sel - 1, 0); draw(); }
    else if (e.key === 'Enter' && shown[sel]) run(shown[sel]);
  });
  d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
  draw(); input.focus();
}
addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (!document.querySelector('dialog[open]')) openPalette(); }
});

// ───────────────────────── router
function mount(node) {
  document.querySelectorAll('dialog').forEach((d) => d.close());
  $('#app').replaceChildren(node);
}
const PROTECTED = new Set(['apps', 'machines', 'billing', 'account']);
async function route() {
  stopTimers();
  const key = (location.hash.replace(/^#\/?/, '') || '').split('?')[0];
  if (PROTECTED.has(key)) {
    if (!S.me) await loadMe();
    if (!S.me) { toast('Sign in to continue'); location.hash = '#/login'; return; }
  } else if (S.me === null && !S.checked) { await loadMe(); }
  S.checked = true;
  if ((key === 'login' || key === 'signup') && S.me) { location.hash = '#/apps'; return; }
  try {
    if (key === '' || key === 'pricing') await viewLanding(key === 'pricing' ? 'pricing' : null);
    else if (key === 'login') viewAuth('login');
    else if (key === 'signup') viewAuth('signup');
    else if (key === 'apps') await viewApps();
    else if (key === 'machines') await viewMachines();
    else if (key === 'billing') await viewBilling();
    else if (key === 'account') await viewAccount();
    else location.hash = '#/';
  } catch (e) {
    if (e.status === 401) { S.me = null; location.hash = '#/login'; return; }
    $('#app').replaceChildren(h('main', { class: 'wrap', id: 'main', style: 'padding:80px 0' }, h('h1', {}, 'Couldn’t load this page'), h('p', { class: 'muted', style: 'margin:12px 0 20px' }, e.message),
      h('button', { class: 'btn', onclick: route }, 'Try again')));
  }
  if (key !== '' && key !== 'pricing') $('#main')?.focus({ preventScroll: true });
  else if (key === '') scrollTo(0, 0);
}
addEventListener('hashchange', route);
(async () => {
  try { S.config = await api('/config'); } catch (_) { /* defaults */ }
  route();
})();
