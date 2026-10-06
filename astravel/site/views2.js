import { h, icon, link, store, save, go, toast } from './core.js';
import { page, img } from './views.js';
import { SEED, SAMPLE_DAYS, SAMPLE_BUDGET, SAMPLE_DESC } from './data.js';

const NOTE = 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.';
const q = () => new URLSearchParams(location.search);
const person = (id) => store().people[id];
const copyLink = async (path) => { try { await navigator.clipboard.writeText(location.origin + path); toast('Link copied'); } catch (_) { toast(location.origin + path); } };
const eImg = (x, cls = '', alt = '') => h('img', { src: `/img/x${x}.webp`, alt, class: cls, loading: 'lazy', decoding: 'async' });
const circleBtn = (ic, label, onclick, cls = 'circle-btn') => h('button', { class: cls, type: 'button', 'aria-label': label, title: label, onclick }, icon(ic));

// ───────────────────────────── profile
function profileShell(p, own, rightPanel) {
  return h('section', { class: 'profile' },
    h('aside', { class: 'pside' },
      p.id === 'frieren' ? h('img', { class: 'avatar round', src: '/img/x3775.webp', alt: p.name, style: 'object-position:50% 20%' }) : eImg(p.img, 'avatar round', p.name),
      h('h1', {}, p.name), h('div', { class: 'email' }, p.email),
      own
        ? h('button', { class: 'btn', type: 'button', onclick: () => toast('Profile editing is not part of this prototype') }, icon('heart'), 'EDIT YOUR PROFILE')
        : (() => { const f = store().following.includes(p.id); const b = h('button', { class: 'btn', type: 'button', style: { width: '136px' }, onclick: () => { const s = store(); const i = s.following.indexOf(p.id); if (i < 0) s.following.push(p.id); else s.following.splice(i, 1); save(); b.textContent = i < 0 ? 'Unfollow' : 'Follow'; toast(i < 0 ? `Following ${p.name}` : `Unfollowed ${p.name}`); } }, f ? 'Unfollow' : 'Follow'); return b; })()),
    rightPanel);
}

export function profileView() {
  const s = store(); const me = person('mimi');
  const tab = q().get('tab') || 'trip';
  const tabs = [['trip', 'MY TRIP'], ['wishlist', 'WISHLIST'], ['following', 'FOLLOWING'], ['follower', 'FOLLOWER']];
  const list = h('div', { class: 'list' });
  const search = h('input', { type: 'text', placeholder: 'Search Here', 'aria-label': 'Search', autocomplete: 'off' });
  let sel = null, filterBtn = null;
  const tripFilter = h('select', { class: 'select', 'aria-label': 'Trip status', style: { width: '145px' }, onchange: draw }, ...['Up Comming', 'All'].map((o) => h('option', {}, o)));
  const wishFilter = h('select', { class: 'select', 'aria-label': 'Kind', style: { width: '108px' }, onchange: draw }, ...['Country', 'All', 'Place'].map((o) => h('option', {}, o)));
  const trash = (t) => circleBtn('trash', 'Delete trip', () => { if (confirm(`Delete "${t.name}"?`)) { s.trips = s.trips.filter((x) => x.id !== t.id); save(); toast('Trip deleted'); draw(); } });
  function tripRow(t) {
    return h('div', { class: 'trow' },
      eImg(t.img, 'thumb', t.name),
      h('div', { class: 'info' },
        h('div', {}, link(`/trip/${t.id}`, {}, h('h3', {}, t.name)), h('span', { class: 'badge' }, t.status)),
        h('p', {}, t.desc), h('div', { class: 'sched' }, h('b', {}, 'schedule'), ' : ' + t.schedule),
        h('div', { class: 'chips' }, h('span', { class: 'chip fill' }, '$' + t.cost), h('span', { class: 'chip' }, t.season))),
      h('div', { class: 'acts' }, circleBtn('share', 'Share', () => copyLink(`/trip/${t.id}`)), trash(t)));
  }
  function wishRow(c) {
    return h('div', { class: 'trow pl' },
      eImg(c.img === 6801 ? 1737 : c.thumb, 'thumb', c.title),
      h('div', { class: 'info' },
        h('div', {}, link(c.kind === 'Plan template' ? '/trip/template-japan' : `/place/${c.id}`, {}, h('h3', {}, c.id === 'japan' ? 'Japan' : c.title)), h('span', { class: 'badge' }, c.kind)),
        h('p', {}, NOTE.replace('consecte tur', 'consecte tur')), h('div', { class: 'chips' }, h('span', { class: 'chip fill' }, '$' + c.cost), h('span', { class: 'chip' }, c.season), h('span', { class: 'chip' }, c.car))),
      h('div', { class: 'acts' }, circleBtn('share', 'Share', () => copyLink(`/place/${c.id}`)),
        (() => { const b = circleBtn('heart', 'Remove from wishlist', () => { s.wishlist = s.wishlist.filter((x) => x !== c.id); save(); toast('Removed from wishlist'); draw(); }, 'circle-btn on'); return b; })()));
  }
  function personRow(id, kind) {
    const p = person(id);
    return h('div', { class: 'frow' }, eImg(p.img, 'round', p.name), link(`/u/${id}`, { style: { gridColumn: 4 } }, h('h3', { style: { gridColumn: 'auto' } }, p.name)),
      kind === 'following'
        ? h('button', { class: 'fbtn', type: 'button', onclick: (e) => { const i = s.following.indexOf(id); if (i >= 0) { s.following.splice(i, 1); e.currentTarget.textContent = 'FOLLOW'; } else { s.following.push(id); e.currentTarget.textContent = 'FOLLOWING'; } save(); } }, 'FOLLOWING')
        : h('button', { class: 'fbtn', type: 'button', onclick: () => { s.followers = s.followers.filter((x) => x !== id); save(); toast(`Removed ${p.name}`); draw(); } }, 'REMOVE'));
  }
  function draw() {
    const term = search.value.trim().toLowerCase(); let rows;
    if (tab === 'trip') {
      const all = tripFilter.value === 'All';
      rows = s.trips.filter((t) => !t.hidden && t.owner === 'mimi' && t.name.toLowerCase().includes(term) && (all || t.status === 'Up Comming')).map(tripRow);
    } else if (tab === 'wishlist') {
      rows = s.catalog.filter((c) => s.wishlist.includes(c.id) && c.title.toLowerCase().includes(term) && (wishFilter.value === 'All' || c.kind === wishFilter.value)).map(wishRow);
    } else {
      const ids = tab === 'following' ? s.following : s.followers;
      rows = ids.filter((id) => person(id).name.toLowerCase().includes(term)).map((id) => personRow(id, tab));
    }
    list.replaceChildren(...(rows.length ? rows : [h('div', { class: 'empty' }, term ? 'No results for that search.' : 'Nothing here yet.')]));
  }
  search.addEventListener('input', draw);
  const searchBox = h('label', { class: 'input-pill grow' }, icon('search'), search);
  const row = h('div', { class: 'prow' }, searchBox, tab === 'trip' ? tripFilter : tab === 'wishlist' ? wishFilter : null,
    (tab === 'trip' || tab === 'wishlist') ? circleBtn('filter', 'Filter', () => toast('Use the dropdown to filter')) : null);
  draw();
  const panel = h('section', { class: 'ppanel' },
    h('div', { class: 'ptabs', role: 'tablist' },
      ...tabs.map(([k, label]) => h('button', { class: 'ptab', role: 'tab', 'aria-selected': String(tab === k), onclick: () => go('/profile' + (k === 'trip' ? '' : `?tab=${k}`)) }, label)),
      link('/trip/new', { class: 'btn create' }, 'CREAD TRIP', icon('plus'))),
    row, list);
  return page('profile', 'Profile', profileShell(me, true, panel));
}

export function otherProfileView({ id }) {
  const p = person(id) || person('frieren');
  const list = h('div', { class: 'list' });
  const search = h('input', { type: 'text', placeholder: 'Search Here', 'aria-label': 'Search', autocomplete: 'off' });
  const items = [{ id: 'template-japan', name: 'Japan in one day', img: 9723, status: 'Up Comming', season: 'Summer' }, { id: 't-nz-f', name: 'New Zealand', img: 1371, status: 'Up Comming', season: 'Winter' }];
  const draw = () => { const term = search.value.toLowerCase(); list.replaceChildren(...items.filter((t) => t.name.toLowerCase().includes(term)).map((t) => h('div', { class: 'trow' },
    eImg(t.img, 'thumb', t.name),
    h('div', { class: 'info' }, h('div', {}, link(t.id === 'template-japan' ? '/trip/template-japan' : '/trip/template-japan', {}, h('h3', {}, t.name)), h('span', { class: 'badge' }, t.status)),
      h('p', {}, NOTE.replace('consecte tur adipiscing', 'consecte tur adipiscing')), h('div', { class: 'sched' }, h('b', {}, 'schedule'), ' : 08:30 a.m. 28 Feb 2027  - 04:30 p.m. 33 Feb 2027'),
      h('div', { class: 'chips' }, h('span', { class: 'chip fill' }, '$30'), h('span', { class: 'chip' }, t.season))),
    h('div', { class: 'acts' }, circleBtn('share', 'Share', () => copyLink('/trip/template-japan')), circleBtn('trash', 'Report', () => toast('Only the owner can delete this')))))); };
  search.addEventListener('input', draw); draw();
  const panel = h('section', { class: 'ppanel' },
    h('div', { class: 'ptabs' }, h('button', { class: 'ptab', 'aria-selected': 'true' }, `${p.name}ˇss Template`.replace('ˇ', '\u2019').toUpperCase())),
    h('div', { class: 'prow' }, h('label', { class: 'input-pill grow' }, icon('search'), search), circleBtn('filter', 'Filter', () => toast('Use the search box to filter'))), list);
  const sh = profileShell(p, false, panel); sh.classList.add('other'); return page('profile', p.name, sh);
}

// ───────────────────────────── explore
export function exploreView() {
  const s = store();
  const grid = h('div', { class: 'xgrid' });
  const search = h('input', { type: 'text', placeholder: 'Search Here', 'aria-label': 'Search places and plans', autocomplete: 'off' });
  const kind = h('select', { class: 'select', 'aria-label': 'Kind', onchange: draw }, h('option', { value: 'All' }, 'Country'), h('option', { value: 'Country' }, 'Only countries'), h('option', { value: 'Place' }, 'Only places'), h('option', { value: 'Plan template' }, 'Only plans'));
  let onlyWish = false;
  const fbtn = circleBtn('filter', 'Show wishlist only', () => { onlyWish = !onlyWish; fbtn.classList.toggle('on', onlyWish); fbtn.setAttribute('aria-pressed', String(onlyWish)); draw(); });
  const cards = [{ id: 'japan', kind: 'Country', title: 'JAPAN', bg: 6801 }, { id: 'template-japan', kind: 'Plan template', title: 'Japan in one day', bg: 6805 }, { id: 'fukuoka', kind: 'Place', title: 'FUKUOKA', bg: 6797 }, { id: 'uminonakamichi', kind: 'Country', title: 'Uminonakamichi Seaside Park', bg: 6793 }];
  function draw() {
    const term = search.value.trim().toLowerCase();
    const shown = cards.filter((c) => c.title.toLowerCase().includes(term) && (kind.value === 'All' || c.kind === kind.value) && (!onlyWish || s.wishlist.includes(c.id)));
    grid.replaceChildren(...(shown.length ? shown : [h('div', { class: 'empty', style: { gridColumn: '1 / -1' } }, 'No matches. Try another search or pick All.')]).map((c) => {
      if (!c.bg) return c;
      const on = s.wishlist.includes(c.id);
      const heart = h('button', { class: 'heart' + (on ? ' on' : ''), type: 'button', 'aria-label': on ? 'Remove from wishlist' : 'Add to wishlist', 'aria-pressed': String(on), onclick: (e) => {
        e.preventDefault(); e.stopPropagation(); const i = s.wishlist.indexOf(c.id); if (i < 0) s.wishlist.push(c.id); else s.wishlist.splice(i, 1); save(); toast(i < 0 ? 'Added to wishlist' : 'Removed from wishlist'); draw(); } }, icon('heart'));
      return link(c.kind === 'Plan template' ? '/trip/template-japan' : `/place/${c.id}`, { class: 'xcard' },
        eImg(c.bg, 'bg'), h('div', { class: 'top' }, h('span', { class: 'kind' }, c.kind), heart),
        h('div', { class: 'txt' }, h('h2', {}, c.title), h('p', {}, 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalaracc lacus vel facilisis volutpat est velitolm.')),
        h('div', { class: 'tags' }, h('span', {}, '$30'), h('span', { class: 'k' }, 'Summer'), h('span', { class: 'k' }, 'No Car')));
    }));
  }
  search.addEventListener('input', draw);
  draw();
  return page('explore', 'Explore',
    h('section', { class: 'explore' },
      h('h1', {}, 'Explore'),
      h('p', { class: 'lead' }, 'Discover places, activities, and unique experiences recommended based on your interests, travel style, and preferences for a more enjoyable journey Discover places,'),
      h('div', { class: 'tools' }, h('label', { class: 'input-pill' }, icon('search'), search), kind, fbtn),
      grid));
}

// ───────────────────────────── place
export function placeView({ id }) {
  const s = store(); const c = s.catalog.find((x) => x.id === id) || s.catalog[0];
  const title = c.id === 'japan' ? 'JAPAN' : c.title;
  const L = 'Lorem ipsum dolor sit amet consectetur adipiscing elit. Quisque faucibus ex sapien vitae pellentesque sem placerat. In id cursus mi pretium tellus duis convallis. Tempus leo eu aenean sed diam urna tempor. Pulvinar vivamus fringilla lacus nec metus bibendum';
  const stars = (n) => h('div', { class: 'stars', role: 'img', 'aria-label': `${n} of 5 stars` }, ...[1, 2, 3, 4, 5].map((i) => { const ic = icon('heart'); ic.innerHTML = '<path d="M12 3.5l2.600 5.400 5.900.8-4.300 4.100 1.100 5.800L12 16.800 6.700 19.600l1.100-5.800L3.500 9.700l5.900-.8z"/>'; if (i <= n) ic.classList.add('on'); return ic; }));
  return page('explore', title, h('section', { class: 'place' },
    h('h1', {}, title), circleBtn('share', 'Share', () => copyLink(`/place/${c.id}`), 'circle-btn share'),
    h('p', { class: 'big', style: { marginTop: '4px' } }, L + 's.'), h('p', { class: 'big', style: { marginTop: '28px' } }, L),
    h('h3', { class: 'h' }, 'Why you go here ?'), h('p', { class: 'big' }, L + ' egestas..'),
    h('h3', { class: 'h', style: { marginTop: '31.3px' } }, 'What you must know before ?'), h('p', { class: 'big' }, L),
    h('h3', { class: 'h', style: { marginBottom: '0', marginTop: '32px' } }, 'Review'),
    h('div', { class: 'rev' },
      h('div', { class: 'review' }, h('div', { class: 'txt' }, 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.'), stars(3), h('div', { class: 'who' }, eImg(3721, 'round'), '@nhdfusdf,;df')),
      h('div', { class: 'review' }, h('div', { class: 'txt' }, 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.'), stars(3), h('div', { class: 'who' }, eImg(3775, 'round'), '@nhdfusdf,;df'))),
    h('div', { class: 'strip' }, ...[7209, 7201, 7205, 3739, 7197].map((x) => eImg(x))),
    h('div', { class: 'mapstrip', role: 'img', 'aria-label': 'Map of the area' }),
    h('h3', { style: { font: '400 20px/24px var(--display)', margin: '24px 0 0' } }, 'Recommend'),
    h('div', { class: 'recrow' }, ...s.recommend.map(([n, x]) => h('div', {}, eImg(x), h('b', {}, 'Japan'))))));
}

// ───────────────────────────── trip (create / edit / view / template)
const PLACE_TEXT = [
  'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.',
  'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.',
  'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.',
];
function loadTrip(mode, id, from) {
  const s = store();
  if (mode === 'create') {
    const base = from === 'template-japan' ? { name: 'Japan in one day' } : {};
    return { name: base.name || '', desc: from ? SAMPLE_DESC : '', tags: ['08.00 - 12.00 a.m.', 'By car'], days: SAMPLE_DAYS(), budget: SAMPLE_BUDGET(), collab: [3721, 3775, 3717], dup: !!from };
  }
  if (id === 'template-japan') return { name: 'Japan in one day', desc: SAMPLE_DESC, tags: ['08.00 - 12.00 a.m.', 'By car'], days: SAMPLE_DAYS(), budget: SAMPLE_BUDGET().map((b) => ({ ...b, who: null })), collab: [], template: true };
  const t = s.trips.find((x) => x.id === id);
  if (!t) return null;
  if (!t.days) { t.days = SAMPLE_DAYS(); t.budget = SAMPLE_BUDGET(); t.tags = ['08.00 - 12.00 a.m.', 'By car']; t.collab = [3721, 3775, 3717]; t.longDesc = SAMPLE_DESC; }
  return t;
}

export function tripView(mode) {
  return ({ id }) => {
    const from = q().get('from');
    const T = loadTrip(mode === 'create' ? 'create' : 'x', id, from);
    if (!T) { return page('plan', 'Trip not found', h('section', { class: 'trip' }, h('div', { class: 'empty', style: { padding: '120px 0' } }, 'We couldn’t find that trip. ', link('/profile', { style: { textDecoration: 'underline' } }, 'Back to my trips')))); }
    const editing = mode === 'create' || mode === 'edit';
    const isTemplate = !!T.template;
    let picked = T.days[0]?.stops[0]?.name || 'Pokemon center';
    let ptab = 'about';
    const root = h('section', { class: 'trip' });
    const s = store();

    const persist = () => { if (mode === 'edit' && !isTemplate) { const t = s.trips.find((x) => x.id === id); Object.assign(t, { name: T.name || t.name, longDesc: T.desc, tags: T.tags, days: T.days, budget: T.budget }); save(); } };
    function saveTrip() {
      const name = (T.name || '').trim() || 'Trip name';
      if (mode === 'create') {
        const nid = 't' + Date.now().toString(36);
        s.trips.unshift({ id: nid, owner: 'mimi', name, status: 'Up Comming', img: 1737, season: 'Summer', cost: Math.max(0, T.budget.reduce((a, b) => a + (+b.amount || 0), 0) / 20) | 0 || 30,
          desc: T.desc || NOTE, schedule: '08:30 a.m. 28 Feb 2027  - 04:30 p.m. 33 Feb 2027', tags: T.tags, days: T.days, budget: T.budget, collab: T.collab, longDesc: T.desc });
        save(); toast('Trip created'); go(`/trip/${nid}`);
      } else { Object.assign(s.trips.find((x) => x.id === id), { name, longDesc: T.desc, tags: T.tags, days: T.days, budget: T.budget }); save(); toast('Saved'); go(`/trip/${id}`); }
    }

    // pieces ---------------------------------------------------------
    const header = () => {
      const avatars = (T.collab || []).map((x) => eImg(x, 'av round'));
      const eye = circleBtn('eye', 'Preview', () => (mode === 'create' ? toast('Create the trip to preview it') : go(`/trip/${id}`)), 'circle-btn');
      const plus = circleBtn('plus', 'Invite friends', () => copyLink(mode === 'create' ? '/trip/new' : `/trip/${id}`), 'circle-btn');
      let right;
      if (isTemplate) right = [eImg(10215, 'av round'), h('button', { class: 'btn primary', type: 'button', onclick: () => go('/trip/new?from=template-japan') }, 'START WITH THIS TEMPLATE')];
      else if (editing) right = [...avatars, plus, eye, h('button', { class: 'btn primary', type: 'button', onclick: saveTrip }, mode === 'create' ? 'CREATE' : 'SAVE', icon(mode === 'create' ? 'plus' : 'save'))];
      else right = [...avatars, plus, eye, circleBtn('pencil', 'Edit trip', () => go(`/trip/${id}/edit`))];
      const ttl = editing ? h('input', { class: 'ttl', value: T.name, placeholder: 'Trip name', 'aria-label': 'Trip name', maxlength: '60', oninput: (e) => { T.name = e.target.value; } })
        : h('h1', { style: { font: '400 57px/70px var(--display)', margin: 0 } }, T.name || 'Trip name');
      return h('div', { class: 'thead' }, ttl, h('div', { class: 'ctl' }, ...right));
    };
    const tagRow = () => {
      const row = h('div', { class: 'tagrow' });
      const draw = () => {
        row.replaceChildren(editing ? h('span', { class: 'lbl' }, 'Tag :') : null,
          ...T.tags.map((t, i) => editing ? h('button', { class: 'pill-o', type: 'button', title: 'Click to remove', onclick: () => { T.tags.splice(i, 1); persist(); draw(); } }, t) : h('span', { class: 'pill-o' }, t)),
          editing ? circleBtn('plus', 'Add tag', () => {
            const inp = h('input', { class: 'pill-o in', placeholder: 'New tag', maxlength: '24', 'aria-label': 'New tag' });
            const commit = () => { const v = inp.value.trim(); if (v) T.tags.push(v); persist(); draw(); };
            inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') draw(); }); inp.addEventListener('blur', commit);
            row.append(inp); inp.focus(); }, 'circle-s') : null);
      }; draw(); return row;
    };
    const stopEl = (d, di, st, si, redraw) => {
      const nm = h('div', { class: 'nm' }, (() => { const p = icon('pin', 'pin'); p.innerHTML = '<path d="M12 22s-7-6.200-7-12a7 7 0 0 1 14 0c0 5.800-7 12-7 12z"/><circle cx="12" cy="10" r="2.600"/>'; return p; })(),
        editing ? h('input', { value: st.name, 'aria-label': 'Place name', style: { font: 'inherit', border: 0, borderBottom: '1px dashed var(--blue)', background: 'transparent', outline: 0, width: '60%' }, oninput: (e) => { st.name = e.target.value; picked = st.name; } })
          : h('button', { type: 'button', style: { all: 'unset', cursor: 'pointer' }, onclick: () => { picked = st.name; redraw(); const c = document.querySelector('.pcard'); if (c && c.refresh) c.refresh(); } }, st.name));
      const el = h('div', { class: 'stop' + (!editing && st.done ? ' done' : '') },
        editing ? h('span', { class: 'grip' }, icon('grip')) : null, nm,
        editing ? circleBtn('trash', 'Remove stop', () => { d.stops.splice(si, 1); if (!d.stops.length && T.days.length > 1) T.days.splice(di, 1); persist(); redraw(); }, 'circle-m del')
          : h('button', { class: 'circle-m check' + (st.done ? ' on' : ''), type: 'button', 'aria-label': st.done ? 'Mark as not done' : 'Mark as done', 'aria-pressed': String(!!st.done), onclick: () => { st.done = !st.done; if (id) { const t = s.trips.find((x) => x.id === id); if (t) save(); } redraw(); } }, icon('check')),
        h('p', { class: 'note' }, st.note),
        h('div', { class: 'tags' },
          editing ? h('button', { class: 'pill-o', type: 'button', title: 'Edit time', onclick: () => { const x = prompt('Time', st.time); if (x) { st.time = x.slice(0, 24); persist(); redraw(); } } }, st.time) : h('span', { class: 'pill-o' }, st.time),
          editing ? h('button', { class: 'pill-o', type: 'button', title: 'Edit transport', onclick: () => { const x = prompt('Transport', st.mode); if (x) { st.mode = x.slice(0, 16); persist(); redraw(); } } }, st.mode) : h('span', { class: 'pill-o' }, st.mode),
          editing ? h('button', { class: 'pill-o fill', type: 'button', title: 'Edit cost', onclick: () => { const x = prompt('Cost in $', st.cost); if (x !== null && !isNaN(+x)) { st.cost = Math.max(0, +x); persist(); redraw(); } } }, '$' + st.cost) : h('span', { class: 'pill-o fill' }, '$' + st.cost)));
      return el;
    };
    const leftBody = () => {
      const wrap = h('div', { class: 'scroll' });
      const draw = () => {
        const kids = [];
        T.days.forEach((d, di) => {
          kids.push(h('div', { class: 'day' }, h('h3', {}, d.date), editing ? h('div', { class: 'acts' },
            circleBtn('pencil', 'Edit date', () => { const v = prompt('Date', d.date); if (v) { d.date = v.slice(0, 20); persist(); draw(); } }, 'circle-m'),
            circleBtn('trash', 'Remove day', () => { if (T.days.length > 1) { T.days.splice(di, 1); persist(); draw(); } else toast('A trip needs at least one day'); }, 'circle-m')) : null));
          d.stops.forEach((st, si) => kids.push(stopEl(d, di, st, si, draw)));
        });
        if (editing) {
          kids.push(h('div', { class: 'rhead' }, 'Recommend'), h('div', { class: 'recrow' }, ...s.recommend.map(([n, x]) => h('div', {}, eImg(x), h('b', {}, n),
            circleBtn('plus', `Add ${n} to the trip`, () => { const d = T.days[T.days.length - 1]; d.stops.push({ name: n === 'Japan' ? 'Tokyo Tower' : n, note: NOTE, time: '08.00 - 12.00 a.m.', mode: 'Walk', cost: 30 }); persist(); toast(`Added ${n}`); draw(); }, 'circle-btn')))),
            h('div', { class: 'addrow' }, circleBtn('plus', 'Add a day', () => { T.days.push({ date: '24 Feb 2027', stops: [{ name: 'New place', note: NOTE, time: '08.00 - 12.00 a.m.', mode: 'Walk', cost: 30 }] }); persist(); draw(); }, 'circle-m')));
        }
        kids.push(budgetEl());
        wrap.replaceChildren(...kids);
      };
      draw(); return wrap;
    };
    const total = () => T.budget.reduce((a, b) => a + (+b.amount || 0), 0);
    function budgetEl() {
      const box = h('div', { class: 'budget' + (editing ? '' : ' v') + (isTemplate ? ' t' : '') });
      const title = (mode === 'edit' || mode === 'view') && !isTemplate ? 'Cost' : 'Budgeting';
      const draw = () => {
        const tot = h('span', { class: 'chip-n' }, String(total()), icon('dollar'));
        box.replaceChildren(
          h('div', { class: 'bh' }, h('h3', {}, title), h('div', { class: 'tot' }, tot, editing || !isTemplate ? circleBtn('plus', 'Add expense', () => { T.budget.push({ name: picked, cat: 'food', amount: 100, who: null }); persist(); draw(); }, 'circle-m') : null)),
          ...T.budget.map((b, i) => h('div', { class: 'bitem' },
            h('div', { class: 'bn' }, b.name), h('div', { class: 'bc' }, b.cat),
            h('div', { class: 'r' },
              editing ? h('label', { class: 'chip-n sm' }, h('input', { type: 'number', value: b.amount, min: '0', 'aria-label': 'Amount', style: { width: '48px', border: 0, background: 'none', outline: 0, color: 'inherit', font: 'inherit', textAlign: 'right' }, oninput: (e) => { b.amount = +e.target.value || 0; tot.firstChild.textContent = String(total()); persist(); } }), icon('dollar'))
                : h('span', { class: 'chip-n sm' }, String(b.amount), icon('dollar')),
              !isTemplate ? circleBtn('trash', 'Remove expense', () => { T.budget.splice(i, 1); persist(); draw(); }, 'circle-m') : null),
            !isTemplate && !editing ? h('div', { class: 'who' }, b.who ? eImg(b.who, 'round') : null, circleBtn('plus', 'Assign to a friend', () => { const pool = T.collab || []; if (!pool.length) return; b.who = pool[(pool.indexOf(b.who) + 1) % pool.length]; persist(); draw(); }, 'circle-m')) : null,
            editing ? h('div', { class: 'who' }, b.who ? eImg(b.who, 'round') : null, circleBtn('plus', 'Assign to a friend', () => { const pool = T.collab || []; if (!pool.length) return; b.who = pool[(pool.indexOf(b.who) + 1) % pool.length]; persist(); draw(); }, 'circle-m')) : null)));
      };
      draw(); return box;
    }
    function placeCard(pos) {
      const card = h('div', { class: 'pcard', style: pos });
      const draw = () => card.replaceChildren(h('div', { style: { padding: '24px' } },
        h('h4', {}, picked),
        h('div', { class: 'ptabs2', role: 'tablist' }, ['about', 'review'].map((k) => h('button', { role: 'tab', type: 'button', 'aria-selected': String(ptab === k), onclick: () => { ptab = k; draw(); } }, k))),
        ptab === 'about' ? h('div', {}, h('div', { class: 'pics' }, eImg(3765, 'round'), eImg(3731, 'round'), eImg(3727, 'round')),
          h('p', {}, NOTE), h('h5', {}, 'Why you go here ?'), h('p', {}, NOTE), h('h5', {}, 'What you must know before ?'), h('p', {}, NOTE))
          : h('div', { class: 'rev-mini' }, h('p', {}, '“Worth the detour — go early to avoid the queue.”'), h('p', { style: { color: 'var(--blue)', fontWeight: 700 } }, '@nhdfusdf,;df'), h('p', {}, '“Great for a rainy afternoon.”'), h('p', { style: { color: 'var(--blue)', fontWeight: 700 } }, '@sakura_trip'))));
      draw();
      // keep the card in sync when the selected stop changes
      card.refresh = draw; return card;
    }

    function draw() {
      const left = h('div', { class: 'tpanel left' + (editing ? '' : ' vm') }, leftBody());
      let main;
      if (editing || isTemplate) {
        const card = placeCard({ left: '825px', top: isTemplate ? '354px' : '642px', width: '543px', height: '410px', overflow: 'auto' });
        main = h('div', { class: 'tmain' }, left, card);
      } else {
        const right = h('div', { class: 'tpanel right vm' }, leftBody());
        main = h('div', { class: 'tmain', style: { height: '852px', backgroundPosition: '0 -270px' } }, right, placeCard({ left: '24px', top: '398px', width: '523px', height: '410px', overflow: 'auto' }));
      }
      if (isTemplate) { main.style.backgroundPosition = '0 -292px'; main.style.height = '808px'; }
      const descBlock = editing
        ? [h('p', { class: 'tdesc-l' }, 'description'), h('textarea', { class: 'tdesc', placeholder: 'Type here', 'aria-label': 'Description', maxlength: '600', oninput: (e) => { T.desc = e.target.value; } }, T.desc || '')]
        : [h('p', { class: 'tdesc-view' }, T.longDesc || T.desc || SAMPLE_DESC)];
      root.replaceChildren(header(), ...descBlock, tagRow(), main);
    }
    draw();
    return page('plan', T.name || 'Plan a trip', root);
  };
}
