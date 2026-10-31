// Dependency-free behavior checks. Synthetic records only; no browser/storage/customer writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function setup() {
  const nodes = new Map();
  const timers = new Map();
  let nextTimer = 0;
  const node = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, {
      value: selector === '#sort-filter' ? 'updated_desc' : '',
      hidden: false, disabled: false, innerHTML: '', textContent: '',
      setAttribute() {}, classList: { toggle() {} },
    });
    return nodes.get(selector);
  };
  const context = vm.createContext({
    document: { querySelector: node, addEventListener() {} },
    window: {
      setTimeout(callback) { const id = ++nextTimer; timers.set(id, callback); return id; },
      clearTimeout(id) { timers.delete(id); },
    },
  });
  const source = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
  const marker = '  document.addEventListener("DOMContentLoaded", () => {';
  assert.ok(source.includes(marker), 'Application startup boundary must be present');
  vm.runInContext(source.replace(marker, `
    globalThis.crmTest = { state, searchableText, applyFilters, scheduleSearch,
      resetFilters, normalizedCopyLines };
    ${marker}`), context);
  const api = context.crmTest;
  api.state.clients = [
    { client_id: 'one', source: 'email_manual', contact_name: 'Alice', company: 'Example A', known_email: 'buyer@example.invalid', known_phone: '+81 70 1234 5678', custom_tags: ['待寄样'], status: 'sampling', product_names: 'Rose Blend', icp_score: 70 },
    { client_id: 'two', source: 'email_manual', contact_name: 'Bob', company: 'Example B', status: 'new', icp_score: 90 },
    { client_id: 'three', source: 'alibaba', contact_name: 'Carol', company: 'Example C', status: 'new', icp_score: 85 },
  ];
  api.state.searchIndex = new Map(api.state.clients.map(client => [client.client_id, api.searchableText(client)]));
  return { api, node, timers, flush() { const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(callback => callback()); } };
}

test('search finds phone, email, product, tags and translated status within the current channel', () => {
  const { api, node } = setup();
  for (const query of ['1234 5678', 'BUYER@EXAMPLE.INVALID', 'rose blend', '待寄样', '寄样中']) {
    node('#search-input').value = query;
    api.applyFilters();
    assert.match(node('#client-grid').innerHTML, /data-client-id="one"/);
    assert.doesNotMatch(node('#client-grid').innerHTML, /data-client-id="two"/);
  }
  node('#search-input').value = 'Carol';
  api.applyFilters();
  assert.equal(node('#client-grid').innerHTML, '');
  api.state.activeChannel = 'alibaba';
  api.applyFilters();
  assert.match(node('#client-grid').innerHTML, /data-client-id="three"/);
});

test('filters and sorting run before pagination, and contact sorting follows the display name', () => {
  const { api, node } = setup();
  node('#sort-filter').value = 'contact_asc';
  api.applyFilters();
  const html = node('#client-grid').innerHTML;
  assert.ok(html.indexOf('data-client-id="one"') < html.indexOf('data-client-id="two"'));
  node('#sort-filter').value = 'score_desc';
  api.applyFilters();
  assert.ok(node('#client-grid').innerHTML.indexOf('data-client-id="two"') < node('#client-grid').innerHTML.indexOf('data-client-id="one"'));
  node('#status-filter').value = 'sampling';
  api.state.page = 100;
  api.applyFilters();
  assert.equal(api.state.page, 1);
  assert.doesNotMatch(node('#client-grid').innerHTML, /data-client-id="two"/);
  assert.equal(node('#filter-status').textContent, '1 项筛选条件');
});

test('search is debounced, ignores IME intermediate input and reset cancels queued work', () => {
  const { api, node, timers, flush } = setup();
  node('#search-input').value = '中文';
  api.scheduleSearch({ isComposing: true });
  assert.equal(timers.size, 0);
  api.scheduleSearch({ isComposing: false });
  api.scheduleSearch({ isComposing: false });
  assert.equal(timers.size, 1);
  api.state.page = 3;
  flush();
  assert.equal(api.state.page, 1);
  assert.equal(node('#empty-state').hidden, false);
  api.scheduleSearch();
  api.resetFilters();
  assert.equal(timers.size, 0);
  assert.equal(node('#clear-search-btn').hidden, true);
  assert.equal(node('#reset-filters').disabled, true);
});

test('contact labels reflect available data and customer text stays escaped', () => {
  const { api, node } = setup();
  api.state.clients[0].known_phone = '';
  api.state.clients[0].contact_name = '<img src=x onerror=alert(1)>';
  api.applyFilters();
  const html = node('#client-grid').innerHTML;
  assert.match(html, /card-field-label">邮箱</);
  assert.match(html, /&lt;img/);
  assert.doesNotMatch(html, /<img/);
});

test('product copy preserves leading, middle and trailing blank row alignment', () => {
  const { api } = setup();
  assert.equal(api.normalizedCopyLines('\r\n CODE1 \r\n\r\n CODE3 \r\n'), '\nCODE1\n\nCODE3\n');
});
