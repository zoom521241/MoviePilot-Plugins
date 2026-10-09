import { importShared } from './__federation_fn_import-SdO2Fg_T.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,createTextVNode:_createTextVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


const {onMounted,reactive,ref} = await importShared('vue');



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
  subscribe_enabled: true,
  subscribe_cron: '0 21 * * *',
  index_cron: '0 6 * * *',
  create_subdir: true,
  link_mode: 'first',
  upgrade_enabled: false,
};
const linkModes = [{ title: '镜像回退（推荐）', value: 'first' }, { title: '分卷 / 多份文件：全部提交', value: 'all' }];

const cfg = reactive({ ...DEFAULTS });
const secrets = reactive({ tencent_ready: false, p115_ready: false });
const msg = ref('');
const msgType = ref('info');
const saving = ref(false);
const loading = ref(false);

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
    const payload = { ...cfg };
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

onMounted(() => load());

return (_ctx, _cache) => {
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_checkbox = _resolveComponent("v-checkbox");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, { variant: "outlined" }, {
    default: _withCtx(() => [
      _createVNode(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center" }, {
        default: _withCtx(() => [
          _cache[17] || (_cache[17] = _createElementVNode("span", null, "115文档订阅与查询 · 设置", -1)),
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
                default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
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
              _createTextVNode(" 腾讯文档 Cookie：" + _toDisplayString(secrets.tencent_ready ? '已配置，保存时留空会保留' : '未配置，请到「详情」页扫码登录或在此粘贴') + " ｜115 Cookie：" + _toDisplayString(secrets.p115_ready ? '已配置，保存时留空会保留' : '未单独配置，可复用其它 115 插件'), 1)
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
          _createVNode(_component_v_select, {
            modelValue: cfg.link_mode,
            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.link_mode) = $event)),
            items: linkModes,
            label: "同一资源的多个链接",
            variant: "outlined",
            density: "comfortable",
            class: "mt-3",
            "persistent-hint": "",
            hint: "默认按镜像回退，首个成功即停止；只有明确属于分卷或多份必要文件时才选择全部提交。"
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_switch, {
            modelValue: cfg.upgrade_enabled,
            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.upgrade_enabled) = $event)),
            color: "primary",
            "hide-details": "",
            label: "允许订阅获取新资源版本"
          }, null, 8, ["modelValue"]),
          _cache[18] || (_cache[18] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "开启后，同一影片出现不同资源链接时可以重新获取，可能产生多个版本。", -1)),
          _createVNode(_component_v_text_field, {
            modelValue: cfg.doc_url,
            "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.doc_url) = $event)),
            label: "腾讯文档链接",
            variant: "outlined",
            density: "comfortable",
            placeholder: "https://docs.qq.com/sheet/xxxx",
            class: "mt-3",
            "hide-details": ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_text_field, {
            modelValue: cfg.tencent_cookie,
            "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.tencent_cookie) = $event)),
            label: "替换腾讯文档 Cookie（留空保留）",
            type: "password",
            autocomplete: "new-password",
            variant: "outlined",
            density: "comfortable",
            class: "mt-3",
            "hide-details": "",
            hint: "推荐在「详情」页扫码登录；已有 Cookie 不会回显。",
            "persistent-hint": ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_checkbox, {
            modelValue: cfg.clear_tencent_cookie,
            "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.clear_tencent_cookie) = $event)),
            label: "清除已保存的腾讯文档 Cookie",
            color: "warning",
            "hide-details": ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_text_field, {
            modelValue: cfg.p115_cookie,
            "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.p115_cookie) = $event)),
            label: "替换 115 Cookie（留空保留）",
            type: "password",
            autocomplete: "new-password",
            variant: "outlined",
            density: "comfortable",
            class: "mt-4",
            "hide-details": ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_checkbox, {
            modelValue: cfg.clear_p115_cookie,
            "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.clear_p115_cookie) = $event)),
            label: "清除单独保存的 115 Cookie（改为复用其它 115 插件）",
            color: "warning",
            "hide-details": ""
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
                    modelValue: cfg.movie_path,
                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.movie_path) = $event)),
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
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.tv_path) = $event)),
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
          _createVNode(_component_v_text_field, {
            modelValue: cfg.magnet_staging_path,
            "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.magnet_staging_path) = $event)),
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
                    "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.index_cron) = $event)),
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
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((cfg.subscribe_cron) = $event)),
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
          })
        ]),
        _: 1
      }),
      _createVNode(_component_v_card_actions, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_btn, {
            variant: "text",
            "prepend-icon": "mdi-refresh",
            loading: loading.value,
            onClick: _cache[15] || (_cache[15] = $event => (load(true)))
          }, {
            default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
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
            default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
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
            default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
              _createTextVNode("保存配置", -1)
            ]))]),
            _: 1
          }, 8, ["loading"])
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};

export { _sfc_main as default };
