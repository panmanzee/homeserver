import { h, icon, link, store, save, go, toast } from './core.js';

export const img = (x, alt = '', props = {}) => h('img', { src: `/img/x${x}.webp`, alt, loading: 'lazy', decoding: 'async', ...props });

// ---------- shell: navbar + footer, shared by every screen ----------
export function navbar(active) {
  const s = store().session;
  const lk = (href, label, key) => link(href, { class: active === key ? 'on' : '' }, label);
  const links = [lk('/plan', 'PLAN', 'plan'), lk('/explore', 'EXPLORE', 'explore'), lk('/#team', 'CONTACT', 'contact')];
  let right;
  if (s && !String(active).startsWith('admin')) {
    const menu = h('div', { class: 'menu', role: 'menu' },
      link('/profile', {}, 'My profile'), link('/plan', {}, 'Plan a trip'),
      s.admin ? link('/admin', {}, 'Admin console') : null,
      h('button', { type: 'button', onclick: () => { store().session = null; save(); toast('Signed out'); go('/'); } }, 'Sign out'));
    const btn = h('button', { class: 'pill', type: 'button', 'aria-haspopup': 'true', onclick: (e) => { e.stopPropagation(); menu.classList.toggle('open'); } }, s.name.split(' ')[0]);
    document.addEventListener('click', () => menu.classList.remove('open'), { once: true });
    right = h('div', { class: 'menu-wrap' }, btn, menu);
  } else right = link(s ? '/profile' : '/login', { class: 'pill' }, 'GET START');
  return h('header', { class: 'nav' },
    link('/', { class: 'logo', 'aria-label': 'ASTRAVEL home' }, h('img', { src: '/img/logo.png', alt: '' }), h('span', {}, 'ASTRAVEL')),
    h('nav', { class: 'nav-links', 'aria-label': 'Main' }, ...links, right));
}
export const footer = () => h('footer', { class: 'foot' }, '© 2027 ASTRAVEL. All rights reserved.');
export function page(active, title, ...body) {
  const out = [navbar(active), h('main', { id: 'main' }, ...body), footer()];
  out.title = title; return out;
}

// ---------- login / register ----------
export function loginView() {
  const go2 = () => {
    store().session = { id: 'mimi', name: 'Mimi Kagari', email: 'Kagari@gmail.com', admin: true }; save();
    const next = sessionStorage.getItem('next') || '/'; sessionStorage.removeItem('next'); toast('Signed in as Mimi (demo account)'); go(next);
  };
  return page('login', 'Login',
    h('section', { class: 'login' },
      h('h2', {}, 'Welcome back, traveler!'),
      h('h1', {}, 'LOGIN / REGISTER'),
      h('button', { class: 'btn google', type: 'button', onclick: go2 }, icon('heart'), 'CONTINUE WITH GOOGLE')));
}

// ---------- landing ----------
export function landingView() {
  const rc = (cls, x, badge, title, text, to) => link(to, { class: 'rcard ' + cls }, img(x, ''), h('span', { class: 'badge' }, badge), h('h3', {}, title), text ? h('p', {}, text) : null);
  return page('home', 'Plan your journey',
    h('section', { class: 'hero' },
      h('h1', {}, 'Plan your Journey', h('br'), 'Design your Trip'),
      h('p', {}, 'Plan your trip, discover new places, and create unforgettable memories. Make every journey simple, exciting, and uniquely yours.'),
      h('div', { class: 'cta' }, link('/plan', { class: 'btn' }, 'Get started'), h('a', { class: 'btn soft', href: '#can', onclick: (e) => { e.preventDefault(); document.getElementById('can').scrollIntoView({ behavior: 'smooth' }); } }, 'What can we do')),
      h('div', { class: 'hero-img' }, img(973, 'Fukuoka skyline at dusk', { loading: 'eager' }))),
    h('section', { class: 'sec can', id: 'can' },
      h('h2', {}, 'What can we do ?'),
      h('div', { class: 'can-grid' },
        h('div', {}, h('img', { src: '/img/icon-plan.png', alt: '' }), h('h3', {}, 'Find your plan'), h('p', {}, 'Discover travel plans that match your interests, budget, and style. Create your perfect itinerary.')),
        h('div', {}, h('img', { src: '/img/icon-cost.png', alt: '' }), h('h3', {}, 'Calculate  cost'), h('p', {}, 'Estimate your travel expenses and manage your budget for a stress-free trip.')),
        h('div', {}, h('img', { src: '/img/icon-share.png', alt: '' }), h('h3', {}, 'Share with friends'), h('p', {}, 'Plan together, share your itinerary, and make decisions with your friends along the way.'))),
      link('/plan', { class: 'btn' }, 'TRY', icon('arrow'))),
    h('section', { class: 'sec rec' },
      h('h2', {}, 'Recommend'),
      h('p', { class: 'lead' }, 'Discover places, activities, and unique experiences recommended based on your interests, travel style, and preferences for a more enjoyable journey.'),
      h('div', { class: 'rec-grid' },
        rc('big', 977, 'Country', 'JAPAN', 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalaracc lacus vel facilisis volutpat est velitolm.', '/explore'),
        rc('col', 957, 'Plan template', 'Japan in one day', '', '/trip/template-japan'),
        rc('col', 953, 'Place', 'FUKU-OKA', '', '/place/fukuoka')),
      link('/explore', { class: 'btn' }, 'Explore', icon('arrow'))),
    h('section', { class: 'sec team', id: 'team' },
      h('h2', {}, 'Meet our team members'),
      h('p', { class: 'sub' }, 'Get to know our team.'),
      h('div', { class: 'team-grid' },
        ...[[937, 'Sheena Totsuki'], [969, 'Mimi Kagari'], [945, 'Omi'], [949, 'Ali Maud'], [933, 'Lizzy Seiran'], [929, 'Fran']].map(([x, n]) =>
          h('div', { class: 'member' }, img(x, n), h('h3', {}, n), h('h4', {}, '6701XXXX'))))),
    h('div', { class: 'land-end' }));
}
