import { importShared } from './__federation_fn_import-SdO2Fg_T.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


const _hoisted_1 = { class: "doc115-config-advanced" };

const {computed,inject,onMounted,reactive,ref} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
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
const directories = ref([]);
const selectedMovieDirectory = ref(''), selectedTvDirectory = ref('');
const movieDirectories = computed(() => directoryOptions('movie'));
const tvDirectories = computed(() => directoryOptions('tv'));
function directoryOptions(type) {
  return directories.value.filter(d => (d.media_type === type || !d.media_type || d.media_type === 'all') && ['115', 'u115', '115网盘Plus'].includes(d.storage)).map(d => ({ title: `${d.name || d.storage} · ${d.path} · ${d.monitored === true ? '监控已启用' : '监控未确认'}`, value: d.path }))
}
function chooseDirectory(type, path) { if (directoryOptions(type).some(d => d.value === path)) cfg[type === 'tv' ? 'tv_path' : 'movie_path'] = path; }
async function loadDirectories() {
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/directories')); const data = res.data || {}; if (res.code === 0 && Array.isArray(data.directories || data.records)) directories.value = data.directories || data.records; }
  catch (_) { /* Older hosts can keep the explicit path fields. */ }
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
    // Credentials never enter the input controls, including older backend responses.
    for (const key of Object.keys(DEFAULTS)) cfg[key] = data[key] === undefined ? DEFAULTS[key] : data[key];
    cfg.tencent_cookie = '';
    cfg.p115_cookie = '';
    cfg.clear_tencent_cookie = false;
    cfg.clear_p115_cookie = false;
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

function close() {
  emit('close');
}

async function save() {
  if (saving.value || loading.value) return
  if ((cfg.clear_tencent_cookie && cfg.tencent_cookie.trim()) || (cfg.clear_p115_cookie && cfg.p115_cookie.trim())) {
    msg.value = '替换 Cookie 和清除 Cookie 不能同时选择';
    msgType.value = 'error';
    return
  }
  saving.value = true;
  try {
    const minimum = Number(cfg.min_media_size_mb);
    if (cfg.min_media_size_mb === '' || cfg.min_media_size_mb == null || !Number.isInteger(minimum) || minimum < 0 || minimum > 1024) throw new Error('小视频阈值必须是 0 到 1024 的整数')
    const payload = { ...cfg, min_media_size_mb: minimum };
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/save_config', payload));
    if (res.code !== 0) throw new Error(res.msg || '配置校验未通过')
    secrets.tencent_ready = cfg.clear_tencent_cookie ? false : !!(cfg.tencent_cookie.trim() || secrets.tencent_ready);
    secrets.p115_ready = cfg.clear_p115_cookie ? false : !!(cfg.p115_cookie.trim() || secrets.p115_ready);
    cfg.tencent_cookie = '';
    cfg.p115_cookie = '';
    cfg.clear_tencent_cookie = false;
    cfg.clear_p115_cookie = false;
    msg.value = '配置已保存';
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

onMounted(() => { load(); loadDirectories(); });

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_checkbox = _resolveComponent("v-checkbox");
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
          _cache[22] || (_cache[22] = _createElementVNode("span", null, [
            _createTextVNode("115文档订阅与查询 · 设置 "),
            _createElementVNode("small", { class: "doc115-muted" }, "前端 v0.10.0")
          ], -1)),
          _createVNode(_component_v_spacer),
          _createVNode(_component_v_btn, {
            icon: "",
            size: "small",
            variant: "text",
            title: "关闭",
            onClick: close
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_icon, null, {
                default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
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
                class: "mb-3"
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(msg.value), 1)
                ]),
                _: 1
              }, 8, ["type"]))
            : _createCommentVNode("", true),
          _createVNode(_component_v_alert, {
            type: secrets.tencent_ready ? 'info' : 'warning',
            variant: "tonal",
            density: "comfortable",
            class: "mb-3"
          }, {
            default: _withCtx(() => [
              _createTextVNode(" 腾讯文档 Cookie：" + _toDisplayString(secrets.tencent_ready ? '已配置，保存时留空会保留' : '未配置，请在插件页面「设置」中扫码登录') + " ｜115 Cookie：" + _toDisplayString(secrets.p115_ready ? '已配置，保存时留空会保留' : '未单独配置，可复用其它 115 插件'), 1)
            ]),
            _: 1
          }, 8, ["type"]),
          _createVNode(_component_v_row, { dense: "" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_col, {
                cols: "12",
                md: "4"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.enabled,
                    "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((cfg.enabled) = $event)),
                    label: "启用插件",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              _createVNode(_component_v_col, {
                cols: "12",
                md: "4"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.subscribe_enabled,
                    "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((cfg.subscribe_enabled) = $event)),
                    label: "启用电影订阅同步",
                    color: "primary",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_row, { dense: "" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_col, { cols: "12" }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.create_subdir,
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((cfg.create_subdir) = $event)),
                    color: "primary",
                    "hide-details": "",
                    label: "转存时按「片名 (年份)」建子目录（推荐开启，便于 MP 整理识别）"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createVNode(_component_v_text_field, {
            modelValue: cfg.doc_url,
            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.doc_url) = $event)),
            label: "腾讯文档链接",
            variant: "outlined",
            density: "comfortable",
            placeholder: "https://docs.qq.com/sheet/xxxx",
            class: "mt-3",
            "hide-details": ""
          }, null, 8, ["modelValue"]),
          _cache[25] || (_cache[25] = _createElementVNode("p", { class: "doc115-muted" }, "下载目录应对应 MP 已配置的 115 存储目录。本插件不修改 MP 监控或整理配置；未核实监控时不能保证保存后会自动整理。", -1)),
          (movieDirectories.value.length)
            ? (_openBlock(), _createBlock(_component_v_select, {
                key: 1,
                modelValue: selectedMovieDirectory.value,
                "onUpdate:modelValue": [
                  _cache[4] || (_cache[4] = $event => ((selectedMovieDirectory).value = $event)),
                  _cache[5] || (_cache[5] = $event => (chooseDirectory('movie', $event)))
                ],
                items: movieDirectories.value,
                label: "选择已缓存的 MP 电影下载目录",
                variant: "outlined",
                density: "comfortable"
              }, null, 8, ["modelValue", "items"]))
            : _createCommentVNode("", true),
          (tvDirectories.value.length)
            ? (_openBlock(), _createBlock(_component_v_select, {
                key: 2,
                modelValue: selectedTvDirectory.value,
                "onUpdate:modelValue": [
                  _cache[6] || (_cache[6] = $event => ((selectedTvDirectory).value = $event)),
                  _cache[7] || (_cache[7] = $event => (chooseDirectory('tv', $event)))
                ],
                items: tvDirectories.value,
                label: "选择已缓存的 MP 电视剧下载目录",
                variant: "outlined",
                density: "comfortable"
              }, null, 8, ["modelValue", "items"]))
            : _createCommentVNode("", true),
          _createVNode(_component_v_row, {
            dense: "",
            class: "mt-3"
          }, {
            default: _withCtx(() => [
              _createVNode(_component_v_col, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_text_field, {
                    modelValue: cfg.movie_path,
                    "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.movie_path) = $event)),
                    label: "115 电影下载目录",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
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
                    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.tv_path) = $event)),
                    label: "115 电视剧下载目录",
                    variant: "outlined",
                    density: "comfortable",
                    "hide-details": ""
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          _createElementVNode("details", _hoisted_1, [
            _cache[23] || (_cache[23] = _createElementVNode("summary", null, "高级设置（链接策略、计划、Cookie）", -1)),
            _createVNode(_component_v_select, {
              modelValue: cfg.link_mode,
              "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.link_mode) = $event)),
              items: linkModes,
              label: "自动订阅：同一资源的多个链接",
              variant: "outlined",
              density: "comfortable",
              class: "mt-3",
              "persistent-hint": "",
              hint: "默认镜像回退，仅明确失败后尝试下一来源。手动获取只使用确认面板选定的链接。分卷 / 全部提交只适用于确实需要全部资源的条目。"
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_switch, {
              modelValue: cfg.upgrade_enabled,
              "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.upgrade_enabled) = $event)),
              color: "primary",
              "hide-details": "",
              label: "允许订阅获取更高画质版本"
            }, null, 8, ["modelValue"]),
            _cache[24] || (_cache[24] = _createElementVNode("p", { class: "doc115-muted" }, "升级失败保留旧版本。画质无法确认时暂停自动升级判断，避免重复获取。", -1)),
            _createVNode(_component_v_text_field, {
              modelValue: cfg.min_media_size_mb,
              "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.min_media_size_mb) = $event)),
              modelModifiers: { number: true },
              type: "number",
              min: "0",
              max: "1024",
              step: "1",
              label: "整理核对忽略小视频（MB）",
              variant: "outlined",
              density: "comfortable",
              class: "mt-3",
              "persistent-hint": "",
              hint: "默认 10，0 关闭。仅忽略已知体积小于阈值的附带视频；不删除文件，不改 MP 过滤规则。新任务使用新设置。"
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_text_field, {
              modelValue: cfg.magnet_staging_path,
              "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.magnet_staging_path) = $event)),
              label: "磁力 / ed2k 暂存目录",
              variant: "outlined",
              density: "comfortable",
              class: "mt-3",
              "hide-details": "",
              hint: "磁力/ed2k 先离线下载到这里，完成后由本插件走「115网盘Plus」搬到上面的电影/电视剧目录（115 分享链接不受影响，直接进最终目录）",
              "persistent-hint": ""
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_row, {
              dense: "",
              class: "mt-3"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.index_cron,
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((cfg.index_cron) = $event)),
                      label: "索引刷新 cron",
                      variant: "outlined",
                      density: "comfortable",
                      placeholder: "0 6 * * *",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: cfg.subscribe_cron,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((cfg.subscribe_cron) = $event)),
                      label: "订阅同步 cron",
                      variant: "outlined",
                      density: "comfortable",
                      placeholder: "0 21 * * *",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            _createVNode(_component_v_text_field, {
              modelValue: cfg.tencent_cookie,
              "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((cfg.tencent_cookie) = $event)),
              label: "替换腾讯文档 Cookie（留空保留）",
              type: "password",
              autocomplete: "new-password",
              variant: "outlined",
              density: "comfortable",
              class: "mt-3",
              "hide-details": ""
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_checkbox, {
              modelValue: cfg.clear_tencent_cookie,
              "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((cfg.clear_tencent_cookie) = $event)),
              label: "清除已保存的腾讯文档 Cookie",
              color: "warning",
              "hide-details": ""
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_text_field, {
              modelValue: cfg.p115_cookie,
              "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((cfg.p115_cookie) = $event)),
              label: "替换 115 Cookie（留空保留）",
              type: "password",
              autocomplete: "new-password",
              variant: "outlined",
              density: "comfortable",
              class: "mt-3",
              "hide-details": ""
            }, null, 8, ["modelValue"]),
            _createVNode(_component_v_checkbox, {
              modelValue: cfg.clear_p115_cookie,
              "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((cfg.clear_p115_cookie) = $event)),
              label: "清除单独保存的 115 Cookie（改为复用其它 115 插件）",
              color: "warning",
              "hide-details": ""
            }, null, 8, ["modelValue"])
          ])
        ]),
        _: 1
      }),
      _createVNode(_component_v_card_actions, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_btn, {
            variant: "text",
            "prepend-icon": "mdi-refresh",
            loading: loading.value,
            onClick: _cache[20] || (_cache[20] = $event => (load(true)))
          }, {
            default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
              _createTextVNode("重新读取配置", -1)
            ]))]),
            _: 1
          }, 8, ["loading"]),
          _createVNode(_component_v_spacer),
          _createVNode(_component_v_btn, {
            variant: "text",
            "prepend-icon": "mdi-close",
            onClick: close
          }, {
            default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
              _createTextVNode("关闭", -1)
            ]))]),
            _: 1
          }),
          _createVNode(_component_v_btn, {
            color: "primary",
            loading: saving.value,
            "prepend-icon": "mdi-content-save",
            onClick: save
          }, {
            default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
              _createTextVNode("保存配置", -1)
            ]))]),
            _: 1
          }, 8, ["loading"])
        ]),
        _: 1
      })
    ]),
    _: 1
  }, 8, ["data-doc115-theme"]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-a02531ab"]]);

export { Config as default };
