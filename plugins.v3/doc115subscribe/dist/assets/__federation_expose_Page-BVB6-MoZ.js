import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createTextVNode:_createTextVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,withKeys:_withKeys,renderList:_renderList,Fragment:_Fragment,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "doc115-page" };
const _hoisted_2 = ["src"];
const _hoisted_3 = { class: "text-caption mt-2" };
const _hoisted_4 = { class: "font-weight-medium" };
const _hoisted_5 = { key: 0 };
const _hoisted_6 = { class: "text-caption" };
const _hoisted_7 = { key: 0 };
const _hoisted_8 = { key: 1 };
const _hoisted_9 = { class: "text-caption text-medium-emphasis" };

const {onBeforeUnmount,onMounted,reactive,ref} = await importShared('vue');



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
  cookie_ready: false, p115_ready: false,
  record_count: 0, sheet_count: 0, built_at_text: '尚未建立',
});
const msg = ref('');
const msgType = ref('info');
const busy = reactive({ refresh: false, qr: false, search: false, subscribe: false, check: false });
const qrImage = ref('');
const qrTip = ref('等待扫码');
const keyword = ref('');
const results = ref([]);
const searched = ref(false);

let qrTimer = null;
let qrTick = 0;

function setMsg(text, type = 'info') {
  msg.value = text;
  msgType.value = type;
}

function close() {
  stopQrTimer();
  emit('close');
}

function linkNames(links) {
  const map = { '115_share': '115分享', magnet: '磁力', ed2k: 'ed2k', http: '网页' };
  return (links || []).map((l) => map[l.kind] || l.kind).join('、') || '无'
}

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
  busy.refresh = true;
  setMsg('正在刷新索引（90 张表，约 4~5 分钟），请稍候…');
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/refresh_index'));
    if (res.code === 0) {
      const d = res.data || {};
      setMsg(`索引刷新完成：${d.record_count || 0} 条记录 / ${d.sheet_count || 0} 张表`, 'success');
      await loadStatus();
    } else {
      setMsg(res.msg || '索引刷新失败', 'error');
    }
  } catch (e) {
    setMsg(`索引刷新失败：${e.message || e}`, 'error');
  } finally {
    busy.refresh = false;
    emit('action');
  }
}

// ---- 扫码登录 -----------------------------------------------------------
function stopQrTimer() {
  if (qrTimer) {
    clearInterval(qrTimer);
    qrTimer = null;
  }
}

function startQrTimer() {
  stopQrTimer();
  qrTick = 0;
  qrTimer = setInterval(async () => {
    qrTick += 1;
    // 每 3 秒自动检查；超过约 100 秒主动换新码，避免过期
    if (qrTick > 34) {
      qrTick = 0;
      await startQr(true);
      return
    }
    await checkQr(true);
  }, 3000);
}

async function startQr(silent = false) {
  busy.qr = !silent;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_start'));
    if (res.code === 0 && res.data && res.data.qr_base64) {
      qrImage.value = res.data.qr_base64;
      qrTip.value = '等待扫码';
      if (!silent) setMsg('二维码已生成，请用微信扫码（扫完会自动完成登录）');
      startQrTimer();
    } else if (!silent) {
      setMsg(res.msg || '获取二维码失败', 'error');
    }
  } catch (e) {
    if (!silent) setMsg(`获取二维码失败：${e.message || e}`, 'error');
  } finally {
    busy.qr = false;
  }
}

async function checkQr(silent = false) {
  if (!silent) busy.check = true;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_status'));
    const data = res.data || {};
    if (res.code === 0 && data.state === 'confirmed') {
      stopQrTimer();
      qrImage.value = '';
      setMsg('登录成功，Cookie 已保存！', 'success');
      await loadStatus();
      return
    }
    if (data.qr_base64) {
      // 过期换新码 / 失败后换新码
      qrImage.value = data.qr_base64;
      qrTip.value = '已换新码，请重新扫码';
    }
    if (res.code !== 0) {
      setMsg(res.msg || '检查失败', 'error');
      if (data.qr_base64) qrTip.value = '已换新码，请重新扫码';
      return
    }
    const map = {
      wait: '等待扫码',
      scanned: '已扫描，请在手机上确认登录',
      expired: '二维码已过期，已自动换新',
      failed: '本次登录失败，已换新码',
    };
    qrTip.value = map[data.state] || '等待扫码';
    if (!silent && data.state) setMsg(map[data.state] || '');
  } catch (e) {
    if (!silent) setMsg(`检查失败：${e.message || e}`, 'error');
  } finally {
    busy.check = false;
  }
}

// ---- 其他 ---------------------------------------------------------------
async function runSubscribe() {
  busy.subscribe = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/run_subscribe'));
    if (res.code === 0) {
      const d = res.data || {};
      setMsg(`订阅同步完成：命中 ${d.matched || 0} 条，转存 ${d.transferred || 0} 条`, 'success');
    } else {
      setMsg(res.msg || '订阅同步失败', 'error');
    }
  } catch (e) {
    setMsg(`订阅同步失败：${e.message || e}`, 'error');
  } finally {
    busy.subscribe = false;
    emit('action');
  }
}

async function doSearch() {
  const kw = (keyword.value || '').trim();
  if (!kw) {
    setMsg('请输入影视名称', 'warning');
    return
  }
  busy.search = true;
  searched.value = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/search', { keyword: kw }));
    if (res.code === 0) {
      results.value = res.data || [];
      setMsg(`「${kw}」找到 ${results.value.length} 条结果`);
    } else {
      results.value = [];
      setMsg(res.msg || '搜索失败', 'error');
    }
  } catch (e) {
    setMsg(`搜索失败：${e.message || e}`, 'error');
  } finally {
    busy.search = false;
    emit('action');
  }
}

async function transfer(index, to) {
  setMsg('正在转存，请稍候…');
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/transfer', {
      keyword: keyword.value || '',
      index,
      to,
    }));
    setMsg(res.msg || (res.code === 0 ? '转存完成' : '转存失败'), res.code === 0 ? 'success' : 'error');
  } catch (e) {
    setMsg(`转存失败：${e.message || e}`, 'error');
  } finally {
    emit('action');
  }
}

onMounted(loadStatus);
onBeforeUnmount(stopQrTimer);

return (_ctx, _cache) => {
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_chip = _resolveComponent("v-chip");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_row, {
      dense: "",
      align: "center",
      class: "mb-1"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, { cols: "10" }, {
          default: _withCtx(() => [...(_cache[1] || (_cache[1] = [
            _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "115文档订阅与查询", -1)
          ]))]),
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
                  default: _withCtx(() => [...(_cache[2] || (_cache[2] = [
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
      type: status.cookie_ready ? 'success' : 'warning',
      variant: "tonal",
      density: "comfortable",
      class: "mb-3"
    }, {
      default: _withCtx(() => [
        _createElementVNode("div", null, "腾讯文档 Cookie：" + _toDisplayString(status.cookie_ready ? '已配置' : '未配置（请用下方扫码登录）'), 1),
        _createElementVNode("div", null, " 本地索引：" + _toDisplayString(status.record_count) + " 条 / " + _toDisplayString(status.sheet_count) + " 张表，更新于 " + _toDisplayString(status.built_at_text) + " ｜115 Cookie：" + _toDisplayString(status.p115_ready ? '可用' : '未检测到'), 1)
      ]),
      _: 1
    }, 8, ["type"]),
    (msg.value)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
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
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "primary",
              loading: busy.refresh,
              "prepend-icon": "mdi-database-refresh",
              onClick: refreshIndex
            }, {
              default: _withCtx(() => [...(_cache[3] || (_cache[3] = [
                _createTextVNode(" 刷新索引 ", -1)
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
              color: "primary",
              loading: busy.qr,
              "prepend-icon": "mdi-qrcode",
              onClick: startQr
            }, {
              default: _withCtx(() => [
                _createTextVNode(_toDisplayString(qrImage.value ? '换一张二维码' : '获取登录二维码'), 1)
              ]),
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
              loading: busy.check,
              "prepend-icon": "mdi-check-decagram",
              onClick: checkQr
            }, {
              default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
                _createTextVNode(" 检查扫码状态 ", -1)
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
              default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
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
    (qrImage.value)
      ? (_openBlock(), _createBlock(_component_v_card, {
          key: 1,
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
                }, null, 8, _hoisted_2),
                _createElementVNode("div", _hoisted_3, " 用微信扫码登录腾讯文档（" + _toDisplayString(qrTip.value) + "） ", 1),
                _cache[6] || (_cache[6] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, " 二维码约 2~3 分钟过期，过期会自动换新；扫过一次后旧码即失效，需点「换一张二维码」。 ", -1))
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
                  md: "9"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: keyword.value,
                      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((keyword).value = $event)),
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
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      block: "",
                      color: "primary",
                      "prepend-icon": "mdi-magnify",
                      loading: busy.search,
                      onClick: doSearch
                    }, {
                      default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
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
    (results.value.length)
      ? (_openBlock(), _createBlock(_component_v_card, {
          key: 2,
          variant: "outlined"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, { class: "text-subtitle-1" }, {
              default: _withCtx(() => [
                _createTextVNode(" 搜索结果（" + _toDisplayString(results.value.length) + " 条，按 4K+中文字幕 优先排序） ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(results.value, (r, i) => {
                  return (_openBlock(), _createBlock(_component_v_card, {
                    key: i,
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
                                  _createElementVNode("div", _hoisted_4, [
                                    _createTextVNode(_toDisplayString(r.title), 1),
                                    (r.year)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_5, "（" + _toDisplayString(r.year) + "）", 1))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", _hoisted_6, [
                                    _createVNode(_component_v_chip, {
                                      size: "x-small",
                                      color: r.media_type === 'movie' ? 'blue' : 'green',
                                      class: "mr-1"
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(r.media_type === 'movie' ? '电影' : '电视剧'), 1)
                                      ]),
                                      _: 2
                                    }, 1032, ["color"]),
                                    (r.tmdbid)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_7, "TMDB:" + _toDisplayString(r.tmdbid) + "｜", 1))
                                      : _createCommentVNode("", true),
                                    _createTextVNode(" 来源表：" + _toDisplayString(r.sheet) + "｜规格：" + _toDisplayString(r.qtext || '—') + " ", 1),
                                    (r.bundle)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_8, "｜打包链接"))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", _hoisted_9, "链接类型：" + _toDisplayString(linkNames(r.links)), 1)
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
                                    color: "primary",
                                    onClick: $event => (transfer(i, 'movie'))
                                  }, {
                                    default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
                                      _createTextVNode("转存到电影", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"])
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
                                    onClick: $event => (transfer(i, 'tv'))
                                  }, {
                                    default: _withCtx(() => [...(_cache[9] || (_cache[9] = [
                                      _createTextVNode("转存到电视剧", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"])
                                ]),
                                _: 2
                              }, 1024)
                            ]),
                            _: 2
                          }, 1024)
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
      : (searched.value)
        ? (_openBlock(), _createBlock(_component_v_alert, {
            key: 3,
            type: "info",
            variant: "tonal"
          }, {
            default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
              _createTextVNode("没有找到匹配的资源，换个关键词试试。", -1)
            ]))]),
            _: 1
          }))
        : _createCommentVNode("", true)
  ]))
}
}

};

export { _sfc_main as default };
