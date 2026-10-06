// Seed data for the prototype. Image numbers are the xref ids of the photos extracted from the Figma export.
export const SEED = {
  v: 3,
  session: null,
  people: {
    mimi:    { id: 'mimi',    name: 'Mimi Kagari',    email: 'Kagari@gmail.com',   img: 1363, code: '6701XXXX' },
    sheena:  { id: 'sheena',  name: 'Sheena Totsuki', email: 'Sheena@gmail.com',   img: 2105 },
    ali:     { id: 'ali',     name: 'Ali Maud',       email: 'Ali@gmail.com',      img: 2093 },
    lizzy:   { id: 'lizzy',   name: 'Lizzy Seiran',   email: 'Lizzy@gmail.com',    img: 2099 },
    anya:    { id: 'anya',    name: 'Anya Forger',    email: 'Anya@gmail.com',     img: 2087 },
    frieren: { id: 'frieren', name: 'Frieren',        email: 'Frieren@gmail.com',  img: 3775 },
  },
  following: ['sheena', 'ali', 'lizzy', 'anya'],
  followers: ['anya', 'sheena', 'ali', 'lizzy'],
  wishlist: ['japan', 'fukuoka-castle'],
  trips: [
    { id: 't-nz', owner: 'mimi', name: 'New Zealand', status: 'Up Comming', img: 1371, season: 'Winter', cost: 30,
      desc: 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.', schedule: '08:30 a.m. 28 Feb 2027  - 04:30 p.m. 33 Feb 2027' },
    { id: 't-us', owner: 'mimi', name: 'America', status: 'Up Comming', img: 1367, season: 'Summer', cost: 30,
      desc: 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.', schedule: '08:30 a.m. 28 Feb 2027  - 04:30 p.m. 33 Feb 2027' },
  ],
  catalog: [
    { id: 'japan', kind: 'Country', title: 'JAPAN', img: 6801, season: 'Summer', car: 'No Car', cost: 30, thumb: 1737 },
    { id: 'template-japan', kind: 'Plan template', title: 'Japan in one day', img: 6805, season: 'Summer', car: 'No Car', cost: 30, thumb: 1737 },
    { id: 'fukuoka', kind: 'Place', title: 'FUKUOKA', img: 6797, season: 'Summer', car: 'No Car', cost: 30, thumb: 1733 },
    { id: 'uminonakamichi', kind: 'Country', title: 'Uminonakamichi Seaside Park', img: 6793, season: 'Summer', car: 'No Car', cost: 30, thumb: 1737 },
    { id: 'fukuoka-castle', kind: 'Place', title: 'Fukuoka Castle Ruins', img: 1733, season: 'Summer', car: 'No Car', cost: 30, thumb: 1733, hidden: true },
  ],
  recommend: [['Seaside', 1737], ['Sakura', 1733], ['Mountain', 3739], ['Japan', 3735]],
  admin: {
    users: [
      ['John Doe', 'johndoe@gmail.com', 'Super Admin', 'Active', '5m ago'], ['Alice Smith', 'alice.s@company.com', 'Editor', 'Active', '1h ago'],
      ['Bob Johnson', 'bobj@io.com', 'Viewer', 'Inactive', '3d ago'], ['Elena Rostova', 'elena.r@agency.ru', 'Developer', 'Active', '10m ago'],
      ['Marcus Aurelius', 'marcus@philosophy.edu', 'Viewer', 'Active', '12h ago'], ['Sarah Connor', 'sconnor@resistance.net', 'Admin', 'Inactive', '1w ago'],
      ['David Miller', 'david.m@corp.com', 'Developer', 'Active', '4m ago'], ['Zoe Washburne', 'zoe@firefly.space', 'Editor', 'Active', '2d ago'] ],
    audit: [
      ['Nov 04, 10:24 AM', 'johndoe@gmail.com', 'Updated user role', 'Alice Smith (Editor)', '192.168.1.45', 'Success'],
      ['Nov 04, 09:12 AM', 'admin@system.io', 'Changed settings', 'General settings config', '127.0.0.1', 'Success'],
      ['Nov 04, 08:05 AM', 'bobj@io.com', 'Login attempt', 'bobj@io.com', '203.45.67.12', 'Failed'],
      ['Nov 03, 05:43 PM', 'johndoe@gmail.com', 'Deleted report', 'Quarterly Audit 2024', '192.168.1.45', 'Success'],
      ['Nov 03, 03:15 PM', 'alice.s@company.com', 'Updated user role', 'Zoe Washburne', '184.22.90.11', 'Success'],
      ['Nov 03, 11:22 AM', 'marcus@philosophy.edu', 'Login attempt', 'marcus@philosophy.edu', '99.88.77.66', 'Success'],
      ['Nov 02, 04:50 PM', 'admin@system.io', 'Changed settings', 'API Keys whitelist', '127.0.0.1', 'Success'],
      ['Nov 02, 02:11 PM', 'david.m@corp.com', 'Changed settings', 'Maintenance Mode off', '172.16.254.1', 'Success'],
      ['Nov 02, 10:05 AM', 'sconnor@resistance.net', 'Login attempt', 'sconnor@resistance.net', '10.0.0.1', 'Failed'],
      ['Nov 01, 09:30 AM', 'elena.r@agency.ru', 'Deleted report', 'Server Bandwidth Spike Logs', '82.34.120.3', 'Success'] ],
    roles: [['Admin', 4], ['Editor', 8], ['Viewer', 21], ['Support', 5], ['Billing', 2]],
    perms: { Admin: [[1,1,1,1],[1,1,1,0],[1,1,1,1],[1,0,0,0],[1,0,0,0]], Editor: [[1,0,0,0],[1,1,1,0],[1,0,0,0],[0,0,0,0],[1,0,0,0]],
             Viewer: [[1,0,0,0],[1,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]], Support: [[1,0,1,0],[1,0,0,0],[0,0,0,0],[0,0,0,0],[1,0,0,0]], Billing: [[0,0,0,0],[1,0,0,0],[0,0,0,0],[1,1,1,0],[1,0,0,0]] },
    settings: { name: 'Admin Portal', lang: 'English', tz: 'UTC-5', datefmt: 'MM/DD/YYYY', maint: false },
  },
};

// The sample itinerary shown in the design's trip screens (used for the example trip, the template and new drafts).
const NOTE = 'Lorem ipsum dolor sit amet consecte tur adipiscing elit semper dalar cons elementum tempus hac.';
export const SAMPLE_DAYS = () => [
  { date: '23 Feb 2027', stops: [
    { name: 'Pokemon center', note: NOTE, time: '08.00 - 12.00 a.m.', mode: 'Walk', cost: 30, done: true },
    { name: 'Mount Fuji', note: NOTE, time: '1.00 - 4.00 p.m.', mode: 'By train', cost: 30 } ] },
  { date: '23 Feb 2027', stops: [
    { name: 'Jigokudani Park', note: NOTE, time: '08.00 - 12.00 a.m.', mode: 'By car', cost: 30 } ] },
];
export const SAMPLE_BUDGET = () => [
  { name: 'Pokemon center', cat: 'food', amount: 300, who: 4271 },
  { name: 'Pokemon center', cat: 'food', amount: 300, who: 4267 },
];
export const SAMPLE_DESC = 'Discover places, activities, and unique experiences recommended based on your interests, travel style, and preferences for a more enjoyable journey Discover places, activities, and unique experiences recommended based on your interests, travel style, and preferences for a more enjoyable journey..';
