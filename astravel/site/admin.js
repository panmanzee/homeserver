import { h, icon, link, store, save, toast } from './core.js';
import { page } from './views.js';

const NAV = [['/admin', 'Dashboard', 'dash', 'dash'], ['/admin/users', 'Users', 'user', 'users'], ['/admin/reports', 'Reports', 'report', 'reports'],
  ['/admin/roles', 'Roles & Permissions', 'key', 'roles'], ['/admin/audit', 'Audit Log', 'doc', 'audit'], ['/admin/settings', 'Settings', 'gear', 'settings']];
const SVG = 'http://www.w3.org/2000/svg';
const sv = (tag, attrs, ...kids) => { const e = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); kids.flat().forEach((c) => c && e.append(c.nodeType ? c : document.createTextNode(c))); return e; };

function shell(active, top, body, cls = '') {
  top = (active === 'dash' || active === 'users') ? 32 : 0;
  const side = h('nav', { class: 'side', style: { top: top + 'px' }, 'aria-label': 'Admin' }, ...NAV.map(([href, label, ic, key]) => link(href, { class: key === active ? 'on' : '', 'aria-current': key === active ? 'page' : null }, icon(ic), label)));
  return page('admin', label(active), h('div', { class: 'adm ' + cls }, side, h('div', { class: 'main' }, ...body)));
}
const label = (k) => (NAV.find((n) => n[3] === k) || [])[1] || 'Admin';
const selectBox = (text, opts, props) => h('select', { class: 'a-sel', 'aria-label': text.replace(': All', ''), ...props }, ...opts.map((o) => h('option', { value: o }, o === 'All' ? text : o)));

function lineChart(w, hgt, pts, x0, y0, ys, gridY, xlabels, yl) {
  const s = sv('svg', { width: w, height: hgt, viewBox: `0 0 ${w} ${hgt}`, role: 'img', 'aria-label': 'Line chart' });
  gridY.forEach((y) => s.append(sv('line', { x1: x0, x2: w - 24, y1: y, y2: y, stroke: '#e5e7eb', 'stroke-dasharray': '3 3' })));
  s.append(sv('polyline', { points: pts.map(([x, y]) => `${x},${y}`).join(' '), fill: 'none', stroke: '#0f172a', 'stroke-width': 2, 'stroke-linejoin': 'round' }));
  pts.forEach(([x, y]) => s.append(sv('circle', { cx: x, cy: y, r: 3.5, fill: '#fff', stroke: '#0f172a', 'stroke-width': 2 })));
  xlabels.forEach(([x, t]) => s.append(sv('text', { x, y: ys, 'font-size': 11, fill: '#9ca3af', 'text-anchor': 'start' }, t)));
  (yl || []).forEach(([y, t]) => s.append(sv('text', { x: 24, y, 'font-size': 11, fill: '#9ca3af' }, t)));
  return s;
}

// ───────────────────────── dashboard
export function dashView() {
  const stat = (t, v, sub, up) => h('div', { class: 'card stat' }, h('h3', {}, t), h('b', {}, v), h('span', {}, up == null ? '' : h('i', {}, up ? '▲' : '▼'), sub));
  const live = h('div', { class: 'card chart' }, h('h3', {}, 'Real-time Activity (req/m)'), h('div', { class: 'live' }, 'Updates live'),
    lineChart(732, 301, [[61, 218], [155, 167], [250, 227], [344, 138], [438, 198], [532, 88], [627, 178], [721, 68]], 61, 0, 273, [57, 124, 190, 257],
      ['12:00', '12:10', '12:20', '12:30', '12:40', '12:50', '13:00'].map((t, i) => [75 + i * 103.5 - 14, t]), [[69, '100k'], [121, '75k'], [172, '50k'], [224, '25k'], [276, '0']]));
  const alerts = h('div', { class: 'card alerts' }, h('h3', {}, 'Alerts & Notifications'),
    ...[['API Gateway latency peak detected', '2m ago', 'f'], ['Database storage utilization > 85%', '15m ago', 'g'], ['SSL certificate renewal pending', '1h ago', ''], ['Backup job completed successfully', '4h ago', '']].map(([t, a, c]) => h('div', { class: 'alert' }, h('i', { class: c }), h('b', {}, t), h('small', {}, a))));
  const hrow = (top, n, b, w, p) => h('div', { class: 'hrow', style: { top: top + 'px' } }, h('span', { class: 'n' }, n), h('span', { class: 'b' }, b), h('span', { class: 't' }, h('i', { style: { width: w } })), h('span', { class: 'p' }, p));
  return shell('dash', 88, [
    h('div', { class: 'stats' }, stat('Active Users', '1,284', '4.3% vs yesterday', true), stat('Total Requests', '45.2K', '12.1% this hour', true), stat('Error Rate', '0.8%', '0.2% vs average', false), stat('Uptime', '99.97%', 'Healthy state')),
    h('div', { class: 'row2' }, live, alerts),
    h('div', { class: 'card health', style: { marginTop: '26px', height: '238px' } }, h('h3', {}, 'System Health & Services'), hrow(57, 'API Server', 'Healthy', '54%', '100%'), hrow(94, 'Database', 'Healthy', '54%', '100%'), hrow(131, 'CDN Cache Edge', 'Warning', '35%', '65%')),
  ], 'dash');
}

// ───────────────────────── users
export function usersView() {
  const a = store().admin; let rows = a.users.map((r, i) => ({ r, i, on: false }));
  const body = h('tbody'); const info = h('span', {}, ''); const search = h('input', { placeholder: 'Placeholder', 'aria-label': 'Search users' });
  const role = h('select', { class: 'a-sel', 'aria-label': 'Role', onchange: draw }, ...['All', 'Super Admin', 'Admin', 'Editor', 'Developer', 'Viewer'].map((o) => h('option', { value: o }, o === 'All' ? 'Role: All' : o)));
  const status = h('select', { class: 'a-sel', 'aria-label': 'Status', onchange: draw }, ...['All', 'Active', 'Inactive'].map((o) => h('option', { value: o }, o === 'All' ? 'Status: All' : o)));
  const joined = h('select', { class: 'a-sel', 'aria-label': 'Date joined', onchange: () => toast('Join dates are not part of the demo data') }, h('option', {}, 'Date Joined: All'), h('option', {}, 'Last 7 days'), h('option', {}, 'Last 30 days'));
  const head = h('input', { type: 'checkbox', class: 'ck', 'aria-label': 'Select all', onchange: (e) => { body.querySelectorAll('.ck').forEach((c) => { c.checked = e.target.checked; }); } });
  function draw() {
    const t = search.value.toLowerCase(); const shown = rows.filter(({ r }) => (role.value === 'All' || r[2] === role.value) && (status.value === 'All' || r[3] === status.value) && (r[0] + r[1]).toLowerCase().includes(t));
    body.replaceChildren(...shown.map(({ r, i }) => h('tr', {}, h('td', { style: { width: '40px' } }, h('input', { type: 'checkbox', class: 'ck', 'aria-label': `Select ${r[0]}` })),
      h('td', { class: 's' }, r[0]), h('td', {}, r[1]), h('td', {}, r[2]), h('td', {}, h('span', { class: 'badge-s' }, r[3])), h('td', {}, r[4]),
      h('td', {}, h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Edit ${r[0]}`, onclick: () => toast(`Edit ${r[0]} (demo)`) }, icon('pencil')),
        h('button', { class: 'icon-btn', type: 'button', 'aria-label': `Delete ${r[0]}`, onclick: () => { rows = rows.filter((x) => x.i !== i); toast(`Removed ${r[0]} (demo only)`); draw(); } }, icon('trash'))))));
    info.textContent = `Showing ${shown.length} of ${45 - (a.users.length - rows.length)} users`;
  }
  search.addEventListener('input', draw); draw();
  return shell('users', 88, [
    h('div', { class: 'fbar' }, role, status, joined, h('span', { class: 'grow' }), h('label', { class: 'a-search' }, search, icon('search'))),
    h('div', { class: 'card tcard', style: { padding: '20px 20px 0' } },
      h('table', { class: 'tbl fixed' }, h('colgroup', {}, ...[40, 196, 236, 156, 116, 283, 69].map((w) => h('col', { style: { width: w + 'px' } }))), h('thead', {}, h('tr', {}, h('th', {}, head), ...['Name', 'Email', 'Role', 'Status', 'Last Active'].map((t) => h('th', {}, t)), h('th', {}, 'Actions'))), body),
      h('div', { class: 'pager', style: { padding: '0' } }, info, h('div', { class: 'pg' }, h('button', { type: 'button' }, 'Previous'), h('button', { class: 'on', type: 'button' }, '1'), h('button', { type: 'button' }, '2'), h('button', { type: 'button' }, '3'), h('button', { type: 'button' }, 'Next'))))], '');
}

// ───────────────────────── reports
export function reportsView() {
  const bars = [54, 90, 72, 153, 107, 170, 125, 80, 107, 143, 98, 161];
  const g = sv('svg', { width: 556, height: 290, viewBox: '0 0 556 290', role: 'img', 'aria-label': 'Monthly user growth bar chart' });
  bars.forEach((v, i) => g.append(sv('rect', { x: 24 + i * 40, y: 237 - v, width: 32, height: v, fill: '#f3f4f6', stroke: '#1f2937', 'stroke-width': 1 })));
  ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].forEach((m, i) => g.append(sv('text', { x: 24 + i * 40 + 9, y: 265, 'font-size': 11, fill: '#9ca3af' }, m)));
  const rv = h('div', { class: 'card ch2' }, h('h3', {}, 'Request Volume (Area Peak)'),
    lineChart(556, 290, [[24, 202], [93, 157], [161, 211], [230, 130], [298, 184], [367, 85], [435, 165], [504, 67]], 24, 0, 265, [57, 117, 177, 237], [[24, 'W1'], [186, 'W2'], [350, 'W3'], [514, 'W4']]));
  const kpi = (t, v, s) => h('div', { class: 'card kpi' }, h('h4', {}, t), h('b', {}, v), h('span', {}, s));
  const rep = [['Monthly Security Audit', 'Oct 31, 2024', 'Security', 'Completed'], ['Quarterly Performance Review', 'Oct 15, 2024', 'Performance', 'Completed'], ['User Retention Analysis', 'Oct 01, 2024', 'Activity', 'Completed'], ['Server Bandwidth Spike Logs', 'Sep 24, 2024', 'Infrastructure', 'Archived']];
  const seg = h('div', { class: 'seg' }, ...['7d', '30d', '90d', '1y'].map((t, i) => h('button', { type: 'button', class: i === 1 ? 'on' : '', onclick: (e) => { seg.querySelectorAll('button').forEach((b) => b.classList.remove('on')); e.currentTarget.classList.add('on'); } }, t)));
  return shell('reports', 56, [
    h('div', { class: 'card range', style: { marginTop: '0' } }, h('span', { class: 'date' }, icon('cal'), 'From: Oct 1, 2024'), h('span', { class: 'date' }, icon('cal'), 'To: Oct 31, 2024'), h('span', { class: 'sep' }), seg, h('span', { style: { flex: 1 } }), h('button', { class: 'a-btn dark', type: 'button', onclick: () => toast('Range applied (demo data)') }, 'Apply Range')),
    h('div', { class: 'charts' }, h('div', { class: 'card ch2' }, h('h3', {}, 'User Growth (Monthly)'), g), rv),
    h('div', { class: 'kpis' }, kpi('New Users', '324', 'Avg: 10.8 per day'), kpi('Avg Session Duration', '4m 32s', 'Healthy range'), kpi('Peak Load', '2.1K req/s', 'Recorded on Monday'), kpi('Bounce Rate', '23%', 'Minimal user drops')),
    h('div', { class: 'card rcr' }, h('h3', {}, 'Recent Compiled Reports'),
      h('table', { class: 'tbl fixed p12', style: { marginTop: '4px' } }, h('colgroup', {}, ...[296, 196, 156, 328, 120].map((w) => h('col', { style: { width: w + 'px' } }))), h('thead', {}, h('tr', {}, ...['Report Name', 'Generated', 'Type', 'Status'].map((t) => h('th', {}, t)), h('th', { class: 'r' }, 'Download'))),
        h('tbody', {}, ...rep.map(([n, d, t, s]) => h('tr', {}, h('td', { style: { color: '#111827', height: '50px', fontWeight: 500 } }, n), h('td', {}, d), h('td', { style: { color: '#9ca3af' } }, t), h('td', {}, h('span', { class: 'badge-s' }, s)),
          h('td', { class: 'r' }, h('button', { class: 'a-btn', style: { width: '26px', padding: 0, height: '26px' }, type: 'button', 'aria-label': `Download ${n}`, onclick: () => toast(`Downloading ${n} (demo)`) }, icon('down'))))))))], '');
}

// ───────────────────────── roles
export function rolesView() {
  const a = store().admin; let cur = 'Admin'; const draftOf = () => structuredClone(a.perms[cur]);
  let draft = draftOf();
  const wrap = h('div', { class: 'roles' });
  const mods = ['Users', 'Reports', 'Settings', 'Billing', 'Audit Log'];
  function draw() {
    wrap.replaceChildren(
      h('div', { class: 'rlist' }, h('h3', {}, 'Available Roles'), ...a.roles.map(([n, c]) => h('button', { class: 'rl' + (n === cur ? ' on' : ''), type: 'button', onclick: () => { cur = n; draft = draftOf(); draw(); } },
        h('b', {}, n), n === cur ? h('span', { class: 'badge-s sel' }, 'Selected') : null, h('span', {}, `${c} active members`)))),
      h('div', { class: 'card perm' }, h('h3', {}, `${cur} Permissions`), h('p', { class: 'a-m', style: { margin: '2px 0 0' } }, `Configure access control levels for members assigned to the ${cur} role.`),
        h('table', { class: 'tbl fixed' }, h('colgroup', {}, ...[244, 108, 108, 108, 116].map((w) => h('col', { style: { width: w + 'px' } }))), h('thead', {}, h('tr', {}, ...['Module', 'View', 'Create', 'Edit', 'Delete'].map((t) => h('th', {}, t)))),
          h('tbody', {}, ...mods.map((m, r) => h('tr', {}, h('td', {}, m), ...[0, 1, 2, 3].map((c) => h('td', {}, h('input', { type: 'checkbox', class: 'ck', checked: !!draft[r][c], 'aria-label': `${cur} ${['view', 'create', 'edit', 'delete'][c]} ${m}`, onchange: (e) => { draft[r][c] = e.target.checked ? 1 : 0; } }))))))),
        h('div', { class: 'pbtns' }, h('button', { class: 'a-btn', type: 'button', onclick: () => { draft = draftOf(); draw(); toast('Changes discarded'); } }, 'Discard Changes'),
          h('button', { class: 'a-btn dark', type: 'button', onclick: () => { a.perms[cur] = structuredClone(draft); save(); toast(`${cur} permissions saved`); } }, 'Save Changes'))));
  }
  draw();
  return shell('roles', 56, [wrap], '');
}

// ───────────────────────── audit
export function auditView() {
  const a = store().admin; const body = h('tbody'); const search = h('input', { placeholder: 'Search actions, targets...', 'aria-label': 'Search the audit log' });
  const user = h('select', { class: 'a-sel', 'aria-label': 'User', onchange: draw }, ...['All', ...new Set(a.audit.map((r) => r[1]))].map((o) => h('option', { value: o }, o === 'All' ? 'User: All' : o)));
  const act = h('select', { class: 'a-sel', 'aria-label': 'Action type', onchange: draw }, ...['All', ...new Set(a.audit.map((r) => r[2]))].map((o) => h('option', { value: o }, o === 'All' ? 'Action Type: All' : o)));
  const dr = h('select', { class: 'a-sel', 'aria-label': 'Date range' }, h('option', {}, 'Date Range: Last 30 days'), h('option', {}, 'Last 7 days'), h('option', {}, 'Last 24 hours'));
  const info = h('span');
  function draw() {
    const t = search.value.toLowerCase(); const shown = a.audit.filter((r) => (user.value === 'All' || r[1] === user.value) && (act.value === 'All' || r[2] === act.value) && r.join(' ').toLowerCase().includes(t));
    body.replaceChildren(...shown.map((r) => h('tr', {}, h('td', {}, r[0]), h('td', { class: 's' }, ...r[1].split('.').flatMap((s, i, arr) => (i < arr.length - 1 ? [s + '.', document.createElement('wbr')] : [s]))), h('td', {}, r[2]), h('td', {}, r[3]), h('td', { style: { color: '#9ca3af' } }, r[4]),
      h('td', { class: 'r', style: { paddingRight: '16px' } }, h('span', { class: 'badge-s' }, r[5])))));
    info.textContent = `Showing ${shown.length} of 124 logs`;
  }
  search.addEventListener('input', draw); draw();
  return shell('audit', 56, [
    h('div', { class: 'fbar' }, user, act, dr, h('span', { class: 'grow' }), h('label', { class: 'a-search sm' }, icon('search'), search)),
    h('div', { class: 'card tcard t2', style: { padding: '20px 20px 0' } },
      h('table', { class: 'tbl fixed p16' }, h('colgroup', {}, ...[176, 176, 236, 196, 200, 112].map((w) => h('col', { style: { width: w + 'px' } }))), h('thead', {}, h('tr', {}, ...['Timestamp', 'User', 'Action', 'Target', 'IP Address'].map((t) => h('th', {}, t)), h('th', { class: 'r' }, 'Status'))), body),
      h('div', { class: 'pager', style: { padding: '0' } }, info, h('div', { class: 'pg' }, h('button', { type: 'button' }, 'Previous'), h('button', { class: 'on', type: 'button' }, '1'), h('button', { type: 'button' }, '2'), h('button', { type: 'button' }, '3'), h('span', { style: { alignSelf: 'center', margin: '0 4px' } }, '...'), h('button', { type: 'button' }, '12'), h('button', { type: 'button' }, 'Next'))))], '');
}

// ───────────────────────── settings
export function settingsView() {
  const S = store().admin.settings; let tab = 'General';
  const wrap = h('div', { class: 'setg' });
  function draw() {
    const name = h('input', { class: 'a-in', value: S.name, id: 'an', maxlength: '40', 'aria-label': 'Application name' });
    const lang = h('select', { class: 'a-sel', id: 'lang' }, ...['English', 'Thai', 'Japanese'].map((o) => h('option', { selected: o === S.lang }, o)));
    const tz = h('select', { class: 'a-sel', id: 'tz' }, ...['UTC-5', 'UTC+0', 'UTC+7', 'UTC+9'].map((o) => h('option', { selected: o === S.tz }, o)));
    const tog = h('button', { class: 'toggle', role: 'switch', type: 'button', 'aria-checked': String(S.maint), 'aria-label': 'Maintenance mode', style: { top: '0' }, onclick: () => { S.maint = !S.maint; tog.setAttribute('aria-checked', String(S.maint)); } });
    const form = tab === 'General'
      ? [h('h3', {}, 'General Settings'), h('p', { class: 'a-m', style: { margin: '2px 0 0' } }, 'Configure your primary portal identity, locale preferences and service status.'),
        h('label', { class: 'l', for: 'an' }, 'Application Name'), name,
        h('div', { style: { display: 'flex', gap: '16px', marginTop: '0' } }, h('div', {}, h('label', { class: 'l', for: 'lang' }, 'Default Language'), lang), h('div', {}, h('label', { class: 'l', for: 'tz' }, 'Timezone'), tz)),
        h('div', { class: 'l', style: { fontWeight: 600, fontSize: '14px', margin: '24px 0 4px' } }, 'Date Format'),
        ...['MM/DD/YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD'].map((f) => h('label', { class: 'radio' }, h('input', { type: 'radio', name: 'df', checked: S.datefmt === f, onchange: () => { S.datefmt = f; } }), f)),
        h('div', { style: { position: 'relative', height: '44px', marginTop: '22px' } }, h('div', { style: { font: '600 14px/20px var(--adm)' } }, 'Maintenance Mode'), h('div', { class: 'a-m', style: { fontSize: '12px', marginTop: '2px' } }, 'Temporarily offline for general users.'), tog),
        h('div', { class: 'sfoot' }, h('button', { class: 'a-btn dark', type: 'button', onclick: () => { S.name = name.value || 'Admin Portal'; S.lang = lang.value; S.tz = tz.value; save(); toast('Settings saved'); } }, 'Save Settings'))]
      : [h('h3', {}, `${tab} settings`), h('p', { class: 'a-m', style: { margin: '8px 0 0' } }, 'This section is a placeholder in the design prototype.')];
    wrap.replaceChildren(h('div', { class: 'stabs', role: 'tablist' }, ...['General', 'Security', 'Notifications', 'API Keys', 'Integrations'].map((t) => h('button', { role: 'tab', type: 'button', class: t === tab ? 'on' : '', 'aria-selected': String(t === tab), onclick: () => { tab = t; draw(); } }, t))),
      h('div', { class: 'card sform' }, ...form));
  }
  draw();
  return shell('settings', 56, [wrap], '');
}
