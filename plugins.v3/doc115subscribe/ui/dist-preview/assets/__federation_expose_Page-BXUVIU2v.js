import { importShared } from './__federation_fn_import-C6HT7yLm.js';

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
});
const msg = ref('');
const msgType = ref('info');
const busy = reactive({ refresh: false, qr: false, search: false, subscribe: false, check: false, offline: false });
const qrImage = ref('');
const qrTip = ref('等待扫码');
const keyword = ref('');
const results = ref([]);
const searched = ref(false);

// ---- 筛选与分页 ----
const page = ref(1);
const filterType = ref('all');
const filterQuality = ref('all');

const filtered = computed(() => {
  return results.value.filter((r) => {
    if (filterType.value !== 'all' && r.media_type !== filterType.value) return false
    if (filterQuality.value === '4k') {
      return /4k|2160p|uhd|蓝光|remux/i.test(`${r.qtext || ''} ${r.title || ''}`)
    }
    if (filterQuality.value === 'cn') {
      const t = `${r.qtext || ''} ${r.title || ''}`;
      if (/无中字|无字幕/i.test(t)) return false
      return /中文字幕|中字|简繁|国语|双语|简中|繁体/i.test(t)
    }
    return true
  })
});
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize)));
const paged = computed(() => {
  const start = (page.value - 1) * pageSize;
  return filtered.value.slice(start, start + pageSize)
});
watch([filterType, filterQuality, results], () => { page.value = 1; });

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
  return 'success'
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

function close() {
  stopQrTimer();
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
  busy.refresh = true;
  setMsg('正在刷新索引（90 张表，约 4~5 分钟），请稍候…');
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/refresh_index', {}, { timeout: 900000 }));
    if (res.code === 0) {
      const d = res.data || {};
      setMsg(`索引刷新完成：${d.record_count || 0} 条记录 / ${d.sheet_count || 0} 张表`, 'success');
      await loadStatus();
    } else {
      setMsg(res.msg || '索引刷新失败', 'error');
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
let qrTick = 0;

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
    if (qrTick > 34) {
      qrTick = 0;
      await startQr(true);
      return
    }
    await checkQr(true);
  }, 3000);
}

async function startQr(silent = false) {
  if (silent !== true) silent = false;
  busy.qr = !silent;
  stopQrTimer();
  if (!silent) setMsg('正在打开登录页并生成二维码（约 10~20 秒），请稍候…');
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_start', { timeout: 180000 }));
    if (res.code === 0 && res.data && res.data.qr_base64) {
      qrImage.value = res.data.qr_base64;
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
  if (silent !== true) silent = false;
  busy.check = !silent;
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_status', { timeout: 120000 }));
    const data = res.data || {};
    if (res.code === 0 && data.state === 'confirmed') {
      stopQrTimer();
      qrImage.value = '';
      setMsg('登录成功，Cookie 已保存！索引正在后台刷新，约 4~5 分钟后可搜索。', 'success');
      await loadStatus();
      return
    }
    if (data.qr_base64) {
      qrImage.value = data.qr_base64;
      qrTip.value = '已换新码，请重新扫码';
    }
    if (res.code !== 0) {
      setMsg(res.msg || '检查失败', 'error');
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
    if (!silent) setMsg(`检查失败：${describeError(e)}`, 'error');
  } finally {
    busy.check = false;
  }
}

// ---- 其它 ---------------------------------------------------------------
async function checkOffline() {
  busy.offline = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/check_offline', {}, { timeout: 180000 }));
    if (res.code === 0) {
      const d = res.data || {};
      setMsg(`离线任务检查完成：本轮通知整理 ${d.finished || 0} 条，仍在下载 ${d.pending || 0} 条`, 'success');
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
  busy.subscribe = true;
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/run_subscribe', {}, { timeout: 900000 }));
    if (res.code === 0) {
      const d = res.data || {};
      setMsg(`订阅同步完成：命中 ${d.matched || 0} 条，转存 ${d.transferred || 0} 条`, 'success');
    } else {
      setMsg(res.msg || '订阅同步失败', 'error');
    }
  } catch (e) {
    setMsg(`订阅同步失败：${describeError(e)}`, 'error');
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
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/search', { keyword: kw }, { timeout: 120000 }));
    if (res.code === 0) {
      results.value = res.data || [];
      page.value = 1;
      setMsg(`「${kw}」找到 ${results.value.length} 条结果`);
    } else {
      results.value = [];
      setMsg(res.msg || '搜索失败', 'error');
    }
  } catch (e) {
    setMsg(`搜索失败：${describeError(e)}`, 'error');
  } finally {
    busy.search = false;
    emit('action');
  }
}

async function transfer(pageIdx, to) {
  const rec = paged.value[pageIdx];
  if (!rec) return
  setMsg(`正在转存「${rec.title}」，请稍候…`);
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/transfer', {
      keyword: keyword.value || '',
      index: (page.value - 1) * pageSize + pageIdx,
      to,
    }, { timeout: 300000 }));
    setMsg(res.msg || (res.code === 0 ? '转存完成' : '转存失败'), res.code === 0 ? 'success' : 'error');
  } catch (e) {
    setMsg(`转存失败：${describeError(e)}`, 'error');
  } finally {
    emit('action');
  }
}

onMounted(loadStatus);
onBeforeUnmount(stopQrTimer);

return (_ctx, _cache) => {
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_pagination = _resolveComponent("v-pagination");

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
              _cache[6] || (_cache[6] = _createTextVNode(" 115文档订阅与查询 ", -1)),
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
                  default: _withCtx(() => [...(_cache[7] || (_cache[7] = [
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
          _cache[8] || (_cache[8] = _createTextVNode(" 本地索引：", -1)),
          _createElementVNode("span", _hoisted_4, _toDisplayString(status.record_count), 1),
          _cache[9] || (_cache[9] = _createTextVNode(" 条 / ", -1)),
          _createElementVNode("span", _hoisted_5, _toDisplayString(status.sheet_count), 1),
          _createTextVNode(" 张表， 更新于 " + _toDisplayString(status.built_at_text) + " ｜115 Cookie：", 1),
          _createElementVNode("span", {
            class: _normalizeClass(status.p115_ready ? 'text-green-darken-2' : 'text-red-darken-2')
          }, _toDisplayString(status.p115_ready ? '可用' : '未检测到'), 3)
        ])
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
              default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
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
              "prepend-icon": "mdi-qrcode",
              onClick: _cache[0] || (_cache[0] = $event => (startQr()))
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
          md: "2"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_btn, {
              block: "",
              color: "secondary",
              loading: busy.check,
              "prepend-icon": "mdi-check-decagram",
              onClick: _cache[1] || (_cache[1] = $event => (checkQr()))
            }, {
              default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
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
              loading: busy.offline,
              "prepend-icon": "mdi-download-network",
              onClick: checkOffline
            }, {
              default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
                _createTextVNode(" 检查离线下载并整理 ", -1)
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
              default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
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
                }, null, 8, _hoisted_6),
                _createElementVNode("div", _hoisted_7, "用微信扫码登录腾讯文档（" + _toDisplayString(qrTip.value) + "）", 1),
                _cache[14] || (_cache[14] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, " 二维码约 2~3 分钟过期，过期会自动换新；扫过一次后旧码即失效。 ", -1))
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
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((keyword).value = $event)),
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
                      default: _withCtx(() => [...(_cache[15] || (_cache[15] = [
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
            _createVNode(_component_v_card_title, { class: "text-subtitle-1 d-flex align-center flex-wrap" }, {
              default: _withCtx(() => [
                _cache[22] || (_cache[22] = _createElementVNode("span", null, "搜索结果", -1)),
                _createVNode(_component_v_chip, {
                  size: "x-small",
                  color: "primary",
                  class: "ml-2"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(results.value.length) + " 条", 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_chip, {
                  size: "x-small",
                  class: "ml-1"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode("筛选后 " + _toDisplayString(filtered.value.length) + " 条", 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn_toggle, {
                  modelValue: filterType.value,
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((filterType).value = $event)),
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
                      default: _withCtx(() => [...(_cache[16] || (_cache[16] = [
                        _createTextVNode("全部", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      value: "movie"
                    }, {
                      default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
                        _createTextVNode("电影", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      value: "tv"
                    }, {
                      default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                        _createTextVNode("电视剧", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                }, 8, ["modelValue"]),
                _createVNode(_component_v_btn_toggle, {
                  modelValue: filterQuality.value,
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((filterQuality).value = $event)),
                  density: "compact",
                  variant: "outlined",
                  mandatory: ""
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      size: "small",
                      value: "all"
                    }, {
                      default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                        _createTextVNode("不限画质", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      value: "4k"
                    }, {
                      default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                        _createTextVNode("4K", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      size: "small",
                      value: "cn"
                    }, {
                      default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                        _createTextVNode("中文字幕", -1)
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
                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(paged.value, (r, i) => {
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
                                  _createElementVNode("div", _hoisted_8, [
                                    _createTextVNode(_toDisplayString(r.title) + " ", 1),
                                    (r.year)
                                      ? (_openBlock(), _createElementBlock("span", _hoisted_9, "（" + _toDisplayString(r.year) + "）", 1))
                                      : _createCommentVNode("", true)
                                  ]),
                                  _createElementVNode("div", _hoisted_10, [
                                    _createVNode(_component_v_chip, {
                                      size: "x-small",
                                      color: r.media_type === 'movie' ? 'indigo' : 'teal',
                                      class: "mr-1"
                                    }, {
                                      default: _withCtx(() => [
                                        _createTextVNode(_toDisplayString(r.media_type === 'movie' ? '电影' : '电视剧'), 1)
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
                                          default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
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
                                    _cache[24] || (_cache[24] = _createElementVNode("span", { class: "text-medium-emphasis" }, "规格：", -1)),
                                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(specTokens(r.qtext), (tk, ti) => {
                                      return (_openBlock(), _createElementBlock("span", {
                                        key: ti,
                                        class: _normalizeClass(tk.color ? tk.color + ' font-weight-bold' : 'text-medium-emphasis')
                                      }, _toDisplayString(tk.text), 3))
                                    }), 128))
                                  ]),
                                  _createElementVNode("div", _hoisted_14, [
                                    _cache[25] || (_cache[25] = _createElementVNode("span", { class: "text-medium-emphasis" }, "链接：", -1)),
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
                                          onClick: $event => (transfer(i, 'movie'))
                                        }, {
                                          default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
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
                                          default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
                                            _createTextVNode("转存到电视剧", -1)
                                          ]))]),
                                          _: 1
                                        }, 8, ["onClick"])
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
                        _createTextVNode(" 第 " + _toDisplayString(page.value) + " / " + _toDisplayString(pageCount.value) + " 页，每页 " + _toDisplayString(pageSize) + " 条（共 " + _toDisplayString(filtered.value.length) + " 条） ", 1)
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_col, {
                      cols: "12",
                      md: "6"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_pagination, {
                          modelValue: page.value,
                          "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((page).value = $event)),
                          length: pageCount.value,
                          "total-visible": 6,
                          density: "comfortable",
                          size: "small"
                        }, null, 8, ["modelValue", "length"])
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
      : (searched.value)
        ? (_openBlock(), _createBlock(_component_v_alert, {
            key: 3,
            type: "info",
            variant: "tonal"
          }, {
            default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
              _createTextVNode(" 没有找到匹配的资源，换个关键词试试。 ", -1)
            ]))]),
            _: 1
          }))
        : _createCommentVNode("", true)
  ]))
}
}

};

export { _sfc_main as default };
