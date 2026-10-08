import { importShared } from './__federation_fn_import-SdO2Fg_T.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = {
  key: 0,
  class: "text-medium-emphasis"
};

const {onMounted,reactive,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
},
  emits: ['save', 'action'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const DEFAULTS = {
  enabled: false,
  doc_url: 'https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo',
  tencent_cookie: '',
  p115_cookie: '',
  movie_path: '/115-影视/115-downloads/电影',
  tv_path: '/115-影视/115-downloads/电视剧',
  subscribe_enabled: true,
  subscribe_cron: '0 21 * * *',
  index_cron: '0 6 * * *',
  use_agent: true,
  create_subdir: true,
  record_history: true,
};

const cfg = reactive({ ...DEFAULTS });
const msg = ref('');
const msgType = ref('info');
const saving = ref(false);
const loading = ref(false);

async function load(showTip = false) {
  loading.value = true;
  try {
    const res = await props.api.get('plugin/Doc115Subscribe/get_config');
    const data = res && res.data !== undefined ? res.data : res;
    if (data && typeof data === 'object') Object.assign(cfg, { ...DEFAULTS, ...data });
    if (showTip) {
      msg.value = cfg.tencent_cookie
        ? `已读取到最新配置：腾讯文档 Cookie 已配置（${cfg.tencent_cookie.length} 字符）`
        : '已读取到最新配置：腾讯文档 Cookie 仍为空（请到「详情」页扫码登录）';
      msgType.value = cfg.tencent_cookie ? 'success' : 'warning';
    }
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}

async function save() {
  saving.value = true;
  try {
    const payload = { ...cfg };
    await props.api.post('plugin/Doc115Subscribe/save_config', payload);
    msg.value = '配置已保存';
    msgType.value = 'success';
    emit('save', payload);
  } catch (e) {
    msg.value = `保存失败：${e.message || e}`;
    msgType.value = 'error';
  } finally {
    saving.value = false;
    emit('action');
  }
}

onMounted(load);

return (_ctx, _cache) => {
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_textarea = _resolveComponent("v-textarea");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, { variant: "outlined" }, {
    default: _withCtx(() => [
      _createVNode(_component_v_card_title, { class: "text-subtitle-1" }, {
        default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
          _createTextVNode("115文档订阅与查询 · 设置", -1)
        ]))]),
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
            type: cfg.tencent_cookie ? 'success' : 'warning',
            variant: "tonal",
            density: "comfortable",
            class: "mb-3"
          }, {
            default: _withCtx(() => [
              _createTextVNode(" 腾讯文档 Cookie：" + _toDisplayString(cfg.tencent_cookie ? `已配置（${cfg.tencent_cookie.length} 字符）` : '未配置 —— 请到「详情」页扫码登录，或在此手动粘贴') + " ", 1),
              (cfg.tencent_cookie)
                ? (_openBlock(), _createElementBlock("span", _hoisted_1, "｜开头：" + _toDisplayString(cfg.tencent_cookie.slice(0, 24)) + "…", 1))
                : _createCommentVNode("", true)
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
              }),
              _createVNode(_component_v_col, {
                cols: "12",
                md: "4"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.use_agent,
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((cfg.use_agent) = $event)),
                    label: "类型不确定时调用 MP 智能体",
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
              _createVNode(_component_v_col, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.create_subdir,
                    "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.create_subdir) = $event)),
                    color: "primary",
                    "hide-details": "",
                    label: "转存时按「片名 (年份)」建子目录（推荐开启，便于 MP 整理识别）"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              }),
              _createVNode(_component_v_col, {
                cols: "12",
                md: "6"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_switch, {
                    modelValue: cfg.record_history,
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.record_history) = $event)),
                    color: "primary",
                    "hide-details": "",
                    label: "转存后写入 MP 下载历史（触发整理 / STRM 生成，强烈建议开启）"
                  }, null, 8, ["modelValue"])
                ]),
                _: 1
              })
            ]),
            _: 1
          }),
          (!cfg.record_history)
            ? (_openBlock(), _createBlock(_component_v_alert, {
                key: 1,
                type: "warning",
                variant: "tonal",
                density: "comfortable",
                class: "mt-3"
              }, {
                default: _withCtx(() => [...(_cache[14] || (_cache[14] = [
                  _createTextVNode(" 关闭「写入下载历史」后，MP 不会知道这次转存，文件会一直留在下载目录、不会被整理， 也不会触发 STRM 生成与媒体库刷新。 ", -1)
                ]))]),
                _: 1
              }))
            : _createCommentVNode("", true),
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
          _createVNode(_component_v_textarea, {
            modelValue: cfg.tencent_cookie,
            "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.tencent_cookie) = $event)),
            label: "腾讯文档 Cookie",
            variant: "outlined",
            density: "comfortable",
            rows: "3",
            class: "mt-3",
            "hide-details": "",
            hint: "推荐在「详情」页用扫码登录自动获取；也可手动粘贴。仅本地保存。",
            "persistent-hint": ""
          }, null, 8, ["modelValue"]),
          _createVNode(_component_v_textarea, {
            modelValue: cfg.p115_cookie,
            "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.p115_cookie) = $event)),
            label: "115 Cookie（留空则自动复用其它115插件）",
            variant: "outlined",
            density: "comfortable",
            rows: "2",
            class: "mt-4",
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
                    "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.index_cron) = $event)),
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
                    "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.subscribe_cron) = $event)),
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
            onClick: _cache[12] || (_cache[12] = $event => (load(true)))
          }, {
            default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
              _createTextVNode("重新读取配置", -1)
            ]))]),
            _: 1
          }, 8, ["loading"]),
          _createVNode(_component_v_spacer),
          _createVNode(_component_v_btn, {
            color: "primary",
            loading: saving.value,
            "prepend-icon": "mdi-content-save",
            onClick: save
          }, {
            default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
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
