import { importShared } from './__federation_fn_import-SdO2Fg_T.js';
import _sfc_main$1 from './__federation_expose_Page-D3JpcIBU.js';

const {createElementVNode:_createElementVNode,vModelCheckbox:_vModelCheckbox,withDirectives:_withDirectives,createTextVNode:_createTextVNode,vModelSelect:_vModelSelect,createVNode:_createVNode,normalizeStyle:_normalizeStyle,toDisplayString:_toDisplayString,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

const _hoisted_1 = { class: "doc115-preview-controls" };
const _hoisted_2 = { class: "doc115-preview-log" };
const {reactive,ref,watch} = await importShared('vue');
const _sfc_main = {
  __name: "App",
  setup(__props) {
    const previewDark = ref(false), previewWidth = ref("100%"), largeFont = ref(false);
    watch(largeFont, (value) => {
      document.documentElement.style.fontSize = value ? "32px" : "16px";
    });
    const calls = reactive([]);
    const SAMPLE_STATUS = { version: "preview", enabled: true, subscribe_enabled: false, cookie_ready: true, p115_ready: true, cookie_days_left: 29, record_count: 1234, sheet_count: 8, built_at_text: "2026-10-09 12:00", movie_path: "/合成115下载目录/电影", tv_path: "/合成115下载目录/电视剧" };
    const SAMPLE_RESULTS = [
      { record_id: "synthetic-tv", title: "合成电视剧的特别长中文标题用于移动端换行测试 第一季", sheet: "合成文档 · 电视剧", year: "2026", tmdbid: "0", media_type: "tv", qtext: "4K 中文字幕 2160P HDR Atmos 全20集", links: [{ kind: "115_share", url: "https://115.com/s/synthetic-not-real" }, { kind: "magnet", url: "magnet:?xt=urn:btih:synthetic-not-a-real-hash" }] },
      { record_id: "synthetic-movie", title: "合成电影（不同年份与不同规格）", sheet: "合成文档 · 电影", year: "2025", media_type: "movie", qtext: "1080P 无中字 国语 双语", links: [{ kind: "ed2k", url: "ed2k://|file|synthetic-not-real.mkv|0|invalid|/" }] },
      { record_id: "synthetic-document", title: "仅文档示例", sheet: "合成文档索引", media_type: "movie", qtext: "蓝光原盘 4K", no_link: true, links: [{ kind: "http", url: "https://example.invalid/document" }] }
    ];
    const SAMPLE_RECORDS = [
      { id: "partial20", title: "合成20集电视剧：整理前删除第20集", year: "2026", type: "tv", kind: "115_share", acquisition_status: "done", organization_status: "partial", final_path: "/合成115下载目录/电视剧/很长很长的中文分类目录用于验证320像素页面换行/合成电视剧第一季", message: "云端获取成功；19集已有本批次整理成功证据，第20集未找到。不会自动重新转存。", organization: { expected: 20, confirmed: 19, failed: 0, missing: 1, manifest_complete: true }, allowed_actions: ["verify"], files: [{ name: "合成电视剧 S01E20.mkv", status: "missing", message: "整理前被人为删除（合成证据）" }], submitted_at: "2026-10-09 12:00" },
      { id: "downloading", title: "合成剧集 · 正常下载", type: "tv", kind: "magnet", acquisition_status: "downloading", organization_status: "pending", final_path: "/合成115下载目录/电视剧", staging_path: "/合成115下载目录/暂存", progress: 62, allowed_actions: ["check_download", "stop_tracking"], next_check_at: "2026-10-09 12:02" },
      { id: "complete", title: "合成电影 · 整理成功", type: "movie", kind: "115_share", acquisition_status: "done", organization_status: "success", organization: { expected: 1, confirmed: 1, manifest_complete: true }, final_path: "/合成115下载目录/电影", allowed_actions: ["verify"], qtext: "4K 中文字幕" },
      { id: "failed", title: "合成资源 · 获取明确失败", type: "movie", kind: "ed2k", acquisition_status: "failed", organization_status: "not_applicable", last_error: "合成鉴权错误，本插件不会继续提交", final_path: "/合成115下载目录/电影", allowed_actions: [] }
    ];
    const apiStub = {
      get: async (path, options) => {
        calls.push({ method: "GET", path, params: options?.params });
        if (path.endsWith("/status")) return { code: 0, data: SAMPLE_STATUS };
        if (path.endsWith("/records")) return { code: 0, data: { records: SAMPLE_RECORDS, total: SAMPLE_RECORDS.length, page: 1, stats: { movie: { total: 2, organized: 1 }, tv: { total: 2, organized: 0 }, total: 4, organized: 1 } } };
        if (path.endsWith("/get_config")) return { code: 0, data: { ...SAMPLE_STATUS, subscribe_enabled: false, tencent_cookie_ready: true, movie_path: SAMPLE_STATUS.movie_path, tv_path: SAMPLE_STATUS.tv_path } };
        if (path.endsWith("/subscriptions_preview")) return { code: 0, data: { subscriptions: [{ id: "movie", title: "合成订阅电影", matched: false, reason: "过滤组无法评估：文档缺少发布信息", qtext: "4K 中文字幕" }], message: "合成缓存，没有提交资源" } };
        if (path.endsWith("/diagnostics")) return { code: 0, data: { summary: "本地索引与任务快照可读取；监控未确认。" } };
        return { code: 0, data: {} };
      },
      post: async (path, payload) => {
        calls.push({ method: "POST", path, payload });
        if (path.endsWith("/search")) return { code: 0, data: { records: SAMPLE_RESULTS, total: SAMPLE_RESULTS.length, page: 1, page_size: 10, index_version: "synthetic-v1" } };
        if (path.endsWith("/records_verify")) return { code: 0, data: { partial: 1 } };
        return { code: 0, data: { state: "queued" }, msg: "合成操作已排队；未进行真实转存、下载或移动。" };
      }
    };
    function noop() {
    }
    return (_ctx, _cache) => {
      const _component_v_container = _resolveComponent("v-container");
      const _component_v_main = _resolveComponent("v-main");
      const _component_v_app = _resolveComponent("v-app");
      return _openBlock(), _createBlock(_component_v_app, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_main, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_container, null, {
                default: _withCtx(() => [
                  _createElementVNode("div", _hoisted_1, [
                    _cache[7] || (_cache[7] = _createElementVNode("strong", null, "合成测试预览 · 所有获取与搬运动作均为桩响应", -1)),
                    _createElementVNode("label", null, [
                      _withDirectives(_createElementVNode("input", {
                        "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => previewDark.value = $event),
                        type: "checkbox"
                      }, null, 512), [
                        [_vModelCheckbox, previewDark.value]
                      ]),
                      _cache[3] || (_cache[3] = _createTextVNode(" 深色主题", -1))
                    ]),
                    _createElementVNode("label", null, [
                      _cache[5] || (_cache[5] = _createTextVNode("内容宽度 ", -1)),
                      _withDirectives(_createElementVNode("select", {
                        "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => previewWidth.value = $event)
                      }, [..._cache[4] || (_cache[4] = [
                        _createElementVNode("option", { value: "100%" }, "桌面", -1),
                        _createElementVNode("option", { value: "320px" }, "320 px", -1),
                        _createElementVNode("option", { value: "360px" }, "360 px", -1),
                        _createElementVNode("option", { value: "390px" }, "390 px", -1)
                      ])], 512), [
                        [_vModelSelect, previewWidth.value]
                      ])
                    ]),
                    _createElementVNode("label", null, [
                      _withDirectives(_createElementVNode("input", {
                        "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => largeFont.value = $event),
                        type: "checkbox"
                      }, null, 512), [
                        [_vModelCheckbox, largeFont.value]
                      ]),
                      _cache[6] || (_cache[6] = _createTextVNode(" 200% 字体", -1))
                    ])
                  ]),
                  _createElementVNode("div", {
                    id: "doc115-synthetic-host",
                    style: _normalizeStyle({ width: previewWidth.value, maxWidth: "100%" })
                  }, [
                    _createVNode(_sfc_main$1, {
                      api: apiStub,
                      model: { dark: previewDark.value },
                      onAction: noop,
                      onClose: noop
                    }, null, 8, ["model"])
                  ], 4),
                  _createElementVNode("details", _hoisted_2, [
                    _cache[8] || (_cache[8] = _createElementVNode("summary", null, "合成接口调用记录", -1)),
                    _createElementVNode("pre", null, _toDisplayString(JSON.stringify(calls, null, 2)), 1)
                  ])
                ]),
                _: 1
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      });
    };
  }
};

const {createApp} = await importShared('vue');
{
  createApp(_sfc_main).mount("#app");
}
