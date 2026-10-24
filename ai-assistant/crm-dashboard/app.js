(() => {
  "use strict";

  const STATUS_LABELS = {
    new: "新建",
    researched: "已研究",
    outreach_1: "开发信 1",
    outreach_2: "开发信 2",
    outreach_3: "开发信 3",
    replied: "已回复",
    sampling: "寄样中",
    quoting: "报价中",
    paid: "已付款",
    won: "已成交",
    lost: "已流失",
    disqualified: "不匹配",
    cold: "冷却",
  };
  const TIER_LABELS = { A: "A · 优先", B: "B · 跟进", C: "C · 观察" };
  const UI_ERROR_CODES = { bulkCopy: "CRM-BULK-COPY-001", draft: "CRM-DRAFT-001", productParse: "CRM-PRODUCT-PARSE-001", contactParse: "CRM-CONTACT-PARSE-001", checklist: "CRM-CHECKLIST-001" };
  const CONTACT_PARSE_FIELDS = Object.freeze(["contact_name", "known_phone", "address", "known_email", "company", "title", "country_region"]);
  const CONTACT_FIELD_LABELS = Object.freeze({
    contact_name: "姓名",
    known_phone: "电话",
    address: "地址",
    known_email: "邮箱",
    company: "公司",
    title: "职位",
    country_region: "地区",
  });
  const CONTACT_PASTE_PLACEHOLDER_EMAIL = "粘贴包含姓名、电话、地址的整段文字，例如邮件签名或收货信息。识别结果会填入下方对应字段。";
  const CONTACT_PASTE_PLACEHOLDER_ALI = "粘贴阿里询盘或聊天中的整段文字。姓名、电话、地址会填入下方；若含产品列表，会同步拆到产品两列。";
  const DRAFT_STORAGE_KEY = "scentedland-crm:new-client-drafts:v1";
  const CHECKLIST_STORAGE_KEY = "scentedland-crm:daily-checklist:v1";
  const CHECKLIST_MAX_TEXT_LENGTH = 240;
  const DETAIL_LINE_LIMIT = 15;
  const DETAIL_COPY_LABELS = Object.freeze({ product_codes: "内部编码", product_names: "产品名称" });
  const PAGE_SIZE_OPTIONS = Object.freeze([12, 24, 48]);
  const state = {
    clients: [],
    filters: { statuses: [], tiers: [], markets: [], sources: [] },
    activeChannel: "email",
    selectedClientId: null,
    loading: false,
    page: 1,
    pageSize: 12,
  };
  const draftState = { activeId: null, baseline: "" };
  const checklistState = { date: "", store: {} };

  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
  const text = (value, fallback = "未填写") => {
    const normalized = String(value ?? "").trim();
    return normalized || fallback;
  };
  const statusLabel = (value) => STATUS_LABELS[value] || text(value);
  const channelOf = (client) => {
    if (client?.customer_channel === "alibaba" || client?.channel === "alibaba" || client?.is_alibaba) return "alibaba";
    return /alibaba|阿里/i.test(String(client?.source || "")) ? "alibaba" : "email";
  };
  const displayName = (client) => {
    const contact = String(client?.contact_name || "").trim();
    const company = String(client?.company || "").trim();
    const clientId = String(client?.client_id || "").trim();
    if (contact) return contact;
    if (company && company !== clientId) return company;
    if (channelOf(client) === "alibaba") return "未命名阿里客户";
    return company || clientId || String(client?.display_name || "").trim() || "未命名客户";
  };
  const boardClients = () => state.clients.filter((client) => channelOf(client) === state.activeChannel);
  const dateLabel = (value) => {
    const normalized = String(value ?? "").trim();
    return normalized || "未更新";
  };

  function localDateKey(date = new Date()) {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return "";
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function todayKey() {
    return localDateKey(new Date());
  }

  function parseChecklistDate(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value ?? "").trim());
    if (!match) return null;
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    if (Number.isNaN(date.getTime()) || localDateKey(date) !== `${match[1]}-${match[2]}-${match[3]}`) return null;
    return date;
  }

  function isChecklistDate(value) {
    return Boolean(parseChecklistDate(value));
  }

  function shiftDateKey(value, offset) {
    const date = parseChecklistDate(value) || new Date();
    const amount = Number.isFinite(Number(offset)) ? Number(offset) : 0;
    date.setDate(date.getDate() + amount);
    return localDateKey(date);
  }

  function checklistTaskId(task, index) {
    const existing = String(task?.id ?? "").trim();
    return existing || `task-${index + 1}`;
  }

  function normalizeChecklistTask(task, index) {
    const source = task && typeof task === "object" ? task : { text: task };
    const taskText = String(source.text ?? "").replace(/\s+/g, " ").trim().slice(0, CHECKLIST_MAX_TEXT_LENGTH);
    if (!taskText) return null;
    return {
      id: checklistTaskId(source, index),
      text: taskText,
      completed: source.completed === true || source.completed === 1 || source.completed === "true",
      createdAt: String(source.createdAt || "").trim(),
      updatedAt: String(source.updatedAt || "").trim(),
    };
  }

  function normalizeChecklistStore(value) {
    const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    const store = {};
    Object.entries(source).forEach(([date, tasks]) => {
      if (!isChecklistDate(date) || !Array.isArray(tasks)) return;
      store[date] = tasks.map((task, index) => normalizeChecklistTask(task, index)).filter(Boolean);
    });
    return store;
  }

  function readChecklistStore() {
    try {
      const raw = window.localStorage.getItem(CHECKLIST_STORAGE_KEY);
      return normalizeChecklistStore(raw ? JSON.parse(raw) : {});
    } catch (_error) {
      showToast(`每日清单读取失败（${UI_ERROR_CODES.checklist}）`, true);
      return {};
    }
  }

  function writeChecklistStore(store) {
    const normalized = normalizeChecklistStore(store);
    try {
      window.localStorage.setItem(CHECKLIST_STORAGE_KEY, JSON.stringify(normalized));
      checklistState.store = normalized;
      return true;
    } catch (_error) {
      showToast(`每日清单保存失败（${UI_ERROR_CODES.checklist}）`, true);
      return false;
    }
  }

  function checklistTasksForDate(date = checklistState.date) {
    return Array.isArray(checklistState.store[date]) ? checklistState.store[date] : [];
  }

  function createChecklistTask(taskText) {
    const now = new Date().toISOString();
    const id = typeof window.crypto?.randomUUID === "function"
      ? window.crypto.randomUUID()
      : `task-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    return { id, text: taskText, completed: false, createdAt: now, updatedAt: now };
  }

  function renderChecklistProgress(tasks) {
    const total = tasks.length;
    const completed = tasks.filter((task) => task.completed).length;
    const percentage = total ? Math.round((completed / total) * 100) : 0;
    const progressText = $("#checklist-progress-text");
    const progressBar = $("#checklist-progress-bar");
    if (progressText) progressText.textContent = `${completed} / ${total} 已完成 · ${percentage}%`;
    if (progressBar) {
      progressBar.max = total || 1;
      progressBar.value = completed;
      progressBar.textContent = `${percentage}%`;
      progressBar.setAttribute("aria-valuenow", String(completed));
      progressBar.setAttribute("aria-valuemax", String(total || 1));
    }
  }

  function renderChecklist() {
    const list = $("#checklist-list");
    const empty = $("#checklist-empty");
    if (!list || !empty) return;
    const tasks = checklistTasksForDate();
    list.innerHTML = tasks.map((task) => {
      const safeId = escapeHtml(task.id);
      const safeText = escapeHtml(task.text);
      const completed = task.completed ? " is-complete" : "";
      const checked = task.completed ? " checked" : "";
      return `<li class="checklist-item${completed}" data-checklist-task-id="${safeId}">
        <input class="checklist-checkbox" type="checkbox" data-checklist-action="toggle"${checked} aria-label="${task.completed ? "取消完成任务" : "标记任务已完成"}：${safeText}" />
        <div class="checklist-task-body">
          <span class="checklist-task-text" data-checklist-text>${safeText}</span>
          <input class="checklist-edit-input" type="text" maxlength="${CHECKLIST_MAX_TEXT_LENGTH}" value="${safeText}" data-checklist-edit-input aria-label="编辑任务文本" hidden />
        </div>
        <div class="checklist-task-actions">
          <button class="checklist-edit-button button button-quiet" type="button" data-checklist-action="edit" aria-label="编辑任务：${safeText}" title="编辑任务">编辑</button>
          <div class="checklist-edit-actions" hidden>
            <button class="button button-quiet" type="button" data-checklist-action="save">保存</button>
            <button class="button button-quiet" type="button" data-checklist-action="cancel">取消</button>
          </div>
          <button class="checklist-delete-button button button-danger" type="button" data-checklist-action="delete" aria-label="删除任务：${safeText}" title="删除任务">删除</button>
        </div>
      </li>`;
    }).join("");
    empty.hidden = tasks.length > 0;
    renderChecklistProgress(tasks);
  }

  function changeChecklistDate(date) {
    const nextDate = isChecklistDate(date) ? String(date) : todayKey();
    checklistState.date = nextDate;
    const dateInput = $("#checklist-date");
    if (dateInput) dateInput.value = nextDate;
    renderChecklist();
  }

  function navigateChecklistDate(offset) {
    changeChecklistDate(shiftDateKey(checklistState.date || todayKey(), offset));
  }

  function addChecklistTask(event) {
    event.preventDefault();
    const input = $("#checklist-input");
    const taskText = String(input?.value ?? "").replace(/\s+/g, " ").trim();
    if (!taskText) {
      showToast("请输入任务内容", true);
      input?.focus();
      return;
    }
    const date = checklistState.date || todayKey();
    const nextTasks = [...checklistTasksForDate(date), createChecklistTask(taskText.slice(0, CHECKLIST_MAX_TEXT_LENGTH))];
    const nextStore = { ...checklistState.store, [date]: nextTasks };
    if (!writeChecklistStore(nextStore)) return;
    input.value = "";
    renderChecklist();
    input.focus();
  }

  function findChecklistTask(item) {
    const taskId = item?.dataset.checklistTaskId;
    return checklistTasksForDate().find((task) => task.id === taskId);
  }

  function toggleChecklistTask(item) {
    const task = findChecklistTask(item);
    const checkbox = item?.querySelector('[data-checklist-action="toggle"]');
    if (!task || !checkbox) return;
    const nextTasks = checklistTasksForDate().map((candidate) => candidate.id === task.id
      ? { ...candidate, completed: checkbox.checked, updatedAt: new Date().toISOString() }
      : candidate);
    writeChecklistStore({ ...checklistState.store, [checklistState.date]: nextTasks });
    renderChecklist();
  }

  function startChecklistTaskEdit(item) {
    const textNode = item?.querySelector("[data-checklist-text]");
    const input = item?.querySelector("[data-checklist-edit-input]");
    const editButton = item?.querySelector('[data-checklist-action="edit"]');
    const editActions = item?.querySelector(".checklist-edit-actions");
    if (!textNode || !input || !editButton || !editActions) return;
    textNode.hidden = true;
    input.hidden = false;
    editButton.hidden = true;
    editActions.hidden = false;
    input.focus();
    input.select();
  }

  function cancelChecklistTaskEdit(item) {
    const task = findChecklistTask(item);
    const textNode = item?.querySelector("[data-checklist-text]");
    const input = item?.querySelector("[data-checklist-edit-input]");
    const editButton = item?.querySelector('[data-checklist-action="edit"]');
    const editActions = item?.querySelector(".checklist-edit-actions");
    if (!task || !textNode || !input || !editButton || !editActions) return;
    input.value = task.text;
    textNode.hidden = false;
    input.hidden = true;
    editButton.hidden = false;
    editActions.hidden = true;
  }

  function saveChecklistTaskEdit(item) {
    const task = findChecklistTask(item);
    const input = item?.querySelector("[data-checklist-edit-input]");
    const nextText = String(input?.value ?? "").replace(/\s+/g, " ").trim();
    if (!task || !input) return;
    if (!nextText) {
      showToast("任务内容不能为空", true);
      input.focus();
      return;
    }
    const nextTasks = checklistTasksForDate().map((candidate) => candidate.id === task.id
      ? { ...candidate, text: nextText.slice(0, CHECKLIST_MAX_TEXT_LENGTH), updatedAt: new Date().toISOString() }
      : candidate);
    if (writeChecklistStore({ ...checklistState.store, [checklistState.date]: nextTasks })) renderChecklist();
  }

  function deleteChecklistTask(item) {
    const task = findChecklistTask(item);
    if (!task || !window.confirm(`确定删除任务“${task.text}”吗？`)) return;
    const nextTasks = checklistTasksForDate().filter((candidate) => candidate.id !== task.id);
    const nextStore = { ...checklistState.store };
    if (nextTasks.length) nextStore[checklistState.date] = nextTasks;
    else delete nextStore[checklistState.date];
    if (writeChecklistStore(nextStore)) renderChecklist();
  }

  function handleChecklistClick(event) {
    const item = event.target.closest("[data-checklist-task-id]");
    const actionNode = event.target.closest("[data-checklist-action]");
    if (!item || !actionNode) return;
    const action = actionNode.dataset.checklistAction;
    if (action === "toggle") toggleChecklistTask(item);
    else if (action === "edit") startChecklistTaskEdit(item);
    else if (action === "save") saveChecklistTaskEdit(item);
    else if (action === "cancel") cancelChecklistTaskEdit(item);
    else if (action === "delete") deleteChecklistTask(item);
  }

  function handleChecklistKeydown(event) {
    const input = event.target.closest("[data-checklist-edit-input]");
    if (!input) return;
    const item = input.closest("[data-checklist-task-id]");
    if (event.key === "Enter") {
      event.preventDefault();
      saveChecklistTaskEdit(item);
    } else if (event.key === "Escape") {
      event.preventDefault();
      cancelChecklistTaskEdit(item);
    }
  }

  function initializeChecklist() {
    checklistState.store = readChecklistStore();
    changeChecklistDate(todayKey());
  }

  function normalizeTags(value) {
    const values = Array.isArray(value) ? value : String(value ?? "").split(/[,，;；\r\n]+/);
    const tags = [];
    const seen = new Set();
    values.forEach((raw) => {
      const candidate = String(raw ?? "").replace(/\s+/g, " ").trim();
      if (!candidate) return;
      const key = candidate.toLocaleLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      tags.push(candidate);
    });
    return tags;
  }

  function tagsText(value) {
    return normalizeTags(value).join(", ");
  }

  function renderTagChips(value, limit = null) {
    const tags = normalizeTags(value);
    if (!tags.length) return "";
    const visible = limit == null ? tags : tags.slice(0, limit);
    const chips = visible.map((tag) => `<span class="tag-chip" title="${escapeHtml(tag)}">${escapeHtml(tag)}</span>`);
    if (limit != null && tags.length > visible.length) {
      chips.push(`<span class="tag-chip tag-chip-more" title="还有 ${tags.length - visible.length} 个标签">+${tags.length - visible.length}</span>`);
    }
    return chips.join("");
  }

  function safePageSize(value) {
    const numeric = Number.parseInt(value, 10);
    return PAGE_SIZE_OPTIONS.includes(numeric) ? numeric : 12;
  }

  function clampPage(page, totalItems, pageSize) {
    const safeSize = safePageSize(pageSize);
    const totalPages = Math.max(1, Math.ceil(Math.max(0, Number(totalItems) || 0) / safeSize));
    const numeric = Number.parseInt(page, 10);
    const candidate = Number.isFinite(numeric) && numeric > 0 ? numeric : 1;
    return Math.min(candidate, totalPages);
  }

  // 纯分页函数：调用方先完成板块、搜索/筛选和排序，再传入结果切片。
  function paginate(items, page = 1, pageSize = 12) {
    const source = Array.isArray(items) ? items : [];
    const safeSize = safePageSize(pageSize);
    const totalItems = source.length;
    const totalPages = Math.max(1, Math.ceil(totalItems / safeSize));
    const safePage = clampPage(page, totalItems, safeSize);
    const startIndex = totalItems ? (safePage - 1) * safeSize : 0;
    const endIndex = Math.min(startIndex + safeSize, totalItems);
    return {
      items: source.slice(startIndex, endIndex),
      page: safePage,
      pageSize: safeSize,
      totalItems,
      totalPages,
      startIndex,
      endIndex,
    };
  }

  function pageTokens(currentPage, totalPages) {
    if (totalPages <= 7) return Array.from({ length: totalPages }, (_value, index) => index + 1);
    const candidates = [1, totalPages, currentPage - 1, currentPage, currentPage + 1]
      .filter((value) => value >= 1 && value <= totalPages);
    const pages = [...new Set(candidates)].sort((a, b) => a - b);
    const tokens = [];
    pages.forEach((page, index) => {
      if (index > 0 && page - pages[index - 1] > 1) tokens.push("ellipsis");
      tokens.push(page);
    });
    return tokens;
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  // 统一的 modal 关闭入口；原生 <dialog> 与 fallback 都由 closeDialog 处理。
  function closeModal(dialog) {
    closeDialog(dialog);
  }

  function showToast(message, isError = false) {
    const region = $("#toast-region");
    const toast = document.createElement("div");
    toast.className = `toast${isError ? " is-error" : ""}`;
    toast.textContent = message;
    region.appendChild(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  async function requestJSON(url, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 12000);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal, headers: { "Accept": "application/json", ...(options.headers || {}) } });
      let body = null;
      try { body = await response.json(); } catch (_error) { body = null; }
      if (!response.ok) throw new Error(body?.error || `请求失败（${response.status}）`);
      return body;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("请求超时，请确认本地服务仍在运行");
      throw error;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function setLoading(value) {
    state.loading = value;
    $("#loading-state").hidden = !value;
    if (value) $("#pagination").hidden = true;
    if (value) {
      $("#client-grid").innerHTML = "";
      $("#empty-state").hidden = true;
      $("#error-state").hidden = true;
    }
  }

  function updateHealth(isOk, count = null) {
    const node = $("#health-status");
    node.classList.toggle("is-ok", isOk);
    node.classList.toggle("is-error", !isOk);
    node.lastElementChild.textContent = isOk ? `服务正常${count == null ? "" : ` · ${count} 位客户`}` : "服务不可用";
  }

  async function checkHealth() {
    try {
      const body = await requestJSON("/api/health");
      updateHealth(body.status === "ok", body.clients);
      return true;
    } catch (_error) {
      updateHealth(false);
      return false;
    }
  }

  function setOptions(select, values, labelMap = null, placeholder = "全部") {
    const current = select.value;
    const options = [`<option value="">${escapeHtml(placeholder)}</option>`];
    values.forEach((value) => options.push(`<option value="${escapeHtml(value)}">${escapeHtml(labelMap?.[value] || value)}</option>`));
    select.innerHTML = options.join("");
    if (values.includes(current)) select.value = current;
  }

  function populateFilterOptions() {
    const currentClients = boardClients();
    const statuses = [...new Set(currentClients.map((client) => client.status).filter(Boolean))];
    const tiers = ["A", "B", "C"].filter((tier) => currentClients.some((client) => client.icp_tier === tier));
    const markets = [...new Set(currentClients.map((client) => client.market_bucket).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "zh"));
    const sources = [...new Set(currentClients.map((client) => client.source).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "zh"));
    setOptions($("#status-filter"), statuses, STATUS_LABELS, "全部状态");
    setOptions($("#tier-filter"), tiers, TIER_LABELS, "全部等级");
    setOptions($("#market-filter"), markets, null, "全部市场");
    setOptions($("#source-filter"), sources, null, "全部来源");
    // 新增/编辑不能只看到当前数据已经出现过的状态，否则无法把客户推进到
    // 例如 quoting、won 或 lost 等尚未出现的阶段。
    const statusOptions = [...new Set([...Object.keys(STATUS_LABELS), ...(state.filters.statuses || [])])];
    const editStatus = $("#edit-status");
    const addStatus = $("#add-status");
    const makeStatusOptions = () => statusOptions.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(statusLabel(value))}</option>`).join("");
    editStatus.innerHTML = makeStatusOptions();
    addStatus.innerHTML = makeStatusOptions();
    if ([...addStatus.options].some((option) => option.value === "new")) addStatus.value = "new";
  }

  function renderChannelTabs() {
    const alibabaCount = state.clients.filter((client) => channelOf(client) === "alibaba").length;
    const emailCount = state.clients.length - alibabaCount;
    $("#count-alibaba").textContent = String(alibabaCount);
    $("#count-email").textContent = String(emailCount);
    ["alibaba", "email"].forEach((channel) => {
      const node = $(`#channel-${channel}`);
      const active = state.activeChannel === channel;
      node.classList.toggle("is-active", active);
      node.setAttribute("aria-selected", active ? "true" : "false");
      node.tabIndex = active ? 0 : -1;
    });
    $("#export-alibaba-btn").hidden = state.activeChannel !== "alibaba";
    $("#add-client-btn").innerHTML = `<span aria-hidden="true">＋</span> 新增${state.activeChannel === "alibaba" ? "阿里" : "邮件"}客户`;
  }

  function currentFilters() {
    return {
      search: $("#search-input").value.trim().toLocaleLowerCase(),
      status: $("#status-filter").value,
      tier: $("#tier-filter").value,
      market: $("#market-filter").value,
      source: $("#source-filter").value,
      sort: $("#sort-filter").value,
    };
  }

  function applyFilters() {
    const filters = currentFilters();
    const currentClients = boardClients();
    const filtered = currentClients.filter((client) => {
      if (filters.status && client.status !== filters.status) return false;
      if (filters.tier && client.icp_tier !== filters.tier) return false;
      if (filters.market && client.market_bucket !== filters.market) return false;
      if (filters.source && client.source !== filters.source) return false;
      if (filters.search) {
        const haystack = [
          client.company, client.display_name, client.contact_name, client.country_region, client.address, client.product_interest,
          client.product_raw, client.product_name, client.fragrance_requirement, client.product_application,
          client.product_quantity, client.product_specification, client.target_price, client.other_requirements,
          client.product_codes, client.product_names, JSON.stringify(client.product_items || []),
          client.custom_tags, normalizeTags(client.custom_tags).join(" "),
          client.source, client.status, client.next_action, client.notes, client.public_summary,
        ].join(" ").toLocaleLowerCase();
        if (!haystack.includes(filters.search)) return false;
      }
      return true;
    });
    filtered.sort((a, b) => {
      if (filters.sort === "score_desc") return (b.icp_score ?? -1) - (a.icp_score ?? -1);
      if (filters.sort === "score_asc") return (a.icp_score ?? 999) - (b.icp_score ?? 999);
      if (filters.sort === "company_asc") return text(a.company, a.client_id).localeCompare(text(b.company, b.client_id), "zh");
      return text(b.updated_at, "").localeCompare(text(a.updated_at, ""));
    });
    const pagination = paginate(filtered, state.page, state.pageSize);
    state.page = pagination.page;
    renderCards(pagination.items);
    if (pagination.totalItems) {
      $("#result-count").textContent = `第 ${pagination.startIndex + 1}–${pagination.endIndex} 条 · 筛选后 ${pagination.totalItems} 条 · 当前渠道 ${currentClients.length} 位`;
    } else {
      $("#result-count").textContent = `筛选后 0 条 · 当前渠道 ${currentClients.length} 位`;
    }
    renderPagination(pagination, currentClients.length);
  }

  function renderPagination(pagination, channelTotal) {
    const nav = $("#pagination");
    const summary = $("#pagination-summary");
    const pages = $("#pagination-pages");
    const previous = $("#pagination-prev");
    const next = $("#pagination-next");
    if (!pagination.totalItems) {
      nav.hidden = true;
      pages.innerHTML = "";
      return;
    }
    nav.hidden = false;
    summary.textContent = `第 ${pagination.startIndex + 1}–${pagination.endIndex} 条 · 筛选后 ${pagination.totalItems} 条 · 当前渠道 ${channelTotal} 位`;
    const singlePage = pagination.totalPages <= 1;
    pages.hidden = singlePage;
    previous.hidden = singlePage;
    next.hidden = singlePage;
    previous.disabled = singlePage || pagination.page <= 1;
    next.disabled = singlePage || pagination.page >= pagination.totalPages;
    pages.innerHTML = singlePage ? "" : pageTokens(pagination.page, pagination.totalPages).map((token) => {
      if (token === "ellipsis") return '<span class="page-ellipsis" role="presentation" aria-hidden="true">…</span>';
      const current = token === pagination.page;
      return `<button class="page-button${current ? " is-current" : ""}" type="button" data-page="${token}" aria-label="第 ${token} 页"${current ? ' aria-current="page"' : ""}>${token}</button>`;
    }).join("");
  }

  function renderStats(stats = {}) {
    const currentClients = boardClients();
    const active = currentClients.filter((client) => !["won", "lost", "disqualified", "cold"].includes(client.status));
    const pending = active.filter((client) => String(client.next_action || "").trim());
    $("#stat-total").textContent = stats.total ?? currentClients.length;
    $("#stat-tier-a").textContent = stats.tier_a ?? currentClients.filter((client) => client.icp_tier === "A").length;
    $("#stat-active").textContent = stats.active ?? active.length;
    $("#stat-pending").textContent = stats.pending ?? pending.length;
  }

  function cardField(label, value) {
    return `<div class="card-field"><span class="card-field-label">${escapeHtml(label)}</span><span class="card-field-value" title="${escapeHtml(text(value))}">${escapeHtml(text(value))}</span></div>`;
  }

  function renderCards(clients) {
    const grid = $("#client-grid");
    $("#empty-state").hidden = clients.length !== 0;
    if (!clients.length) {
      const hasFilter = Object.values(currentFilters()).some((value) => value && value !== "updated_desc");
      $("#empty-title").textContent = hasFilter ? "没有匹配的客户" : "还没有客户档案";
      $("#empty-message").textContent = hasFilter ? "换个关键词或清除筛选，看看其他客户。" : "点击右上角“新增客户”建立第一份档案。";
      grid.innerHTML = "";
      return;
    }
    grid.innerHTML = clients.map((client) => {
      const isAlibaba = channelOf(client) === "alibaba";
      const tier = client.icp_tier || "C";
      const score = client.icp_score == null ? "—" : client.icp_score;
      const subtitle = text(client.company, "公司待补充");
      const next = text(client.next_action, "尚未设置下一步");
      const title = displayName(client);
      const primaryLabel = "电话";
      const primaryValue = client.known_phone || client.known_email;
      const secondaryLabel = "地址";
      const secondaryValue = client.address || client.country_region;
      const tertiary = client.product_interest || client.product_name || client.product_application || client.product_raw;
      return `<button class="client-card ${isAlibaba ? "channel-alibaba" : "channel-email"} tier-${escapeHtml(tier.toLowerCase())}" type="button" data-client-id="${escapeHtml(client.client_id)}" data-channel="${isAlibaba ? "alibaba" : "email"}" aria-label="查看 ${escapeHtml(title)} 详情">
        <div class="card-top">
          <div class="card-title"><h3 title="${escapeHtml(title)}">${escapeHtml(title)}</h3><p class="card-contact" title="${escapeHtml(subtitle)}">${escapeHtml(subtitle)}</p></div>
          <span class="tier-badge" title="ICP ${escapeHtml(tier)} 级">${escapeHtml(tier)}</span>
        </div>
        <div class="card-meta"><span class="status-chip" data-status="${escapeHtml(client.status || "")}">${escapeHtml(statusLabel(client.status || "未设置"))}</span><span class="score">${escapeHtml(String(score))}<span> / 100</span></span></div>
        ${renderTagChips(client.custom_tags, 3) ? `<div class="card-tags" aria-label="自定义标签">${renderTagChips(client.custom_tags, 3)}</div>` : ""}
        <div class="card-divider"></div>
        ${cardField(primaryLabel, primaryValue)}
        ${cardField(secondaryLabel, secondaryValue)}
        ${cardField("产品", tertiary)}
        <div class="card-action"><span class="card-action-label">下一步</span><span class="card-action-value" title="${escapeHtml(next)}">${escapeHtml(next)}</span></div>
        <div class="card-footer"><span class="card-source">来源 · ${escapeHtml(text(client.source))}</span><span>更新 · ${escapeHtml(dateLabel(client.updated_at))}</span></div>
      </button>`;
    }).join("");
  }

  function markdownToHtml(markdown) {
    const raw = String(markdown || "").trim();
    if (!raw) return `<p class="detail-copy">未填写</p>`;
    const lines = raw.split(/\r?\n/);
    let output = "";
    let listOpen = false;
    const closeList = () => { if (listOpen) { output += "</ul>"; listOpen = false; } };
    lines.forEach((line) => {
      const safe = escapeHtml(line);
      if (/^\s*[-*]\s+/.test(line)) {
        if (!listOpen) { output += "<ul class=\"md-list\">"; listOpen = true; }
        output += `<li>${escapeHtml(line.replace(/^\s*[-*]\s+/, ""))}</li>`;
      } else if (!line.trim()) {
        closeList();
      } else {
        closeList();
        output += `<p>${safe}</p>`;
      }
    });
    closeList();
    return `<div class="detail-copy">${output}</div>`;
  }

  function detailItem(label, value) {
    return `<div class="detail-item"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(text(value))}</dd></div>`;
  }

  function detailLines(value) {
    return String(value ?? "")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/\r\n?/g, "\n")
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }

  function detailMultilineItem(label, value, field) {
    const lines = detailLines(value);
    const visibleLines = lines.slice(0, DETAIL_LINE_LIMIT);
    const extraLines = lines.slice(DETAIL_LINE_LIMIT);
    const extraId = `detail-${field}-extra`;
    const lineMarkup = (line) => `<span class="detail-line">${escapeHtml(line)}</span>`;
    const visibleMarkup = visibleLines.length ? visibleLines.map(lineMarkup).join("") : '<span class="detail-empty">未填写</span>';
    const extraMarkup = extraLines.map(lineMarkup).join("");
    const toggle = extraLines.length
      ? `<button class="detail-expand-toggle" type="button" data-detail-expand="${extraId}" data-remaining="${extraLines.length}" aria-expanded="false" aria-controls="${extraId}">展开剩余 ${extraLines.length} 条</button>`
      : "";
    const count = lines.length ? ` <small class="detail-line-count">${lines.length} 条</small>` : "";
    return `<div class="detail-item detail-item-multiline"><dt>${escapeHtml(label)}${count}</dt><dd><div class="detail-line-list">${visibleMarkup}</div>${extraLines.length ? `<div id="${extraId}" class="detail-lines-extra" hidden>${extraMarkup}</div>` : ""}${toggle}</dd></div>`;
  }

  function renderDetail(client) {
    if (!client) return;
    const isAlibaba = channelOf(client) === "alibaba";
    const title = displayName(client);
    $("#dialog-kicker").textContent = `${TIER_LABELS[client.icp_tier] || "客户详情"} · ${statusLabel(client.status)}`;
    $("#dialog-title").textContent = title;
    const score = client.icp_score == null ? "未评分" : `${client.icp_score} / 100`;
    $("#detail-view").innerHTML = `
      <div class="detail-overview">
        <div class="detail-stat"><span class="detail-stat-label">当前状态</span><strong class="detail-stat-value">${escapeHtml(statusLabel(client.status))}</strong></div>
        <div class="detail-stat"><span class="detail-stat-label">ICP 分数</span><strong class="detail-stat-value">${escapeHtml(score)}</strong></div>
        <div class="detail-stat"><span class="detail-stat-label">最近更新</span><strong class="detail-stat-value">${escapeHtml(dateLabel(client.updated_at))}</strong></div>
      </div>
      <section class="detail-section"><h3>基本资料</h3><dl class="detail-grid">
        ${detailItem("联系人", client.contact_name)}
        ${detailItem("电话", client.known_phone)}
        ${detailItem("地址", client.address)}
        ${detailItem("公司", client.company)}
        ${detailItem("职位", client.title)}
        ${detailItem("地区", client.country_region)}
        ${detailItem("市场", client.market_bucket)}
        ${detailItem("板块", isAlibaba ? "阿里客户" : "邮件客户")}
        ${detailItem("来源", client.source)}
        ${detailItem("邮箱", client.known_email)}
        ${detailItem("渠道类型", client.channel_type)}
        ${detailItem("产品兴趣", client.product_interest)}
        ${detailItem("客户 ID", client.client_id)}
        ${detailItem("创建时间", client.created_at)}
        ${detailItem("详情档案", client.has_profile ? client.source_file : "索引 / pipeline 记录")}
      </dl><div class="detail-tags" aria-label="自定义标签"><span class="detail-tags-label">自定义标签</span><div class="tag-list">${renderTagChips(client.custom_tags) || '<span class="detail-empty">未设置</span>'}</div></div></section>
      ${isAlibaba ? `<section class="detail-section"><h3>Alibaba 产品信息</h3><dl class="detail-grid">
        ${detailMultilineItem("内部编码", client.product_codes, "product-codes")}
        ${detailMultilineItem("批量产品名称", client.product_names, "product-names")}
        ${detailItem("批量产品条数", Array.isArray(client.product_items) ? client.product_items.length : 0)}
        ${detailItem("产品名称", client.product_name)}
        ${detailItem("香型要求", client.fragrance_requirement)}
        ${detailItem("产品用途", client.product_application)}
        ${detailItem("产品数量", client.product_quantity)}
        ${detailItem("产品规格", client.product_specification)}
        ${detailItem("目标价格", client.target_price)}
        ${detailItem("其他要求", client.other_requirements)}
        ${detailMultilineItem("产品原文", client.product_raw, "product-raw")}
      </dl><div class="bulk-product-actions detail-product-copy-actions" aria-label="复制 Alibaba 产品信息">
        <button class="button button-quiet" type="button" data-detail-copy-field="product_codes">一键复制内部编码</button>
        <button class="button button-quiet" type="button" data-detail-copy-field="product_names">一键复制产品名称</button>
      </div></section>` : ""}
      <section class="detail-section"><h3>下一步行动</h3>${markdownToHtml(client.next_action)}</section>
      <section class="detail-section"><h3>公开摘要</h3>${markdownToHtml(client.public_summary)}</section>
      <section class="detail-section"><h3>ICP 判断</h3>${markdownToHtml(client.icp_rationale)}</section>
      <section class="detail-section"><h3>备注</h3>${markdownToHtml(client.notes)}</section>
      <section class="detail-section"><h3>沟通记录</h3>${markdownToHtml(client.outreach_log)}</section>
      <section class="detail-section"><h3>沟通要点</h3>${markdownToHtml(client.communication_points)}</section>
      <section class="detail-section"><h3>产品 / 报价链接</h3>${markdownToHtml(client.product_quote_links)}</section>
      ${client.raw_markdown ? `<details class="detail-section raw-details"><summary>查看完整原始档案</summary><pre class="detail-raw">${escapeHtml(client.raw_markdown)}</pre></details>` : ""}`;
  }

  function showClientDetail(clientId) {
    const client = state.clients.find((item) => item.client_id === clientId);
    if (!client) return;
    state.selectedClientId = clientId;
    renderDetail(client);
    $("#detail-view").hidden = false;
    $("#edit-form").hidden = true;
    $("#detail-actions").hidden = false;
    openDialog($("#client-dialog"));
  }

  function showEditForm() {
    const client = state.clients.find((item) => item.client_id === state.selectedClientId);
    if (!client) return;
    const editFields = [
      "company", "contact_name", "title", "country_region", "address", "market_bucket",
      "channel_type", "known_email", "known_phone", "custom_tags", "product_interest", "product_raw",
      "product_codes", "product_names", "icp_tier", "icp_score", "status", "next_action", "notes",
    ];
    const form = $("#edit-form");
    editFields.forEach((field) => {
      const input = form.elements.namedItem(field);
      if (!input) return;
      if (field === "status") input.value = client.status || "new";
      else if (field === "icp_tier") input.value = client.icp_tier || "C";
      else if (field === "icp_score") input.value = Number.isFinite(Number(client.icp_score)) ? String(client.icp_score) : "0";
      else if (field === "custom_tags") input.value = tagsText(client.custom_tags);
      else input.value = client[field] || "";
    });
    const isAlibaba = channelOf(client) === "alibaba";
    $("#edit-company").required = !isAlibaba;
    $("#edit-company-label").textContent = isAlibaba ? "公司名称" : "公司名称 *";
    $("#edit-contact-raw").placeholder = isAlibaba ? CONTACT_PASTE_PLACEHOLDER_ALI : CONTACT_PASTE_PLACEHOLDER_EMAIL;
    $("#edit-product-parse-status").textContent = "手工编码和名称不会被自动覆盖";
    resetContactParser(editContactParser, "#edit-contact-raw", "#edit-contact-parse-status");
    CONTACT_PARSE_FIELDS.forEach((field) => {
      const input = form.elements.namedItem(field);
      if (input && String(input.value || "").trim()) editContactParser.manual.add(field);
    });
    $("#detail-view").hidden = true;
    $("#detail-actions").hidden = true;
    form.hidden = false;
    window.setTimeout(() => $("#edit-contact-raw").focus(), 0);
  }

  function showDetailView() {
    $("#detail-view").hidden = false;
    $("#detail-actions").hidden = false;
    $("#edit-form").hidden = true;
    const client = state.clients.find((item) => item.client_id === state.selectedClientId);
    if (client) renderDetail(client);
  }

  function formObject(form) {
    const result = {};
    const preserveMultiline = new Set(["product_raw", "product_codes", "product_names", "other_requirements", "notes", "address"]);
    new FormData(form).forEach((value, key) => {
      result[key] = typeof value === "string" && !preserveMultiline.has(key) ? value.trim() : value;
    });
    return result;
  }

  function readDrafts() {
    try {
      const parsed = JSON.parse(window.localStorage.getItem(DRAFT_STORAGE_KEY) || "[]");
      return Array.isArray(parsed) ? parsed.filter((draft) => draft && draft.id && draft.data) : [];
    } catch (_error) {
      showToast(`草稿箱读取失败（${UI_ERROR_CODES.draft}）`, true);
      return [];
    }
  }

  function writeDrafts(drafts) {
    try {
      window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(drafts));
      return true;
    } catch (_error) {
      showToast(`草稿箱保存失败（${UI_ERROR_CODES.draft}）`, true);
      return false;
    }
  }

  function collectDraftData() {
    const data = formObject($("#add-form"));
    data.source = state.activeChannel === "alibaba" ? "alibaba" : "email_manual";
    data.customer_channel = state.activeChannel;
    return data;
  }

  function draftFingerprint(data) {
    const ordered = {};
    Object.keys(data || {}).sort().forEach((key) => { ordered[key] = String(data[key] ?? ""); });
    return JSON.stringify(ordered);
  }

  function captureDraftBaseline() {
    draftState.baseline = draftFingerprint(collectDraftData());
  }

  function isAddFormDirty() {
    return draftFingerprint(collectDraftData()) !== draftState.baseline;
  }

  function draftDisplayName(draft) {
    const data = draft.data || {};
    const firstProduct = String(data.product_names || "").split(/\r?\n/).find((value) => value.trim());
    return String(data.contact_name || data.company || firstProduct || (draft.channel === "alibaba" ? "未命名阿里客户" : "未命名邮件客户")).trim();
  }

  function draftProductCount(draft) {
    const data = draft.data || {};
    const codes = String(data.product_codes || "").split(/\r?\n/);
    const names = String(data.product_names || "").split(/\r?\n/);
    const rows = Math.max(codes.length, names.length);
    let count = 0;
    for (let index = 0; index < rows; index += 1) {
      if (String(codes[index] || "").trim() || String(names[index] || "").trim()) count += 1;
    }
    return count;
  }

  function updateDraftCount() {
    const count = readDrafts().length;
    const node = $("#draft-count");
    if (node) node.textContent = String(count);
  }

  function renderDrafts() {
    const list = $("#draft-list");
    const drafts = readDrafts();
    updateDraftCount();
    if (!drafts.length) {
      list.innerHTML = `<div class="draft-empty"><strong>草稿箱为空</strong><span>退出未完成的新建表单时，可以选择保存到这里。</span></div>`;
      return;
    }
    list.innerHTML = drafts.map((draft) => {
      const savedAt = new Date(draft.savedAt || Date.now());
      const savedLabel = Number.isNaN(savedAt.getTime()) ? "时间未知" : savedAt.toLocaleString("zh-CN", { hour12: false });
      const productCount = draftProductCount(draft);
      return `<article class="draft-item" data-draft-id="${escapeHtml(draft.id)}">
        <div class="draft-item-copy">
          <span class="draft-channel">${draft.channel === "alibaba" ? "阿里客户" : "邮件客户"}</span>
          <strong>${escapeHtml(draftDisplayName(draft))}</strong>
          <small>${escapeHtml(savedLabel)}${productCount ? ` · ${productCount} 项产品` : ""}</small>
        </div>
        <div class="draft-item-actions">
          <button class="button button-quiet" type="button" data-draft-action="restore">继续编辑</button>
          <button class="button button-danger" type="button" data-draft-action="delete">删除</button>
        </div>
      </article>`;
    }).join("");
  }

  function resetAndCloseAddDialog() {
    closeDialog($("#draft-confirm-dialog"));
    closeDialog($("#add-dialog"));
    $("#add-form").reset();
    resetProductParser();
    resetContactParser(addContactParser, "#add-contact-raw", "#add-contact-parse-status");
    draftState.activeId = null;
    draftState.baseline = "";
  }

  function requestCloseAddDialog() {
    const dialog = $("#add-dialog");
    if (!dialog?.open && !dialog?.hasAttribute("open")) return;
    if (!isAddFormDirty()) {
      resetAndCloseAddDialog();
      return;
    }
    openDialog($("#draft-confirm-dialog"));
  }

  function saveCurrentDraft() {
    const data = collectDraftData();
    const drafts = readDrafts();
    const draft = {
      id: draftState.activeId || `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      channel: state.activeChannel,
      savedAt: new Date().toISOString(),
      data,
    };
    const nextDrafts = [draft, ...drafts.filter((item) => item.id !== draft.id)];
    if (!writeDrafts(nextDrafts)) return;
    resetAndCloseAddDialog();
    renderDrafts();
    showToast("未完成信息已保存到草稿箱");
  }

  function removeActiveDraft() {
    if (!draftState.activeId) return;
    const drafts = readDrafts().filter((draft) => draft.id !== draftState.activeId);
    writeDrafts(drafts);
    draftState.activeId = null;
    updateDraftCount();
  }

  function restoreDraft(draft) {
    if (!draft) return;
    closeDialog($("#draft-dialog"));
    state.activeChannel = draft.channel === "alibaba" ? "alibaba" : "email";
    state.page = 1;
    renderChannelTabs();
    populateFilterOptions();
    renderStats({});
    applyFilters();
    openAddDialog(draft);
  }

  function handleDraftListClick(event) {
    const button = event.target.closest("[data-draft-action]");
    const item = event.target.closest("[data-draft-id]");
    if (!button || !item) return;
    const drafts = readDrafts();
    const draft = drafts.find((candidate) => candidate.id === item.dataset.draftId);
    if (!draft) return renderDrafts();
    if (button.dataset.draftAction === "restore") {
      restoreDraft(draft);
      return;
    }
    if (button.dataset.draftAction === "delete" && window.confirm(`确定删除草稿“${draftDisplayName(draft)}”吗？`)) {
      if (writeDrafts(drafts.filter((candidate) => candidate.id !== draft.id))) {
        renderDrafts();
        showToast("草稿已删除");
      }
    }
  }

  const productSplitFields = [
    "product_codes",
    "product_names",
  ];
  const productParserState = { manual: new Set(), manualInterest: false, manualRaw: false, suggested: {}, suggestedInterest: "", suggestedRaw: "", timer: null, requestId: 0, applying: false };
  function newContactParserState() {
    return { manual: new Set(), suggested: {}, timer: null, requestId: 0, applying: false };
  }
  const addContactParser = newContactParserState();
  const editContactParser = newContactParserState();

  function resetContactParser(parser, rawSelector, statusSelector) {
    parser.manual = new Set();
    parser.suggested = {};
    parser.requestId += 1;
    parser.applying = false;
    if (parser.timer) window.clearTimeout(parser.timer);
    parser.timer = null;
    const raw = $(rawSelector);
    if (raw) raw.value = "";
    const status = $(statusSelector);
    if (status) status.textContent = "";
  }

  function applyContactFields(form, parser, fields) {
    const filled = [];
    parser.applying = true;
    CONTACT_PARSE_FIELDS.forEach((field) => {
      const input = form.elements.namedItem(field);
      if (!input) return;
      const suggestion = String(fields[field] || "").trim();
      const current = String(input.value || "").trim();
      const previous = String(parser.suggested[field] || "").trim();
      parser.suggested[field] = suggestion;
      if (!suggestion) return;
      if (parser.manual.has(field) && current && current !== previous) return;
      input.value = suggestion;
      filled.push(CONTACT_FIELD_LABELS[field] || field);
    });
    parser.applying = false;
    return filled;
  }

  function scheduleContactParse(parser, rawSelector, statusSelector, formSelector) {
    if (parser.timer) window.clearTimeout(parser.timer);
    const requestId = ++parser.requestId;
    const raw = $(rawSelector)?.value.trim() || "";
    const status = $(statusSelector);
    if (!raw) {
      if (status) status.textContent = "";
      return;
    }
    if (status) status.textContent = "正在识别姓名、电话和地址…";
    parser.timer = window.setTimeout(async () => {
      try {
        const body = await requestJSON("/api/contact-info/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw_text: raw }),
        });
        if (requestId !== parser.requestId) return;
        const fields = body.fields || body;
        const filled = applyContactFields($(formSelector), parser, fields);
        const productExcerpt = String(body.product_excerpt || "").trim();
        const productSynced = await fillAlibabaProductsFromContact(productExcerpt, formSelector);
        if (status) {
          if (filled.length && productSynced > 0) status.textContent = `已填入${filled.join("、")}，并同步识别 ${productSynced} 项产品`;
          else if (filled.length && productSynced < 0) status.textContent = `已填入${filled.join("、")}，正在同步识别产品…`;
          else if (filled.length) status.textContent = `已填入${filled.join("、")}，可继续手工修改`;
          else status.textContent = "暂未识别出姓名、电话或地址，可继续手工填写";
        }
      } catch (error) {
        if (status) status.textContent = `${error.message || "识别暂不可用"}（${UI_ERROR_CODES.contactParse}），仍可手工填写`;
      }
    }, 420);
  }

  function bindContactParser(parser, rawSelector, statusSelector, formSelector) {
    const raw = $(rawSelector);
    const form = $(formSelector);
    if (!raw || !form) return;
    raw.addEventListener("input", () => scheduleContactParse(parser, rawSelector, statusSelector, formSelector));
    raw.addEventListener("paste", () => window.setTimeout(() => scheduleContactParse(parser, rawSelector, statusSelector, formSelector), 0));
    CONTACT_PARSE_FIELDS.forEach((field) => {
      const input = form.elements.namedItem(field);
      if (!input) return;
      input.addEventListener("input", () => {
        if (!parser.applying) parser.manual.add(field);
      });
    });
  }

  function isAlibabaContactForm(formSelector) {
    if (formSelector === "#add-form") return state.activeChannel === "alibaba";
    const client = state.clients.find((item) => item.client_id === state.selectedClientId);
    return channelOf(client) === "alibaba";
  }

  async function fillAlibabaProductsFromContact(excerpt, formSelector) {
    if (!excerpt || !isAlibabaContactForm(formSelector)) return 0;
    const isAdd = formSelector === "#add-form";
    const rawInput = isAdd ? $("#add-product-raw") : $("#edit-product-raw");
    const codesInput = isAdd ? $("#add-product-codes") : $("#edit-product-codes");
    const namesInput = isAdd ? $("#add-product-names") : $("#edit-product-names");
    if (!rawInput) return 0;
    const current = String(rawInput.value || "").trim();
    const previous = String(productParserState.suggestedRaw || "").trim();
    if (isAdd) {
      if (productParserState.manualRaw && current && current !== previous) return 0;
    } else if (current || String(codesInput?.value || "").trim() || String(namesInput?.value || "").trim()) {
      return 0;
    }
    rawInput.value = excerpt;
    productParserState.suggestedRaw = excerpt;
    if (isAdd) {
      scheduleProductParse();
      return -1;
    }
    await parseEditProducts();
    const items = String($("#edit-product-codes")?.value || "").split(/\r?\n/).filter((line) => line.trim());
    return items.length;
  }

  function resetProductParser() {
    productParserState.manual = new Set();
    productParserState.manualInterest = false;
    productParserState.manualRaw = false;
    productParserState.suggested = {};
    productParserState.suggestedInterest = "";
    productParserState.suggestedRaw = "";
    productParserState.requestId += 1;
    if (productParserState.timer) window.clearTimeout(productParserState.timer);
    productParserState.timer = null;
    const status = $("#product-parse-status");
    if (status) status.textContent = "";
    const count = $("#bulk-product-count");
    const pairing = $("#bulk-product-pairing-status");
    if (count) count.textContent = "未识别产品";
    if (pairing) pairing.textContent = "等待产品原文";
  }

  function setAddFormChannel() {
    const isAlibaba = state.activeChannel === "alibaba";
    const form = $("#add-form");
    const company = $("#add-company");
    const companyLabel = $("#add-company-label");
    const source = $("#add-source");
    const status = $("#add-status");
    company.required = !isAlibaba;
    companyLabel.textContent = isAlibaba ? "公司名称" : "公司名称 *";
    source.innerHTML = `<option value="${isAlibaba ? "alibaba" : "email_manual"}">${isAlibaba ? "Alibaba（固定）" : "邮件录入（固定）"}</option>`;
    source.value = isAlibaba ? "alibaba" : "email_manual";
    source.disabled = true;
    $("#product-parser-fields").hidden = !isAlibaba;
    $("#add-contact-raw").placeholder = isAlibaba ? CONTACT_PASTE_PLACEHOLDER_ALI : CONTACT_PASTE_PLACEHOLDER_EMAIL;
    $("#add-dialog-title").textContent = isAlibaba ? "新增阿里客户" : "新增邮件客户";
    $("#add-dialog-intro").textContent = isAlibaba
      ? "可先粘贴阿里询盘整段文字，系统会识别姓名、电话、地址，并拆分产品列表。其他字段都可以先留空。"
      : "录入后会生成客户 Markdown，并同步索引与 pipeline。邮件客户需要公司名称。粘贴整段联系信息可自动填入姓名、电话和地址。";
    if (status && !status.value) status.value = "new";
  }

  function openAddDialog(draft = null) {
    const form = $("#add-form");
    form.reset();
    resetProductParser();
    resetContactParser(addContactParser, "#add-contact-raw", "#add-contact-parse-status");
    setAddFormChannel();
    $("#add-form-error").hidden = true;
    if ([...$("#add-status").options].some((option) => option.value === "new")) $("#add-status").value = "new";
    draftState.activeId = draft?.id || null;
    if (draft?.data) {
      Object.entries(draft.data).forEach(([field, value]) => {
        const input = form.elements.namedItem(field);
        if (input && typeof input.value === "string") input.value = String(value ?? "");
      });
      const count = draftProductCount(draft);
      $("#bulk-product-count").textContent = count ? `草稿含 ${count} 项产品` : "草稿暂无产品";
      $("#bulk-product-pairing-status").textContent = count ? "编码与名称按行对应" : "等待产品原文";
      $("#add-dialog-title").textContent = state.activeChannel === "alibaba" ? "继续编辑阿里客户草稿" : "继续编辑邮件客户草稿";
      productParserState.manualInterest = Boolean(String(draft.data.product_interest || "").trim());
    }
    captureDraftBaseline();
    openDialog($("#add-dialog"));
    window.setTimeout(() => $("#add-contact-raw").focus(), 0);
  }

  function scheduleProductParse() {
    if (productParserState.timer) window.clearTimeout(productParserState.timer);
    const requestId = ++productParserState.requestId;
    const raw = $("#add-product-raw").value.trim();
    const status = $("#product-parse-status");
    if (!raw) {
      status.textContent = "";
      const count = $("#bulk-product-count");
      const pairing = $("#bulk-product-pairing-status");
      if (count) count.textContent = "未识别产品";
      if (pairing) pairing.textContent = "等待产品原文";
      return;
    }
    status.textContent = "正在生成拆分建议…";
    productParserState.timer = window.setTimeout(async () => {
      try {
        const body = await requestJSON("/api/product-info/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw_text: raw }),
        });
        if (requestId !== productParserState.requestId) return;
        const fields = body.fields || body;
        productParserState.applying = true;
        productSplitFields.forEach((field) => {
          const input = $("#add-form").elements.namedItem(field);
          if (!input) return;
          const suggestion = String(fields[field] || "");
          // 每次新原文解析都刷新未标记为 manual 的字段；手工字段保持原值。
          if (!productParserState.manual.has(field)) input.value = suggestion;
          productParserState.suggested[field] = suggestion;
        });
        productParserState.applying = false;
        const bulkItems = Array.isArray(fields.product_items) ? fields.product_items : [];
        const bulkCount = $("#bulk-product-count");
        const bulkPairing = $("#bulk-product-pairing-status");
        if (bulkCount) bulkCount.textContent = bulkItems.length ? `识别 ${bulkItems.length} 项产品` : "未识别产品";
        if (bulkPairing) bulkPairing.textContent = bulkItems.length ? "编码与名称按行对应；缺失一侧留空" : "可继续手动填写批量字段";
        const productInterest = $("#add-form").elements.namedItem("product_interest");
        if (productInterest && !productParserState.manualInterest) {
          const previousInterest = productParserState.suggestedInterest || "";
          const summary = String(fields.product_names || "").split(/\r?\n/).map((value) => value.trim()).filter(Boolean).slice(0, 3).join(" / ").slice(0, 600);
          if (!productInterest.value.trim() || productInterest.value.trim() === previousInterest) productInterest.value = summary;
          productParserState.suggestedInterest = summary;
        }
        status.textContent = bulkItems.length ? `已拆分 ${bulkItems.length} 项产品，请核对两列后分别复制` : "暂未识别产品名称与内部编码，可在两列中手动填写";
      } catch (error) {
        productParserState.applying = false;
        status.textContent = `${error.message || "拆分暂不可用"}（${UI_ERROR_CODES.productParse}），仍可手动填写两列`;
      }
    }, 420);
  }

  function normalizedCopyLines(value) {
    // 复制到 Excel 时必须保留空位，否则编码列和名称列会发生行错位。
    // 这里只做换行归一化及逐行横向 trim，不删除任何行。
    return String(value ?? "").replace(/\r\n?/g, "\n").split("\n").map((line) => line.trim()).join("\n");
  }

  async function copyProductColumn(field, label, valueOverride) {
    const input = $("#add-form").elements.namedItem(field);
    const value = normalizedCopyLines(valueOverride === undefined ? input?.value : valueOverride);
    const rows = value.split("\n");
    const hasContent = rows.some((line) => line.length > 0);
    if (!hasContent) {
      showToast(`${label}暂无可复制内容（${UI_ERROR_CODES.bulkCopy}）`, true);
      return;
    }
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(value);
      } else {
        const helper = document.createElement("textarea");
        helper.value = value;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.focus();
        helper.select();
        const copied = document.execCommand("copy");
        helper.remove();
        if (!copied) throw new Error("clipboard fallback rejected");
      }
      const emptyRows = rows.reduce((count, line) => count + (line.length ? 0 : 1), 0);
      showToast(`${label}已复制 ${rows.length} 行${emptyRows ? "（含空位）" : ""}`);
    } catch (_error) {
      showToast(`${label}复制失败（${UI_ERROR_CODES.bulkCopy}），请手动选择复制`, true);
    }
  }

  function copyDetailProductColumn(field) {
    const client = state.clients.find((item) => item.client_id === state.selectedClientId);
    if (!client) {
      showToast(`${DETAIL_COPY_LABELS[field] || "产品信息"}复制失败（${UI_ERROR_CODES.bulkCopy}），请先重新打开详情`, true);
      return Promise.resolve();
    }
    return copyProductColumn(field, DETAIL_COPY_LABELS[field] || "产品信息", client[field] ?? "");
  }

  function localValidateNew(data) {
    if (state.activeChannel === "email" && !data.company) return "邮件客户必须填写公司名称";
    if (data.icp_score !== "" && (!/^\d+$/.test(data.icp_score) || Number(data.icp_score) < 0 || Number(data.icp_score) > 100)) return "分数必须是 0 到 100 的整数";
    if (data.known_email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.known_email)) return "邮箱格式不正确";
    return "";
  }

  async function loadData({ showLoading = true } = {}) {
    if (showLoading) setLoading(true);
    $("#error-state").hidden = true;
    try {
      const body = await requestJSON("/api/clients");
      state.clients = Array.isArray(body.clients) ? body.clients : [];
      state.filters = body.filters || state.filters;
      renderChannelTabs();
      populateFilterOptions();
      renderStats({});
      applyFilters();
      $("#loading-state").hidden = true;
      await checkHealth();
    } catch (error) {
      $("#loading-state").hidden = true;
      $("#client-grid").innerHTML = "";
      $("#pagination").hidden = true;
      $("#empty-state").hidden = true;
      $("#error-state").hidden = false;
      $("#error-message").textContent = error.message || "请确认本地服务仍在运行，然后重试。";
      updateHealth(false);
    } finally {
      setLoading(false);
    }
  }

  async function submitEdit(event) {
    event.preventDefault();
    const payload = formObject(event.currentTarget);
    const client = state.clients.find((item) => item.client_id === state.selectedClientId);
    if (!client) return showToast("当前客户不存在，请刷新后重试", true);
    if (channelOf(client) === "email" && !payload.company) return showToast("邮件客户必须填写公司名称", true);
    if (!payload.status) return showToast("请选择客户状态", true);
    if (payload.icp_score === "") payload.icp_score = "0";
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await requestJSON(`/api/clients/${encodeURIComponent(state.selectedClientId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      showToast("客户更新成功，已同步原始 Markdown");
      closeDialog($("#client-dialog"));
      await loadData({ showLoading: false });
    } catch (error) {
      showToast(error.message || "保存失败", true);
    } finally {
      button.disabled = false;
    }
  }

  async function parseEditProducts() {
    const raw = $("#edit-product-raw").value.trim();
    const status = $("#edit-product-parse-status");
    if (!raw) {
      status.textContent = "请先填写产品原文";
      return;
    }
    const button = $("#edit-parse-products");
    button.disabled = true;
    status.textContent = "正在重新识别…";
    try {
      const body = await requestJSON("/api/product-info/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw_text: raw }),
      });
      const fields = body.fields || body;
      $("#edit-product-codes").value = String(fields.product_codes || "");
      $("#edit-product-names").value = String(fields.product_names || "");
      const count = Array.isArray(fields.product_items) ? fields.product_items.length : 0;
      status.textContent = count ? `已重新拆分 ${count} 项产品，请核对后保存` : "未识别出编码和名称，可继续手工编辑";
    } catch (error) {
      status.textContent = `${error.message || "重新拆分失败"}（${UI_ERROR_CODES.productParse}）`;
    } finally {
      button.disabled = false;
    }
  }

  async function submitNew(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = formObject(form);
    const errorMessage = localValidateNew(data);
    const errorNode = $("#add-form-error");
    if (errorMessage) {
      errorNode.textContent = errorMessage;
      errorNode.hidden = false;
      return;
    }
    errorNode.hidden = true;
    data.source = state.activeChannel === "alibaba" ? "alibaba" : "email_manual";
    data.customer_channel = state.activeChannel;
    if (!data.status) data.status = "new";
    if (state.activeChannel === "alibaba" && !data.product_interest) {
      const summary = String(data.product_names || "").split(/\r?\n/).map((value) => value.trim()).filter(Boolean).slice(0, 3).join(" / ");
      if (summary) data.product_interest = summary.slice(0, 600);
    }
    if (data.icp_score === "") delete data.icp_score;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await requestJSON("/api/clients", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      showToast("客户已创建，并同步索引与 pipeline");
      removeActiveDraft();
      resetAndCloseAddDialog();
      await loadData({ showLoading: false });
    } catch (error) {
      errorNode.textContent = error.message || "创建失败，请稍后重试";
      errorNode.hidden = false;
      showToast(error.message || "创建失败", true);
    } finally {
      button.disabled = false;
    }
  }

  function resetFilters() {
    state.page = 1;
    $("#search-input").value = "";
    $("#status-filter").value = "";
    $("#tier-filter").value = "";
    $("#market-filter").value = "";
    $("#source-filter").value = "";
    $("#sort-filter").value = "updated_desc";
    applyFilters();
  }

  function goToPage(page) {
    state.page = page;
    applyFilters();
    const heading = $(".results-heading");
    if (heading && typeof heading.scrollIntoView === "function") {
      const reducedMotion = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      heading.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
    }
  }

  function handleFilterChange() {
    state.page = 1;
    applyFilters();
  }

  function bindEvents() {
    ["#search-input", "#status-filter", "#tier-filter", "#market-filter", "#source-filter", "#sort-filter"].forEach((selector) => $(selector).addEventListener(selector === "#search-input" ? "input" : "change", handleFilterChange));
    $("#reset-filters").addEventListener("click", resetFilters);
    $("#empty-reset-btn").addEventListener("click", resetFilters);
    $("#refresh-btn").addEventListener("click", () => loadData());
    $("#retry-btn").addEventListener("click", () => loadData());
    $("#page-size").value = String(state.pageSize);
    $("#page-size").addEventListener("change", (event) => {
      state.pageSize = safePageSize(event.currentTarget.value);
      event.currentTarget.value = String(state.pageSize);
      state.page = 1;
      applyFilters();
    });
    $("#pagination-prev").addEventListener("click", () => goToPage(state.page - 1));
    $("#pagination-next").addEventListener("click", () => goToPage(state.page + 1));
    $("#pagination-pages").addEventListener("click", (event) => {
      const pageButton = event.target.closest("[data-page]");
      if (pageButton) goToPage(pageButton.dataset.page);
    });
    $("#checklist-form").addEventListener("submit", addChecklistTask);
    $("#checklist-prev-day").addEventListener("click", () => navigateChecklistDate(-1));
    $("#checklist-next-day").addEventListener("click", () => navigateChecklistDate(1));
    $("#checklist-today").addEventListener("click", () => changeChecklistDate(todayKey()));
    $("#checklist-date").addEventListener("change", (event) => changeChecklistDate(event.currentTarget.value));
    $("#checklist-list").addEventListener("click", handleChecklistClick);
    $("#checklist-list").addEventListener("keydown", handleChecklistKeydown);
    $("#client-grid").addEventListener("click", (event) => {
      const card = event.target.closest("[data-client-id]");
      if (card) showClientDetail(card.dataset.clientId);
    });
    $("#detail-view").addEventListener("click", (event) => {
      const copyButton = event.target.closest("[data-detail-copy-field]");
      if (copyButton) {
        copyDetailProductColumn(copyButton.dataset.detailCopyField);
        return;
      }
      const toggle = event.target.closest("[data-detail-expand]");
      if (!toggle) return;
      const extra = document.getElementById(toggle.dataset.detailExpand);
      if (!extra) return;
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      extra.hidden = expanded;
      toggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      toggle.textContent = expanded ? `展开剩余 ${toggle.dataset.remaining} 条` : "收起";
    });
    ["alibaba", "email"].forEach((channel) => {
      $(`#channel-${channel}`).addEventListener("click", () => {
        if (state.activeChannel === channel) return;
        state.activeChannel = channel;
        resetFilters();
        renderChannelTabs();
        populateFilterOptions();
        renderStats({});
        applyFilters();
      });
    });
    $("#add-client-btn").addEventListener("click", () => openAddDialog());
    $("#draft-box-btn").addEventListener("click", () => { renderDrafts(); openDialog($("#draft-dialog")); });
    $("#draft-dialog-close").addEventListener("click", () => closeDialog($("#draft-dialog")));
    $("#draft-dialog-done").addEventListener("click", () => closeDialog($("#draft-dialog")));
    $("#draft-list").addEventListener("click", handleDraftListClick);
    $("#dialog-close").addEventListener("click", () => closeDialog($("#client-dialog")));
    $("#detail-close-btn").addEventListener("click", () => closeDialog($("#client-dialog")));
    $("#add-dialog-close").addEventListener("click", requestCloseAddDialog);
    $("#add-cancel").addEventListener("click", requestCloseAddDialog);
    $("#draft-continue-editing").addEventListener("click", () => closeDialog($("#draft-confirm-dialog")));
    $("#draft-discard").addEventListener("click", resetAndCloseAddDialog);
    $("#draft-save").addEventListener("click", saveCurrentDraft);
    $("#edit-client-btn").addEventListener("click", showEditForm);
    $("#edit-cancel").addEventListener("click", showDetailView);
    $("#edit-form").addEventListener("submit", submitEdit);
    $("#edit-parse-products").addEventListener("click", parseEditProducts);
    $("#add-form").addEventListener("submit", submitNew);
    bindContactParser(addContactParser, "#add-contact-raw", "#add-contact-parse-status", "#add-form");
    bindContactParser(editContactParser, "#edit-contact-raw", "#edit-contact-parse-status", "#edit-form");
    $("#add-product-raw").addEventListener("input", () => {
      if (!productParserState.applying) productParserState.manualRaw = true;
      scheduleProductParse();
    });
    $("#copy-product-codes").addEventListener("click", () => copyProductColumn("product_codes", "内部编码"));
    $("#copy-product-names").addEventListener("click", () => copyProductColumn("product_names", "产品名称"));
    productSplitFields.forEach((field) => {
      const input = $("#add-form").elements.namedItem(field);
      if (input) input.addEventListener("input", () => {
        if (!productParserState.applying) productParserState.manual.add(field);
      });
    });
    const productInterestInput = $("#add-form").elements.namedItem("product_interest");
    if (productInterestInput) productInterestInput.addEventListener("input", () => {
      if (!productParserState.applying) productParserState.manualInterest = true;
    });
    [$("#client-dialog"), $("#draft-dialog")].forEach((dialog) => dialog.addEventListener("click", (event) => { if (event.target === dialog) closeDialog(dialog); }));
    $("#add-dialog").addEventListener("click", (event) => { if (event.target === event.currentTarget) requestCloseAddDialog(); });
    $("#add-dialog").addEventListener("cancel", (event) => { event.preventDefault(); requestCloseAddDialog(); });
    $("#draft-confirm-dialog").addEventListener("cancel", (event) => { event.preventDefault(); closeDialog(event.currentTarget); });
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")) {
        event.preventDefault();
        $("#search-input").focus();
      }
      if (event.key === "Escape") {
        if ($("#draft-confirm-dialog").open) {
          event.preventDefault();
          closeDialog($("#draft-confirm-dialog"));
          return;
        }
        if ($("#add-dialog").open) {
          event.preventDefault();
          requestCloseAddDialog();
          return;
        }
        if ($("#client-dialog").open) closeDialog($("#client-dialog"));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    initializeChecklist();
    updateDraftCount();
    loadData();
  });
})();
