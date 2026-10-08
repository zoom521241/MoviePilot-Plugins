import { importShared } from './__federation_fn_import-SdO2Fg_T.js';
import _sfc_main$1 from './__federation_expose_Page-D6VQwYbD.js';

const {createVNode:_createVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

// 仅用于本地预览的桩数据：不连 MoviePilot 也能看到界面（含「转存记录」页的进度条）

const _sfc_main = {
  __name: 'App',
  setup(__props) {

const SAMPLE_RECORDS = [
  {
    id: '1', title: '独立日2：卷土重来[国英多音轨中文字幕].2016.UHD.BluRay.REMUX.2160p.HEVC.Atmos.TrueHD7.1.2Audio-DreamHD',
    year: '2016', type: 'movie', kind: 'magnet', status: 'downloading', progress: 46,
    staging_path: '/115-影视/115-downloads/磁力链接', final_path: '/115-影视/115-downloads/电影/独立日2：卷土重来 (2016)',
    message: '已提交离线下载，先落 /115-影视/115-downloads/磁力链接', submitted_at: '2026-10-08 15:09:21',
  },
  {
    id: '2', title: '流浪地球3 The Wandering Earth III 2027 2160p WEB-DL DDP5.1 Atmos',
    year: '2027', type: 'movie', kind: 'magnet', status: 'moving', progress: 100,
    staging_path: '/115-影视/115-downloads/磁力链接', final_path: '/115-影视/115-downloads/电影/流浪地球3 (2027)',
    message: '', submitted_at: '2026-10-08 14:52:03',
  },
  {
    id: '3', title: '肖申克的救赎 The Shawshank Redemption 1994 4K',
    year: '1994', type: 'movie', kind: '115_share', status: 'done', progress: 100,
    staging_path: '/115-影视/115-downloads/电影', final_path: '/115-影视/115-downloads/电影',
    message: '已转存到 /115-影视/115-downloads/电影，等待 115 整理', submitted_at: '2026-10-08 13:20:11',
  },
];

const SAMPLE_STATUS = {
  version: '0.6.0', enabled: true, cookie_ready: true, p115_ready: true, cookie_days_left: 29,
  record_count: 231659, sheet_count: 88, built_at_text: '2026-10-08 11:27',
};

const SAMPLE_RESULTS = [
  {
    sheet_id: '000010', sheet: '最新电影（持续更新）', row: 12,
    title: '流浪地球3 The Wandering Earth III', year: '2027', tmdbid: '843527',
    media_type: 'movie', quality_score: 3, qtext: '4K 中文字幕 2160p 20.4GB',
    bundle: false, sheet_bundle: false, no_link: false,
    links: [{ kind: 'magnet', url: 'magnet:?xt=urn:btih:9f2c1a7d4e5b6c8f0a1b2c3d4e5f60718293a4b5' }],
  },
  {
    sheet_id: '000010', sheet: '豆瓣电影Top250原盘', row: 4,
    title: '1.［肖申克的救赎 The Shawshank Redemption 1994］［4K］［DIY三次国三国配简繁+双语特效字幕］',
    year: '1994', tmdbid: '0111161', media_type: 'movie', quality_score: 3,
    qtext: '4K 国语 简繁 68.27GB', bundle: true, sheet_bundle: true, no_link: false,
    links: [{ kind: '115_share', url: 'https://115cdn.com/s/swfy5j833je?password=1314' }],
  },
];

const apiStub = {
  get: async (path) => {
    if (String(path).includes('/status')) return { code: 0, data: SAMPLE_STATUS }
    if (String(path).includes('/records')) return { code: 0, data: SAMPLE_RECORDS }
    return { code: 0, data: {} }
  },
  post: async (path) => {
    if (String(path).includes('/search')) return { code: 0, data: SAMPLE_RESULTS }
    return { code: 0, data: {} }
  },
};
function noop() {}

return (_ctx, _cache) => {
  const _component_v_container = _resolveComponent("v-container");
  const _component_v_main = _resolveComponent("v-main");
  const _component_v_app = _resolveComponent("v-app");

  return (_openBlock(), _createBlock(_component_v_app, null, {
    default: _withCtx(() => [
      _createVNode(_component_v_main, null, {
        default: _withCtx(() => [
          _createVNode(_component_v_container, null, {
            default: _withCtx(() => [
              _createVNode(_sfc_main$1, {
                api: apiStub,
                onAction: noop,
                onClose: noop
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
}
}

};

const {createApp} = await importShared('vue');
{
  createApp(_sfc_main).mount("#app");
}
