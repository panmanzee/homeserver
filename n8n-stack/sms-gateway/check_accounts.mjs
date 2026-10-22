import api from '@actual-app/api';
await api.init({ dataDir: '/tmp/actual-cache', serverURL: process.env.ACTUAL_SERVER_URL, password: process.env.ACTUAL_PASSWORD });
await api.downloadBudget(process.env.ACTUAL_SYNC_ID);
const accounts = await api.getAccounts();
console.log(JSON.stringify(accounts, null, 2));
await api.shutdown();
