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
  const UI_ERROR_CODES = { bulkCopy: "CRM-BULK-COPY-001" };
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
    if (String(client?.display_name || "").trim()) return String(client.display_name).trim();
    if (channelOf(client) === "alibaba" && String(client?.contact_name || "").trim()) return String(client.contact_name).trim();
    if (String(client?.company || "").trim() && String(client.company).trim() !== String(client.client_id || "").trim()) return String(client.company).trim();
    if (String(client?.contact_name || "").trim()) return String(client.contact_name).trim();
    return channelOf(client) === "alibaba" ? "未命名阿里客户" : text(client?.company, client?.client_id || "未命名客户");
  };
  const boardClients = () => state.clients.filter((client) => channelOf(client) === state.activeChannel);
  const dateLabel = (value) => {
    const normalized = String(value ?? "").trim();
    return normalized || "未更新";
  };

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
      const contact = text(client.contact_name, "联系人待确认");
      const subtitle = isAlibaba ? text(client.company, "公司待补充") : contact;
      const next = text(client.next_action, "尚未设置下一步");
      const title = displayName(client);
      const primaryLabel = isAlibaba ? "地址" : "地区";
      const primaryValue = isAlibaba ? client.address : client.country_region;
      const secondaryLabel = isAlibaba ? "电话" : "产品";
      const secondaryValue = isAlibaba ? (client.known_phone || client.known_email) : (client.product_interest || client.product_name);
      const tertiary = isAlibaba ? (client.product_interest || client.product_application || client.product_raw) : "";
      return `<button class="client-card ${isAlibaba ? "channel-alibaba" : "channel-email"} tier-${escapeHtml(tier.toLowerCase())}" type="button" data-client-id="${escapeHtml(client.client_id)}" data-channel="${isAlibaba ? "alibaba" : "email"}" aria-label="查看 ${escapeHtml(title)} 详情">
        <div class="card-top">
          <div class="card-title"><h3 title="${escapeHtml(title)}">${escapeHtml(title)}</h3><p class="card-contact" title="${escapeHtml(subtitle)}">${escapeHtml(subtitle)}</p></div>
          <span class="tier-badge" title="ICP ${escapeHtml(tier)} 级">${escapeHtml(tier)}</span>
        </div>
        <div class="card-meta"><span class="status-chip" data-status="${escapeHtml(client.status || "")}">${escapeHtml(statusLabel(client.status || "未设置"))}</span><span class="score">${escapeHtml(String(score))}<span> / 100</span></span></div>
        <div class="card-divider"></div>
        ${cardField(primaryLabel, primaryValue)}
        ${cardField(secondaryLabel, secondaryValue)}
        ${isAlibaba ? cardField("产品", tertiary) : ""}
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
        ${detailItem("客户 ID", client.client_id)}
        ${detailItem("联系人", client.contact_name)}
        ${detailItem("职位", client.title)}
        ${detailItem("地区", client.country_region)}
        ${detailItem("地址", client.address)}
        ${detailItem("市场", client.market_bucket)}
        ${detailItem("板块", isAlibaba ? "阿里客户" : "邮件客户")}
        ${detailItem("来源", client.source)}
        ${detailItem("邮箱", client.known_email)}
        ${detailItem("电话", client.known_phone)}
        ${detailItem("渠道类型", client.channel_type)}
        ${detailItem("产品兴趣", client.product_interest)}
        ${detailItem("创建时间", client.created_at)}
        ${detailItem("详情档案", client.has_profile ? client.source_file : "索引 / pipeline 记录")}
      </dl></section>
      ${isAlibaba ? `<section class="detail-section"><h3>Alibaba 产品信息</h3><dl class="detail-grid">
        ${detailItem("内部编码", client.product_codes)}
        ${detailItem("批量产品名称", client.product_names)}
        ${detailItem("批量产品条数", Array.isArray(client.product_items) ? client.product_items.length : 0)}
        ${detailItem("产品名称", client.product_name)}
        ${detailItem("香型要求", client.fragrance_requirement)}
        ${detailItem("产品用途", client.product_application)}
        ${detailItem("产品数量", client.product_quantity)}
        ${detailItem("产品规格", client.product_specification)}
        ${detailItem("目标价格", client.target_price)}
        ${detailItem("其他要求", client.other_requirements)}
      </dl>${client.product_raw ? `<h4 class="detail-subheading">产品原文</h4>${markdownToHtml(client.product_raw)}` : ""}</section>` : ""}
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
    $("#edit-status").value = client.status || "new";
    $("#edit-next-action").value = client.next_action || "";
    $("#edit-notes").value = client.notes || "";
    $("#detail-view").hidden = true;
    $("#detail-actions").hidden = true;
    $("#edit-form").hidden = false;
    window.setTimeout(() => $("#edit-status").focus(), 0);
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
    const preserveMultiline = new Set(["product_raw", "product_codes", "product_names", "other_requirements", "notes"]);
    new FormData(form).forEach((value, key) => {
      result[key] = typeof value === "string" && !preserveMultiline.has(key) ? value.trim() : value;
    });
    return result;
  }

  const productSplitFields = [
    "product_name",
    "fragrance_requirement",
    "product_application",
    "product_quantity",
    "product_specification",
    "target_price",
    "other_requirements",
    "product_codes",
    "product_names",
  ];
  const productParserState = { manual: new Set(), manualInterest: false, suggested: {}, suggestedInterest: "", timer: null, requestId: 0, applying: false };

  function resetProductParser() {
    productParserState.manual = new Set();
    productParserState.manualInterest = false;
    productParserState.suggested = {};
    productParserState.suggestedInterest = "";
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
    $("#add-dialog-title").textContent = isAlibaba ? "新增阿里客户" : "新增邮件客户";
    $("#add-dialog-intro").textContent = isAlibaba
      ? "阿里客户的姓名、公司、地址、产品与备注都可以先留空，保存后会生成安全唯一档案。"
      : "录入后会生成客户 Markdown，并同步索引与 pipeline。邮件客户需要公司名称。";
    if (status && !status.value) status.value = "new";
  }

  function openAddDialog() {
    const form = $("#add-form");
    form.reset();
    resetProductParser();
    setAddFormChannel();
    $("#add-form-error").hidden = true;
    if ([...$("#add-status").options].some((option) => option.value === "new")) $("#add-status").value = "new";
    openDialog($("#add-dialog"));
    window.setTimeout(() => $("#add-company").focus(), 0);
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
          const summary = [fields.product_name, fields.product_application, fields.fragrance_requirement].filter(Boolean).join(" / ").slice(0, 600);
          if (!productInterest.value.trim() || productInterest.value.trim() === previousInterest) productInterest.value = summary;
          productParserState.suggestedInterest = summary;
        }
        status.textContent = body.matched_fields?.length ? `已建议 ${body.matched_fields.length} 个字段，可继续编辑` : "暂未识别明确字段，可手动填写";
      } catch (error) {
        productParserState.applying = false;
        status.textContent = error.message || "拆分建议暂不可用，可手动填写";
      }
    }, 420);
  }

  function normalizedCopyLines(value) {
    // 复制到 Excel 时必须保留空位，否则编码列和名称列会发生行错位。
    // 这里只做换行归一化及逐行横向 trim，不删除任何行。
    return String(value ?? "").replace(/\r\n?/g, "\n").split("\n").map((line) => line.trim()).join("\n");
  }

  async function copyProductColumn(field, label) {
    const input = $("#add-form").elements.namedItem(field);
    const value = normalizedCopyLines(input?.value);
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
    if (!payload.status) return showToast("请选择客户状态", true);
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
      const summary = [data.product_name, data.product_application, data.fragrance_requirement].filter(Boolean).join(" / ");
      if (summary) data.product_interest = summary.slice(0, 600);
    }
    if (data.icp_score === "") delete data.icp_score;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      await requestJSON("/api/clients", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
      showToast("客户已创建，并同步索引与 pipeline");
      closeDialog($("#add-dialog"));
      form.reset();
      $("#add-status").value = "new";
      resetProductParser();
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
    $("#client-grid").addEventListener("click", (event) => {
      const card = event.target.closest("[data-client-id]");
      if (card) showClientDetail(card.dataset.clientId);
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
    $("#add-client-btn").addEventListener("click", openAddDialog);
    $("#dialog-close").addEventListener("click", () => closeDialog($("#client-dialog")));
    $("#detail-close-btn").addEventListener("click", () => closeDialog($("#client-dialog")));
    $("#add-dialog-close").addEventListener("click", () => closeDialog($("#add-dialog")));
    $("#add-cancel").addEventListener("click", () => closeModal($("#add-dialog")));
    $("#edit-client-btn").addEventListener("click", showEditForm);
    $("#edit-cancel").addEventListener("click", showDetailView);
    $("#edit-form").addEventListener("submit", submitEdit);
    $("#add-form").addEventListener("submit", submitNew);
    $("#add-product-raw").addEventListener("input", scheduleProductParse);
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
    [$("#client-dialog"), $("#add-dialog")].forEach((dialog) => dialog.addEventListener("click", (event) => { if (event.target === dialog) closeDialog(dialog); }));
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName || "")) {
        event.preventDefault();
        $("#search-input").focus();
      }
      if (event.key === "Escape") {
        // 原生 dialog 已处理 Escape；非原生 fallback 也要能关闭。
        if ($("#client-dialog").open) closeDialog($("#client-dialog"));
        if ($("#add-dialog").open) closeDialog($("#add-dialog"));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadData();
  });
})();
