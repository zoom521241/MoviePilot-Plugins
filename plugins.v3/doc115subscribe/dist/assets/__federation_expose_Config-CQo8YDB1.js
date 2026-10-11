import { importShared } from './__federation_fn_import-SdO2Fg_T.js';

// 前端构建版本：Page 与 Config 共用；测试会断言它与 ui/package.json、package.v3.json 一致。
const UI_BUILD = '0.11.3';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,renderSlot:_renderSlot,withModifiers:_withModifiers,unref:_unref,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "doc115-config-switches" };
const _hoisted_2 = { class: "doc115-muted" };
const _hoisted_3 = { class: "doc115-muted" };
const _hoisted_4 = { class: "doc115-muted doc115-config-version" };

const {computed,inject,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
  // 嵌在插件详情页「设置」里时为 true：扫码登录、刷新索引、诊断通过插槽放进对应分组
  embedded: { type: Boolean, default: false },
  backendVersion: { type: String, default: '' },
},
  emits: ['action', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;
const hostTheme = inject(Symbol.for('vuetify:theme'), null);
const darkTheme = computed(() => !!(props.model?.dark ?? hostTheme?.current?.value?.dark));

const DEFAULTS = {
  enabled: false,
  doc_url: 'https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo',
  tencent_cookie: '',
  p115_cookie: '',
  clear_tencent_cookie: false,
  clear_p115_cookie: false,
  movie_path: '/115-影视/115-downloads/电影',
  tv_path: '/115-影视/115-downloads/电视剧',
  magnet_staging_path: '/115-影视/115-downloads/磁力链接',
  subscribe_enabled: false,
  subscribe_cron: '0 21 * * *',
  index_cron: '0 6 * * *',
  create_subdir: true,
  link_mode: 'first',
  upgrade_enabled: false,
  min_media_size_mb: 10,
};
const linkModes = [{ title: '镜像回退（推荐）', value: 'first' }, { title: '分卷 / 多份文件：全部提交', value: 'all' }];

const cfg = reactive({ ...DEFAULTS });
const secrets = reactive({ tencent_ready: false, p115_ready: false });
const msg = ref('');
const msgType = ref('info');
const saving = ref(false);
const loading = ref(false);
const formRef = ref(null);
const openPanels = ref(['tencent', 'paths']);
const fetchedVersion = ref('');
const shownBackendVersion = computed(() => props.backendVersion || fetchedVersion.value);
const directories = ref([]);
const selectedMovieDirectory = ref(''), selectedTvDirectory = ref('');
const movieDirectories = computed(() => directoryOptions('movie'));
const tvDirectories = computed(() => directoryOptions('tv'));
const tencentHint = computed(() => secrets.tencent_ready
  ? '腾讯文档 Cookie 已配置。'
  : props.embedded ? '腾讯文档 Cookie 未配置，请用下方「扫码登录腾讯文档」登录。' : '腾讯文档 Cookie 未配置。请打开插件详情页，在「设置」的腾讯文档分组中扫码登录。');

// ---- 校验：返回 true 或错误文案（Vuetify rules 约定），保存前统一再跑一遍 ----
function normPath(value) { return String(value || '').trim().replace(/\\/g, '/').replace(/\/+$/, '') }
function isNested(a, b) { return a === b || a.startsWith(b + '/') || b.startsWith(a + '/') }
const CRON_FIELD = /^(\*|\?|[0-9A-Za-z]+(-[0-9A-Za-z]+)?)(\/\d+)?(,(\*|[0-9A-Za-z]+(-[0-9A-Za-z]+)?)(\/\d+)?)*$/;
const rules = {
  docUrl: v => { const value = String(v || '').trim(); if (!value) return '请填写腾讯文档链接'; return /^https:\/\/docs\.qq\.com\/sheet\/[A-Za-z0-9_-]+/.test(value) || '必须是 https://docs.qq.com/sheet/ 开头的表格链接' },
  cron: v => { const value = String(v || '').trim(); if (!value) return '请填写 cron 表达式'; const parts = value.split(/\s+/); return (parts.length === 5 && parts.every(p => CRON_FIELD.test(p))) || '格式应为 5 段：分 时 日 月 周，例如 0 6 * * *' },
  path: v => { const value = normPath(v); if (!value) return '请填写目录'; if (!value.startsWith('/')) return '目录必须以 / 开头'; if (value.split('/').some(p => p === '.' || p === '..')) return '目录不能包含 . 或 ..'; if ([...value].some(c => c.charCodeAt(0) < 32)) return '目录含有非法字符'; return true },
  staging: v => { const value = normPath(v); if (!value) return true; for (const [key, name] of [['movie_path', '电影'], ['tv_path', '电视剧']]) { const other = normPath(cfg[key]); if (other && isNested(value, other)) return `暂存目录不能与${name}目录相同或互相嵌套` } return true },
  minSize: v => { const n = Number(v); return (v !== '' && v != null && Number.isInteger(n) && n >= 0 && n <= 1024) || '小视频阈值必须是 0 到 1024 的整数' },
};
function validateAll() {
  const checks = [[rules.docUrl, cfg.doc_url], [rules.cron, cfg.index_cron], [rules.cron, cfg.subscribe_cron], [rules.path, cfg.movie_path], [rules.path, cfg.tv_path], [rules.path, cfg.magnet_staging_path], [rules.staging, cfg.magnet_staging_path], [rules.minSize, cfg.min_media_size_mb]];
  for (const [rule, value] of checks) { const result = rule(value); if (result !== true) return result }
  return ''
}

function directoryOptions(type) {
  return directories.value.filter(d => (d.media_type === type || !d.media_type || d.media_type === 'all') && ['115', 'u115', '115网盘Plus'].includes(d.storage)).map(d => ({ title: `${d.name || d.storage} · ${d.path}${d.monitored === true ? ' · 监控已启用' : d.monitored === false ? ' · 未开启监控' : ''}`, value: d.path }))
}
function chooseDirectory(type, path) { if (directoryOptions(type).some(d => d.value === path)) cfg[type === 'tv' ? 'tv_path' : 'movie_path'] = path; }
async function loadDirectories() {
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/directories')); const data = res.data || {}; if (res.code === 0 && Array.isArray(data.directories || data.records)) directories.value = data.directories || data.records; }
  catch (_) { /* 旧后端没有目录接口时保留手填路径 */ }
}
async function loadVersion() {
  if (props.embedded) return
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/status')); if (res.code === 0 && res.data?.version) fetchedVersion.value = String(res.data.version); } catch (_) { /* 版本号仅用于展示 */ }
}

// 把后端返回的配置填回表单；Cookie 明文永远不进输入框（兼容旧后端返回明文）
function applyConfig(data) {
  for (const key of Object.keys(DEFAULTS)) if (data[key] !== undefined) cfg[key] = data[key];
  cfg.tencent_cookie = '';
  cfg.p115_cookie = '';
  cfg.clear_tencent_cookie = false;
  cfg.clear_p115_cookie = false;
}

async function load(showTip = false) {
  if (loading.value || saving.value) return
  loading.value = true;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/get_config'));
    if (res.code !== 0) throw new Error(res.msg || '读取配置失败')
    const data = res.data;
    if (!data || typeof data !== 'object') throw new Error('配置响应格式错误')
    secrets.tencent_ready = !!(data.tencent_cookie_ready || data.cookie_ready || data.tencent_cookie);
    secrets.p115_ready = 'p115_cookie_ready' in data ? !!data.p115_cookie_ready : !!(data.p115_ready || data.p115_cookie);
    for (const key of Object.keys(DEFAULTS)) cfg[key] = DEFAULTS[key];
    applyConfig(data);
    if (showTip === true) {
      msg.value = secrets.tencent_ready ? '已读取最新配置，腾讯文档 Cookie 已配置' : '已读取最新配置，腾讯文档 Cookie 未配置';
      msgType.value = secrets.tencent_ready ? 'info' : 'warning';
    }
  } catch (e) {
    msg.value = `读取失败：${e.message || e}`;
    msgType.value = 'error';
  } finally {
    loading.value = false;
  }
}

function close() { emit('close'); }

async function save() {
  if (saving.value || loading.value) return
  if ((cfg.clear_tencent_cookie && cfg.tencent_cookie.trim()) || (cfg.clear_p115_cookie && cfg.p115_cookie.trim())) {
    msg.value = '替换 Cookie 和清除 Cookie 不能同时选择';
    msgType.value = 'error';
    return
  }
  const invalid = validateAll();
  if (invalid) {
    msg.value = `请先修正：${invalid}`;
    msgType.value = 'error';
    formRef.value?.validate?.();
    return
  }
  saving.value = true;
  try {
    const payload = { ...cfg, min_media_size_mb: Number(cfg.min_media_size_mb), doc_url: String(cfg.doc_url).trim(), index_cron: String(cfg.index_cron).trim(), subscribe_cron: String(cfg.subscribe_cron).trim() };
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/save_config', payload));
    if (res.code !== 0) throw new Error(res.msg || '配置校验未通过')
    const data = res.data && typeof res.data === 'object' ? res.data : null;
    if (data && ('tencent_cookie_ready' in data || 'p115_cookie_ready' in data)) {
      secrets.tencent_ready = !!data.tencent_cookie_ready;
      secrets.p115_ready = !!data.p115_cookie_ready;
    } else {
      secrets.tencent_ready = cfg.clear_tencent_cookie ? false : !!(cfg.tencent_cookie.trim() || secrets.tencent_ready);
      secrets.p115_ready = cfg.clear_p115_cookie ? false : !!(cfg.p115_cookie.trim() || secrets.p115_ready);
    }
    // 后端会规范化路径（去尾部 /、统一分隔符），用返回值回填，界面与实际生效值一致
    if (data) applyConfig(data);
    else applyConfig({});
    msg.value = '设置已保存';
    msgType.value = 'success';
  } catch (e) {
    msg.value = `保存失败：${e.message || e}`;
    msgType.value = 'error';
  } finally {
    saving.value = false;
    emit('action');
  }
}

function unwrap(res) {
  if (res && typeof res === 'object' && 'code' in res) return res
  return { code: 0, data: res }
}

onMounted(() => { load(); loadDirectories(); loadVersion(); });

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_expansion_panel_title = _resolveComponent("v-expansion-panel-title");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_expansion_panel_text = _resolveComponent("v-expansion-panel-text");
  const _component_v_expansion_panel = _resolveComponent("v-expansion-panel");
  const _component_v_checkbox = _resolveComponent("v-checkbox");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_expansion_panels = _resolveComponent("v-expansion-panels");
  const _component_v_form = _resolveComponent("v-form");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, {
    variant: "outlined",
    class: "doc115-config",
    "data-doc115-theme": darkTheme.value ? 'dark' : 'light'
  }, {
    default: _withCtx(() => [
      _createVNode(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center" }, {
        default: _withCtx(() => [
          _createElementVNode("span", null, _toDisplayString(__props.embedded ? '设置' : '115文档订阅与查询 · 设置'), 1),
          _createVNode(_component_v_spacer),
          _createVNode(_component_v_btn, {
            icon: "",
            size: "small",
            variant: "text",
            title: "关闭设置",
            "aria-label": "关闭设置",
            onClick: close
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, null, {
                default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                  _createTextVNode("mdi-close", -1)
                ]))]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_card_text, null, {
        default: _withCtx(() => [
          (msg.value)
            ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 0,
                type: msgType.value,
                variant: "tonal",
                density: "comfortable",
                class: "mb-3",
                role: "status"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(msg.value), 1)
                ]),
                _: 1
              }, 8, ["type"]))
            : _createCommentVNode("", true),
          _createElementVNode("div", _hoisted_1, [
            _createVNode(_component_v_switch, {
              modelValue: cfg.enabled,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((cfg.enabled) = $event)),
              label: "启用插件",
              color: "primary",
              "hide-details": ""
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_switch, {
              modelValue: cfg.subscribe_enabled,
              "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((cfg.subscribe_enabled) = $event)),
              label: "启用电影订阅同步",
              color: "primary",
              "hide-details": ""
            }, null, 8, ["modelValue"])
          ]),
          _createVNode(_component_v_form, {
            ref_key: "formRef",
            ref: formRef,
            "validate-on": "input",
            onSubmit: _withModifiers(save, ["prevent"])
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_expansion_panels, {
                modelValue: openPanels.value,
                "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((openPanels).value = $event)),
                multiple: "",
                variant: "accordion",
                class: "doc115-config-groups"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_expansion_panel, { value: "tencent" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_expansion_panel_title, null, {
                        default: _withCtx(() => [
                          _cache[23] || (_cache[23] = _createTextVNode("腾讯文档", -1)),
                          _createElementVNode("span", {
                            class: _normalizeClass(["doc115-group-state", secrets.tencent_ready ? 'doc115-green' : 'doc115-amber'])
                          }, _toDisplayString(secrets.tencent_ready ? '已登录' : '未登录'), 3)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_expansion_panel_text, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.doc_url,
                            "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((cfg.doc_url) = $event)),
                            label: "腾讯文档链接",
                            variant: "outlined",
                            density: "comfortable",
                            placeholder: "https://docs.qq.com/sheet/xxxx",
                            rules: [rules.docUrl],
                            "hide-details": "auto"
                          }, null, 8, ["modelValue", "rules"]),
                          _createElementVNode("p", _hoisted_2, _toDisplayString(tencentHint.value), 1),
                          _renderSlot(_ctx.$slots, "tencent", {}, undefined, true)
                        ]),
                        _: 3
                      })
                    ]),
                    _: 3
                  }),
                  _createVNode(_component_v_expansion_panel, { value: "p115" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_expansion_panel_title, null, {
                        default: _withCtx(() => [
                          _cache[24] || (_cache[24] = _createTextVNode("115 网盘", -1)),
                          _createElementVNode("span", {
                            class: _normalizeClass(["doc115-group-state", secrets.p115_ready ? 'doc115-green' : 'doc115-neutral'])
                          }, _toDisplayString(secrets.p115_ready ? '已配置' : '复用其它插件'), 3)
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_expansion_panel_text, null, {
                        default: _withCtx(() => [
                          _createElementVNode("p", _hoisted_3, _toDisplayString(secrets.p115_ready ? '115 Cookie 已配置，保存时留空会保留。' : '未单独配置 115 Cookie，会复用其它 115 插件的登录。'), 1),
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.p115_cookie,
                            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.p115_cookie) = $event)),
                            label: "替换 115 Cookie（留空保留）",
                            type: "password",
                            autocomplete: "new-password",
                            variant: "outlined",
                            density: "comfortable",
                            disabled: cfg.clear_p115_cookie,
                            "hide-details": ""
                          }, null, 8, ["modelValue", "disabled"]),
                          _createVNode(_component_v_checkbox, {
                            modelValue: cfg.clear_p115_cookie,
                            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.clear_p115_cookie) = $event)),
                            label: "清除单独保存的 115 Cookie（改为复用其它 115 插件）",
                            color: "warning",
                            "hide-details": ""
                          }, null, 8, ["modelValue"])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_expansion_panel, { value: "paths" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_expansion_panel_title, null, {
                        default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
                          _createTextVNode("保存目录", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_v_expansion_panel_text, null, {
                        default: _withCtx(() => [
                          _cache[26] || (_cache[26] = _createElementVNode("p", { class: "doc115-muted" }, "下载目录应对应 MP 已配置的 115 存储目录。本插件不修改 MP 监控或整理配置；未核实监控时不能保证保存后会自动整理。", -1)),
                          (movieDirectories.value.length)
                            ? (_openBlock(), _createBlock(_component_v_select, {
                                key: 0,
                                modelValue: selectedMovieDirectory.value,
                                "onUpdate:modelValue": [
                                  _cache[5] || (_cache[5] = $event => ((selectedMovieDirectory).value = $event)),
                                  _cache[6] || (_cache[6] = $event => (chooseDirectory('movie', $event)))
                                ],
                                items: movieDirectories.value,
                                label: "选择已缓存的 MP 电影下载目录",
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": "",
                                class: "mb-3"
                              }, null, 8, ["modelValue", "items"]))
                            : _createCommentVNode("", true),
                          (tvDirectories.value.length)
                            ? (_openBlock(), _createBlock(_component_v_select, {
                                key: 1,
                                modelValue: selectedTvDirectory.value,
                                "onUpdate:modelValue": [
                                  _cache[7] || (_cache[7] = $event => ((selectedTvDirectory).value = $event)),
                                  _cache[8] || (_cache[8] = $event => (chooseDirectory('tv', $event)))
                                ],
                                items: tvDirectories.value,
                                label: "选择已缓存的 MP 电视剧下载目录",
                                variant: "outlined",
                                density: "comfortable",
                                "hide-details": "",
                                class: "mb-3"
                              }, null, 8, ["modelValue", "items"]))
                            : _createCommentVNode("", true),
                          _createVNode(_component_v_row, { dense: "" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_col, {
                                cols: "12",
                                md: "6"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_text_field, {
                                    modelValue: cfg.movie_path,
                                    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.movie_path) = $event)),
                                    label: "115 电影下载目录",
                                    variant: "outlined",
                                    density: "comfortable",
                                    rules: [rules.path],
                                    "hide-details": "auto"
                                  }, null, 8, ["modelValue", "rules"])
                                ]),
                                _: 1
                              }),
                              _createVNode(_component_v_col, {
                                cols: "12",
                                md: "6"
                              }, {
                                default: _withCtx(() => [
                                  _createVNode(_component_v_text_field, {
                                    modelValue: cfg.tv_path,
                                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.tv_path) = $event)),
                                    label: "115 电视剧下载目录",
                                    variant: "outlined",
                                    density: "comfortable",
                                    rules: [rules.path],
                                    "hide-details": "auto"
                                  }, null, 8, ["modelValue", "rules"])
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.magnet_staging_path,
                            "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.magnet_staging_path) = $event)),
                            label: "磁力 / ed2k 暂存目录",
                            variant: "outlined",
                            density: "comfortable",
                            class: "mt-2",
                            rules: [rules.path, rules.staging],
                            "hide-details": "auto",
                            "persistent-hint": "",
                            hint: "磁力 / ed2k 先离线下载到这里，完成后由本插件借助 115网盘Plus 搬到电影 / 电视剧目录；115 分享链接直接进最终目录。不能与电影或电视剧目录相同或互相嵌套。"
                          }, null, 8, ["modelValue", "rules"]),
                          _createVNode(_component_v_switch, {
                            modelValue: cfg.create_subdir,
                            "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.create_subdir) = $event)),
                            color: "primary",
                            "hide-details": "",
                            class: "mt-2",
                            label: "保存时按「片名 (年份)」建子目录（推荐，便于 MP 识别）"
                          }, null, 8, ["modelValue"])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_expansion_panel, { value: "subscribe" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_expansion_panel_title, null, {
                        default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                          _createTextVNode("电影订阅", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_v_expansion_panel_text, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.subscribe_cron,
                            "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.subscribe_cron) = $event)),
                            label: "订阅同步计划（cron）",
                            variant: "outlined",
                            density: "comfortable",
                            placeholder: "0 21 * * *",
                            rules: [rules.cron],
                            "hide-details": "auto",
                            "persistent-hint": "",
                            hint: "5 段 cron：分 时 日 月 周，例如 0 21 * * * 表示每天 21:00。"
                          }, null, 8, ["modelValue", "rules"]),
                          _createVNode(_component_v_select, {
                            modelValue: cfg.link_mode,
                            "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((cfg.link_mode) = $event)),
                            items: linkModes,
                            label: "同一资源有多个链接时",
                            variant: "outlined",
                            density: "comfortable",
                            class: "mt-3",
                            "persistent-hint": "",
                            hint: "镜像回退：仅明确失败后才尝试下一来源。分卷 / 全部提交只适用于确实需要全部文件的条目。手动获取只使用确认对话框里选定的链接。"
                          }, null, 8, ["modelValue"]),
                          _createVNode(_component_v_switch, {
                            modelValue: cfg.upgrade_enabled,
                            "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((cfg.upgrade_enabled) = $event)),
                            color: "primary",
                            "hide-details": "",
                            class: "mt-2",
                            label: "允许订阅获取更高画质版本"
                          }, null, 8, ["modelValue"]),
                          _cache[28] || (_cache[28] = _createElementVNode("p", { class: "doc115-muted" }, "升级失败保留旧版本；画质无法确认时暂停自动升级，避免重复获取。", -1))
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_expansion_panel, { value: "advanced" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_expansion_panel_title, null, {
                        default: _withCtx(() => [...(_cache[29] || (_cache[29] = [
                          _createTextVNode("高级", -1)
                        ]))]),
                        _: 1
                      }),
                      _createVNode(_component_v_expansion_panel_text, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.index_cron,
                            "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((cfg.index_cron) = $event)),
                            label: "索引刷新计划（cron）",
                            variant: "outlined",
                            density: "comfortable",
                            placeholder: "0 6 * * *",
                            rules: [rules.cron],
                            "hide-details": "auto"
                          }, null, 8, ["modelValue", "rules"]),
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.min_media_size_mb,
                            "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((cfg.min_media_size_mb) = $event)),
                            modelModifiers: { number: true },
                            type: "number",
                            min: "0",
                            max: "1024",
                            step: "1",
                            label: "整理核对忽略小视频（MB）",
                            variant: "outlined",
                            density: "comfortable",
                            class: "mt-3",
                            rules: [rules.minSize],
                            "hide-details": "auto",
                            "persistent-hint": "",
                            hint: "默认 10，0 关闭。只忽略已知体积小于阈值的附带视频；不删除文件，不改 MP 过滤规则。新任务使用新设置。"
                          }, null, 8, ["modelValue", "rules"]),
                          _createVNode(_component_v_text_field, {
                            modelValue: cfg.tencent_cookie,
                            "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((cfg.tencent_cookie) = $event)),
                            label: "手动替换腾讯文档 Cookie（留空保留）",
                            type: "password",
                            autocomplete: "new-password",
                            variant: "outlined",
                            density: "comfortable",
                            class: "mt-3",
                            disabled: cfg.clear_tencent_cookie,
                            "hide-details": ""
                          }, null, 8, ["modelValue", "disabled"]),
                          _createVNode(_component_v_checkbox, {
                            modelValue: cfg.clear_tencent_cookie,
                            "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((cfg.clear_tencent_cookie) = $event)),
                            label: "清除已保存的腾讯文档 Cookie",
                            color: "warning",
                            "hide-details": ""
                          }, null, 8, ["modelValue"]),
                          _renderSlot(_ctx.$slots, "advanced", {}, undefined, true)
                        ]),
                        _: 3
                      })
                    ]),
                    _: 3
                  })
                ]),
                _: 3
              }, 8, ["modelValue"])
            ]),
            _: 3
          }, 512),
          _createElementVNode("p", _hoisted_4, [
            _createTextVNode("前端 v" + _toDisplayString(_unref(UI_BUILD)), 1),
            (shownBackendVersion.value)
              ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                  _createTextVNode(" · 后端 v" + _toDisplayString(shownBackendVersion.value), 1)
                ], 64))
              : _createCommentVNode("", true)
          ])
        ]),
        _: 3
      }),
      _createVNode(_component_v_card_actions, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_btn, {
            variant: "text",
            "prepend-icon": "mdi-refresh",
            loading: loading.value,
            disabled: saving.value,
            onClick: _cache[21] || (_cache[21] = $event => (load(true)))
          }, {
            default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
              _createTextVNode("重新读取", -1)
            ]))]),
            _: 1
          }, 8, ["loading", "disabled"]),
          _createVNode(_component_v_spacer),
          _createVNode(_component_v_btn, {
            variant: "text",
            onClick: close
          }, {
            default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
              _createTextVNode("关闭", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            color: "primary",
            variant: "flat",
            loading: saving.value,
            disabled: loading.value,
            "prepend-icon": "mdi-content-save",
            onClick: save
          }, {
            default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
              _createTextVNode("保存设置", -1)
            ]))]),
            _: 1
          }, 8, ["loading", "disabled"])
        ]),
        _: 1
      })
    ]),
    _: 3
  }, 8, ["data-doc115-theme"]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-3d9ae519"]]);

export { UI_BUILD as U, Config as default };
