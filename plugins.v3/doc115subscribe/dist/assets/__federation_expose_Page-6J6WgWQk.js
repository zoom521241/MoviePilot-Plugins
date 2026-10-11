import { importShared } from './__federation_fn_import-SdO2Fg_T.js';
import Config, { U as UI_BUILD } from './__federation_expose_Config-CQo8YDB1.js';

const {toDisplayString:_toDisplayString$1,createElementVNode:_createElementVNode$1,vModelCheckbox:_vModelCheckbox,withDirectives:_withDirectives$1,createTextVNode:_createTextVNode$1,openBlock:_openBlock$1,createElementBlock:_createElementBlock$1,createCommentVNode:_createCommentVNode$1,resolveComponent:_resolveComponent$1,withCtx:_withCtx$1,createVNode:_createVNode$1,normalizeClass:_normalizeClass$1,createBlock:_createBlock$1} = await importShared('vue');


const _hoisted_1$1 = ["data-doc115-theme", "aria-labelledby", "aria-describedby"];
const _hoisted_2$1 = ["id"];
const _hoisted_3$1 = ["id"];
const _hoisted_4$1 = {
  key: 0,
  class: "doc115-confirm-check"
};
const _hoisted_5$1 = { class: "doc115-actions doc115-confirm-actions" };

const {ref: ref$1,watch: watch$1} = await importShared('vue');


// 统一确认弹窗：替代浏览器原生确认框。v-dialog 会传送到 body，所以根节点自带 data-doc115-theme。

const _sfc_main$1 = {
  __name: 'ConfirmDialog',
  props: {
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  text: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  tone: { type: String, default: 'primary' },
  // 非空时需要先勾选这句说明才能确认（用于「人工确认已转存」这类二次确认）
  check: { type: String, default: '' },
  dark: { type: Boolean, default: false },
},
  emits: ['confirm', 'cancel'],
  setup(__props) {

const props = __props;

const uid = Math.random().toString(36).slice(2, 8);
const ids = { title: `doc115-confirm-title-${uid}`, text: `doc115-confirm-text-${uid}` };
const checked = ref$1(false);
watch$1(() => props.modelValue, value => { if (value) checked.value = false; });

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent$1("v-btn");
  const _component_v_dialog = _resolveComponent$1("v-dialog");

  return (_openBlock$1(), _createBlock$1(_component_v_dialog, {
    "model-value": __props.modelValue,
    "max-width": "480",
    "onUpdate:modelValue": _cache[3] || (_cache[3] = value => { if (!value) _ctx.$emit('cancel'); })
  }, {
    default: _withCtx$1(() => [
      _createElementVNode$1("section", {
        class: "doc115-page doc115-confirm",
        "data-doc115-theme": __props.dark ? 'dark' : 'light',
        role: "alertdialog",
        "aria-labelledby": ids.title,
        "aria-describedby": ids.text
      }, [
        _createElementVNode$1("h3", {
          id: ids.title
        }, _toDisplayString$1(__props.title), 9, _hoisted_2$1),
        _createElementVNode$1("p", {
          id: ids.text,
          class: "doc115-confirm-text"
        }, _toDisplayString$1(__props.text), 9, _hoisted_3$1),
        (__props.check)
          ? (_openBlock$1(), _createElementBlock$1("label", _hoisted_4$1, [
              _withDirectives$1(_createElementVNode$1("input", {
                "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((checked).value = $event)),
                type: "checkbox"
              }, null, 512), [
                [_vModelCheckbox, checked.value]
              ]),
              _createTextVNode$1(" " + _toDisplayString$1(__props.check), 1)
            ]))
          : _createCommentVNode$1("", true),
        _createElementVNode$1("div", _hoisted_5$1, [
          _createVNode$1(_component_v_btn, {
            variant: "text",
            onClick: _cache[1] || (_cache[1] = $event => (_ctx.$emit('cancel')))
          }, {
            default: _withCtx$1(() => [...(_cache[4] || (_cache[4] = [
              _createTextVNode$1("取消", -1)
            ]))]),
            _: 1
          }),
          _createVNode$1(_component_v_btn, {
            variant: "flat",
            class: _normalizeClass$1(__props.tone === 'danger' ? 'doc115-cta doc115-cta-danger' : 'doc115-cta'),
            disabled: !!__props.check && !checked.value,
            onClick: _cache[2] || (_cache[2] = $event => (_ctx.$emit('confirm')))
          }, {
            default: _withCtx$1(() => [
              _createTextVNode$1(_toDisplayString$1(__props.confirmText), 1)
            ]),
            _: 1
          }, 8, ["class", "disabled"])
        ])
      ], 8, _hoisted_1$1)
    ]),
    _: 1
  }, 8, ["model-value"]))
}
}

};

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,unref:_unref,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock,normalizeClass:_normalizeClass,withKeys:_withKeys,vModelText:_vModelText,withDirectives:_withDirectives,normalizeStyle:_normalizeStyle} = await importShared('vue');


const _hoisted_1 = ["data-doc115-theme"];
const _hoisted_2 = { class: "doc115-header" };
const _hoisted_3 = { class: "doc115-header-text" };
const _hoisted_4 = { class: "doc115-muted doc115-small" };
const _hoisted_5 = { class: "doc115-actions" };
const _hoisted_6 = { class: "doc115-small" };
const _hoisted_7 = {
  key: 3,
  class: "doc115-statsbar",
  role: "group",
  "aria-label": "任务统计，点击查看对应任务"
};
const _hoisted_8 = ["aria-pressed", "onClick"];
const _hoisted_9 = {
  key: 4,
  class: "doc115-settings-panel",
  "aria-label": "设置"
};
const _hoisted_10 = { class: "doc115-small" };
const _hoisted_11 = { class: "doc115-actions doc115-wrap" };
const _hoisted_12 = {
  key: 0,
  class: "doc115-qr"
};
const _hoisted_13 = ["src"];
const _hoisted_14 = { class: "doc115-actions doc115-wrap" };
const _hoisted_15 = {
  key: 0,
  class: "doc115-diagnostic"
};
const _hoisted_16 = {
  class: "doc115-tabs",
  "aria-label": "插件功能"
};
const _hoisted_17 = ["aria-current", "onClick"];
const _hoisted_18 = {
  key: 0,
  "aria-label": "文档搜索"
};
const _hoisted_19 = { class: "doc115-panel doc115-search-input" };
const _hoisted_20 = {
  class: "doc115-panel doc115-filterbox",
  "aria-label": "搜索筛选"
};
const _hoisted_21 = ["id"];
const _hoisted_22 = { class: "doc115-filter-row" };
const _hoisted_23 = ["aria-busy"];
const _hoisted_24 = { class: "doc115-section-heading" };
const _hoisted_25 = { class: "doc115-chip doc115-blue" };
const _hoisted_26 = {
  key: 1,
  class: "doc115-empty"
};
const _hoisted_27 = { class: "doc115-title" };
const _hoisted_28 = {
  key: 0,
  class: "doc115-hit"
};
const _hoisted_29 = {
  key: 0,
  class: "doc115-blue doc115-year"
};
const _hoisted_30 = { class: "doc115-meta" };
const _hoisted_31 = {
  key: 0,
  class: "doc115-chip doc115-orange"
};
const _hoisted_32 = { class: "doc115-purple" };
const _hoisted_33 = {
  key: 1,
  class: "doc115-muted"
};
const _hoisted_34 = { class: "doc115-spec" };
const _hoisted_35 = { class: "doc115-links" };
const _hoisted_36 = ["href"];
const _hoisted_37 = { class: "doc115-card-footer" };
const _hoisted_38 = {
  key: 0,
  class: "doc115-muted"
};
const _hoisted_39 = { class: "doc115-muted" };
const _hoisted_40 = {
  key: 2,
  class: "doc115-pagination"
};
const _hoisted_41 = { class: "doc115-muted doc115-small" };
const _hoisted_42 = { class: "doc115-jump-wrap" };
const _hoisted_43 = ["max"];
const _hoisted_44 = {
  key: 1,
  class: "doc115-panel",
  "aria-label": "电影订阅"
};
const _hoisted_45 = { class: "doc115-section-heading" };
const _hoisted_46 = { class: "doc115-actions doc115-wrap" };
const _hoisted_47 = { class: "doc115-muted doc115-small" };
const _hoisted_48 = {
  key: 1,
  class: "doc115-muted doc115-small"
};
const _hoisted_49 = {
  key: 2,
  class: "doc115-empty"
};
const _hoisted_50 = {
  key: 3,
  class: "doc115-empty"
};
const _hoisted_51 = { class: "doc115-title" };
const _hoisted_52 = {
  key: 0,
  class: "doc115-blue doc115-year"
};
const _hoisted_53 = {
  key: 0,
  class: "doc115-spec"
};
const _hoisted_54 = ["aria-busy"];
const _hoisted_55 = { class: "doc115-section-heading" };
const _hoisted_56 = { class: "doc115-chip doc115-blue" };
const _hoisted_57 = { class: "doc115-filterbox" };
const _hoisted_58 = { class: "doc115-filter-row" };
const _hoisted_59 = { class: "doc115-filter-row" };
const _hoisted_60 = {
  key: 1,
  class: "doc115-bulkbar",
  role: "group",
  "aria-label": "批量操作"
};
const _hoisted_61 = { class: "doc115-check" };
const _hoisted_62 = ["checked", ".indeterminate"];
const _hoisted_63 = { class: "doc115-muted doc115-small" };
const _hoisted_64 = {
  key: 2,
  class: "doc115-empty"
};
const _hoisted_65 = ["checked", "aria-label", "onChange"];
const _hoisted_66 = ["onClick"];
const _hoisted_67 = { class: "doc115-row-title" };
const _hoisted_68 = {
  key: 0,
  class: "doc115-muted"
};
const _hoisted_69 = { class: "doc115-row-time doc115-small doc115-muted" };
const _hoisted_70 = { class: "doc115-section-heading" };
const _hoisted_71 = ["checked", "aria-label", "onChange"];
const _hoisted_72 = { class: "doc115-title" };
const _hoisted_73 = {
  key: 0,
  class: "doc115-blue doc115-year"
};
const _hoisted_74 = {
  key: 0,
  class: "doc115-chip doc115-neutral"
};
const _hoisted_75 = { class: "doc115-stage" };
const _hoisted_76 = {
  key: 0,
  class: "doc115-cyan doc115-path"
};
const _hoisted_77 = {
  key: 1,
  class: "doc115-download"
};
const _hoisted_78 = ["value"];
const _hoisted_79 = {
  key: 0,
  class: "doc115-amber"
};
const _hoisted_80 = {
  key: 2,
  class: "doc115-small doc115-message"
};
const _hoisted_81 = {
  key: 3,
  class: "doc115-red doc115-small"
};
const _hoisted_82 = { class: "doc115-meta doc115-small doc115-muted" };
const _hoisted_83 = { key: 0 };
const _hoisted_84 = { key: 1 };
const _hoisted_85 = {
  key: 4,
  class: "doc115-small doc115-amber"
};
const _hoisted_86 = { class: "doc115-actions doc115-wrap doc115-task-actions" };
const _hoisted_87 = { class: "doc115-details" };
const _hoisted_88 = {
  key: 0,
  class: "doc115-cyan doc115-path"
};
const _hoisted_89 = {
  key: 1,
  class: "doc115-purple"
};
const _hoisted_90 = { class: "doc115-spec" };
const _hoisted_91 = {
  key: 2,
  class: "doc115-cyan doc115-path"
};
const _hoisted_92 = { class: "doc115-muted" };
const _hoisted_93 = { key: 3 };
const _hoisted_94 = {
  key: 4,
  class: "doc115-muted"
};
const _hoisted_95 = { key: 5 };
const _hoisted_96 = { class: "doc115-actions doc115-wrap doc115-task-actions" };
const _hoisted_97 = {
  key: 1,
  class: "doc115-muted doc115-small"
};
const _hoisted_98 = {
  key: 3,
  class: "doc115-pagination"
};
const _hoisted_99 = { class: "doc115-muted doc115-small" };
const _hoisted_100 = { class: "doc115-jump-wrap" };
const _hoisted_101 = ["max"];
const _hoisted_102 = { class: "doc115-maintenance" };
const _hoisted_103 = { class: "doc115-actions doc115-wrap" };
const _hoisted_104 = ["data-doc115-theme"];
const _hoisted_105 = { id: "doc115-transfer-title" };
const _hoisted_106 = { class: "doc115-title" };
const _hoisted_107 = {
  key: 0,
  class: "doc115-year doc115-muted"
};
const _hoisted_108 = { class: "doc115-cyan doc115-path doc115-small" };
const _hoisted_109 = { class: "doc115-muted doc115-small" };
const _hoisted_110 = { class: "doc115-actions doc115-confirm-actions" };

const {computed,inject,onActivated,onBeforeUnmount,onDeactivated,onMounted,reactive,ref,watch} = await importShared('vue');

const pageSize = 10;
const MSG_TIMEOUT = 6000, JOB_POLL_MS = 5000, RECORDS_QUERY_DEBOUNCE = 400;
const PREFS_KEY = 'doc115subscribe.search.v1';

const _sfc_main = {
  __name: 'Page',
  props: { model: { type: Object, default: () => ({}) }, api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) } },
  emits: ['action', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const hostTheme = inject(Symbol.for('vuetify:theme'), null);
const darkTheme = computed(() => !!(props.model?.dark ?? hostTheme?.current?.value?.dark));
const status = reactive({ version: '', enabled: null, subscribe_enabled: false, cookie_ready: false, p115_ready: false, cookie_days_left: null, record_count: 0, sheet_count: 0, built_at_text: '尚未建立', index_errors: [], stale_sheets: [], last_subscribe: null, refreshing: false, movie_path: '', tv_path: '', stats: null, jobs: null });
const msg = ref(''), msgType = ref('info');
const busy = reactive({ refresh: false, qr: false, search: false, subscribe: false, check: false, records: false, preview: false, diagnostics: false, bulk: false });
const qrImage = ref(''), qrTip = ref('等待扫码'), qrSessionId = ref('');
const settingsOpen = ref(false), diagnostics = ref(null);
const emptyStats = () => ({ movie: { total: 0, organized: 0 }, tv: { total: 0, organized: 0 }, total: 0, organized: 0 });
const recordsStats = ref(null);
const jump = reactive({ search: '', records: '' });
const keyword = ref(''), results = ref([]), searched = ref(false), searchedKeyword = ref(''), total = ref(0), resultVersion = ref('');
const transferring = reactive({}), retrying = reactive({}), verifying = reactive({});
const tabs = [{ value: 'search', label: '搜索' }, { value: 'subscriptions', label: '电影订阅' }, { value: 'records', label: '任务' }];
const tab = ref('search'), records = ref([]), recordsTotal = ref(0), recordsPage = ref(1), recordsFilter = ref('all'), recordsMedia = ref('all'), recordsQuery = ref('');
const selected = reactive({}), expanded = reactive({});
const subscriptions = ref([]), subscriptionNote = ref('预演只读取本地缓存，不提交资源。'), subscriptionCacheEmpty = ref(false);
const subscriptionNextAt = computed(() => Number(subscriptions.value.find(s => Number(s.next_check_at) > 0)?.next_check_at) || 0);
const prefs = readPrefs();
const page = ref(1), filterType = ref(prefs.type || 'all'), filterQuality = ref(prefs.quality || 'all'), filterSubtitle = ref(prefs.subtitle || 'all'), filterLink = ref(prefs.link || 'all'), sortBy = ref(prefs.sort || 'relevance');
// reactive() 会解包并回写这些 ref，模板里的 chip 组可以按 key 循环绑定
const searchFilters = reactive({ type: filterType, quality: filterQuality, subtitle: filterSubtitle, link: filterLink });
const transferOpen = ref(false), transferRecord = ref(null), transferTarget = ref('movie'), transferSource = ref(''), transferIndexVersion = ref(''), transferQuick = ref(false);
const confirmState = reactive({ open: false, title: '', text: '', confirmText: '确认', tone: 'primary', check: '' });
const narrow = ref(false);
let searchSerial = 0, searchController = null, searchDebounce = null, disposed = false, componentActive = true;
let recTimer = null, recFailures = 0, recUnchanged = 0, lastRecordsSnapshot = '', recordsSerial = 0, recController = null, reloadPending = false, pageFallbackSerial = -1, recQueryTimer = null;
let qrTimer = null, qrGeneration = 0, msgTimer = null, jobTimer = null, confirmResolve = null, mediaQuery = null;
const watchedJobs = new Set(), lastRetryNotice = {};

const searchFilterGroups = [
  { key: 'type', label: '类型', options: [{ value: 'all', label: '全部' }, { value: 'movie', label: '电影' }, { value: 'tv', label: '电视剧' }] },
  { key: 'quality', label: '画质', options: [{ value: 'all', label: '不限' }, { value: '4k', label: '4K' }, { value: '1080p', label: '1080P' }] },
  { key: 'subtitle', label: '字幕', options: [{ value: 'all', label: '不限' }, { value: 'cn', label: '中文字幕 / 国语' }] },
  { key: 'link', label: '链接', options: [{ value: 'all', label: '不限' }, { value: 'share', label: '115分享' }, { value: 'magnet', label: '磁力' }, { value: 'ed2k', label: 'ed2k' }, { value: 'doc', label: '仅文档' }] },
];
const sortOptions = [{ title: '相关度', value: 'relevance' }, { title: '年份：新 → 旧', value: 'year_desc' }, { title: '年份：旧 → 新', value: 'year_asc' }, { title: '画质优先', value: 'quality' }];
const recordFilterOptions = [{ value: 'all', label: '全部' }, { value: 'active', label: '进行中' }, { value: 'needs_attention', label: '需处理' }, { value: 'completed', label: '已入库' }, { value: 'hidden', label: '已隐藏' }];
const mediaOptions = [{ value: 'all', label: '全部' }, { value: 'movie', label: '电影' }, { value: 'tv', label: '电视剧' }];
const targetOptions = [{ title: '电影目录', value: 'movie' }, { title: '电视剧目录', value: 'tv' }];
const ACTIONS = {
  reconcile: { label: '核对转存结果', primary: true },
  check_download: { label: '重查下载状态' },
  retry_move: { label: '重试搬运', primary: true },
  retry_submit: { label: '重新获取（此前未获取成功）' },
  confirm_saved: { label: '我已确认文件在 115 中' },
  stop_tracking: { label: '停止自动跟踪' },
};

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const recordsPageCount = computed(() => Math.max(1, Math.ceil(recordsTotal.value / pageSize)));
const indexSummary = computed(() => `本地索引 ${status.record_count || 0} 条，来自 ${status.sheet_count || 0} 张表` + (status.enabled === false ? '；插件已停用' : ''));
const indexWarnings = computed(() => [...new Set([...(status.index_errors || []).map(String), ...(status.stale_sheets || []).map(s => typeof s === 'string' ? `保留旧索引：${s}` : `保留旧索引：${s.title || s.name || s.sheet_id || '未知工作表'}`)])]);
const cookieText = computed(() => !status.cookie_ready ? '未登录，请扫码' : status.cookie_days_left == null ? '已登录' : `已登录，约 ${Math.max(0, Math.floor(status.cookie_days_left))} 天后过期`);
// 统计优先用 status.stats（全局、不受筛选影响）；旧后端只在 records 响应里给 stats
const stats = computed(() => ({ ...emptyStats(), ...(status.stats || recordsStats.value || {}) }));
const statsItems = computed(() => {
  const s = stats.value, items = [
    { key: 'movie', label: `电影 · 已入库 ${s.movie?.organized || 0}`, value: s.movie?.total || 0, color: 'doc115-purple' },
    { key: 'tv', label: `电视剧 · 已入库 ${s.tv?.organized || 0}`, value: s.tv?.total || 0, color: 'doc115-cyan' },
    { key: 'completed', label: '已入库', value: s.organized || 0, color: 'doc115-green' },
  ];
  if (s.active != null) items.push({ key: 'active', label: '进行中', value: s.active, color: 'doc115-blue' });
  if (s.attention != null) items.push({ key: 'needs_attention', label: '需处理', value: s.attention, color: s.attention ? 'doc115-red' : 'doc115-neutral' });
  items.push({ key: 'all', label: '全部任务', value: s.total || 0, color: 'doc115-neutral' });
  return items
});
const jobs = computed(() => status.jobs && typeof status.jobs === 'object' ? status.jobs : {});
const runningJobs = computed(() => {
  const list = [];
  const index = jobs.value.index?.state;
  if (index === 'running' || status.refreshing) list.push({ name: 'index', label: '索引更新中…' });
  else if (index === 'queued') list.push({ name: 'index', label: '索引更新已排队…' });
  const sub = jobs.value.subscribe?.state;
  if (sub === 'running') list.push({ name: 'subscribe', label: '订阅同步中…' });
  else if (sub === 'queued') list.push({ name: 'subscribe', label: '订阅同步已排队…' });
  return list
});
const selectedIds = computed(() => records.value.filter(r => selected[r.id]).map(r => r.id));
const selectedRecords = computed(() => records.value.filter(r => selected[r.id]));
const allSelected = computed(() => records.value.length > 0 && records.value.every(r => selected[r.id]));
const someSelected = computed(() => selectedIds.value.length > 0);
const orderedRecords = computed(() => {
  const rank = r => needsAttention(r) ? 0 : isActiveTask(r) || isPendingOrganize(r) ? 1 : 2;
  return records.value.map((r, i) => [r, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(x => x[0])
});
const recordsEmptyText = computed(() => recordsQuery.value.trim() ? `没有标题包含「${recordsQuery.value.trim()}」的任务。` : recordsFilter.value === 'hidden' ? '没有已隐藏的任务。' : '此范围暂无任务。搜索资源并获取后，进度会显示在这里。');
const transferPath = computed(() => transferTarget.value === 'tv' ? (status.tv_path || '使用已配置的电视剧目录') : (status.movie_path || '使用已配置的电影目录'));
const transferNote = computed(() => {
  const kind = sourceOptions(transferRecord.value).find(o => o.value === transferSource.value)?.kind;
  const subdir = '是否在目录下建「片名 (年份)」子目录以插件设置为准。';
  if (kind === 'magnet' || kind === 'ed2k') return `只提交所选链接。磁力 / ed2k 先由 115 离线下载到暂存目录，完成后借助 115网盘Plus 搬到上面的目录；${subdir}整理由 MP 已配置的流程处理。`
  return `只提交所选链接，不自动切换其它来源。115 分享直接转存到上面的目录；${subdir}整理由 MP 已配置的流程处理。`
});
const diagnosticText = computed(() => {
  const data = diagnostics.value || {}, cloud = data.cloud || {}, mp = data.mp || {};
  if (data.summary || data.message || data.msg) return data.summary || data.message || data.msg
  return `活动任务 ${data.active_tasks || 0} 个；115：${cloud.reason || cloud.state || '按预算处理'}；MP：${mp.last_error || mp.state || (mp.port_ready ? '只读接口已确认' : '只读接口待验证')}${cloud.reason && cloud.retry_at ? `；下次允许请求：${formatTime(cloud.retry_at)}` : ''}`
});

function readPrefs() { try { const raw = typeof localStorage !== 'undefined' && localStorage.getItem(PREFS_KEY); const value = raw ? JSON.parse(raw) : {}; return value && typeof value === 'object' ? value : {} } catch (_) { return {} } }
function savePrefs() { try { if (typeof localStorage !== 'undefined') localStorage.setItem(PREFS_KEY, JSON.stringify({ type: filterType.value, quality: filterQuality.value, subtitle: filterSubtitle.value, link: filterLink.value, sort: sortBy.value })); } catch (_) { /* 隐私模式等场景不记忆即可 */ } }
function mediaTypeName(type) { return ({ movie: '电影', tv: '电视剧' })[type] || '类型待确认' }
function clearMsg() { if (msgTimer) { clearTimeout(msgTimer); msgTimer = null; } msg.value = ''; }
function setMsg(text, type = 'info') {
  if (disposed) return
  if (msgTimer) { clearTimeout(msgTimer); msgTimer = null; }
  msg.value = text; msgType.value = type;
  if (text) msgTimer = setTimeout(() => { msgTimer = null; msg.value = ''; }, MSG_TIMEOUT);
}
function unwrap(res) { return res && typeof res === 'object' && 'code' in res ? res : { code: 0, msg: '', data: res } }
function describeError(e) { return e?.response?.status === 403 ? '当前账号没有权限' : e?.message || '请求失败，请稍后重试' }
function isAbort(e) { return e?.name === 'AbortError' || e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED' }
function formatTime(value) { if (!value) return '时间待确认'; if (typeof value === 'number') return new Date(value < 1e12 ? value * 1000 : value).toLocaleString(); return String(value) }

// 统一确认弹窗：返回 Promise<boolean>，替代浏览器原生确认框
function askConfirm(options) {
  if (confirmResolve) confirmResolve(false);
  Object.assign(confirmState, { title: '请确认', confirmText: '确认', tone: 'primary', check: '', text: '' }, options, { open: true });
  return new Promise(resolve => { confirmResolve = resolve; })
}
function answerConfirm(value) { const resolve = confirmResolve; confirmResolve = null; confirmState.open = false; if (resolve) resolve(!!value); }

const LINK_STYLE = { '115_share': { color: 'doc115-cyan', name: '115分享', icon: 'mdi-cloud-download' }, magnet: { color: 'doc115-orange', name: '磁力', icon: 'mdi-magnet' }, ed2k: { color: 'doc115-brown', name: 'ed2k', icon: 'mdi-link-variant' }, http: { color: 'doc115-neutral', name: '文档 / 网页', icon: 'mdi-web' } };
function linkColor(kind) { return LINK_STYLE[kind]?.color || 'doc115-neutral' }
function linkName(kind) { return LINK_STYLE[kind]?.name || kind || '来源待确认' }
function linkIcon(kind) { return LINK_STYLE[kind]?.icon || 'mdi-link' }
function shortUrl(url) { const value = String(url || '').replace(/^https?:\/\//i, ''); return value.length > 44 ? value.slice(0, 44) + '…' : value }
function linkHref(url) {
  const value = String(url || '').trim();
  if (/^(https?:\/\/|magnet:\?|ed2k:\/\/)/i.test(value)) return value
  if (/^(?:www\.)?(?:115\.com|115cdn\.com|anxia\.com|docs\.qq\.com)\//i.test(value)) return 'https://' + value
  return undefined
}
// 命中高亮：优先用后端给的 match 片段，没有就用本次搜索关键词，大小写不敏感；只做文本切分，不拼 HTML
function highlightParts(text, match) {
  const value = String(text ?? '');
  const needles = (Array.isArray(match) ? match : [match || searchedKeyword.value]).map(x => String(x || '').trim()).filter(Boolean);
  if (!value || !needles.length) return [{ text: value, hit: false }]
  const escaped = needles.sort((a, b) => b.length - a.length).map(x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const re = new RegExp(escaped.join('|'), 'gi');
  const parts = []; let last = 0, m;
  while ((m = re.exec(value)) !== null) {
    if (!m[0]) { re.lastIndex += 1; continue }
    if (m.index > last) parts.push({ text: value.slice(last, m.index), hit: false });
    parts.push({ text: m[0], hit: true }); last = m.index + m[0].length;
  }
  if (last < value.length) parts.push({ text: value.slice(last), hit: false });
  return parts.length ? parts : [{ text: value, hit: false }]
}
const SPEC_RE = /(4K|2160[pP]|1080[pP]|720[pP]|REMUX|UHD|HDR10\+?|HDR|杜比视界|Dolby\s?Vision|Atmos|蓝光原盘|原盘|中文字幕|简繁|简体|繁体|国语|双语|粤语|无中字)/gi;
function specTokens(text) {
  const value = String(text || '');
  if (!value) return [{ text: '规格待确认', color: 'doc115-neutral' }]
  const parts = []; let last = 0, match; SPEC_RE.lastIndex = 0;
  while ((match = SPEC_RE.exec(value)) !== null) {
    if (match.index > last) parts.push({ text: value.slice(last, match.index), color: '' });
    const word = match[0].toUpperCase();
    const color = /无中字/.test(word) ? 'doc115-red' : /中文字幕|简繁|简体|繁体|国语|双语|粤语/.test(word) ? 'doc115-green' : 'doc115-amber';
    parts.push({ text: match[0], color }); last = match.index + match[0].length;
  }
  if (last < value.length) parts.push({ text: value.slice(last), color: '' });
  return parts
}
const STATUS_STYLE = {
  submitting: ['提交中', 'blue'], submitted: ['115已接受，结果待确认', 'blue'], uncertain: ['提交结果待确认', 'amber'], downloading: ['115下载中', 'blue'], waiting: ['等待文件落盘', 'amber'], awaiting_move: ['等待搬运', 'amber'], moving: ['搬运中', 'blue'], queued: ['已排队', 'blue'], done: ['已保存到下载目录', 'green'], moved: ['已保存到下载目录', 'green'], saved: ['已保存到下载目录', 'green'], acquired: ['云端已保存', 'green'], missing: ['文件位置待核实', 'amber'], unverified: ['MP整理待核实', 'neutral'], pending: ['MP整理待核实', 'neutral'], unknown: ['证据不足，待核实', 'neutral'], incomplete: ['清单不完整，待核实', 'amber'], organizing: ['MP整理中', 'blue'], partial: ['MP部分整理成功', 'orange'], unfound: ['暂无本批次整理证据', 'neutral'], organized: ['MP整理成功', 'green'], success: ['MP整理成功', 'green'], confirmed: ['MP整理成功', 'green'], failed: ['失败，需要处理', 'red'], query_error: ['核对查询失败', 'red'], paused: ['自动核对已暂停', 'neutral'], cancelled: ['已停止自动跟踪', 'neutral'], stopped: ['已停止自动跟踪', 'neutral'], not_started: ['MP整理待核实', 'neutral'], not_applicable: ['暂不核对整理', 'neutral']
};
function statusName(value) { return STATUS_STYLE[value]?.[0] || value || '待核实' }
function statusColor(value) { return 'doc115-' + (STATUS_STYLE[value]?.[1] || 'neutral') }
function acquisitionState(r) { const state = r.acquisition_status || r.acquisition?.status || (r.organization_confirmed || r.status === 'organized' ? 'done' : r.status); return state === 'success' ? 'saved' : state }
function organizationState(r) { return r.organization_status || r.organization?.status || (r.organization_confirmed ? 'organized' : ['partial', 'unverified', 'unfound'].includes(r.status) ? r.status : 'pending') }
function statusCss(r) { const state = r.query_error ? 'query_error' : acquisitionState(r) === 'failed' ? 'failed' : isActiveTask(r) || ['pending', 'not_applicable', 'not_started'].includes(organizationState(r)) ? acquisitionState(r) : organizationState(r); return `var(--doc115-${STATUS_STYLE[state]?.[1] || 'neutral'})` }
function organizationCounts(r) { const o = r.organization || {}; return { confirmed: Number(o.confirmed ?? r.organization_count ?? r.organized_count ?? 0), expected: Number(o.expected ?? r.expected_count ?? r.organized_total ?? 0), failed: Number(o.failed ?? r.organization_failed_count ?? r.organized_failed ?? 0), missing: Number(o.missing ?? r.organized_missing ?? 0), complete: !!(o.manifest_complete ?? r.manifest_complete) } }
function organizationSummary(r) { const counts = organizationCounts(r); return statusName(organizationState(r)) + (counts.expected ? ` · ${counts.confirmed}/${counts.expected}` : counts.confirmed ? ` · 已确认 ${counts.confirmed} 个` : '') + (counts.missing ? ` · ${counts.missing} 个待核实` : '') }
function manifestText(r) { const counts = organizationCounts(r); return counts.complete ? `必要清单完整：已确认 ${counts.confirmed}/${counts.expected} 个${counts.failed ? `，失败 ${counts.failed} 个` : ''}${counts.missing ? `，${counts.missing} 个暂无整理证据` : ''}` : `已确认 ${counts.confirmed} 个，必要文件清单完整性待核实。` }
function fileDetails(r) { return Array.isArray(r.files) ? r.files : Array.isArray(r.organization?.files) ? r.organization.files : [] }
function progressValue(r) { return Math.max(0, Math.min(100, Number(r.progress) || 0)) }
function hasAction(r, action) { return Array.isArray(r?.allowed_actions) && r.allowed_actions.some(a => (typeof a === 'string' ? a : a.action || a.name) === action) }
function needsVerify(r) { return Array.isArray(r.allowed_actions) ? hasAction(r, 'verify') : !r.organization_confirmed && r.status !== 'failed' }
function visibleActions(r) { return Object.keys(ACTIONS).filter(action => hasAction(r, action)).map(action => ({ action, ...ACTIONS[action] })) }
function recordMedia(r) { const kind = String(r.media_type || r.type || r.target_type || '').toLowerCase(); return ['tv', '电视剧', '剧集'].includes(kind) ? 'tv' : ['movie', '电影'].includes(kind) ? 'movie' : kind }
function isActiveTask(r) { return r.tracking_enabled !== false && !['cancelled', 'stopped', 'paused'].includes(acquisitionState(r)) && ['submitting', 'submitted', 'uncertain', 'downloading', 'waiting', 'awaiting_move', 'moving', 'queued'].includes(acquisitionState(r)) }
function isPendingOrganize(r) { return r.tracking_enabled !== false && !r.org_giveup && !r.tracking_stopped && !['organized', 'success', 'confirmed', 'paused', 'cancelled', 'stopped', 'not_applicable'].includes(organizationState(r)) && ['done', 'moved', 'saved', 'acquired'].includes(acquisitionState(r)) }
function needsAttention(r) { return !!(r.query_error || ['partial', 'failed', 'paused'].includes(organizationState(r)) || ['uncertain', 'failed'].includes(acquisitionState(r))) }
// 后端 0.11.0 给出 tracking；旧后端以 stop_tracking 是否可用推断
function isTracking(r) { return typeof r.tracking === 'boolean' ? r.tracking : hasAction(r, 'stop_tracking') }
// 已完成任务用紧凑单行；需处理/进行中保持卡片
function isDone(r) { return ['success', 'confirmed', 'organized'].includes(String(organizationState(r))) }
function isCompact(r) { return isDone(r) && !needsAttention(r) }
function recordBusy(r) { return !!(retrying[r.id] || verifying[r.id]) || busy.bulk }

// 只保留后端实际会返回的结果形态：code≠0 失败；state=queued 排队；uncertain 提交结果待确认；批量 done/skipped
function resultFeedback(res, fallback) {
  const data = res?.data || {};
  if (res?.code !== 0 || data.query_error) return [res?.msg || data.query_error || '操作失败，请查看任务详情。', 'error']
  if (data.uncertain) return [res.msg || '115 已收到请求但结果未确定，请在任务页「核对转存结果」，不要重复获取。', 'warning']
  if ('done' in data && 'skipped' in data) return [`${res.msg ? res.msg + '：' : ''}完成 ${Number(data.done) || 0} 条${Number(data.skipped) ? `，跳过 ${Number(data.skipped)} 条` : ''}。`, Number(data.skipped) && !Number(data.done) ? 'warning' : 'success']
  if (data.state === 'queued') return [res.msg || '已加入后台队列，任务页可查看进度。', 'info']
  return [res.msg || fallback, 'info']
}
function showResult(res, fallback) { setMsg(...resultFeedback(res, fallback)); }
async function post(endpoint, payload, timeout = 30000) { return unwrap(await props.api.post(`plugin/Doc115Subscribe/${endpoint}`, payload, { timeout })) }

async function verifyOne(r) {
  if (!r?.id || verifying[r.id]) return
  verifying[r.id] = true;
  try { showResult(await post('records_verify', { id: r.id }), '已排队核对整理证据。'); }
  catch (e) { setMsg(`核对失败：${describeError(e)}`, 'error'); }
  finally { verifying[r.id] = false; }
  await loadRecords();
}
function recordParams() {
  const params = { page: recordsPage.value, page_size: pageSize, filter: recordsFilter.value };
  // 只在非默认值时才带新参数，旧后端不认识的参数不会被发送
  const q = String(recordsQuery.value || '').trim();
  if (q) params.q = q;
  if (recordsMedia.value !== 'all') params.media = recordsMedia.value;
  return params
}
async function loadRecords() {
  if (disposed) return false
  // 已有请求在途：记下来，等它结束后补刷一次，保证操作后的刷新不会丢
  if (busy.records) { reloadPending = true; return false }
  const serial = ++recordsSerial;
  busy.records = true;
  reloadPending = false;
  recController = typeof AbortController === 'function' ? new AbortController() : null;
  let fallbackPage = 0;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/records', { params: recordParams(), signal: recController?.signal, timeout: 30000 }));
    if (disposed || serial !== recordsSerial) return false
    if (res.code !== 0) throw new Error(res.msg || '读取任务失败')
    const data = res.data || [];
    if (Array.isArray(data)) { records.value = data; recordsTotal.value = data.length; }
    else {
      records.value = Array.isArray(data.records) ? data.records : [];
      recordsTotal.value = Number(data.total) || 0;
      if (Number(data.page) >= 1) recordsPage.value = Number(data.page);
      if (data.stats) recordsStats.value = data.stats;
      // 页码越界（例如隐藏后本页清空）：回退到最后一页再取一次
      const last = Math.max(1, Math.ceil(recordsTotal.value / pageSize));
      if (!records.value.length && recordsTotal.value > 0 && recordsPage.value > last && pageFallbackSerial !== serial) { pageFallbackSerial = serial + 1; fallbackPage = last; }
    }
    for (const id of Object.keys(selected)) if (!records.value.some(r => r.id === id)) delete selected[id];
    const snapshot = JSON.stringify(records.value.map(r => [r.id, r.status, r.acquisition_status, r.organization_status, r.progress, r.organization, r.query_error, r.last_error, r.updated_at, r.allowed_actions, r.hidden]));
    recUnchanged = snapshot === lastRecordsSnapshot ? recUnchanged + 1 : 0;
    lastRecordsSnapshot = snapshot;
    recFailures = 0;
    return true
  } catch (e) { if (!disposed && serial === recordsSerial && !isAbort(e)) { recFailures += 1; setMsg(`读取任务失败：${describeError(e)}`, 'error'); } return false }
  finally {
    if (serial === recordsSerial) {
      busy.records = false; recController = null;
      if (fallbackPage) { recordsPage.value = fallbackPage; reloadPending = true; }
      if (reloadPending && !disposed) { reloadPending = false; loadRecords(); } else scheduleRecTimer();
    }
  }
}
function restartRecords() { recordsSerial += 1; recController?.abort(); recController = null; busy.records = false; reloadPending = false; loadRecords(); }
function pageVisible() { return typeof document === 'undefined' || document.visibilityState !== 'hidden' }
function shouldPoll() { return !disposed && componentActive && pageVisible() && tab.value === 'records' && !settingsOpen.value && records.value.some(r => isActiveTask(r) || isPendingOrganize(r)) }
function stopRecTimer() { if (recTimer) { clearTimeout(recTimer); recTimer = null; } }
function scheduleRecTimer() { stopRecTimer(); if (!shouldPoll()) return; recTimer = setTimeout(() => { recTimer = null; if (shouldPoll()) loadRecords(); }, Math.min(300000, 20000 * 2 ** Math.min(Math.max(recFailures, recUnchanged), 4))); }
function visibilityChanged() { stopRecTimer(); stopQrTimer(); stopJobPoll(); if (!pageVisible() || !componentActive || disposed) return; if (tab.value === 'records' && !settingsOpen.value) loadRecords(); if (settingsOpen.value && qrSessionId.value) startQrTimer(); if (watchedJobs.size) startJobPoll(); }
function abortSearch() { if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null; } searchController?.abort(); searchController = null; }
function pause() { stopQrTimer(); stopRecTimer(); stopJobPoll(); if (recQueryTimer) { clearTimeout(recQueryTimer); recQueryTimer = null; } }
function dispose() { disposed = true; searchSerial += 1; abortSearch(); pause(); clearMsg(); answerConfirm(false); recordsSerial += 1; recController?.abort(); if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visibilityChanged); mediaQuery?.removeEventListener?.('change', updateNarrow); }
// 关闭只通知宿主；资源清理交给卸载 / 失活钩子，宿主用 KeepAlive 复用实例时仍可正常工作
function close() { emit('close'); }

// ---- 任务操作 ----
const BULK_TEXT = {
  verify: { label: '批量核对整理', text: n => `为选中的 ${n} 条任务排队核对 MP 整理证据？只读取整理记录，不会重新获取资源。` },
  hide: { label: '批量隐藏', text: n => `把选中的 ${n} 条任务从列表隐藏？仅从列表隐藏，可在『已隐藏』筛选中恢复；跟踪中的任务会被跳过。` },
  unhide: { label: '恢复显示', text: n => `恢复显示选中的 ${n} 条任务？` },
  stop_tracking: { label: '批量停止跟踪', text: n => `停止选中的 ${n} 条任务的自动跟踪？已有下载与文件会保留，之后不再自动核对；来自电影订阅的任务，对应订阅也不再由本插件自动获取。`, tone: 'danger' },
};
// 写操作后同时刷新列表与全局统计（统计来自 status，不受筛选影响）
async function afterMutation() { await Promise.all([loadRecords(), loadStatus()]); }
function toggleSelect(r, value) { if (value) selected[r.id] = true; else delete selected[r.id]; }
function toggleAll(value) { for (const r of records.value) toggleSelect(r, value); }
async function bulkAction(action, ids = selectedIds.value, skipConfirm = false) {
  const info = BULK_TEXT[action];
  if (!info || !ids.length || busy.bulk) return
  if (!skipConfirm && !(await askConfirm({ title: info.label, text: info.text(ids.length), confirmText: info.label, tone: info.tone || 'primary' }))) return
  busy.bulk = true;
  try { showResult(await post('records_bulk', { ids: [...ids], action }), `${info.label}已提交。`); for (const id of ids) delete selected[id]; }
  catch (e) { setMsg(`${info.label}失败：${describeError(e)}`, 'error'); }
  finally { busy.bulk = false; }
  await afterMutation();
}
async function deleteRecord(r) {
  if (!r?.id || recordBusy(r)) return
  if (isTracking(r)) { setMsg(`「${r.title}」仍在跟踪中，请先停止跟踪再隐藏。`, 'warning'); return }
  if (!(await askConfirm({ title: '从列表隐藏', text: `仅从列表隐藏「${r.title}」，可在『已隐藏』筛选中恢复。任务、网盘文件与防重复获取记录都会保留。`, confirmText: '隐藏' }))) return
  retrying[r.id] = 'hide';
  try { showResult(await post('records_delete', { id: r.id }), '已从列表隐藏，可在『已隐藏』筛选中恢复。'); }
  catch (e) { setMsg(`隐藏失败：${describeError(e)}`, 'error'); }
  finally { delete retrying[r.id]; }
  await afterMutation();
}
async function unhideRecord(r) {
  if (!r?.id || recordBusy(r)) return
  retrying[r.id] = 'unhide';
  try { showResult(await post('records_bulk', { ids: [r.id], action: 'unhide' }), '已恢复显示。'); }
  catch (e) { setMsg(`恢复显示失败：${describeError(e)}`, 'error'); }
  finally { delete retrying[r.id]; }
  await afterMutation();
}
async function clearRecords() {
  if (busy.bulk || !(await askConfirm({ title: '隐藏全部已结束任务', text: '把所有不在跟踪中的任务从列表隐藏？仅从列表隐藏，可在『已隐藏』筛选中恢复；跟踪中的任务会保留显示。', confirmText: '全部隐藏' }))) return
  busy.bulk = true;
  try {
    const res = await post('records_delete', {});
    const data = res.data || {};
    if (res.code === 0 && 'hidden' in data) setMsg(`已隐藏 ${Number(data.hidden) || 0} 条${Number(data.skipped) ? `，跟踪中的 ${Number(data.skipped)} 条保留` : ''}。可在『已隐藏』筛选中恢复。`, 'success');
    else showResult(res, '已从列表隐藏，可在『已隐藏』筛选中恢复。');
  } catch (e) { setMsg(`隐藏失败：${describeError(e)}`, 'error'); }
  finally { busy.bulk = false; }
  await afterMutation();
}
async function taskAction(r, action) {
  if (!r?.id || !hasAction(r, action) || retrying[r.id]) return
  retrying[r.id] = action;
  try { showResult(await post('task_action', { id: r.id, action }), '操作已提交。'); }
  catch (e) { setMsg(`操作失败：${describeError(e)}`, 'error'); }
  finally { delete retrying[r.id]; }
  await afterMutation();
}
const ACTION_CONFIRM = {
  stop_tracking: r => ({ title: '停止自动跟踪', text: `停止「${r.title}」的自动跟踪？已有下载与文件会保留，之后不再自动核对${r.subscription_key ? '；对应的电影订阅也不再由本插件自动获取' : ''}。`, confirmText: '停止跟踪', tone: 'danger' }),
  retry_submit: r => ({ title: '重新获取', text: `重新获取「${r.title}」？会再次提交 115 转存或离线下载，只适用于此前已明确获取失败的任务。`, confirmText: '重新获取', tone: 'danger' }),
  confirm_saved: r => ({ title: '人工确认已转存', text: `把「${r.title}」标记为已保存，并转入 MP 整理核对。仅当你已在 115 中确认文件存在时使用；标记错误会让任务停在待整理状态。`, confirmText: '确认已转存', tone: 'danger', check: '我已在 115 网盘中看到这些文件' }),
  confirm_organized: r => ({ title: '人工确认已整理', text: `把「${r.title}」标记为整理成功。适用于文件已在 Emby/Plex/Jellyfin 入库，但 MP 历史记录因标题差异过大查询不到的情况。`, confirmText: '确认已整理', tone: 'danger', check: '我已在媒体库中看到这些影片' }),
};
async function runRecordAction(r, action) {
  if (!r?.id || recordBusy(r) || !hasAction(r, action)) return
  const confirm = ACTION_CONFIRM[action];
  if (confirm && !(await askConfirm(confirm(r)))) return
  await taskAction(r, action);
}
function changeRecordsPage(value) { const target = Math.min(Math.max(1, Number(value) || 1), recordsPageCount.value); if (target === recordsPage.value && !busy.records) return; recordsPage.value = target; restartRecords(); }
function applyStatsFilter(key) {
  const media = key === 'movie' || key === 'tv' ? key : 'all';
  const filter = ['completed', 'active', 'needs_attention'].includes(key) ? key : 'all';
  recordsMedia.value = media; recordsFilter.value = filter;
  tab.value = 'records';
}
function statActive(key) {
  if (tab.value !== 'records') return false
  if (key === 'movie' || key === 'tv') return recordsMedia.value === key && recordsFilter.value === 'all'
  if (key === 'all') return recordsMedia.value === 'all' && recordsFilter.value === 'all'
  return recordsFilter.value === key && recordsMedia.value === 'all'
}

function jumpTo(which) {
  const raw = parseInt(String(jump[which] || '').trim(), 10);
  if (!Number.isFinite(raw) || raw < 1) { setMsg('请输入要跳转的页码（从 1 开始）', 'warning'); return }
  const max = which === 'search' ? pageCount.value : recordsPageCount.value;
  const target = Math.min(raw, max);
  jump[which] = '';
  if (which === 'search') changePage(target);
  else changeRecordsPage(target);
}

// ---- 插件状态与后台作业 ----
async function loadStatus() {
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/status')); if (!disposed && res.code === 0 && res.data) Object.assign(status, res.data); return res.code === 0 }
  catch (e) { setMsg(`读取插件状态失败：${describeError(e)}`, 'error'); return false }
}
const JOB_LABEL = { index: '文档索引', subscribe: '订阅同步' };
let jobLegacyPolls = 0;
function jobState(name) { const job = jobs.value[name]; return job && typeof job === 'object' ? job.state : undefined }
function jobBusy(name) { const state = jobState(name); return state === 'queued' || state === 'running' || state === 'retrying' || (name === 'index' && !!status.refreshing) }
function stopJobPoll() { if (jobTimer) { clearTimeout(jobTimer); jobTimer = null; } }
function startJobPoll() { stopJobPoll(); if (disposed || !componentActive || !pageVisible() || !watchedJobs.size) return; jobTimer = setTimeout(pollJobs, JOB_POLL_MS); }
// 排队后每 5 秒读一次 status，作业离开 queued/running 后提示结果并停止
async function pollJobs() {
  jobTimer = null;
  if (disposed || !watchedJobs.size) return
  const ok = await loadStatus();
  if (disposed) return
  for (const name of [...watchedJobs]) {
    const state = jobState(name);
    if (state === undefined) {
      // 旧后端没有 jobs 字段：只能看 refreshing，最多观察 30 秒
      jobLegacyPolls += 1;
      if ((name === 'index' && status.refreshing) || (jobLegacyPolls < 6 && ok)) continue
      watchedJobs.delete(name); continue
    }
    if (state === 'retrying') {
      // 后台会自动重试：提示一次原因，不当作失败、不停止观察
      const job = jobs.value[name] || {};
      if (job.failures !== lastRetryNotice[name]) { lastRetryNotice[name] = job.failures; setMsg(`${JOB_LABEL[name]}暂未完成（${job.msg || '稍后自动重试'}），${job.next_at ? `将于 ${formatTime(job.next_at)} ` : ''}自动重试。`, 'warning'); }
      continue
    }
    if (state === 'queued' || state === 'running' || (name === 'index' && status.refreshing)) continue
    watchedJobs.delete(name);
    const job = jobs.value[name] || {};
    if (state === 'failed') setMsg(`${JOB_LABEL[name]}失败：${job.msg || '请查看插件日志'}`, 'error');
    else setMsg(job.msg || `${JOB_LABEL[name]}已完成。`, 'success');
    if (name === 'subscribe' && tab.value === 'subscriptions') loadSubscriptions();
    emit('action');
  }
  if (watchedJobs.size) startJobPoll();
}
function watchJob(name) { watchedJobs.add(name); jobLegacyPolls = 0; startJobPoll(); }
async function loadDiagnostics() { if (busy.diagnostics) return; busy.diagnostics = true; try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/diagnostics')); if (res.code !== 0) throw new Error(res.msg || '本地诊断不可用'); diagnostics.value = res.data || {}; } catch (e) { setMsg(`本地诊断：${describeError(e)}`, 'warning'); } finally { busy.diagnostics = false; } }
// 只读拉取 MP 订阅（不提交资源），再刷新本地预演
async function fetchSubscriptions() {
  if (busy.preview || disposed) return
  busy.preview = true;
  let res = null;
  try { res = await post('subscriptions_fetch', {}); } catch (e) { setMsg(`读取 MP 订阅失败：${describeError(e)}`, 'error'); } finally { busy.preview = false; }
  if (res && res.code !== 0) setMsg(res.msg || '读取 MP 订阅失败', 'warning');
  else if (res) setMsg(res.msg || '已读取 MP 订阅', 'success');
  await loadSubscriptions();
}
async function loadSubscriptions() {
  if (busy.preview || disposed) return
  busy.preview = true;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/subscriptions_preview'));
    if (res.code !== 0) throw new Error(res.msg || '匹配预演不可用')
    const data = res.data || {};
    subscriptions.value = Array.isArray(data) ? data : data.subscriptions || data.records || [];
    const cachedAt = data.cached_at || data.updated_at;
    subscriptionCacheEmpty.value = data.cache_empty === true || (data.cache_empty === undefined && !Array.isArray(data) && !cachedAt && !subscriptions.value.length);
    subscriptionNote.value = subscriptionCacheEmpty.value ? '预演只读取本地缓存，不提交资源。' : `${data.message || data.note || data.msg || '本地预演，不提交资源'}${cachedAt ? `；订阅缓存更新于 ${formatTime(cachedAt)}` : ''}。`;
  } catch (e) { subscriptionNote.value = `匹配预演暂不可用：${describeError(e)}。没有提交资源。`; } finally { busy.preview = false; }
}
async function refreshIndex() {
  if (busy.refresh || jobBusy('index')) return
  busy.refresh = true;
  try { const res = await post('refresh_index', {}); showResult(res, '已排队刷新文档索引。'); if (res.code === 0) { await loadStatus(); watchJob('index'); } }
  catch (e) { setMsg(`刷新索引失败：${describeError(e)}`, 'error'); } finally { busy.refresh = false; }
}
async function runSubscribe() {
  if (busy.subscribe || jobBusy('subscribe')) return
  if (!(await askConfirm({ title: '同步电影订阅', text: '现在同步 MP 电影订阅并获取匹配资源？此操作可能提交 115 转存或离线下载。', confirmText: '开始同步' }))) return
  busy.subscribe = true;
  try { const res = await post('run_subscribe', {}); showResult(res, '已排队同步电影订阅。'); if (res.code === 0) { await loadStatus(); watchJob('subscribe'); } }
  catch (e) { setMsg(`订阅同步失败：${describeError(e)}`, 'error'); } finally { busy.subscribe = false; }
}

// ---- 扫码登录 ----
function stopQrTimer() { qrGeneration += 1; if (qrTimer) { clearTimeout(qrTimer); qrTimer = null; } }
function startQrTimer() { if (disposed || !componentActive || !pageVisible() || !settingsOpen.value || !qrSessionId.value || qrTimer) return; const generation = qrGeneration; qrTimer = setTimeout(async () => { qrTimer = null; await checkQr(true); if (generation === qrGeneration) startQrTimer(); }, 3000); }
function qrInvalid(text) { stopQrTimer(); qrSessionId.value = ''; qrImage.value = ''; qrTip.value = text; setMsg(text, 'warning'); }
async function startQr(silent = false) {
  if (busy.qr || busy.check || disposed) return
  busy.qr = true; stopQrTimer(); const generation = qrGeneration; qrSessionId.value = ''; qrImage.value = '';
  if (silent !== true) setMsg('正在生成腾讯文档登录二维码，请稍候。');
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_start', { params: { force: true }, timeout: 180000 })); if (generation !== qrGeneration || disposed) return; const data = res.data || {}; if (res.code === 0 && data.state === 'confirmed') await qrConfirmed(); else if (res.code === 0 && data.qr_base64 && data.session_id) { qrSessionId.value = data.session_id; qrImage.value = data.qr_base64; qrTip.value = '等待扫码'; setMsg('二维码已生成，请用微信扫码。'); startQrTimer(); } else setMsg(res.msg || '获取二维码失败', 'error'); } catch (e) { setMsg(`获取二维码失败：${describeError(e)}`, 'error'); } finally { busy.qr = false; }
}
const QR_STATES = { wait: '等待扫码', scanned: '已扫描，请在手机上确认', expired: '二维码已过期，请重新获取', failed: '登录失败，请重新获取二维码', error: '登录检查失败，请重新获取二维码' };
async function checkQr(silent = false) {
  if (busy.check || busy.qr || !qrSessionId.value || disposed) return
  busy.check = true; const generation = qrGeneration, sessionId = qrSessionId.value;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_status', { params: { session_id: sessionId }, timeout: 30000 }));
    if (generation !== qrGeneration || disposed) return
    const data = res.data || {};
    // 先看 data.state：失效时后端 code=1 且 state 为 expired/error
    if (data.state === 'confirmed' && res.code === 0) { await qrConfirmed(); return }
    if (['expired', 'failed', 'error'].includes(data.state)) { qrInvalid(QR_STATES[data.state]); return }
    if (res.code !== 0) { qrInvalid(res.msg ? `${res.msg}，请重新获取二维码` : QR_STATES.error); return }
    if (data.qr_base64) qrImage.value = data.qr_base64;
    qrTip.value = QR_STATES[data.state] || '等待扫码';
    if (silent !== true) setMsg(qrTip.value);
  } catch (e) { if (silent !== true) setMsg(`扫码检查失败：${describeError(e)}`, 'error'); } finally { busy.check = false; }
}
async function qrConfirmed() { stopQrTimer(); qrSessionId.value = ''; qrImage.value = ''; setMsg('腾讯文档登录成功，Cookie 已保存。', 'success'); await loadStatus(); }

// ---- 搜索与获取 ----
function onSearchKey(e) { if (e?.isComposing || e?.keyCode === 229) return; doSearch(); }
async function doSearch() { if (status.enabled === false) { setMsg('插件已停用，请先在「设置」中启用。', 'warning'); return } const kw = (keyword.value || '').trim(); if (!kw) { setMsg('请输入影视名称', 'warning'); return } abortSearch(); await searchPage(kw, 1, true); }
function changePage(value) { const target = Math.min(Math.max(1, Number(value) || 1), pageCount.value); if (searchedKeyword.value && !busy.search) searchPage(searchedKeyword.value, target); }
async function searchPage(kw, requestedPage, fresh = false) {
  searchController?.abort(); const controller = typeof AbortController === 'function' ? new AbortController() : null; searchController = controller;
  const serial = ++searchSerial; searchedKeyword.value = kw; busy.search = true; searched.value = true;
  // 翻页保留旧结果，只显示进度条；新关键词才清空
  if (fresh) { results.value = []; total.value = 0; resultVersion.value = ''; }
  const payload = { keyword: kw, media_type: filterType.value, quality: filterQuality.value, subtitle: filterSubtitle.value, link_kind: filterLink.value, page: requestedPage, page_size: pageSize };
  if (sortBy.value !== 'relevance') payload.sort = sortBy.value;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/search', payload, { timeout: 30000, signal: controller?.signal }));
    if (serial !== searchSerial || disposed) return
    if (res.code !== 0) throw new Error(res.msg || '搜索失败')
    const data = res.data || {}; if (!Array.isArray(data.records) || !data.index_version) throw new Error('搜索响应缺少有效索引版本')
    results.value = data.records; total.value = Number(data.total) || 0; page.value = Number(data.page) || requestedPage; resultVersion.value = data.index_version;
    if (fresh) setMsg(`「${kw}」符合筛选的结果共 ${total.value} 条`);
  } catch (e) { if (serial === searchSerial && !disposed && !isAbort(e)) setMsg(`搜索失败：${describeError(e)}`, 'error'); }
  finally { if (serial === searchSerial) { busy.search = false; searchController = null; } }
}
function sourceOptions(rec) { return (rec?.links || []).map((link, index) => ({ value: String(index), kind: link.kind, label: `${linkName(link.kind)} · ${shortUrl(link.url)}` })).filter(o => ['115_share', 'magnet', 'ed2k'].includes(o.kind)) }
// quick=true：卡片上只有一个来源时的「一键获取」，仍弹确认框，但来源与目录已预选
function prepareTransfer(rec, quick = false) {
  if (!rec?.record_id || busy.search || transferring[rec.record_id] || rec.bundle || rec.sheet_bundle || rec.no_link) return
  const options = sourceOptions(rec); if (!options.length) { setMsg('此条目没有可获取的链接', 'warning'); return }
  transferRecord.value = rec; transferIndexVersion.value = resultVersion.value; transferTarget.value = rec.media_type === 'tv' ? 'tv' : 'movie';
  const selectedKind = filterLink.value === 'share' ? '115_share' : filterLink.value;
  transferSource.value = (options.find(o => o.kind === selectedKind) || options[0]).value;
  transferQuick.value = quick === true && options.length === 1;
  transferOpen.value = true;
}
async function confirmTransfer() { const rec = transferRecord.value; const index = Number(transferSource.value); if (!rec || !Number.isInteger(index) || !rec.links?.[index]) return; if (transferIndexVersion.value !== resultVersion.value) { setMsg('搜索索引已变化，请重新选择来源与目录。', 'warning'); transferOpen.value = false; return } await transfer(rec, transferTarget.value, index); transferOpen.value = false; }
async function transfer(rec, to, sourceIndex) {
  if (!rec?.record_id || !resultVersion.value || busy.search || transferring[rec.record_id]) return
  const payload = { record_id: rec.record_id, index_version: resultVersion.value, to };
  if (sourceIndex !== undefined) { if (!Number.isInteger(sourceIndex) || !['115_share', 'magnet', 'ed2k'].includes(rec.links?.[sourceIndex]?.kind)) { setMsg('所选来源已经失效，请重新搜索', 'warning'); return } payload.link_kind = rec.links[sourceIndex].kind; payload.link_index = sourceIndex; }
  transferring[rec.record_id] = true;
  try { showResult(unwrap(await props.api.post('plugin/Doc115Subscribe/transfer', payload, { timeout: 30000 })), '获取请求已受理，请到任务页查看进度。'); } catch (e) { setMsg(`获取请求失败：${describeError(e)}。提交结果请先查看任务，避免重复获取。`, 'error'); }
  finally { delete transferring[rec.record_id]; emit('action'); }
}
function updateNarrow() { narrow.value = !!mediaQuery?.matches; }

watch([filterType, filterQuality, filterSubtitle, filterLink, sortBy], () => { savePrefs(); if (!searchedKeyword.value || disposed) return; searchSerial += 1; abortSearch(); busy.search = true; searchDebounce = setTimeout(() => { searchDebounce = null; if (!disposed) searchPage(searchedKeyword.value, 1); }, 220); });
watch(tab, value => { stopRecTimer(); clearMsg(); if (value === 'records') loadRecords(); else if (value === 'subscriptions') loadSubscriptions(); });
watch([recordsFilter, recordsMedia], () => { recordsPage.value = 1; for (const id of Object.keys(selected)) delete selected[id]; if (tab.value === 'records') restartRecords(); });
watch(recordsQuery, () => { if (recQueryTimer) clearTimeout(recQueryTimer); recQueryTimer = setTimeout(() => { recQueryTimer = null; recordsPage.value = 1; if (!disposed && tab.value === 'records') restartRecords(); }, RECORDS_QUERY_DEBOUNCE); });
watch(settingsOpen, value => { stopQrTimer(); clearMsg(); if (value) { stopRecTimer(); if (pageVisible()) startQrTimer(); } else if (tab.value === 'records') loadRecords(); });
function startWatchingRunningJobs() { for (const name of ['index', 'subscribe']) if (jobBusy(name)) watchedJobs.add(name); if (watchedJobs.size) startJobPoll(); }
onMounted(async () => {
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visibilityChanged);
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') { mediaQuery = window.matchMedia('(max-width: 599px)'); updateNarrow(); mediaQuery.addEventListener?.('change', updateNarrow); }
  if (tab.value === 'records') loadRecords(); else if (tab.value === 'subscriptions') loadSubscriptions();
  await loadStatus();
  startWatchingRunningJobs();
});
onActivated(() => { disposed = false; componentActive = true; visibilityChanged(); loadStatus().then(startWatchingRunningJobs); });
onDeactivated(() => { componentActive = false; pause(); });
onBeforeUnmount(dispose);

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_progress_linear = _resolveComponent("v-progress-linear");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_chip_group = _resolveComponent("v-chip-group");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_pagination = _resolveComponent("v-pagination");
  const _component_v_dialog = _resolveComponent("v-dialog");

  return (_openBlock(), _createElementBlock("section", {
    class: "doc115-page",
    "data-doc115-theme": darkTheme.value ? 'dark' : 'light',
    "aria-label": "115文档订阅与查询"
  }, [
    _createElementVNode("header", _hoisted_2, [
      _createElementVNode("div", _hoisted_3, [
        _cache[26] || (_cache[26] = _createElementVNode("h2", null, "115文档订阅与查询", -1)),
        _createElementVNode("p", _hoisted_4, _toDisplayString(indexSummary.value), 1)
      ]),
      _createElementVNode("div", _hoisted_5, [
        _createVNode(_component_v_btn, {
          variant: "text",
          size: "small",
          "prepend-icon": settingsOpen.value ? 'mdi-arrow-left' : 'mdi-cog-outline',
          "aria-pressed": settingsOpen.value ? 'true' : 'false',
          onClick: _cache[0] || (_cache[0] = $event => (settingsOpen.value = !settingsOpen.value))
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(settingsOpen.value ? '返回' : '设置'), 1)
          ]),
          _: 1
        }, 8, ["prepend-icon", "aria-pressed"]),
        _createVNode(_component_v_btn, {
          icon: "",
          size: "small",
          variant: "text",
          title: "关闭",
          "aria-label": "关闭插件页面",
          onClick: close
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_icon, null, {
              default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                _createTextVNode("mdi-close", -1)
              ]))]),
              _: 1
            })
          ]),
          _: 1
        })
      ])
    ]),
    (msg.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: msgType.value,
          variant: "tonal",
          density: "comfortable",
          class: "doc115-feedback",
          role: "status",
          closable: "",
          "onClick:close": clearMsg
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(msg.value), 1)
          ]),
          _: 1
        }, 8, ["type"]))
      : _createCommentVNode("", true),
    (status.version && status.version !== _unref(UI_BUILD))
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 1,
          type: "warning",
          variant: "tonal",
          density: "compact",
          class: "doc115-feedback"
        }, {
          default: _withCtx(() => [
            _createTextVNode("前端 v" + _toDisplayString(_unref(UI_BUILD)) + " 与后端 v" + _toDisplayString(status.version) + " 不一致，请重新打开插件页面；仍不一致时请检查插件更新是否完成。", 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (indexWarnings.value.length)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 2,
          type: "warning",
          variant: "tonal",
          density: "compact",
          class: "doc115-feedback"
        }, {
          default: _withCtx(() => [
            _createTextVNode("部分索引尚未更新：" + _toDisplayString(indexWarnings.value.join('；')), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(runningJobs.value, (job) => {
      return (_openBlock(), _createElementBlock("div", {
        key: job.name,
        class: "doc115-job",
        role: "status"
      }, [
        _createElementVNode("span", _hoisted_6, _toDisplayString(job.label), 1),
        _createVNode(_component_v_progress_linear, {
          indeterminate: "",
          color: "primary",
          height: "4",
          rounded: ""
        })
      ]))
    }), 128)),
    (!settingsOpen.value && stats.value.total)
      ? (_openBlock(), _createElementBlock("div", _hoisted_7, [
          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(statsItems.value, (item) => {
            return (_openBlock(), _createElementBlock("button", {
              key: item.key,
              type: "button",
              class: _normalizeClass(["doc115-stat", [item.color, { 'doc115-stat-active': statActive(item.key) }]]),
              "aria-pressed": statActive(item.key) ? 'true' : 'false',
              onClick: $event => (applyStatsFilter(item.key))
            }, [
              _createElementVNode("strong", null, _toDisplayString(item.value), 1),
              _createElementVNode("span", null, _toDisplayString(item.label), 1)
            ], 10, _hoisted_8))
          }), 128))
        ]))
      : _createCommentVNode("", true),
    (settingsOpen.value)
      ? (_openBlock(), _createElementBlock("section", _hoisted_9, [
          _createVNode(Config, {
            api: __props.api,
            model: __props.model,
            embedded: "",
            "backend-version": status.version,
            onAction: loadStatus,
            onClose: _cache[3] || (_cache[3] = $event => (settingsOpen.value = false))
          }, {
            tencent: _withCtx(() => [
              _createElementVNode("p", _hoisted_10, [
                _cache[28] || (_cache[28] = _createTextVNode("登录状态：", -1)),
                _createElementVNode("span", {
                  class: _normalizeClass(status.cookie_ready ? 'doc115-green' : 'doc115-amber')
                }, _toDisplayString(cookieText.value), 3),
                _createTextVNode(" · 索引更新于 " + _toDisplayString(status.built_at_text || '尚未建立'), 1)
              ]),
              _createElementVNode("div", _hoisted_11, [
                _createVNode(_component_v_btn, {
                  size: "small",
                  variant: "outlined",
                  loading: busy.qr,
                  disabled: busy.check,
                  "prepend-icon": "mdi-qrcode",
                  onClick: _cache[1] || (_cache[1] = $event => (startQr()))
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(qrImage.value ? '换一张二维码' : '扫码登录腾讯文档'), 1)
                  ]),
                  _: 1
                }, 8, ["loading", "disabled"]),
                (qrSessionId.value)
                  ? (_openBlock(), _createBlock(_component_v_btn, {
                      key: 0,
                      size: "small",
                      variant: "text",
                      loading: busy.check,
                      disabled: busy.qr,
                      onClick: _cache[2] || (_cache[2] = $event => (checkQr()))
                    }, {
                      default: _withCtx(() => [...(_cache[29] || (_cache[29] = [
                        _createTextVNode("检查扫码状态", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading", "disabled"]))
                  : _createCommentVNode("", true),
                _createVNode(_component_v_btn, {
                  size: "small",
                  variant: "outlined",
                  "prepend-icon": "mdi-refresh",
                  loading: busy.refresh,
                  disabled: jobBusy('index') || status.enabled === false,
                  onClick: refreshIndex
                }, {
                  default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
                    _createTextVNode("刷新文档索引", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading", "disabled"])
              ]),
              (qrImage.value)
                ? (_openBlock(), _createElementBlock("div", _hoisted_12, [
                    _createElementVNode("img", {
                      src: qrImage.value,
                      alt: "微信扫码登录腾讯文档"
                    }, null, 8, _hoisted_13),
                    _createElementVNode("p", null, _toDisplayString(qrTip.value), 1),
                    _cache[31] || (_cache[31] = _createElementVNode("p", { class: "doc115-muted doc115-small" }, "只扫描当前二维码；离开设置后停止检查扫码状态。", -1))
                  ]))
                : _createCommentVNode("", true)
            ]),
            advanced: _withCtx(() => [
              _createElementVNode("div", _hoisted_14, [
                _createVNode(_component_v_btn, {
                  size: "small",
                  variant: "text",
                  "prepend-icon": "mdi-stethoscope",
                  loading: busy.diagnostics,
                  onClick: loadDiagnostics
                }, {
                  default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
                    _createTextVNode("查看本地诊断", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"])
              ]),
              (diagnostics.value)
                ? (_openBlock(), _createElementBlock("div", _hoisted_15, [
                    _createElementVNode("p", null, _toDisplayString(diagnosticText.value), 1),
                    _cache[33] || (_cache[33] = _createElementVNode("p", { class: "doc115-muted doc115-small" }, "只读取本插件状态，不测试真实转存。", -1))
                  ]))
                : _createCommentVNode("", true)
            ]),
            _: 1
          }, 8, ["api", "model", "backend-version"])
        ]))
      : (_openBlock(), _createElementBlock(_Fragment, { key: 5 }, [
          _createElementVNode("nav", _hoisted_16, [
            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(tabs, (item) => {
              return _createElementVNode("button", {
                key: item.value,
                type: "button",
                class: _normalizeClass({ 'doc115-tab-active': tab.value === item.value }),
                "aria-current": tab.value === item.value ? 'page' : undefined,
                onClick: $event => (tab.value = item.value)
              }, _toDisplayString(item.label), 11, _hoisted_17)
            }), 64))
          ]),
          (tab.value === 'search')
            ? (_openBlock(), _createElementBlock("section", _hoisted_18, [
                (status.enabled === false)
                  ? (_openBlock(), _createBlock(_component_v_alert, {
                      key: 0,
                      type: "info",
                      variant: "tonal",
                      density: "compact",
                      class: "doc115-feedback"
                    }, {
                      default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
                        _createTextVNode("插件已停用，搜索暂不可用。请在「设置」中启用插件。", -1)
                      ]))]),
                      _: 1
                    }))
                  : _createCommentVNode("", true),
                _createElementVNode("div", _hoisted_19, [
                  _createVNode(_component_v_text_field, {
                    modelValue: keyword.value,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((keyword).value = $event)),
                    label: "影视名称（跨全部工作表）",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": "",
                    clearable: "",
                    disabled: status.enabled === false,
                    onKeydown: _withKeys(onSearchKey, ["enter"])
                  }, null, 8, ["modelValue", "disabled"]),
                  _createVNode(_component_v_btn, {
                    color: "primary",
                    "prepend-icon": "mdi-magnify",
                    loading: busy.search,
                    disabled: status.enabled === false,
                    onClick: doSearch
                  }, {
                    default: _withCtx(() => [...(_cache[35] || (_cache[35] = [
                      _createTextVNode("搜索", -1)
                    ]))]),
                    _: 1
                  }, 8, ["loading", "disabled"])
                ]),
                _createElementVNode("div", _hoisted_20, [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(searchFilterGroups, (group) => {
                    return _createElementVNode("div", {
                      key: group.key,
                      class: "doc115-filter-row"
                    }, [
                      _createElementVNode("span", {
                        class: "doc115-filter-label",
                        id: 'doc115-f-' + group.key
                      }, _toDisplayString(group.label), 9, _hoisted_21),
                      _createVNode(_component_v_chip_group, {
                        modelValue: searchFilters[group.key],
                        "onUpdate:modelValue": $event => ((searchFilters[group.key]) = $event),
                        mandatory: "",
                        "selected-class": "doc115-chip-on",
                        "aria-labelledby": 'doc115-f-' + group.key
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(group.options, (option) => {
                            return (_openBlock(), _createBlock(_component_v_chip, {
                              key: option.value,
                              value: option.value,
                              size: "small",
                              variant: "outlined",
                              filter: ""
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(option.label), 1)
                              ]),
                              _: 2
                            }, 1032, ["value"]))
                          }), 128))
                        ]),
                        _: 2
                      }, 1032, ["modelValue", "onUpdate:modelValue", "aria-labelledby"])
                    ])
                  }), 64)),
                  _createElementVNode("div", _hoisted_22, [
                    _cache[36] || (_cache[36] = _createElementVNode("span", { class: "doc115-filter-label" }, "排序", -1)),
                    _createVNode(_component_v_select, {
                      modelValue: sortBy.value,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((sortBy).value = $event)),
                      items: sortOptions,
                      density: "compact",
                      variant: "outlined",
                      "hide-details": "",
                      class: "doc115-sort",
                      "aria-label": "结果排序"
                    }, null, 8, ["modelValue"])
                  ])
                ]),
                (searched.value)
                  ? (_openBlock(), _createElementBlock("section", {
                      key: 1,
                      class: "doc115-panel",
                      "aria-busy": busy.search ? 'true' : 'false'
                    }, [
                      _createElementVNode("div", _hoisted_24, [
                        _createElementVNode("h3", null, "「" + _toDisplayString(searchedKeyword.value) + "」", 1),
                        _createElementVNode("span", _hoisted_25, "共 " + _toDisplayString(total.value) + " 条", 1)
                      ]),
                      _cache[43] || (_cache[43] = _createElementVNode("p", { class: "doc115-muted doc115-small" }, "来源筛选表示条目包含此类链接；获取前会确认本次实际使用的来源和保存目录。", -1)),
                      (busy.search)
                        ? (_openBlock(), _createBlock(_component_v_progress_linear, {
                            key: 0,
                            indeterminate: "",
                            color: "primary",
                            class: "mb-2"
                          }))
                        : _createCommentVNode("", true),
                      (!busy.search && !results.value.length)
                        ? (_openBlock(), _createElementBlock("p", _hoisted_26, "没有匹配资源。试试更短的关键词，或放宽上方筛选。"))
                        : _createCommentVNode("", true),
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(results.value, (r) => {
                        return (_openBlock(), _createElementBlock("article", {
                          key: r.record_id,
                          class: _normalizeClass(["doc115-resource-card", { 'doc115-stale': busy.search }])
                        }, [
                          _createElementVNode("h3", _hoisted_27, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(highlightParts(r.title, r.match), (part, i) => {
                              return (_openBlock(), _createElementBlock(_Fragment, { key: i }, [
                                (part.hit)
                                  ? (_openBlock(), _createElementBlock("mark", _hoisted_28, _toDisplayString(part.text), 1))
                                  : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                      _createTextVNode(_toDisplayString(part.text), 1)
                                    ], 64))
                              ], 64))
                            }), 128)),
                            _cache[37] || (_cache[37] = _createTextVNode()),
                            (r.year)
                              ? (_openBlock(), _createElementBlock("span", _hoisted_29, "（" + _toDisplayString(r.year) + "）", 1))
                              : _createCommentVNode("", true)
                          ]),
                          _createElementVNode("div", _hoisted_30, [
                            _createElementVNode("span", {
                              class: _normalizeClass(["doc115-chip", r.media_type === 'movie' ? 'doc115-purple' : 'doc115-blue'])
                            }, _toDisplayString(mediaTypeName(r.media_type)), 3),
                            (r.bundle)
                              ? (_openBlock(), _createElementBlock("span", _hoisted_31, "大包链接"))
                              : _createCommentVNode("", true),
                            _createElementVNode("span", _hoisted_32, "来源：" + _toDisplayString(r.sheet || '文档'), 1),
                            (r.tmdbid)
                              ? (_openBlock(), _createElementBlock("span", _hoisted_33, "TMDB " + _toDisplayString(r.tmdbid), 1))
                              : _createCommentVNode("", true)
                          ]),
                          _createElementVNode("p", _hoisted_34, [
                            _cache[38] || (_cache[38] = _createElementVNode("span", { class: "doc115-muted" }, "规格：", -1)),
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(specTokens(r.qtext), (token, i) => {
                              return (_openBlock(), _createElementBlock("span", {
                                key: i,
                                class: _normalizeClass(token.color || 'doc115-muted')
                              }, _toDisplayString(token.text), 3))
                            }), 128))
                          ]),
                          _createElementVNode("div", _hoisted_35, [
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(r.links || [], (link, i) => {
                              return (_openBlock(), _createElementBlock("a", {
                                key: i,
                                class: _normalizeClass(["doc115-chip", linkColor(link.kind)]),
                                href: linkHref(link.url),
                                target: "_blank",
                                rel: "noopener noreferrer"
                              }, [
                                _createVNode(_component_v_icon, { size: "small" }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(linkIcon(link.kind)), 1)
                                  ]),
                                  _: 2
                                }, 1024),
                                _createTextVNode(_toDisplayString(linkName(link.kind)) + " · " + _toDisplayString(shortUrl(link.url)), 1)
                              ], 10, _hoisted_36))
                            }), 128))
                          ]),
                          _createElementVNode("div", _hoisted_37, [
                            (r.sheet_bundle || r.no_link || r.bundle)
                              ? (_openBlock(), _createElementBlock("p", _hoisted_38, _toDisplayString(r.no_link ? '此条目只提供文档，请打开上方链接查看。' : '此条目是大包，不提供一键获取，请打开原链接确认范围。'), 1))
                              : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                  _createElementVNode("p", _hoisted_39, "默认保存到" + _toDisplayString(mediaTypeName(r.media_type === 'tv' ? 'tv' : 'movie')) + "目录，确认前可修改。", 1),
                                  (sourceOptions(r).length === 1)
                                    ? (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 0,
                                        size: "small",
                                        variant: "flat",
                                        class: "doc115-cta",
                                        "prepend-icon": "mdi-download",
                                        disabled: busy.search || !r.record_id || !!transferring[r.record_id],
                                        loading: !!transferring[r.record_id],
                                        onClick: $event => (prepareTransfer(r, true))
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode("一键获取（" + _toDisplayString(linkName(sourceOptions(r)[0].kind)) + "）", 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["disabled", "loading", "onClick"]))
                                    : (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 1,
                                        size: "small",
                                        variant: "flat",
                                        class: "doc115-cta",
                                        "prepend-icon": "mdi-download",
                                        disabled: busy.search || !r.record_id || !!transferring[r.record_id],
                                        loading: !!transferring[r.record_id],
                                        onClick: $event => (prepareTransfer(r))
                                      }, {
                                        default: _withCtx(() => [...(_cache[39] || (_cache[39] = [
                                          _createTextVNode("选择来源与保存目录", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["disabled", "loading", "onClick"]))
                                ], 64))
                          ])
                        ], 2))
                      }), 128)),
                      (total.value > 0 && pageCount.value > 1)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_40, [
                            _createElementVNode("span", _hoisted_41, "第 " + _toDisplayString(page.value) + " / " + _toDisplayString(pageCount.value) + " 页", 1),
                            _createVNode(_component_v_pagination, {
                              "model-value": page.value,
                              length: pageCount.value,
                              disabled: busy.search,
                              "total-visible": narrow.value ? 1 : 5,
                              density: "comfortable",
                              size: "small",
                              "onUpdate:modelValue": changePage
                            }, null, 8, ["model-value", "length", "disabled", "total-visible"]),
                            _createElementVNode("span", _hoisted_42, [
                              _cache[41] || (_cache[41] = _createElementVNode("label", { for: 'doc115-jump-search' }, "跳至", -1)),
                              _withDirectives(_createElementVNode("input", {
                                id: "doc115-jump-search",
                                class: "doc115-jump",
                                type: "number",
                                min: "1",
                                max: pageCount.value,
                                "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((jump.search) = $event)),
                                "aria-label": "搜索结果跳转页码",
                                onKeydown: _cache[7] || (_cache[7] = _withKeys($event => (jumpTo('search')), ["enter"]))
                              }, null, 40, _hoisted_43), [
                                [_vModelText, jump.search]
                              ]),
                              _cache[42] || (_cache[42] = _createTextVNode("页", -1)),
                              _createVNode(_component_v_btn, {
                                size: "x-small",
                                variant: "text",
                                disabled: busy.search,
                                onClick: _cache[8] || (_cache[8] = $event => (jumpTo('search')))
                              }, {
                                default: _withCtx(() => [...(_cache[40] || (_cache[40] = [
                                  _createTextVNode("跳转", -1)
                                ]))]),
                                _: 1
                              }, 8, ["disabled"])
                            ])
                          ]))
                        : _createCommentVNode("", true)
                    ], 8, _hoisted_23))
                  : _createCommentVNode("", true)
              ]))
            : (tab.value === 'subscriptions')
              ? (_openBlock(), _createElementBlock("section", _hoisted_44, [
                  _createElementVNode("div", _hoisted_45, [
                    _cache[44] || (_cache[44] = _createElementVNode("h3", null, "电影订阅", -1)),
                    _createElementVNode("span", {
                      class: _normalizeClass(["doc115-chip", status.subscribe_enabled ? 'doc115-green' : 'doc115-neutral'])
                    }, _toDisplayString(status.subscribe_enabled ? '自动同步已启用' : '自动同步已关闭'), 3)
                  ]),
                  _cache[48] || (_cache[48] = _createElementVNode("p", { class: "doc115-muted doc115-small" }, "按已缓存的 MP 电影订阅预演文档匹配结果，不提交资源。订阅的创建、编辑和整理由 MP 处理。", -1)),
                  _createElementVNode("div", _hoisted_46, [
                    _createVNode(_component_v_btn, {
                      variant: "outlined",
                      size: "small",
                      "prepend-icon": "mdi-eye-outline",
                      loading: busy.preview,
                      disabled: status.enabled === false,
                      onClick: fetchSubscriptions
                    }, {
                      default: _withCtx(() => [...(_cache[45] || (_cache[45] = [
                        _createTextVNode("读取 MP 订阅并预演", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading", "disabled"]),
                    _createVNode(_component_v_btn, {
                      variant: "outlined",
                      size: "small",
                      "prepend-icon": "mdi-sync",
                      loading: busy.subscribe,
                      disabled: status.enabled === false || !status.subscribe_enabled || jobBusy('subscribe'),
                      onClick: runSubscribe
                    }, {
                      default: _withCtx(() => [...(_cache[46] || (_cache[46] = [
                        _createTextVNode("同步并获取匹配资源", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading", "disabled"])
                  ]),
                  (status.last_subscribe)
                    ? (_openBlock(), _createElementBlock("p", {
                        key: 0,
                        class: _normalizeClass(["doc115-small", status.last_subscribe.success === false ? 'doc115-red' : 'doc115-muted'])
                      }, "最近同步：" + _toDisplayString(status.last_subscribe.msg || status.last_subscribe.error || '已完成'), 3))
                    : _createCommentVNode("", true),
                  _createElementVNode("p", _hoisted_47, _toDisplayString(subscriptionNote.value), 1),
                  (subscriptionNextAt.value)
                    ? (_openBlock(), _createElementBlock("p", _hoisted_48, "下次自动同步：" + _toDisplayString(formatTime(subscriptionNextAt.value)), 1))
                    : _createCommentVNode("", true),
                  (subscriptionCacheEmpty.value)
                    ? (_openBlock(), _createElementBlock("p", _hoisted_49, "还没有读取过 MP 订阅。点「读取 MP 订阅并预演」只读查看匹配结果，不会提交资源。"))
                    : (!busy.preview && !subscriptions.value.length)
                      ? (_openBlock(), _createElementBlock("p", _hoisted_50, "MP 中暂无电影订阅。"))
                      : _createCommentVNode("", true),
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(subscriptions.value, (s, i) => {
                    return (_openBlock(), _createElementBlock("article", {
                      key: s.id || i,
                      class: "doc115-resource-card doc115-sub-card"
                    }, [
                      _createElementVNode("h3", _hoisted_51, [
                        _createTextVNode(_toDisplayString(s.title || s.name || '电影订阅') + " ", 1),
                        (s.year)
                          ? (_openBlock(), _createElementBlock("span", _hoisted_52, "（" + _toDisplayString(s.year) + "）", 1))
                          : _createCommentVNode("", true)
                      ]),
                      _createElementVNode("p", {
                        class: _normalizeClass(Number(s.matched) > 0 ? 'doc115-green' : 'doc115-amber')
                      }, [
                        _createTextVNode(_toDisplayString(s.reason || s.message || (Number(s.matched) > 0 ? '匹配到可用资源' : '当前没有匹配资源')), 1),
                        (Number(s.matched) > 0)
                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                              _createTextVNode(" · " + _toDisplayString(s.matched) + " 条可用", 1)
                            ], 64))
                          : _createCommentVNode("", true)
                      ], 2),
                      (s.qtext)
                        ? (_openBlock(), _createElementBlock("p", _hoisted_53, [
                            _cache[47] || (_cache[47] = _createElementVNode("span", { class: "doc115-muted" }, "候选规格：", -1)),
                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(specTokens(s.qtext), (token, j) => {
                              return (_openBlock(), _createElementBlock("span", {
                                key: j,
                                class: _normalizeClass(token.color || 'doc115-muted')
                              }, _toDisplayString(token.text), 3))
                            }), 128))
                          ]))
                        : _createCommentVNode("", true)
                    ]))
                  }), 128))
                ]))
              : (_openBlock(), _createElementBlock("section", {
                  key: 2,
                  class: "doc115-panel",
                  "aria-label": "任务记录",
                  "aria-busy": busy.records ? 'true' : 'false'
                }, [
                  _createElementVNode("div", _hoisted_55, [
                    _cache[50] || (_cache[50] = _createElementVNode("h3", null, "任务", -1)),
                    _createElementVNode("span", _hoisted_56, _toDisplayString(recordsTotal.value) + " 条", 1),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      variant: "text",
                      "prepend-icon": "mdi-refresh",
                      loading: busy.records,
                      onClick: loadRecords
                    }, {
                      default: _withCtx(() => [...(_cache[49] || (_cache[49] = [
                        _createTextVNode("刷新状态", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"])
                  ]),
                  _createElementVNode("div", _hoisted_57, [
                    _createElementVNode("div", _hoisted_58, [
                      _cache[51] || (_cache[51] = _createElementVNode("span", {
                        id: "doc115-rf-scope",
                        class: "doc115-filter-label"
                      }, "范围", -1)),
                      _createVNode(_component_v_chip_group, {
                        modelValue: recordsFilter.value,
                        "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((recordsFilter).value = $event)),
                        mandatory: "",
                        "selected-class": "doc115-chip-on",
                        "aria-labelledby": "doc115-rf-scope"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(), _createElementBlock(_Fragment, null, _renderList(recordFilterOptions, (option) => {
                            return _createVNode(_component_v_chip, {
                              key: option.value,
                              value: option.value,
                              size: "small",
                              variant: "outlined",
                              filter: ""
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(option.label), 1)
                              ]),
                              _: 2
                            }, 1032, ["value"])
                          }), 64))
                        ]),
                        _: 1
                      }, 8, ["modelValue"])
                    ]),
                    _createElementVNode("div", _hoisted_59, [
                      _cache[52] || (_cache[52] = _createElementVNode("span", {
                        id: "doc115-rf-media",
                        class: "doc115-filter-label"
                      }, "类型", -1)),
                      _createVNode(_component_v_chip_group, {
                        modelValue: recordsMedia.value,
                        "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((recordsMedia).value = $event)),
                        mandatory: "",
                        "selected-class": "doc115-chip-on",
                        "aria-labelledby": "doc115-rf-media"
                      }, {
                        default: _withCtx(() => [
                          (_openBlock(), _createElementBlock(_Fragment, null, _renderList(mediaOptions, (option) => {
                            return _createVNode(_component_v_chip, {
                              key: option.value,
                              value: option.value,
                              size: "small",
                              variant: "outlined",
                              filter: ""
                            }, {
                              default: _withCtx(() => [
                                _createTextVNode(_toDisplayString(option.label), 1)
                              ]),
                              _: 2
                            }, 1032, ["value"])
                          }), 64))
                        ]),
                        _: 1
                      }, 8, ["modelValue"])
                    ]),
                    _createVNode(_component_v_text_field, {
                      modelValue: recordsQuery.value,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((recordsQuery).value = $event)),
                      label: "按标题查找任务",
                      "prepend-inner-icon": "mdi-magnify",
                      variant: "outlined",
                      density: "compact",
                      "hide-details": "",
                      clearable: "",
                      class: "doc115-records-q"
                    }, null, 8, ["modelValue"])
                  ]),
                  _cache[70] || (_cache[70] = _createElementVNode("p", { class: "doc115-muted doc115-small" }, "刷新只读取本地任务。获取、搬运与 MP 整理分别确认；MP 整理成功不代表媒体服务器已收录。", -1)),
                  (busy.records)
                    ? (_openBlock(), _createBlock(_component_v_progress_linear, {
                        key: 0,
                        indeterminate: "",
                        color: "primary",
                        class: "mb-2"
                      }))
                    : _createCommentVNode("", true),
                  (records.value.length)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_60, [
                        _createElementVNode("label", _hoisted_61, [
                          _createElementVNode("input", {
                            type: "checkbox",
                            checked: allSelected.value,
                            ".indeterminate": someSelected.value && !allSelected.value,
                            "aria-label": "全选本页任务",
                            onChange: _cache[12] || (_cache[12] = $event => (toggleAll($event.target.checked)))
                          }, null, 40, _hoisted_62),
                          _cache[53] || (_cache[53] = _createTextVNode(" 全选本页", -1))
                        ]),
                        _createElementVNode("span", _hoisted_63, _toDisplayString(selectedIds.value.length ? `已选 ${selectedIds.value.length} 条` : '勾选任务后可批量处理'), 1),
                        (selectedIds.value.length)
                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                              _createVNode(_component_v_btn, {
                                size: "small",
                                variant: "text",
                                loading: busy.bulk,
                                disabled: busy.bulk,
                                onClick: _cache[13] || (_cache[13] = $event => (bulkAction('verify')))
                              }, {
                                default: _withCtx(() => [...(_cache[54] || (_cache[54] = [
                                  _createTextVNode("核对整理", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading", "disabled"]),
                              (recordsFilter.value !== 'hidden')
                                ? (_openBlock(), _createBlock(_component_v_btn, {
                                    key: 0,
                                    size: "small",
                                    variant: "text",
                                    loading: busy.bulk,
                                    disabled: busy.bulk,
                                    onClick: _cache[14] || (_cache[14] = $event => (bulkAction('hide')))
                                  }, {
                                    default: _withCtx(() => [...(_cache[55] || (_cache[55] = [
                                      _createTextVNode("隐藏", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["loading", "disabled"]))
                                : _createCommentVNode("", true),
                              (recordsFilter.value === 'hidden' || selectedRecords.value.some(r => r.hidden))
                                ? (_openBlock(), _createBlock(_component_v_btn, {
                                    key: 1,
                                    size: "small",
                                    variant: "text",
                                    loading: busy.bulk,
                                    disabled: busy.bulk,
                                    onClick: _cache[15] || (_cache[15] = $event => (bulkAction('unhide')))
                                  }, {
                                    default: _withCtx(() => [...(_cache[56] || (_cache[56] = [
                                      _createTextVNode("恢复显示", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["loading", "disabled"]))
                                : _createCommentVNode("", true),
                              _createVNode(_component_v_btn, {
                                size: "small",
                                variant: "text",
                                loading: busy.bulk,
                                disabled: busy.bulk,
                                onClick: _cache[16] || (_cache[16] = $event => (bulkAction('stop_tracking')))
                              }, {
                                default: _withCtx(() => [...(_cache[57] || (_cache[57] = [
                                  _createTextVNode("停止跟踪", -1)
                                ]))]),
                                _: 1
                              }, 8, ["loading", "disabled"])
                            ], 64))
                          : _createCommentVNode("", true)
                      ]))
                    : _createCommentVNode("", true),
                  (!busy.records && !records.value.length)
                    ? (_openBlock(), _createElementBlock("p", _hoisted_64, _toDisplayString(recordsEmptyText.value), 1))
                    : _createCommentVNode("", true),
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(orderedRecords.value, (r) => {
                    return (_openBlock(), _createElementBlock(_Fragment, {
                      key: r.id
                    }, [
                      (isCompact(r) && !expanded[r.id])
                        ? (_openBlock(), _createElementBlock("div", {
                            key: 0,
                            class: "doc115-row",
                            style: _normalizeStyle({ '--doc115-status-color': statusCss(r) })
                          }, [
                            _createElementVNode("input", {
                              type: "checkbox",
                              class: "doc115-row-check",
                              checked: !!selected[r.id],
                              "aria-label": `选择「${r.title}」`,
                              onChange: $event => (toggleSelect(r, $event.target.checked))
                            }, null, 40, _hoisted_65),
                            _createElementVNode("button", {
                              type: "button",
                              class: "doc115-row-main",
                              "aria-expanded": 'false',
                              onClick: $event => (expanded[r.id] = true)
                            }, [
                              _createElementVNode("span", _hoisted_67, [
                                _createTextVNode(_toDisplayString(r.title), 1),
                                (r.year)
                                  ? (_openBlock(), _createElementBlock("span", _hoisted_68, "（" + _toDisplayString(r.year) + "）", 1))
                                  : _createCommentVNode("", true)
                              ]),
                              _createElementVNode("span", {
                                class: _normalizeClass(["doc115-row-type doc115-small", recordMedia(r) === 'tv' ? 'doc115-blue' : 'doc115-purple'])
                              }, _toDisplayString(mediaTypeName(recordMedia(r))), 3),
                              _createElementVNode("span", {
                                class: _normalizeClass(["doc115-row-status doc115-small", statusColor(organizationState(r))])
                              }, _toDisplayString(r.hidden ? '已隐藏 · ' : '') + _toDisplayString(organizationSummary(r)), 3),
                              _createElementVNode("span", _hoisted_69, _toDisplayString(formatTime(r.updated_at || r.submitted_at)), 1)
                            ], 8, _hoisted_66)
                          ], 4))
                        : (_openBlock(), _createElementBlock("article", {
                            key: 1,
                            class: "doc115-resource-card doc115-record-row",
                            style: _normalizeStyle({ '--doc115-status-color': statusCss(r) })
                          }, [
                            _createElementVNode("div", _hoisted_70, [
                              _createElementVNode("input", {
                                type: "checkbox",
                                class: "doc115-row-check",
                                checked: !!selected[r.id],
                                "aria-label": `选择「${r.title}」`,
                                onChange: $event => (toggleSelect(r, $event.target.checked))
                              }, null, 40, _hoisted_71),
                              _createElementVNode("h3", _hoisted_72, [
                                _createTextVNode(_toDisplayString(r.title) + " ", 1),
                                (r.year)
                                  ? (_openBlock(), _createElementBlock("span", _hoisted_73, "（" + _toDisplayString(r.year) + "）", 1))
                                  : _createCommentVNode("", true)
                              ]),
                              (r.hidden)
                                ? (_openBlock(), _createElementBlock("span", _hoisted_74, "已隐藏"))
                                : _createCommentVNode("", true),
                              _createElementVNode("span", {
                                class: _normalizeClass(["doc115-chip", recordMedia(r) === 'tv' ? 'doc115-blue' : 'doc115-purple'])
                              }, _toDisplayString(mediaTypeName(recordMedia(r))), 3),
                              (r.kind)
                                ? (_openBlock(), _createElementBlock("span", {
                                    key: 1,
                                    class: _normalizeClass(["doc115-chip", linkColor(r.kind)])
                                  }, _toDisplayString(linkName(r.kind)), 3))
                                : _createCommentVNode("", true),
                              (isCompact(r))
                                ? (_openBlock(), _createBlock(_component_v_btn, {
                                    key: 2,
                                    size: "x-small",
                                    variant: "text",
                                    onClick: $event => (expanded[r.id] = false)
                                  }, {
                                    default: _withCtx(() => [...(_cache[58] || (_cache[58] = [
                                      _createTextVNode("收起", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"]))
                                : _createCommentVNode("", true)
                            ]),
                            _createElementVNode("div", _hoisted_75, [
                              _createElementVNode("span", {
                                class: _normalizeClass(["doc115-chip", statusColor(acquisitionState(r))])
                              }, _toDisplayString(statusName(acquisitionState(r))), 3),
                              _cache[59] || (_cache[59] = _createElementVNode("span", { "aria-hidden": "true" }, "→", -1)),
                              _createElementVNode("span", {
                                class: _normalizeClass(["doc115-chip", statusColor(organizationState(r))])
                              }, _toDisplayString(organizationSummary(r)), 3)
                            ]),
                            (!isDone(r))
                              ? (_openBlock(), _createElementBlock("p", _hoisted_76, "目标：" + _toDisplayString(r.final_path || '待确认'), 1))
                              : _createCommentVNode("", true),
                            (acquisitionState(r) === 'downloading')
                              ? (_openBlock(), _createElementBlock("div", _hoisted_77, [
                                  _createElementVNode("label", null, [
                                    _createTextVNode("115 下载进度：" + _toDisplayString(progressValue(r)) + "%", 1),
                                    _createElementVNode("progress", {
                                      value: progressValue(r),
                                      max: "100"
                                    }, null, 8, _hoisted_78)
                                  ]),
                                  (progressValue(r) === 100)
                                    ? (_openBlock(), _createElementBlock("p", _hoisted_79, "下载已显示 100%，文件落盘与搬运仍需确认。"))
                                    : _createCommentVNode("", true)
                                ]))
                              : _createCommentVNode("", true),
                            (r.message)
                              ? (_openBlock(), _createElementBlock("p", _hoisted_80, _toDisplayString(r.message), 1))
                              : _createCommentVNode("", true),
                            (r.query_error || r.last_error)
                              ? (_openBlock(), _createElementBlock("p", _hoisted_81, _toDisplayString(r.query_error ? '核对查询失败：' : '最近错误：') + _toDisplayString(r.query_error || r.last_error), 1))
                              : _createCommentVNode("", true),
                            _createElementVNode("div", _hoisted_82, [
                              _createElementVNode("span", null, _toDisplayString(formatTime(r.updated_at || r.submitted_at)), 1),
                              (r.next_check_at && !isDone(r))
                                ? (_openBlock(), _createElementBlock("span", _hoisted_83, "下次核对：" + _toDisplayString(formatTime(r.next_check_at)), 1))
                                : _createCommentVNode("", true),
                              (r.pause_reason)
                                ? (_openBlock(), _createElementBlock("span", _hoisted_84, "暂停：" + _toDisplayString(r.pause_reason), 1))
                                : _createCommentVNode("", true)
                            ]),
                            (hasAction(r, 'reconcile'))
                              ? (_openBlock(), _createElementBlock("p", _hoisted_85, "此前的提交结果未确定。「核对转存结果」只读查询 115，不会重新提交。"))
                              : _createCommentVNode("", true),
                            _createElementVNode("div", _hoisted_86, [
                              (needsVerify(r))
                                ? (_openBlock(), _createBlock(_component_v_btn, {
                                    key: 0,
                                    size: "small",
                                    variant: "outlined",
                                    loading: !!verifying[r.id],
                                    disabled: busy.records || recordBusy(r),
                                    onClick: $event => (verifyOne(r))
                                  }, {
                                    default: _withCtx(() => [...(_cache[60] || (_cache[60] = [
                                      _createTextVNode("核对 MP 整理", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["loading", "disabled", "onClick"]))
                                : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(visibleActions(r), (item) => {
                                return (_openBlock(), _createBlock(_component_v_btn, {
                                  key: item.action,
                                  size: "small",
                                  variant: item.primary ? 'outlined' : 'text',
                                  loading: retrying[r.id] === item.action,
                                  disabled: recordBusy(r),
                                  onClick: $event => (runRecordAction(r, item.action))
                                }, {
                                  default: _withCtx(() => [
                                    _createTextVNode(_toDisplayString(item.label), 1)
                                  ]),
                                  _: 2
                                }, 1032, ["variant", "loading", "disabled", "onClick"]))
                              }), 128))
                            ]),
                            _createElementVNode("details", _hoisted_87, [
                              _cache[63] || (_cache[63] = _createElementVNode("summary", null, "详细信息", -1)),
                              (isDone(r))
                                ? (_openBlock(), _createElementBlock("p", _hoisted_88, "目标：" + _toDisplayString(r.final_path || '待确认'), 1))
                                : _createCommentVNode("", true),
                              (r.sheet)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_89, "文档来源：" + _toDisplayString(r.sheet), 1))
                                : _createCommentVNode("", true),
                              _createElementVNode("p", _hoisted_90, [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(specTokens(r.qtext || r.quality || ''), (token, i) => {
                                  return (_openBlock(), _createElementBlock("span", {
                                    key: i,
                                    class: _normalizeClass(token.color || 'doc115-muted')
                                  }, _toDisplayString(token.text), 3))
                                }), 128))
                              ]),
                              (r.staging_path && r.staging_path !== r.final_path)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_91, "离线暂存：" + _toDisplayString(r.staging_path), 1))
                                : _createCommentVNode("", true),
                              _createElementVNode("p", _hoisted_92, _toDisplayString(manifestText(r)), 1),
                              (fileDetails(r).length)
                                ? (_openBlock(), _createElementBlock("ul", _hoisted_93, [
                                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(fileDetails(r), (file, i) => {
                                      return (_openBlock(), _createElementBlock("li", {
                                        key: file.id || file.file_id || i
                                      }, [
                                        _createElementVNode("span", {
                                          class: _normalizeClass(file.status === 'success' ? 'doc115-green' : file.status === 'failed' || file.status === 'missing' ? 'doc115-red' : 'doc115-neutral')
                                        }, _toDisplayString(file.name || file.path || '媒体文件') + " · " + _toDisplayString(file.message || statusName(file.status)), 3)
                                      ]))
                                    }), 128))
                                  ]))
                                : _createCommentVNode("", true),
                              (r.ignored_files?.length)
                                ? (_openBlock(), _createElementBlock("p", _hoisted_94, "附带小视频 " + _toDisplayString(r.ignored_files.length) + " 个，不计入必要整理数；删除这些文件不影响主要资源状态。", 1))
                                : _createCommentVNode("", true),
                              (r.ignored_files?.length)
                                ? (_openBlock(), _createElementBlock("ul", _hoisted_95, [
                                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(r.ignored_files, (file, i) => {
                                      return (_openBlock(), _createElementBlock("li", {
                                        key: i,
                                        class: "doc115-muted"
                                      }, _toDisplayString(file.name) + " · " + _toDisplayString(file.reason), 1))
                                    }), 128))
                                  ]))
                                : _createCommentVNode("", true),
                              _createElementVNode("div", _hoisted_96, [
                                (r.hidden)
                                  ? (_openBlock(), _createBlock(_component_v_btn, {
                                      key: 0,
                                      size: "small",
                                      variant: "text",
                                      "prepend-icon": "mdi-eye-outline",
                                      loading: retrying[r.id] === 'unhide',
                                      disabled: recordBusy(r),
                                      onClick: $event => (unhideRecord(r))
                                    }, {
                                      default: _withCtx(() => [...(_cache[61] || (_cache[61] = [
                                        _createTextVNode("恢复显示", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["loading", "disabled", "onClick"]))
                                  : (isTracking(r))
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_97, "跟踪中的任务不能隐藏，请先停止跟踪。"))
                                    : (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 2,
                                        size: "small",
                                        variant: "text",
                                        "prepend-icon": "mdi-eye-off-outline",
                                        loading: retrying[r.id] === 'hide',
                                        disabled: recordBusy(r),
                                        onClick: $event => (deleteRecord(r))
                                      }, {
                                        default: _withCtx(() => [...(_cache[62] || (_cache[62] = [
                                          _createTextVNode("从列表隐藏", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["loading", "disabled", "onClick"]))
                              ])
                            ])
                          ], 4))
                    ], 64))
                  }), 128)),
                  (recordsTotal.value > 0 && recordsPageCount.value > 1)
                    ? (_openBlock(), _createElementBlock("div", _hoisted_98, [
                        _createElementVNode("span", _hoisted_99, "第 " + _toDisplayString(recordsPage.value) + " / " + _toDisplayString(recordsPageCount.value) + " 页", 1),
                        _createVNode(_component_v_pagination, {
                          "model-value": recordsPage.value,
                          length: recordsPageCount.value,
                          disabled: busy.records,
                          "total-visible": narrow.value ? 1 : 5,
                          size: "small",
                          "onUpdate:modelValue": changeRecordsPage
                        }, null, 8, ["model-value", "length", "disabled", "total-visible"]),
                        _createElementVNode("span", _hoisted_100, [
                          _cache[65] || (_cache[65] = _createElementVNode("label", { for: "doc115-jump-records" }, "跳至", -1)),
                          _withDirectives(_createElementVNode("input", {
                            id: "doc115-jump-records",
                            class: "doc115-jump",
                            type: "number",
                            min: "1",
                            max: recordsPageCount.value,
                            "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((jump.records) = $event)),
                            "aria-label": "任务列表跳转页码",
                            onKeydown: _cache[18] || (_cache[18] = _withKeys($event => (jumpTo('records')), ["enter"]))
                          }, null, 40, _hoisted_101), [
                            [_vModelText, jump.records]
                          ]),
                          _cache[66] || (_cache[66] = _createTextVNode("页", -1)),
                          _createVNode(_component_v_btn, {
                            size: "x-small",
                            variant: "text",
                            disabled: busy.records,
                            onClick: _cache[19] || (_cache[19] = $event => (jumpTo('records')))
                          }, {
                            default: _withCtx(() => [...(_cache[64] || (_cache[64] = [
                              _createTextVNode("跳转", -1)
                            ]))]),
                            _: 1
                          }, 8, ["disabled"])
                        ])
                      ]))
                    : _createCommentVNode("", true),
                  _createElementVNode("details", _hoisted_102, [
                    _cache[68] || (_cache[68] = _createElementVNode("summary", null, "任务管理", -1)),
                    _cache[69] || (_cache[69] = _createElementVNode("p", { class: "doc115-muted doc115-small" }, "只影响本插件的任务列表。云端搬运由后台按预算自动进行，无需手动触发。", -1)),
                    _createElementVNode("div", _hoisted_103, [
                      _createVNode(_component_v_btn, {
                        size: "small",
                        variant: "text",
                        loading: busy.bulk,
                        disabled: !recordsTotal.value || busy.bulk,
                        onClick: clearRecords
                      }, {
                        default: _withCtx(() => [...(_cache[67] || (_cache[67] = [
                          _createTextVNode("隐藏全部已结束任务", -1)
                        ]))]),
                        _: 1
                      }, 8, ["loading", "disabled"])
                    ])
                  ])
                ], 8, _hoisted_54))
        ], 64)),
    _createVNode(_component_v_dialog, {
      modelValue: transferOpen.value,
      "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((transferOpen).value = $event)),
      "max-width": "560"
    }, {
      default: _withCtx(() => [
        _createElementVNode("section", {
          class: "doc115-page doc115-confirm",
          "data-doc115-theme": darkTheme.value ? 'dark' : 'light',
          role: "dialog",
          "aria-labelledby": "doc115-transfer-title"
        }, [
          _createElementVNode("h3", _hoisted_105, _toDisplayString(transferQuick.value ? '一键获取' : '确认获取资源'), 1),
          _createElementVNode("p", _hoisted_106, [
            _createTextVNode(_toDisplayString(transferRecord.value?.title), 1),
            (transferRecord.value?.year)
              ? (_openBlock(), _createElementBlock("span", _hoisted_107, "（" + _toDisplayString(transferRecord.value.year) + "）", 1))
              : _createCommentVNode("", true)
          ]),
          _createVNode(_component_v_select, {
            modelValue: transferTarget.value,
            "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((transferTarget).value = $event)),
            items: targetOptions,
            label: "保存到",
            variant: "outlined",
            density: "comfortable",
            "hide-details": "",
            class: "mt-3"
          }, null, 8, ["modelValue"]),
          _createElementVNode("p", _hoisted_108, _toDisplayString(transferPath.value), 1),
          _createVNode(_component_v_select, {
            modelValue: transferSource.value,
            "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((transferSource).value = $event)),
            items: sourceOptions(transferRecord.value),
            "item-title": "label",
            "item-value": "value",
            label: "本次实际来源",
            variant: "outlined",
            density: "comfortable",
            "hide-details": "",
            class: "mt-3"
          }, null, 8, ["modelValue", "items"]),
          _createElementVNode("p", _hoisted_109, _toDisplayString(transferNote.value), 1),
          _createElementVNode("div", _hoisted_110, [
            _createVNode(_component_v_btn, {
              variant: "text",
              onClick: _cache[22] || (_cache[22] = $event => (transferOpen.value = false))
            }, {
              default: _withCtx(() => [...(_cache[71] || (_cache[71] = [
                _createTextVNode("取消", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_btn, {
              variant: "flat",
              class: "doc115-cta",
              disabled: !transferSource.value || !transferRecord.value,
              loading: !!transferring[transferRecord.value?.record_id],
              onClick: confirmTransfer
            }, {
              default: _withCtx(() => [...(_cache[72] || (_cache[72] = [
                _createTextVNode("确认获取", -1)
              ]))]),
              _: 1
            }, 8, ["disabled", "loading"])
          ])
        ], 8, _hoisted_104)
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_sfc_main$1, {
      "model-value": confirmState.open,
      title: confirmState.title,
      text: confirmState.text,
      "confirm-text": confirmState.confirmText,
      tone: confirmState.tone,
      check: confirmState.check,
      dark: darkTheme.value,
      onConfirm: _cache[24] || (_cache[24] = $event => (answerConfirm(true))),
      onCancel: _cache[25] || (_cache[25] = $event => (answerConfirm(false)))
    }, null, 8, ["model-value", "title", "text", "confirm-text", "tone", "check", "dark"])
  ], 8, _hoisted_1))
}
}

};

export { _sfc_main as default };
