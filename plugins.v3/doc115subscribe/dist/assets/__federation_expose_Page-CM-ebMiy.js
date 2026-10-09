import { importShared } from './__federation_fn_import-SdO2Fg_T.js';

const {toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementVNode:_createElementVNode,createVNode:_createVNode,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass,withKeys:_withKeys,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "doc115-page" };
const _hoisted_2 = { class: "text-subtitle-1 font-weight-medium" };
const _hoisted_3 = {
  key: 0,
  class: "font-weight-medium"
};
const _hoisted_4 = { class: "text-primary font-weight-medium" };
const _hoisted_5 = { class: "text-primary font-weight-medium" };
const _hoisted_6 = ["src"];
const _hoisted_7 = { class: "text-caption mt-2" };
const _hoisted_8 = { class: "font-weight-bold text-body-1 text-primary" };
const _hoisted_9 = {
  key: 0,
  class: "text-medium-emphasis font-weight-regular"
};
const _hoisted_10 = { class: "text-caption mt-1" };
const _hoisted_11 = { class: "text-purple-darken-2" };
const _hoisted_12 = {
  key: 1,
  class: "text-grey-darken-1"
};
const _hoisted_13 = { class: "text-caption mt-1" };
const _hoisted_14 = { class: "text-caption mt-1" };
const _hoisted_15 = { class: "text-caption text-medium-emphasis" };
const _hoisted_16 = { class: "d-flex align-center flex-wrap" };
const _hoisted_17 = { class: "font-weight-bold text-body-1 text-primary" };
const _hoisted_18 = { class: "text-caption text-medium-emphasis" };
const _hoisted_19 = {
  class: "text-caption mt-1 text-medium-emphasis",
  style: {"word-break":"break-all"}
};
const _hoisted_20 = {
  key: 0,
  class: "text-caption mt-1",
  style: {"border-radius":"6px","padding":"6px 8px","background":"rgba(255, 180, 0, 0.14)"}
};
const _hoisted_21 = {
  key: 1,
  class: "text-caption mt-1"
};
const _hoisted_22 = { class: "text-medium-emphasis" };
const _hoisted_23 = {
  key: 0,
  class: "ml-2"
};

const {computed,onBeforeUnmount,onMounted,reactive,ref,watch} = await importShared('vue');


const pageSize = 10;


const _sfc_main = {
  __name: 'Page',
  props: {
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
},
  emits: ['action', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const status = reactive({
  version: '', cookie_ready: false, p115_ready: false, cookie_days_left: null,
  record_count: 0, sheet_count: 0, built_at_text: '尚未建立',
  index_errors: [], stale_sheets: [], last_refresh: null, last_subscribe: null,
});
const msg = ref('');
const msgType = ref('info');
const busy = reactive({ refresh: false, qr: false, search: false, subscribe: false, check: false, offline: false, records: false });
const qrImage = ref('');
const qrTip = ref('等待扫码');
const qrSessionId = ref('');
const keyword = ref('');
const results = ref([]);
const searched = ref(false);
const searchedKeyword = ref('');
const total = ref(0);
const resultVersion = ref('');
const transferring = reactive({});
const retrying = reactive({});
let searchSerial = 0;
let disposed = false;

// ---- 页签：搜索 / 转存记录 ----
const tab = ref('search');
const records = ref([]);

// ---- 筛选与分页 ----
const page = ref(1);
const filterType = ref('all');
const filterQuality = ref('all');
// 链接类型筛选：区分「115 转存 / 磁力 / ed2k / 纯文档（没有可转存的资源链接）」
const filterLink = ref('all');

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
watch([filterType, filterQuality, filterLink], () => {
  if (searchedKeyword.value) searchPage(searchedKeyword.value, 1);
});
const indexWarnings = computed(() => [...new Set([
  ...(status.index_errors || []).map(String),
  ...(status.stale_sheets || []).map((s) => typeof s === 'string' ? `保留旧索引：${s}` : `保留旧索引：${s.title || s.name || s.sheet_id || '未知工作表'}`),
])]);
function mediaTypeName(type) { return ({ movie: '电影', tv: '电视剧' })[type] || '类型待确认' }

// ---- Cookie 状态文案 ----
const cookieDays = computed(() => {
  const d = status.cookie_days_left;
  return (d === null || d === undefined) ? null : Math.floor(d)
});
const cookieText = computed(() => {
  if (!status.cookie_ready) return '未配置（请用下方扫码登录）'
  return cookieDays.value === null ? '已配置' : `已配置（剩余约 ${cookieDays.value} 天）`
});
const cookieAlertType = computed(() => {
  if (!status.cookie_ready) return 'warning'
  if (cookieDays.value !== null && cookieDays.value <= 5) return 'warning'
  return 'info'
});

// ---- 字段配色 ----
// 链接类型：颜色 + 图标双重区分，一眼能看出是 115 分享还是磁力
const LINK_STYLE = {
  '115_share': { color: 'deep-purple', name: '115分享', icon: 'mdi-cloud-download' },
  magnet: { color: 'blue-darken-3', name: '磁力', icon: 'mdi-magnet' },
  ed2k: { color: 'teal-darken-3', name: 'ed2k', icon: 'mdi-link-variant' },
  http: { color: 'grey-darken-2', name: '网页', icon: 'mdi-web' },
};
function linkColor(kind) { return (LINK_STYLE[kind] || {}).color || 'grey' }
function linkName(kind) { return (LINK_STYLE[kind] || {}).name || kind }
function linkIcon(kind) { return (LINK_STYLE[kind] || {}).icon || 'mdi-link' }

function shortUrl(u) {
  let t = String(u || '');
  t = t.replace(/^https?:\/\//i, '');
  if (/^ed2k:\/\//i.test(t)) { const p = t.split('|'); return p.length > 2 ? p[2] : t }
  return t.length > 44 ? t.slice(0, 44) + '…' : t
}
function linkHref(u) {
  let t = String(u || '');
  if (/^(ed2k:\/\/|magnet:)/i.test(t)) return t
  if (!/^https?:\/\//i.test(t)) t = 'https://' + t;
  return t
}

const SPEC_RE = /(4K|2160[pP]|1080[pP]|720[pP]|REMUX|UHD|HDR10\+?|HDR|杜比视界|Dolby\s?Vision|Atmos|蓝光原盘|原盘|中文字幕|简繁|简体|繁体|国语|双语|粤语|无中字)/gi;
function specTokens(text) {
  const t = (text || '').slice(0, 100);
  if (!t) return [{ text: '—', color: '' }]
  const parts = [];
  let last = 0;
  let m;
  SPEC_RE.lastIndex = 0;
  while ((m = SPEC_RE.exec(t)) !== null) {
    if (m.index > last) parts.push({ text: t.slice(last, m.index), color: '' });
    const w = m[0].toUpperCase();
    let color;
    if (/无中字/.test(w)) color = 'red-darken-2';
    else if (/4K|2160P|REMUX|UHD|HDR|杜比|DOLBY|ATMOS|原盘/.test(w)) color = 'amber-darken-3';
    else if (/中文字幕|简繁|简体|繁体|国语|双语|粤语/.test(w)) color = 'green-darken-2';
    else if (/1080P|720P/.test(w)) color = 'blue-darken-1';
    else color = 'grey-darken-1';
    parts.push({ text: m[0], color });
    last = m.index + m[0].length;
  }
  if (last < t.length) parts.push({ text: t.slice(last), color: '' });
  return parts
}

function setMsg(text, type = 'info') {
  msg.value = text;
  msgType.value = type;
}

// ---- 转存记录 ----
const KIND_STYLE = {
  '115_share': { name: '115分享', color: 'deep-purple' },
  magnet: { name: '磁力', color: 'blue-darken-3' },
  ed2k: { name: 'ed2k', color: 'teal-darken-3' },
};
const STATUS_STYLE = {
  submitting: { name: '提交中', color: 'blue-darken-2' },
  submitted: { name: '已提交', color: 'blue-darken-2' },
  downloading: { name: '下载中', color: 'blue-darken-2' },
  waiting: { name: '等待文件', color: 'amber-darken-3' },
  awaiting_move: { name: '等待搬运', color: 'amber-darken-3' },
  moving: { name: '搬运中', color: 'amber-darken-3' },
  done: { name: '已搬入下载目录', color: 'amber-darken-3' },
  moved: { name: '已搬入下载目录', color: 'amber-darken-3' },
  missing: { name: '原目录未找到，整理待确认', color: 'amber-darken-3' },
  unverified: { name: '整理待确认', color: 'amber-darken-3' },
  partial: { name: '部分整理失败', color: 'deep-orange-darken-2' },
  organized: { name: '已整理入库', color: 'green-darken-2' },
  failed: { name: '失败', color: 'red-darken-2' },
  cancelled: { name: '已停止自动搬运', color: 'grey' },
};
function kindName(k) { return (KIND_STYLE[k] || {}).name || k }
function kindColor(k) { return (KIND_STYLE[k] || {}).color || 'grey' }
function statusName(s) { return (STATUS_STYLE[s] || {}).name || s }
function statusColor(s) { return (STATUS_STYLE[s] || {}).color || 'grey' }

async function loadRecords(force = false) {
  if (busy.records || disposed) return
  busy.records = true;
  try {
    // 读取记录；force=true（点「刷新」）时让后端**强制**用 MP 整理记录核对一次整理结果，
    // 否则走后端 30 秒节流（打开页面 / 定时轮询）。
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/records', {
      params: force ? { verify: 1 } : undefined,
      timeout: 180000,
    }));
    if (res.code === 0) records.value = res.data || [];
    else setMsg(res.msg || '读取转存记录失败', 'error');
  } catch (e) {
    setMsg(`读取转存记录失败：${describeError(e)}`, 'error');
  } finally {
    busy.records = false;
  }
}

// 记录页有活动任务时轮询读取后台检查结果。
let recTimer = null;
function stopRecTimer() {
  if (recTimer) { clearInterval(recTimer); recTimer = null; }
}
function startRecTimer() {
  stopRecTimer();
  recTimer = setInterval(() => {
    if (tab.value !== 'records') return
    if (!records.value.some(isActiveTask)) return
    loadRecords();
  }, 20000);
}

async function deleteRecord(r) {
  if (!window.confirm(`删除这条历史记录？下载与自动搬运任务继续执行。\n${r.title}`)) return
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/records_delete', { id: r.id }));
    if (res.code === 0) {
      setMsg('已删除该条记录', 'success');
      await loadRecords();
    } else {
      setMsg(res.msg || '删除失败', 'error');
    }
  } catch (e) {
    setMsg(`删除失败：${describeError(e)}`, 'error');
  }
}

async function clearRecords() {
  if (!window.confirm('清空全部转存历史记录？网盘文件、下载与自动搬运任务不受影响。')) return
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/records_delete', {}));
    if (res.code === 0) {
      setMsg('已清空转存记录', 'success');
      await loadRecords();
    } else {
      setMsg(res.msg || '清空失败', 'error');
    }
  } catch (e) {
    setMsg(`清空失败：${describeError(e)}`, 'error');
  }
}

function isActiveTask(r) { return ['submitting', 'submitted', 'downloading', 'waiting', 'awaiting_move', 'moving'].includes(r.status) && r.kind !== '115_share' }
async function retryTask(r) {
  if (retrying[r.id]) return
  retrying[r.id] = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/retry_task', { id: r.id }, { timeout: 300000 }));
    setMsg(res.msg || (res.code === 0 ? '已重新尝试该任务' : '重试失败'), res.code === 0 ? 'success' : 'error');
    if (res.code === 0) await loadRecords();
  } catch (e) { setMsg(`重试失败：${describeError(e)}`, 'error'); }
  finally { delete retrying[r.id]; }
}
async function cancelTask(r) {
  if (!window.confirm(`停止「${r.title}」的自动跟踪与搬运？\n115 中的下载和文件会保留，完成后需要你手动搬运。`)) return
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/cancel_task', { id: r.id }));
    setMsg(res.msg || (res.code === 0 ? '已停止自动搬运' : '停止失败'), res.code === 0 ? 'success' : 'error');
    if (res.code === 0) await loadRecords();
  } catch (e) { setMsg(`停止失败：${describeError(e)}`, 'error'); }
}

function close() {
  disposed = true;
  searchSerial += 1;
  stopQrTimer();
  stopRecTimer();
  emit('close');
}

function describeError(e) {
  if (!e) return '未知错误'
  const parts = [];
  if (e.message) parts.push(e.message);
  if (e.response && e.response.status) parts.push(`HTTP ${e.response.status}`);
  if (e.response && e.response.data) {
    try { parts.push(JSON.stringify(e.response.data).slice(0, 200)); } catch (_) { /* ignore */ }
  }
  return parts.join(' | ') || String(e)
}

// 插件接口返回 {code,msg,data}；MP 统一层可能已把 data 解包出来
function unwrap(res) {
  if (res && typeof res === 'object' && 'code' in res) return res
  return { code: 0, msg: '', data: res }
}

async function loadStatus() {
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/status'));
    if (res.code === 0 && res.data) Object.assign(status, res.data);
  } catch (e) {
    console.error(e);
  }
}

async function refreshIndex() {
  if (busy.refresh) return
  busy.refresh = true;
  setMsg('正在读取所有工作表并刷新索引，可能需要数分钟，请稍候…');
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/refresh_index', {}, { timeout: 900000 }));
    if (res.code === 0) {
      const d = res.data || {};
      const errors = d.errors || d.index_errors || [];
      setMsg(`索引${errors.length ? '部分更新' : '刷新完成'}：${d.record_count || 0} 条记录 / ${d.sheet_count || 0} 张表${errors.length ? '\n' + errors.join('\n') : ''}`, errors.length ? 'warning' : 'success');
      await loadStatus();
    } else {
      setMsg(res.msg || '索引刷新失败', 'error');
      await loadStatus();
    }
  } catch (e) {
    setMsg(`索引刷新失败：${describeError(e)}`, 'error');
  } finally {
    busy.refresh = false;
    emit('action');
  }
}

// ---- 扫码登录 -----------------------------------------------------------
let qrTimer = null;
let qrGeneration = 0;

function stopQrTimer() {
  qrGeneration += 1;
  if (qrTimer) {
    clearTimeout(qrTimer);
    qrTimer = null;
  }
}

function startQrTimer() {
  if (disposed || !qrSessionId.value || qrTimer) return
  const generation = qrGeneration;
  qrTimer = setTimeout(async () => {
    qrTimer = null;
    await checkQr(true);
    if (generation === qrGeneration) startQrTimer();
  }, 3000);
}

async function startQr(silent = false) {
  if (busy.qr || busy.check || disposed) return
  if (silent !== true) silent = false;
  busy.qr = true;
  stopQrTimer();
  const generation = qrGeneration;
  qrSessionId.value = '';
  qrImage.value = '';
  if (!silent) setMsg('正在打开登录页并生成二维码（约 10~20 秒），请稍候…');
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_start', { params: { force: true }, timeout: 180000 }));
    if (generation !== qrGeneration || disposed) return
    const data = res.data || {};
    if (res.code === 0 && data.state === 'confirmed') {
      await qrConfirmed();
    } else if (res.code === 0 && data.qr_base64 && data.session_id) {
      qrSessionId.value = data.session_id;
      qrImage.value = data.qr_base64;
      qrTip.value = '等待扫码';
      setMsg('二维码已生成，请用微信扫码（扫完会自动完成登录）');
      startQrTimer();
    } else {
      setMsg(res.msg || '获取二维码失败', 'error');
    }
  } catch (e) {
    setMsg(`获取二维码失败：${describeError(e)}`, 'error');
  } finally {
    busy.qr = false;
  }
}

async function checkQr(silent = false) {
  if (busy.check || busy.qr || !qrSessionId.value || disposed) return
  if (silent !== true) silent = false;
  busy.check = true;
  const generation = qrGeneration;
  const sessionId = qrSessionId.value;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_status', { params: { session_id: sessionId }, timeout: 120000 }));
    if (generation !== qrGeneration || disposed) return
    const data = res.data || {};
    if (res.code === 0 && data.state === 'confirmed') {
      await qrConfirmed();
      return
    }
    if (data.qr_base64) {
      qrImage.value = data.qr_base64;
      qrTip.value = '已换新码，请重新扫码';
    }
    if (res.code !== 0) {
      setMsg(res.msg || '检查失败', 'error');
      stopQrTimer();
      return
    }
    const map = {
      wait: '等待扫码',
      scanned: '已扫描，请在手机上确认登录',
      expired: '二维码已过期，请获取新二维码',
      failed: '本次登录失败，请获取新二维码',
      error: '登录检查失败，请获取新二维码',
    };
    qrTip.value = map[data.state] || '等待扫码';
    if (['expired', 'failed', 'error'].includes(data.state)) {
      stopQrTimer();
      qrSessionId.value = '';
      setMsg(data.msg || qrTip.value, 'warning');
      return
    }
    if (!silent && data.state) setMsg(map[data.state] || '');
  } catch (e) {
    if (!silent) setMsg(`检查失败：${describeError(e)}`, 'error');
  } finally {
    busy.check = false;
  }
}

async function qrConfirmed() {
  stopQrTimer();
  qrSessionId.value = '';
  qrImage.value = '';
  setMsg('登录成功，Cookie 已保存。可刷新索引查看文档读取结果。', 'success');
  await loadStatus();
}

// ---- 其它 ---------------------------------------------------------------
async function checkOffline() {
  if (busy.offline) return
  busy.offline = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/check_offline', {}, { timeout: 180000 }));
    if (res.code === 0) {
      const d = res.data || {};
      setMsg(`离线任务检查完成：本轮搬运 ${d.finished || 0} 条，待完成 ${d.pending || 0} 条${d.failed ? `，失败 ${d.failed} 条（请查看转存记录）` : ''}`, d.failed ? 'warning' : 'success');
      await loadRecords();
    } else {
      setMsg(res.msg || '检查离线任务失败', 'error');
    }
  } catch (e) {
    setMsg(`检查离线任务失败：${describeError(e)}`, 'error');
  } finally {
    busy.offline = false;
  }
}

async function runSubscribe() {
  if (busy.subscribe) return
  busy.subscribe = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/run_subscribe', {}, { timeout: 900000 }));
    if (res.code === 0) {
      const d = res.data || {};
      const errors = d.errors || [];
      setMsg(`订阅同步完成：命中 ${d.matched || 0} 条，成功提交 ${d.transferred || 0} 条${errors.length ? '\n' + errors.join('\n') : ''}`, errors.length ? 'warning' : 'success');
    } else {
      setMsg(res.msg || '订阅同步失败', 'error');
    }
  } catch (e) {
    setMsg(`订阅同步失败：${describeError(e)}`, 'error');
  } finally {
    busy.subscribe = false;
    await loadStatus();
    emit('action');
  }
}

async function doSearch() {
  const kw = (keyword.value || '').trim();
  if (!kw) {
    setMsg('请输入影视名称', 'warning');
    return
  }
  await searchPage(kw, 1);
}

function changePage(value) {
  if (searchedKeyword.value && !busy.search) searchPage(searchedKeyword.value, value);
}

async function searchPage(kw, requestedPage) {
  const serial = ++searchSerial;
  const mediaType = filterType.value;
  const quality = filterQuality.value;
  const linkKind = filterLink.value;
  searchedKeyword.value = kw;
  busy.search = true;
  searched.value = true;
  results.value = [];
  total.value = 0;
  resultVersion.value = '';
  page.value = requestedPage;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/search', {
      keyword: kw, media_type: mediaType, quality, link_kind: linkKind,
      page: requestedPage, page_size: pageSize,
    }, { timeout: 120000 }));
    if (serial !== searchSerial || disposed) return
    if (res.code === 0) {
      const data = res.data || {};
      if (!Array.isArray(data.records) || !data.index_version) throw new Error('搜索响应无有效索引版本，请更新插件后重试')
      results.value = data.records;
      total.value = data.total || 0;
      page.value = data.page || requestedPage;
      resultVersion.value = data.index_version;
      setMsg(`「${kw}」符合当前筛选的结果共 ${total.value} 条`);
    } else {
      results.value = [];
      setMsg(res.msg || '搜索失败', 'error');
    }
  } catch (e) {
    if (serial === searchSerial && !disposed) setMsg(`搜索失败：${describeError(e)}`, 'error');
  } finally {
    if (serial === searchSerial) {
      busy.search = false;
      emit('action');
    }
  }
}

async function transfer(rec, to) {
  if (!rec || !rec.record_id || !resultVersion.value || busy.search || transferring[rec.record_id]) return
  const recordId = rec.record_id;
  const indexVersion = resultVersion.value;
  transferring[recordId] = true;
  setMsg(`正在转存「${rec.title}」，请稍候…`);
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/transfer', {
      record_id: recordId, index_version: indexVersion, to,
    }, { timeout: 300000 }));
    setMsg(res.msg || (res.code === 0 ? '转存完成' : '转存失败'), res.code === 0 ? 'success' : 'error');
  } catch (e) {
    setMsg(`转存失败：${describeError(e)}`, 'error');
  } finally {
    delete transferring[recordId];
    emit('action');
  }
}

onMounted(() => {
  loadStatus();
  loadRecords();
  startRecTimer();
});
watch(tab, (v) => {
  if (v === 'records') loadRecords();
});
onBeforeUnmount(() => {
  disposed = true;
  searchSerial += 1;
  stopQrTimer();
  stopRecTimer();
});

return (_ctx, _cache) => {
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_tab = _resolveComponent("v-tab");
  const _component_v_tabs = _resolveComponent("v-tabs");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_progress_linear = _resolveComponent("v-progress-linear");
  const _component_v_pagination = _resolveComponent("v-pagination");
  const _component_v_btn_group = _resolveComponent("v-btn-group");
  const _component_v_card_subtitle = _resolveComponent("v-card-subtitle");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_row, {
      dense: "",
      align: "center",
      class: "mb-1"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, { cols: "10" }, {
          default: _withCtx(() => [
            _createElementVNode("div", _hoisted_2, [
              _cache[8] || (_cache[8] = _createTextVNode(" 115文档订阅与查询 ", -1)),
              (status.version)
                ? (_openBlock(), _createBlock(_component_v_chip, {
                    key: 0,
                    size: "x-small",
                    color: "grey-darken-1",
                    variant: "flat",
                    class: "ml-1"
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(" 前端 v" + _toDisplayString(status.version), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode("", true)
            ])
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "2",
          class: "text-right"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              icon: "",
              size: "small",
              variant: "text",
              title: "关闭",
              onClick: close
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_icon, null, {
                  default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                    _createTextVNode("mdi-close", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_alert, {
      type: cookieAlertType.value,
      variant: "tonal",
      density: "comfortable",
      class: "mb-3"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", null, [
          _createTextVNode(" 腾讯文档 Cookie：" + _toDisplayString(cookieText.value) + " ", 1),
          (cookieDays.value !== null && cookieDays.value <= 5)
            ? (_openBlock(), _createElementBlock("span", _hoisted_3, " —— 即将到期，请重新扫码登录 "))
            : _createCommentVNode("", true)
        ]),
        _createElementVNode("div", null, [
          _cache[10] || (_cache[10] = _createTextVNode(" 本地索引：", -1)),
          _createElementVNode("span", _hoisted_4, _toDisplayString(status.record_count), 1),
          _cache[11] || (_cache[11] = _createTextVNode(" 条 / ", -1)),
          _createElementVNode("span", _hoisted_5, _toDisplayString(status.sheet_count), 1),
          _createTextVNode(" 张表， 更新于 " + _toDisplayString(status.built_at_text) + " ｜115 Cookie：", 1),
          _createElementVNode("span", {
            class: _normalizeClass(status.p115_ready ? 'text-green-darken-2' : 'text-red-darken-2')
          }, _toDisplayString(status.p115_ready ? '已配置' : '未检测到'), 3)
        ])
      ]),
      _: 1
    }, 8, ["type"]),
    (indexWarnings.value.length)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: "warning",
          variant: "tonal",
          class: "mb-3",
          style: {"white-space":"pre-wrap"}
        }, {
          default: _withCtx(() => [
            _cache[12] || (_cache[12] = _createElementVNode("div", null, "索引存在未更新的工作表，部分结果可能已过时：", -1)),
            _createTextVNode(_toDisplayString(indexWarnings.value.join('\n')), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (status.last_subscribe && status.last_subscribe.success === false)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 1,
          type: "error",
          variant: "tonal",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(" 最近订阅同步失败：" + _toDisplayString(status.last_subscribe.msg || status.last_subscribe.error || '请手动同步查看原因'), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (status.last_refresh && status.last_refresh.success === false)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 2,
          type: "error",
          variant: "tonal",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(" 最近索引刷新失败：" + _toDisplayString(status.last_refresh.msg || status.last_refresh.error || '请刷新索引查看原因'), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (msg.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 3,
          type: msgType.value,
          variant: "tonal",
          density: "comfortable",
          class: "mb-3",
          style: {"white-space":"pre-wrap"}
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(msg.value), 1)
          ]),
          _: 1
        }, 8, ["type"]))
      : _createCommentVNode("", true),
    _createVNode(_component_v_row, {
      dense: "",
      class: "mb-2"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, {
          cols: "6",
          md: "2"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "primary",
              loading: busy.refresh,
              "prepend-icon": "mdi-database-refresh",
              onClick: refreshIndex
            }, {
              default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
                _createTextVNode(" 刷新索引 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "6",
          md: "2"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "primary",
              loading: busy.qr,
              disabled: busy.check,
              "prepend-icon": "mdi-qrcode",
              onClick: _cache[0] || (_cache[0] = $event => (startQr()))
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(qrImage.value ? '换一张二维码' : '获取登录二维码'), 1)
              ]),
              _: 1
            }, 8, ["loading", "disabled"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "6",
          md: "2"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "secondary",
              loading: busy.check,
              disabled: busy.qr || !qrSessionId.value,
              "prepend-icon": "mdi-check-decagram",
              onClick: _cache[1] || (_cache[1] = $event => (checkQr()))
            }, {
              default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                _createTextVNode(" 检查扫码状态 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading", "disabled"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "6",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "secondary",
              loading: busy.offline,
              "prepend-icon": "mdi-download-network",
              onClick: checkOffline
            }, {
              default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
                _createTextVNode(" 检查离线下载与搬运 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ]),
          _: 1
        }),
        _createVNode(_component_v_col, {
          cols: "6",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "secondary",
              loading: busy.subscribe,
              "prepend-icon": "mdi-sync",
              onClick: runSubscribe
            }, {
              default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                _createTextVNode(" 手动同步电影订阅 ", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_tabs, {
      modelValue: tab.value,
      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((tab).value = $event)),
      density: "comfortable",
      class: "mb-3"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_tab, { value: "search" }, {
          default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
            _createTextVNode("搜索", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_tab, { value: "records" }, {
          default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
            _createTextVNode("转存记录", -1)
          ]))]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    (tab.value === 'search')
      ? (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
          (qrImage.value)
            ? (_openBlock(), _createBlock(_component_v_card, {
                key: 0,
                variant: "outlined",
                class: "mb-3"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card_text, { class: "text-center" }, {
                    default: _withCtx(() => [
                      _createElementVNode("img", {
                        src: qrImage.value,
                        style: {"width":"220px","height":"220px","display":"block","margin":"0 auto"},
                        alt: "扫码登录"
                      }, null, 8, _hoisted_6),
                      _createElementVNode("div", _hoisted_7, "用微信扫码登录腾讯文档（" + _toDisplayString(qrTip.value) + "）", 1),
                      _cache[19] || (_cache[19] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, " 二维码过期后请点「换一张二维码」；请只扫描当前页面显示的二维码。 ", -1))
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }))
            : _createCommentVNode("", true),
          _createVNode(_component_v_card, {
            variant: "outlined",
            class: "mb-3"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_card_text, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_row, {
                    dense: "",
                    align: "center"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_col, {
                        cols: "12",
                        md: "8"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: keyword.value,
                            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((keyword).value = $event)),
                            label: "输入影视名称搜索（跨全部工作表）",
                            variant: "outlined",
                            density: "comfortable",
                            "hide-details": "",
                            clearable: "",
                            onKeyup: _withKeys(doSearch, ["enter"])
                          }, null, 8, ["modelValue"])
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "12",
                        md: "4"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_btn, {
                            block: "",
                            color: "primary",
                            "prepend-icon": "mdi-magnify",
                            loading: busy.search,
                            onClick: doSearch
                          }, {
                            default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                              _createTextVNode(" 搜索 ", -1)
                            ]))]),
                            _: 1
                          }, 8, ["loading"])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          (searched.value)
            ? (_openBlock(), _createBlock(_component_v_card, {
                key: 1,
                variant: "outlined"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center flex-wrap" }, {
                    default: _withCtx(() => [
                      _createElementVNode("span", null, "「" + _toDisplayString(searchedKeyword.value) + "」的搜索结果", 1),
                      _createVNode(_component_v_chip, {
                        size: "x-small",
                        color: "primary",
                        class: "ml-2"
                      }, {
                        default: _withCtx(() => [
                          _createTextVNode("共 " + _toDisplayString(total.value) + " 条", 1)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_spacer),
                      _createVNode(_component_v_btn_toggle, {
                        modelValue: filterType.value,
                        "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((filterType).value = $event)),
                        density: "compact",
                        variant: "outlined",
                        mandatory: "",
                        class: "mr-2"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "all"
                          }, {
                            default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                              _createTextVNode("全部", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "movie"
                          }, {
                            default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                              _createTextVNode("电影", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "tv"
                          }, {
                            default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
                              _createTextVNode("电视剧", -1)
                            ]))]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }, 8, ["modelValue"]),
                      _createVNode(_component_v_btn_toggle, {
                        modelValue: filterQuality.value,
                        "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((filterQuality).value = $event)),
                        density: "compact",
                        variant: "outlined",
                        mandatory: "",
                        class: "mr-2"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "all"
                          }, {
                            default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                              _createTextVNode("不限画质", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "4k"
                          }, {
                            default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
                              _createTextVNode("4K", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "cn"
                          }, {
                            default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                              _createTextVNode("中文字幕", -1)
                            ]))]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }, 8, ["modelValue"]),
                      _createVNode(_component_v_btn_toggle, {
                        modelValue: filterLink.value,
                        "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((filterLink).value = $event)),
                        density: "compact",
                        variant: "outlined",
                        mandatory: ""
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "all"
                          }, {
                            default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                              _createTextVNode("不限来源", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "share"
                          }, {
                            default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                              _createTextVNode("115转存", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "magnet"
                          }, {
                            default: _withCtx(() => [...(_cache[29] || (_cache[29] = [
                              _createTextVNode("磁力", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "ed2k"
                          }, {
                            default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
                              _createTextVNode("ed2k", -1)
                            ]))]),
                            _: 1
                          }),
                          _createVNode(_component_v_btn, {
                            size: "small",
                            value: "doc"
                          }, {
                            default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
                              _createTextVNode("仅文档", -1)
                            ]))]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }, 8, ["modelValue"])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_card_text, null, {
                    default: _withCtx(() => [
                      (busy.search)
                        ? (_openBlock(), _createBlock(_component_v_progress_linear, {
                            key: 0,
                            indeterminate: "",
                            color: "primary",
                            class: "mb-2"
                          }))
                        : (!results.value.length)
                          ? (_openBlock(), _createBlock(_component_v_alert, {
                              key: 1,
                              type: "info",
                              variant: "tonal",
                              class: "mb-2"
                            }, {
                              default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
                                _createTextVNode("没有找到匹配的资源，可调整筛选或换个关键词。", -1)
                              ]))]),
                              _: 1
                            }))
                          : _createCommentVNode("", true),
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(results.value, (r) => {
                        return (_openBlock(), _createBlock(_component_v_card, {
                          key: r.record_id,
                          variant: "tonal",
                          class: "mb-2"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_card_text, { class: "py-2" }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_row, {
                                  dense: "",
                                  align: "center"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_v_col, {
                                      cols: "12",
                                      md: "8"
                                    }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", _hoisted_8, [
                                          _createTextVNode(_toDisplayString(r.title) + " ", 1),
                                          (r.year)
                                            ? (_openBlock(), _createElementBlock("span", _hoisted_9, "（" + _toDisplayString(r.year) + "）", 1))
                                            : _createCommentVNode("", true)
                                        ]),
                                        _createElementVNode("div", _hoisted_10, [
                                          _createVNode(_component_v_chip, {
                                            size: "x-small",
                                            variant: "flat",
                                            color: r.media_type === 'movie' ? 'deep-purple' : 'blue-darken-2',
                                            class: "mr-1"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(mediaTypeName(r.media_type)), 1)
                                            ]),
                                            _: 2
                                          }, 1032, ["color"]),
                                          (r.bundle)
                                            ? (_openBlock(), _createBlock(_component_v_chip, {
                                                key: 0,
                                                size: "x-small",
                                                color: "deep-orange",
                                                class: "mr-1"
                                              }, {
                                                default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                                                  _createTextVNode("打包链接", -1)
                                                ]))]),
                                                _: 1
                                              }))
                                            : _createCommentVNode("", true),
                                          _createElementVNode("span", _hoisted_11, "来源：" + _toDisplayString(r.sheet), 1),
                                          (r.tmdbid)
                                            ? (_openBlock(), _createElementBlock("span", _hoisted_12, "｜TMDB：" + _toDisplayString(r.tmdbid), 1))
                                            : _createCommentVNode("", true)
                                        ]),
                                        _createElementVNode("div", _hoisted_13, [
                                          _cache[34] || (_cache[34] = _createElementVNode("span", { class: "text-medium-emphasis" }, "规格：", -1)),
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(specTokens(r.qtext), (tk, ti) => {
                                            return (_openBlock(), _createElementBlock("span", {
                                              key: ti,
                                              class: _normalizeClass(tk.color ? tk.color + ' font-weight-bold' : 'text-medium-emphasis')
                                            }, _toDisplayString(tk.text), 3))
                                          }), 128))
                                        ]),
                                        _createElementVNode("div", _hoisted_14, [
                                          _cache[35] || (_cache[35] = _createElementVNode("span", { class: "text-medium-emphasis" }, "链接：", -1)),
                                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((r.links || []), (lk, li) => {
                                            return (_openBlock(), _createBlock(_component_v_chip, {
                                              key: li,
                                              size: "small",
                                              variant: "flat",
                                              color: linkColor(lk.kind),
                                              "prepend-icon": linkIcon(lk.kind),
                                              href: linkHref(lk.url),
                                              target: "_blank",
                                              rel: "noopener",
                                              class: "mr-1"
                                            }, {
                                              default: _withCtx(() => [
                                                _createTextVNode(_toDisplayString(linkName(lk.kind)) + " " + _toDisplayString(shortUrl(lk.url)), 1)
                                              ]),
                                              _: 2
                                            }, 1032, ["color", "prepend-icon", "href"]))
                                          }), 128))
                                        ])
                                      ]),
                                      _: 2
                                    }, 1024),
                                    (r.sheet_bundle || r.no_link || r.bundle)
                                      ? (_openBlock(), _createBlock(_component_v_col, {
                                          key: 0,
                                          cols: "12",
                                          md: "4"
                                        }, {
                                          default: _withCtx(() => [
                                            _createElementVNode("div", _hoisted_15, _toDisplayString(r.no_link
                      ? '该表为纯列表，资源在外部文档：请点上方的链接自行查看（本插件不转存）'
                      : '该条目是打包链接（大包），已关闭一键转存：请点上方的 115/磁力 链接自行查看或转存'), 1)
                                          ]),
                                          _: 2
                                        }, 1024))
                                      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                          _createVNode(_component_v_col, {
                                            cols: "6",
                                            md: "2"
                                          }, {
                                            default: _withCtx(() => [
                                              _createVNode(_component_v_btn, {
                                                block: "",
                                                size: "small",
                                                color: "primary",
                                                loading: !!transferring[r.record_id],
                                                disabled: busy.search || !!transferring[r.record_id] || !r.record_id,
                                                onClick: $event => (transfer(r, 'movie'))
                                              }, {
                                                default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
                                                  _createTextVNode("转存到电影", -1)
                                                ]))]),
                                                _: 1
                                              }, 8, ["loading", "disabled", "onClick"])
                                            ]),
                                            _: 2
                                          }, 1024),
                                          _createVNode(_component_v_col, {
                                            cols: "6",
                                            md: "2"
                                          }, {
                                            default: _withCtx(() => [
                                              _createVNode(_component_v_btn, {
                                                block: "",
                                                size: "small",
                                                color: "secondary",
                                                disabled: busy.search || !!transferring[r.record_id] || !r.record_id,
                                                onClick: $event => (transfer(r, 'tv'))
                                              }, {
                                                default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                                                  _createTextVNode("转存到电视剧", -1)
                                                ]))]),
                                                _: 1
                                              }, 8, ["disabled", "onClick"])
                                            ]),
                                            _: 2
                                          }, 1024)
                                        ], 64))
                                  ]),
                                  _: 2
                                }, 1024)
                              ]),
                              _: 2
                            }, 1024)
                          ]),
                          _: 2
                        }, 1024))
                      }), 128)),
                      _createVNode(_component_v_row, {
                        dense: "",
                        align: "center",
                        class: "mt-2"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6",
                            class: "text-caption text-medium-emphasis"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(" 第 " + _toDisplayString(page.value) + " / " + _toDisplayString(pageCount.value) + " 页，每页 " + _toDisplayString(pageSize) + " 条（共 " + _toDisplayString(total.value) + " 条） ", 1)
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_pagination, {
                                "model-value": page.value,
                                length: pageCount.value,
                                disabled: busy.search,
                                "total-visible": 6,
                                density: "comfortable",
                                size: "small",
                                "onUpdate:modelValue": changePage
                              }, null, 8, ["model-value", "length", "disabled"])
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }))
            : _createCommentVNode("", true)
        ], 64))
      : (_openBlock(), _createBlock(_component_v_card, {
          key: 5,
          variant: "outlined"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center flex-wrap" }, {
              default: _withCtx(() => [
                _cache[40] || (_cache[40] = _createElementVNode("span", null, "转存记录", -1)),
                _createVNode(_component_v_chip, {
                  size: "x-small",
                  color: "primary",
                  class: "ml-2"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(records.value.length) + " 条", 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn_group, {
                  variant: "text",
                  density: "comfortable",
                  divided: ""
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      "prepend-icon": "mdi-refresh",
                      loading: busy.records,
                      onClick: _cache[7] || (_cache[7] = $event => (loadRecords(true)))
                    }, {
                      default: _withCtx(() => [...(_cache[38] || (_cache[38] = [
                        _createTextVNode(" 刷新 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      color: "error",
                      "prepend-icon": "mdi-delete-sweep",
                      disabled: !records.value.length,
                      onClick: clearRecords
                    }, {
                      default: _withCtx(() => [...(_cache[39] || (_cache[39] = [
                        _createTextVNode(" 清空 ", -1)
                      ]))]),
                      _: 1
                    }, 8, ["disabled"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_subtitle, { class: "text-caption pt-0" }, {
              default: _withCtx(() => [...(_cache[41] || (_cache[41] = [
                _createTextVNode(" 点「刷新」会一并按 MoviePilot 的「整理记录」核对整理结果；最多保留最近 200 条。 ", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                (!records.value.length)
                  ? (_openBlock(), _createBlock(_component_v_alert, {
                      key: 0,
                      type: "info",
                      variant: "tonal"
                    }, {
                      default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                        _createTextVNode(" 还没有转存 / 离线下载记录。去「搜索」页转存一条试试。 ", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(records.value, (r, i) => {
                  return (_openBlock(), _createBlock(_component_v_card, {
                    key: i,
                    variant: "tonal",
                    class: "mb-2"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_card_text, { class: "py-2" }, {
                        default: _withCtx(() => [
                          _createElementVNode("div", _hoisted_16, [
                            _createElementVNode("span", _hoisted_17, _toDisplayString(r.title), 1),
                            _createVNode(_component_v_chip, {
                              size: "x-small",
                              variant: "flat",
                              color: r.type === 'movie' ? 'deep-purple' : 'blue-darken-2',
                              class: "ml-2"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(mediaTypeName(r.type)), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"]),
                            _createVNode(_component_v_chip, {
                              size: "x-small",
                              variant: "flat",
                              color: kindColor(r.kind),
                              class: "ml-1"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(kindName(r.kind)), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"]),
                            _createVNode(_component_v_chip, {
                              size: "x-small",
                              variant: "flat",
                              color: statusColor(r.status),
                              class: "ml-1"
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(statusName(r.status)), 1)
                              ]),
                              _: 2
                            }, 1032, ["color"]),
                            _createVNode(_component_v_spacer),
                            _createElementVNode("span", _hoisted_18, _toDisplayString(r.submitted_at), 1),
                            (isActiveTask(r))
                              ? (_openBlock(), _createBlock(_component_v_btn, {
                                  key: 0,
                                  size: "x-small",
                                  variant: "text",
                                  color: "warning",
                                  disabled: busy.records,
                                  onClick: $event => (cancelTask(r))
                                }, {
                                  default: _withCtx(() => [...(_cache[43] || (_cache[43] = [
                                    _createTextVNode("停止自动搬运", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["disabled", "onClick"]))
                              : _createCommentVNode("", true),
                            (['failed', 'missing'].includes(r.status))
                              ? (_openBlock(), _createBlock(_component_v_btn, {
                                  key: 1,
                                  size: "x-small",
                                  variant: "text",
                                  color: "primary",
                                  disabled: busy.records || !!retrying[r.id],
                                  loading: !!retrying[r.id],
                                  onClick: $event => (retryTask(r))
                                }, {
                                  default: _withCtx(() => [...(_cache[44] || (_cache[44] = [
                                    _createTextVNode("重试", -1)
                                  ]))]),
                                  _: 1
                                }, 8, ["disabled", "loading", "onClick"]))
                              : _createCommentVNode("", true),
                            _createVNode(_component_v_btn, {
                              icon: "",
                              size: "x-small",
                              variant: "text",
                              color: "error",
                              class: "ml-1",
                              title: "删除这条记录",
                              onClick: $event => (deleteRecord(r))
                            }, {
                              default: _withCtx(() => [
                                _createVNode(_component_v_icon, null, {
                                  default: _withCtx(() => [...(_cache[45] || (_cache[45] = [
                                    _createTextVNode("mdi-delete", -1)
                                  ]))]),
                                  _: 1
                                })
                              ]),
                              _: 1
                            }, 8, ["onClick"])
                          ]),
                          _createElementVNode("div", _hoisted_19, [
                            _createTextVNode(" 目标：" + _toDisplayString(r.final_path) + " ", 1),
                            (r.kind !== '115_share' && r.staging_path && r.staging_path !== r.final_path)
                              ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                  _createTextVNode(" （离线先落 " + _toDisplayString(r.staging_path) + "） ", 1)
                                ], 64))
                              : _createCommentVNode("", true)
                          ]),
                          _createVNode(_component_v_progress_linear, {
                            class: "mt-2",
                            "model-value": (r.status === 'done' || r.status === 'organized') ? 100 : (r.progress || 0),
                            color: statusColor(r.status),
                            height: "8",
                            rounded: ""
                          }, null, 8, ["model-value", "color"]),
                          (r.status === 'downloading' && (r.progress || 0) >= 100)
                            ? (_openBlock(), _createElementBlock("div", _hoisted_20, _toDisplayString(r.message || '离线任务已完成，但文件未出现在暂存目录'), 1))
                            : (_openBlock(), _createElementBlock("div", _hoisted_21, [
                                _createElementVNode("span", _hoisted_22, _toDisplayString(r.message || ''), 1),
                                (r.status === 'downloading')
                                  ? (_openBlock(), _createElementBlock("span", _hoisted_23, _toDisplayString(r.progress || 0) + "%", 1))
                                  : _createCommentVNode("", true)
                              ]))
                        ]),
                        _: 2
                      }, 1024)
                    ]),
                    _: 2
                  }, 1024))
                }), 128))
              ]),
              _: 1
            })
          ]),
          _: 1
        }))
  ]))
}
}

};

export { _sfc_main as default };
