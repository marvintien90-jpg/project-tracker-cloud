/**
 * 專案管理員 — 後端（Google Apps Script）
 *
 * 資料全部存在一份 Google Sheet 的四個分頁：部門、人員、事項、追蹤紀錄。
 * 前端 Index.html 透過 google.script.run 呼叫下面以 api_ 開頭的函式。
 */

const TABLES = {
  dept: { name: '部門', cols: ['id', 'name', 'sort'] },
  people: { name: '人員', cols: ['id', 'name', 'dept', 'email', 'line_id', 'active'] },
  items: {
    name: '事項',
    cols: ['id', 'title', 'detail', 'dept', 'owner', 'priority', 'due', 'status',
      'note', 'selected', 'source', 'next_followup', 'created_at', 'updated_at'],
  },
  log: { name: '追蹤紀錄', cols: ['id', 'item_id', 'at', 'action', 'content'] },
};

const DEFAULT_DEPTS = [
  '董事長室', '營運中心', '研發課', '教育訓練課', '食安課',
  '展店課', '直營部', '財務部', '行銷部', '人資部',
  '採購部', '工程部', '行政部', '資訊部',
];

const STATUSES = ['待處理', '進行中', '等待回覆', '已完成', '暫緩'];
const PRIORITIES = ['高', '中', '低'];

// ───────────────────────── 進入點 ─────────────────────────

function doGet() {
  setup();
  return HtmlService.createHtmlOutputFromFile('Index')
    .setTitle('專案管理員')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.DEFAULT);
}

/** 建立分頁並放入預設部門；第一次開網頁時會自動執行，也可在編輯器手動執行。 */
function setup() {
  ensureSchema_();
  if (readAll_('dept').length === 0) {
    DEFAULT_DEPTS.forEach((name, i) => insert_('dept', { name: name, sort: i + 1 }));
  }
  Logger.log('完成：試算表 ' + getSpreadsheet_().getUrl());
}

// ───────────────────────── 前端 API ─────────────────────────

function api_bootstrap() {
  ensureSchema_();
  return {
    depts: readAll_('dept').sort((a, b) => Number(a.sort) - Number(b.sort)),
    people: readAll_('people'),
    items: readAll_('items'),
    statuses: STATUSES,
    priorities: PRIORITIES,
    today: today_(),
  };
}

function api_saveItem(input) {
  return withLock_(() => {
    const data = pick_(input, ['title', 'detail', 'dept', 'owner', 'priority', 'due',
      'status', 'note', 'next_followup', 'source']);
    if (!String(data.title || '').trim()) throw new Error('請輸入事項標題');
    data.title = String(data.title).trim();
    if (data.due) data.due = normDate_(data.due);
    if (data.next_followup) data.next_followup = normDate_(data.next_followup);

    if (input.id) {
      const before = findById_('items', input.id);
      if (!before) throw new Error('找不到這個事項，可能已被刪除');
      const after = update_('items', input.id, data);
      const changes = describeChanges_(before, after);
      if (changes) addLog_(input.id, '修改', changes);
      return after;
    }
    const row = insert_('items', Object.assign({
      priority: '中', status: '待處理', selected: false, source: '手動新增',
    }, data));
    addLog_(row.id, '建立', row.title);
    return row;
  });
}

function api_deleteItem(id) {
  return withLock_(() => {
    const item = findById_('items', id);
    if (!item) return true;
    remove_('items', id);
    addLog_(id, '刪除', item.title);
    return true;
  });
}

function api_setStatus(id, status) {
  if (STATUSES.indexOf(status) < 0) throw new Error('不明的狀態：' + status);
  return withLock_(() => {
    const before = findById_('items', id);
    if (!before) throw new Error('找不到這個事項');
    const after = update_('items', id, { status: status });
    addLog_(id, '狀態', before.status + ' → ' + status);
    return after;
  });
}

/** 勾選或取消勾選一批事項，回傳更新後的事項。 */
function api_setSelected(ids, selected) {
  return withLock_(() => ids.map(id => update_('items', id, { selected: !!selected }))
    .filter(Boolean));
}

/** 批次把勾選的事項改成同一狀態。 */
function api_bulkStatus(ids, status) {
  if (STATUSES.indexOf(status) < 0) throw new Error('不明的狀態：' + status);
  return withLock_(() => ids.map(id => {
    const before = findById_('items', id);
    if (!before) return null;
    const after = update_('items', id, { status: status, selected: false });
    if (before.status !== status) addLog_(id, '狀態', before.status + ' → ' + status);
    return after;
  }).filter(Boolean));
}

function api_addNote(id, text) {
  text = String(text || '').trim();
  if (!text) throw new Error('補充說明不能是空的');
  return withLock_(() => {
    const item = update_('items', id, { note: text });
    if (!item) throw new Error('找不到這個事項');
    addLog_(id, '補充', text);
    return item;
  });
}

function api_getLog(itemId) {
  return readAll_('log')
    .filter(r => String(r.item_id) === String(itemId))
    .sort((a, b) => String(b.at).localeCompare(String(a.at)));
}

function api_savePerson(input) {
  return withLock_(() => {
    const data = pick_(input, ['name', 'dept', 'email', 'line_id', 'active']);
    if (!String(data.name || '').trim()) throw new Error('請輸入姓名');
    if (data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
      throw new Error('Email 格式不正確');
    }
    if (input.id) return update_('people', input.id, data);
    return insert_('people', Object.assign({ active: true }, data));
  });
}

function api_deletePerson(id) {
  return withLock_(() => {
    const used = readAll_('items').some(i => String(i.owner) === String(id) && i.status !== '已完成');
    if (used) throw new Error('這位負責人還有未完成的事項，請先改派再刪除');
    remove_('people', id);
    return true;
  });
}

function api_saveDept(input) {
  return withLock_(() => {
    const name = String(input.name || '').trim();
    if (!name) throw new Error('請輸入部門名稱');
    if (input.id) {
      const before = findById_('dept', input.id);
      if (!before) throw new Error('找不到這個部門');
      if (before.name !== name) {
        // 改名時一併更新事項與人員上的部門名稱
        readAll_('items').filter(i => i.dept === before.name)
          .forEach(i => update_('items', i.id, { dept: name }));
        readAll_('people').filter(p => p.dept === before.name)
          .forEach(p => update_('people', p.id, { dept: name }));
      }
      return update_('dept', input.id, { name: name });
    }
    if (readAll_('dept').some(d => d.name === name)) throw new Error('已經有這個部門');
    const max = readAll_('dept').reduce((m, d) => Math.max(m, Number(d.sort) || 0), 0);
    return insert_('dept', { name: name, sort: max + 1 });
  });
}

function api_deleteDept(id) {
  return withLock_(() => {
    const dept = findById_('dept', id);
    if (!dept) return true;
    const used = readAll_('items').some(i => i.dept === dept.name && i.status !== '已完成');
    if (used) throw new Error('這個部門還有未完成的事項，請先處理再刪除');
    remove_('dept', id);
    return true;
  });
}

// ───────────────────────── 資料層 ─────────────────────────

function getSpreadsheet_() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  if (id) return SpreadsheetApp.openById(id);
  const active = SpreadsheetApp.getActiveSpreadsheet();
  if (active) return active;
  const created = SpreadsheetApp.create('專案管理員資料庫');
  PropertiesService.getScriptProperties().setProperty('SPREADSHEET_ID', created.getId());
  return created;
}

function ensureSchema_() {
  const ss = getSpreadsheet_();
  Object.keys(TABLES).forEach(key => {
    const t = TABLES[key];
    let sh = ss.getSheetByName(t.name);
    if (!sh) {
      sh = ss.insertSheet(t.name);
      // 全部存成純文字，避免 Sheets 自作主張把日期、編號轉格式
      sh.getRange(1, 1, sh.getMaxRows(), t.cols.length).setNumberFormat('@');
      sh.getRange(1, 1, 1, t.cols.length).setValues([t.cols]).setFontWeight('bold');
      sh.setFrozenRows(1);
      return;
    }
    const header = sh.getRange(1, 1, 1, Math.max(sh.getLastColumn(), 1)).getValues()[0];
    const missing = t.cols.filter(c => header.indexOf(c) < 0);
    if (missing.length) {
      const start = header.filter(String).length + 1;
      sh.getRange(1, start, 1, missing.length).setValues([missing]).setFontWeight('bold');
    }
  });
}

function sheet_(key) {
  return getSpreadsheet_().getSheetByName(TABLES[key].name);
}

function readAll_(key) {
  const sh = sheet_(key);
  const last = sh.getLastRow();
  if (last < 2) return [];
  const values = sh.getRange(1, 1, last, sh.getLastColumn()).getValues();
  const header = values[0];
  return values.slice(1)
    .filter(r => r[0] !== '' && r[0] != null)
    .map(r => rowToObj_(header, r));
}

function rowToObj_(header, row) {
  const o = {};
  header.forEach((h, i) => {
    if (!h) return;
    let v = row[i];
    if (v instanceof Date) v = Utilities.formatDate(v, tz_(), 'yyyy-MM-dd');
    if (v === 'TRUE' || v === true) v = true;
    else if (v === 'FALSE' || v === false) v = false;
    o[h] = v;
  });
  return o;
}

function findRow_(key, id) {
  const sh = sheet_(key);
  const last = sh.getLastRow();
  if (last < 2) return -1;
  const ids = sh.getRange(2, 1, last - 1, 1).getValues();
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]) === String(id)) return i + 2;
  }
  return -1;
}

function findById_(key, id) {
  const row = findRow_(key, id);
  if (row < 0) return null;
  const sh = sheet_(key);
  const header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  return rowToObj_(header, sh.getRange(row, 1, 1, header.length).getValues()[0]);
}

function insert_(key, obj) {
  const sh = sheet_(key);
  const header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  const now = nowStr_();
  const full = Object.assign({ id: newId_() }, obj);
  if (header.indexOf('created_at') >= 0) full.created_at = now;
  if (header.indexOf('updated_at') >= 0) full.updated_at = now;
  const cells = header.map(h => toCell_(full[h]));
  // 先設成純文字再寫入，避免日期、編號被自動轉格式
  sh.getRange(sh.getLastRow() + 1, 1, 1, header.length).setNumberFormat('@').setValues([cells]);
  return rowToObj_(header, cells);
}

function update_(key, id, patch) {
  const row = findRow_(key, id);
  if (row < 0) return null;
  const sh = sheet_(key);
  const header = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  const range = sh.getRange(row, 1, 1, header.length);
  const current = rowToObj_(header, range.getValues()[0]);
  const next = Object.assign(current, patch);
  if (header.indexOf('updated_at') >= 0) next.updated_at = nowStr_();
  const cells = header.map(h => toCell_(next[h]));
  range.setValues([cells]);
  return rowToObj_(header, cells);
}

function remove_(key, id) {
  const row = findRow_(key, id);
  if (row > 0) sheet_(key).deleteRow(row);
}

function addLog_(itemId, action, content) {
  insert_('log', { item_id: itemId, at: nowStr_(), action: action, content: content });
}

// ───────────────────────── 小工具 ─────────────────────────

function withLock_(fn) {
  const lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

function pick_(obj, keys) {
  const o = {};
  keys.forEach(k => { if (obj[k] !== undefined) o[k] = obj[k]; });
  return o;
}

function toCell_(v) {
  if (v === undefined || v === null) return '';
  if (v === true) return 'TRUE';
  if (v === false) return 'FALSE';
  return String(v);
}

function describeChanges_(before, after) {
  const labels = { title: '標題', detail: '內容', dept: '部門', owner: '負責人', priority: '優先',
    due: '期限', status: '狀態', next_followup: '下次追蹤' };
  return Object.keys(labels)
    .filter(k => String(before[k] || '') !== String(after[k] || ''))
    .map(k => labels[k] + '：' + (before[k] || '（空）') + ' → ' + (after[k] || '（空）'))
    .join('；');
}

function normDate_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, tz_(), 'yyyy-MM-dd');
  const s = String(v).trim().replace(/\//g, '-');
  const m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (!m) throw new Error('日期格式請用 2026-10-31：' + v);
  return m[1] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[3]).slice(-2);
}

function newId_() {
  return Utilities.getUuid().replace(/-/g, '').slice(0, 12);
}

function tz_() {
  return Session.getScriptTimeZone() || 'Asia/Taipei';
}

function nowStr_() {
  return Utilities.formatDate(new Date(), tz_(), 'yyyy-MM-dd HH:mm:ss');
}

function today_() {
  return Utilities.formatDate(new Date(), tz_(), 'yyyy-MM-dd');
}
