import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


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
};

const cfg = reactive({ ...DEFAULTS });
const msg = ref('');
const msgType = ref('info');
const saving = ref(false);

async function load() {
  try {
    const res = await props.api.get('plugin/Doc115Subscribe/get_config');
    const data = res && res.data !== undefined ? res.data : res;
    if (data && typeof data === 'object') Object.assign(cfg, { ...DEFAULTS, ...data });
  } catch (e) {
    console.error(e);
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
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, { variant: "outlined" }, {
    default: _withCtx(() => [
      _createVNode(_component_v_card_title, { class: "text-subtitle-1" }, {
        default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
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
          _createVNode(_component_v_textarea, {
            modelValue: cfg.tencent_cookie,
            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.tencent_cookie) = $event)),
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
            "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.p115_cookie) = $event)),
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
                    "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.movie_path) = $event)),
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
                    "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.tv_path) = $event)),
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
                    "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.index_cron) = $event)),
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
                    "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.subscribe_cron) = $event)),
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
          _createVNode(_component_v_spacer),
          _createVNode(_component_v_btn, {
            color: "primary",
            loading: saving.value,
            "prepend-icon": "mdi-content-save",
            onClick: save
          }, {
            default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
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
