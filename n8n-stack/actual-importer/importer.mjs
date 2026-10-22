// Actual Budget importer — polls the SMS-gateway's queue file for new
// Kasikorn transactions and writes them into Actual as real transactions.
//
// Design:
//  - Reads /queue/queue.jsonl (shared volume with sms-gateway) directly,
//    rather than HTTP, so we never miss entries beyond the /queue/recent
//    HTTP endpoint's 20-item window.
//  - Tracks a byte-offset cursor in /state/cursor.json so restarts don't
//    re-import everything.
//  - Only imports entries with parsed_confidently === true and a known
//    direction; anything ambiguous is skipped and logged instead of
//    guessed, so the budget never gets silently wrong data.
//  - Uses importTransactions() (not addTransactions) specifically because
//    it deduplicates by imported_id and matches Actual's normal import
//    behavior for bank-sourced data.
import api from '@actual-app/api';
import fs from 'fs';
import crypto from 'crypto';

const QUEUE_PATH = process.env.QUEUE_PATH || '/queue/queue.jsonl';
const STATE_PATH = process.env.STATE_PATH || '/state/cursor.json';
const ACCOUNT_NAME = process.env.ACTUAL_ACCOUNT_NAME || 'Kasikorn';
const POLL_SECONDS = parseInt(process.env.POLL_SECONDS || '60', 10);

function loadCursor() {
  try {
    return JSON.parse(fs.readFileSync(STATE_PATH, 'utf8')).offset || 0;
  } catch {
    return 0;
  }
}

function saveCursor(offset) {
  fs.mkdirSync('/state', { recursive: true });
  fs.writeFileSync(STATE_PATH, JSON.stringify({ offset }));
}

async function getOrCreateAccount() {
  const accounts = await api.getAccounts();
  const existing = accounts.find(a => a.name === ACCOUNT_NAME);
  if (existing) return existing.id;
  console.log(`Creating account "${ACCOUNT_NAME}" (first run)`);
  return await api.createAccount({ name: ACCOUNT_NAME, type: 'checking', offbudget: false }, 0);
}

function toActualTxn(record) {
  if (!record.parsed_confidently || !record.direction || record.amount == null) {
    return null; // never guess — skip ambiguous parses
  }
  const cents = Math.round(record.amount * 100);
  const amount = record.direction === 'debit' ? -cents : cents;
  const dateMs = typeof record.sent_at === 'number' ? record.sent_at : Date.parse(record.received_at);
  const date = new Date(dateMs).toISOString().slice(0, 10);
  // stable dedup id from the raw SMS content + timestamp
  const imported_id = crypto.createHash('sha1')
    .update(`${record.sender}|${record.sent_at}|${record.raw_text}`)
    .digest('hex').slice(0, 20);
  return {
    date,
    amount,
    payee_name: record.direction === 'debit' ? 'Kasikorn transfer out' : 'Kasikorn transfer in',
    notes: record.raw_text,
    imported_id,
  };
}

async function runOnce(accountId) {
  if (!fs.existsSync(QUEUE_PATH)) return;
  const stat = fs.statSync(QUEUE_PATH);
  let offset = loadCursor();
  if (offset > stat.size) offset = 0; // file was rotated/cleared

  const fd = fs.openSync(QUEUE_PATH, 'r');
  const length = stat.size - offset;
  if (length <= 0) { fs.closeSync(fd); return; }
  const buf = Buffer.alloc(length);
  fs.readSync(fd, buf, 0, length, offset);
  fs.closeSync(fd);

  const lines = buf.toString('utf8').split('\n').filter(Boolean);
  const txns = [];
  for (const line of lines) {
    let record;
    try { record = JSON.parse(line); } catch { continue; }
    const txn = toActualTxn(record);
    if (txn) txns.push(txn);
    else console.log('skipped unparseable/ambiguous record:', JSON.stringify(record));
  }

  if (txns.length) {
    const { added, updated } = await api.importTransactions(accountId, txns);
    console.log(`imported ${added.length} new, ${updated.length} already existed (dedup)`);
    await api.sync();
  }

  saveCursor(stat.size);
}

async function main() {
  fs.mkdirSync('/tmp/actual-cache', { recursive: true });
  await api.init({
    dataDir: '/tmp/actual-cache',
    serverURL: process.env.ACTUAL_SERVER_URL,
    password: process.env.ACTUAL_PASSWORD,
  });
  await api.downloadBudget(process.env.ACTUAL_SYNC_ID);
  const accountId = await getOrCreateAccount();
  console.log(`actual-importer running, account=${ACCOUNT_NAME} (${accountId}), polling every ${POLL_SECONDS}s`);

  // run once immediately, then on an interval
  await runOnce(accountId).catch(e => console.error('run error:', e));
  setInterval(() => runOnce(accountId).catch(e => console.error('run error:', e)), POLL_SECONDS * 1000);
}

main().catch(e => { console.error('fatal:', e); process.exit(1); });
