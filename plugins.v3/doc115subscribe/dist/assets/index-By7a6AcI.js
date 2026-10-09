import { importShared } from './__federation_fn_import-SdO2Fg_T.js';
import _sfc_main$1 from './__federation_expose_Page-D_pLF0Xr.js';

const {createVNode:_createVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');

// 仅用于本地预览的桩数据：不连 MoviePilot 也能看到界面（含「转存记录」页的进度条）

const _sfc_main = {
  __name: 'App',
  setup(__props) {

const SAMPLE_RECORDS = [
  {
    id: '1', title: '飞驰人生[60帧率版本][高码版][国语配音+中文字幕].Pegasus.2019.2160p.WEB-DL.H265.HQ.60fps',
    year: '2019', type: 'movie', kind: 'magnet', status: 'organized', progress: 100,
    staging_path: '/115-影视/115-downloads/磁力链接', final_path: '/115-影视/115-downloads/电影',
    message: '整理完成：本次资源已入库 1 个文件｜/115-影视/115-links/电影/华语电影/飞驰人生 (2019)/飞驰人生 (2019) - 2160p.mkv',
    submitted_at: '2026-10-08 18:29:38',
  },
  {
    id: '2', title: '肖申克的救赎 The Shawshank Redemption 1994 2160p 4K',
    year: '1994', type: 'movie', kind: '115_share', status: 'organized', progress: 100,
    staging_path: '/115-影视/115-downloads/电影', final_path: '/115-影视/115-downloads/电影',
    message: '整理完成：本次资源已入库 1 个文件｜/115-影视/115-links/电影/外语电影/肖申克的救赎 (1994)/肖申克的救赎 (1994) - 2160p.mkv',
    submitted_at: '2026-10-09 09:12:04',
  },
  {
    id: '3', title: '洛基 第二季[全6集][简繁英字幕].Loki.S02.2023.Hotstar.WEB-DL.2160p.HEVC.HDR.DDP',
    year: '2023', type: 'tv', kind: '115_share', status: 'organized', progress: 100,
    staging_path: '/115-影视/115-downloads/电视剧', final_path: '/115-影视/115-downloads/电视剧',
    message: '整理完成：本次资源已入库 6 个文件｜/115-影视/115-links/电视剧/欧美剧/洛基 (2021)/Season 2/洛基 - S02E06 - 第 6 集.mkv',
    submitted_at: '2026-10-08 18:53:10',
  },
  {
    id: '4', title: '流浪地球3 The Wandering Earth III 2027 2160p WEB-DL DDP5.1 Atmos',
    year: '2027', type: 'movie', kind: 'magnet', status: 'moving', progress: 100,
    staging_path: '/115-影视/115-downloads/磁力链接', final_path: '/115-影视/115-downloads/电影',
    message: '115已接收搬运请求，等待按文件ID确认目标目录', submitted_at: '2026-10-09 13:40:22',
  },
  {
    id: '5', title: '庆余年[第三季][全36集][国语中字].Joy.of.Life.S03.2026.2160p.WEB-DL',
    year: '2026', type: 'tv', kind: 'magnet', status: 'downloading', progress: 62,
    staging_path: '/115-影视/115-downloads/磁力链接', final_path: '/115-影视/115-downloads/电视剧',
    message: '离线下载中，先落 /115-影视/115-downloads/磁力链接', submitted_at: '2026-10-09 13:52:41',
  },
  {
    id: '6', title: '超级战舰4K原盘REMUX国英双音特效字幕',
    year: '2012', type: 'movie', kind: '115_share', status: 'failed', progress: 0,
    staging_path: '/115-影视/115-downloads/电影', final_path: '/115-影视/115-downloads/电影',
    message: '整理失败：目标路径已存在同名文件（阶段 transfer，重试 0 次）', submitted_at: '2026-10-09 10:05:33',
  },
];

const SAMPLE_STATUS = {
  version: '0.9.3', enabled: true, cookie_ready: true, p115_ready: true, cookie_days_left: 29,
  record_count: 231659, sheet_count: 88, built_at_text: '2026-10-08 11:27',
};

const SAMPLE_RESULTS = [
  {
    sheet_id: '000012', sheet: '最新电视剧（持续更新）', row: 8,
    title: '洛基 第二季[全6集][简繁英字幕].Loki.S02.2023.Hotstar.WEB-DL.2160p.HEVC.HDR.DDP5.1',
    year: '2023', tmdbid: '84958', media_type: 'tv', quality_score: 3,
    qtext: '4K 中文字幕 2160p 36.5GB 全6集',
    bundle: false, sheet_bundle: false, no_link: false,
    links: [{ kind: '115_share', url: 'https://115.com/s/swzuzpk369i?password=mayi' }],
  },
  {
    sheet_id: '000012', sheet: '最新电视剧（持续更新）', row: 9,
    title: '洛基.第一季[全6集][国英多音轨+简繁英字幕].Loki.S01.2021.2160p.DSNP.WEB-DL.DDP5.1.Atmos.H265',
    year: '2021', tmdbid: '84958', media_type: 'tv', quality_score: 3,
    qtext: '4K 国语 多音轨 2160p 31.2GB',
    bundle: false, sheet_bundle: false, no_link: false,
    links: [{ kind: 'magnet', url: 'magnet:?xt=urn:btih:9f2c1a7d4e5b6c8f0a1b2c3d4e5f60718293a4b5' }],
  },
  {
    sheet_id: '000003', sheet: '高清影视之家 1', row: 21,
    title: '【高清影视之家发布】洛基[合集][简繁字幕].Loki.S01-S02.2021-2023.2160p.WEB-DL',
    year: '2023', tmdbid: '', media_type: 'tv', quality_score: 2,
    qtext: '4K 中文字幕 合集 68.2GB',
    bundle: true, sheet_bundle: false, no_link: false,
    links: [{ kind: '115_share', url: 'https://115cdn.com/s/swhdic033mp?password=ayss' }],
  },
  {
    sheet_id: '000004', sheet: '蚂蚁和 rb4k', row: 3,
    title: '洛基恐怖秀[HDR+杜比视界双版本][简繁英字幕].1975.2160p.UHD.BluRay',
    year: '1975', tmdbid: '10700', media_type: 'movie', quality_score: 3,
    qtext: '4K 中文字幕 2160p 62.4GB',
    bundle: false, sheet_bundle: false, no_link: false,
    links: [{ kind: 'magnet', url: 'magnet:?xt=urn:btih:4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e' }],
  },
  {
    sheet_id: '000020', sheet: '目录索引（只管看）', row: 2,
    title: '洛基恐怖秀 Rocky Horror Picture Show 1975 蓝光原盘',
    year: '1975', tmdbid: '', media_type: 'movie', quality_score: 1,
    qtext: '蓝光原盘 1080p',
    bundle: false, sheet_bundle: false, no_link: true,
    links: [{ kind: 'http', url: 'https://docs.qq.com/sheet/DZWJxTU1Mak1XV0tj?tab=bb08j2' }],
  },
];

const apiStub = {
  get: async (path) => {
    if (String(path).includes('/status')) return { code: 0, data: SAMPLE_STATUS }
    if (String(path).includes('/records')) return { code: 0, data: SAMPLE_RECORDS }
    return { code: 0, data: {} }
  },
  post: async (path) => {
    if (String(path).includes('/search')) {
      // 搜索接口是分页结构（records/total/page/page_size/index_version）
      return { code: 0, data: {
        records: SAMPLE_RESULTS, total: SAMPLE_RESULTS.length, page: 1, page_size: 10,
        index_version: 'preview-v1', source_doc_id: 'preview',
      } }
    }
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
