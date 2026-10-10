<template>
  <v-app><v-main><v-container>
    <div class="doc115-preview-controls">
      <strong>合成测试预览 · 所有获取与搬运动作均为桩响应</strong>
      <label><input v-model="previewDark" type="checkbox" /> 深色主题</label>
      <label>内容宽度 <select v-model="previewWidth"><option value="100%">桌面</option><option value="320px">320 px</option><option value="360px">360 px</option><option value="390px">390 px</option></select></label>
      <label><input v-model="largeFont" type="checkbox" /> 200% 字体</label>
    </div>
    <div id="doc115-synthetic-host" :style="{ width: previewWidth, maxWidth: '100%' }">
      <PageComponent :api="apiStub" :model="{ dark: previewDark }" @action="noop" @close="noop" />
    </div>
    <details class="doc115-preview-log"><summary>合成接口调用记录</summary><pre>{{ JSON.stringify(calls, null, 2) }}</pre></details>
  </v-container></v-main></v-app>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import PageComponent from './components/Page.vue'

// Development-only test data. The mock transport never performs a network request.
const previewDark = ref(false), previewWidth = ref('100%'), largeFont = ref(false)
watch(largeFont, value => { document.documentElement.style.fontSize = value ? '32px' : '16px' })
const calls = reactive([])
const SAMPLE_STATUS = { version: '0.11.0', enabled: true, subscribe_enabled: true, cookie_ready: true, p115_ready: true, cookie_days_left: 29, record_count: 1234, sheet_count: 8, built_at_text: '2026-10-09 12:00', movie_path: '/合成115下载目录/电影', tv_path: '/合成115下载目录/电视剧', refreshing: false, index_errors: [], stale_sheets: [], last_subscribe: { success: true, msg: '合成：同步 3 部订阅，未提交资源' },
  stats: { movie: { total: 3, organized: 1 }, tv: { total: 2, organized: 0 }, total: 5, organized: 1, active: 1, attention: 2 },
  jobs: { index: { state: 'idle', msg: '', at: 0 }, subscribe: { state: 'idle', msg: '', at: 0 } } }
const SAMPLE_RESULTS = [
  { record_id: 'synthetic-tv', title: '合成电视剧的特别长中文标题用于移动端换行测试 第一季', sheet: '合成文档 · 电视剧', year: '2026', tmdbid: '0', media_type: 'tv', qtext: '4K 中文字幕 2160P HDR Atmos 全20集', match: '合成电视剧', links: [{ kind: '115_share', url: 'https://115.com/s/synthetic-not-real' }, { kind: 'magnet', url: 'magnet:?xt=urn:btih:synthetic-not-a-real-hash' }] },
  { record_id: 'synthetic-movie', title: '合成电影（不同年份与不同规格）', sheet: '合成文档 · 电影', year: '2025', media_type: 'movie', qtext: '1080P 无中字 国语 双语', links: [{ kind: 'ed2k', url: 'ed2k://|file|synthetic-not-real.mkv|0|invalid|/' }] },
  { record_id: 'synthetic-document', title: '仅文档示例', sheet: '合成文档索引', media_type: 'movie', qtext: '蓝光原盘 4K', no_link: true, links: [{ kind: 'http', url: 'https://example.invalid/document' }] },
]
const SAMPLE_RECORDS = [
  { id: 'partial20', title: '合成20集电视剧：整理前删除第20集', year: '2026', type: 'tv', kind: '115_share', hidden: false, tracking: false, acquisition_status: 'saved', organization_status: 'partial', final_path: '/合成115下载目录/电视剧/很长很长的中文分类目录用于验证320像素页面换行/合成电视剧第一季', message: '云端获取成功；19集已有本批次整理成功证据，第20集未找到。不会自动重新转存。', organization: { expected: 20, confirmed: 19, failed: 0, missing: 1, manifest_complete: true }, allowed_actions: ['verify'], files: [{ name: '合成电视剧 S01E20.mkv', status: 'unverified', message: '尚无本批次整理证据' }], submitted_at: '2026-10-09 12:00' },
  { id: 'uncertain', title: '合成电影 · 提交结果待确认', year: '2024', type: 'movie', kind: '115_share', hidden: false, tracking: true, acquisition_status: 'uncertain', organization_status: 'not_applicable', final_path: '/合成115下载目录/电影', message: '115 返回超时，未确认是否转存成功。', allowed_actions: ['reconcile', 'confirm_saved', 'stop_tracking'] },
  { id: 'downloading', title: '合成剧集 · 正常下载', type: 'tv', kind: 'magnet', hidden: false, tracking: true, acquisition_status: 'downloading', organization_status: 'pending', final_path: '/合成115下载目录/电视剧', staging_path: '/合成115下载目录/暂存', progress: 62, allowed_actions: ['check_download', 'stop_tracking'], next_check_at: '2026-10-09 12:02' },
  { id: 'complete', title: '合成电影 · 整理成功', year: '2023', type: 'movie', kind: '115_share', hidden: false, tracking: false, acquisition_status: 'saved', organization_status: 'success', organization: { expected: 1, confirmed: 1, manifest_complete: true }, final_path: '/合成115下载目录/电影', allowed_actions: ['verify'], qtext: '4K 中文字幕', updated_at: '2026-10-08 21:10' },
  { id: 'failed', title: '合成资源 · 获取明确失败', type: 'movie', kind: 'ed2k', hidden: false, tracking: false, acquisition_status: 'failed', organization_status: 'not_applicable', last_error: '合成鉴权错误，本插件不会继续提交', final_path: '/合成115下载目录/电影', allowed_actions: ['retry_submit'] },
]
const apiStub = {
  get: async (path, options) => {
    calls.push({ method: 'GET', path, params: options?.params })
    if (path.endsWith('/status')) return { code: 0, data: SAMPLE_STATUS }
    if (path.endsWith('/records')) {
      const p = options?.params || {}
      let rows = SAMPLE_RECORDS.filter(r => p.filter === 'hidden' ? r.hidden : !r.hidden)
      if (p.media && p.media !== 'all') rows = rows.filter(r => r.type === p.media)
      if (p.q) rows = rows.filter(r => r.title.toLowerCase().includes(String(p.q).toLowerCase()))
      if (p.filter === 'completed') rows = rows.filter(r => r.organization_status === 'success')
      return { code: 0, data: { records: rows, total: rows.length, page: 1, page_size: 10, stats: SAMPLE_STATUS.stats } }
    }
    if (path.endsWith('/get_config')) return { code: 0, data: { enabled: true, subscribe_enabled: true, tencent_cookie_ready: true, p115_cookie_ready: false, p115_ready: true, movie_path: SAMPLE_STATUS.movie_path, tv_path: SAMPLE_STATUS.tv_path, magnet_staging_path: '/合成115下载目录/暂存' } }
    if (path.endsWith('/subscriptions_preview')) return { code: 0, data: { records: [{ id: 'movie', title: '合成订阅电影', year: '2026', matched: 0, state: 'blocked', reason: '外部过滤规则组不能在文档记录中可靠校验，未自动下载', qtext: '4K 中文字幕', next_check_at: '2026-10-10 21:00' }], cache_empty: false, cached_at: 1791600000, msg: '本地预演，不提交资源' } }
    if (path.endsWith('/diagnostics')) return { code: 0, data: { summary: '本地索引与任务快照可读取；监控未确认。' } }
    return { code: 0, data: {} }
  },
  post: async (path, payload) => {
    calls.push({ method: 'POST', path, payload })
    if (path.endsWith('/search')) return { code: 0, data: { records: SAMPLE_RESULTS, total: SAMPLE_RESULTS.length, page: 1, page_size: 10, index_version: 'synthetic-v1' } }
    if (path.endsWith('/records_bulk')) return { code: 0, msg: '合成批量操作', data: { done: payload.ids.length, skipped: 0 } }
    return { code: 0, data: { state: 'queued' }, msg: '合成操作已排队；未进行真实转存、下载或移动。' }
  },
}
if (import.meta.env.DEV) window.__doc115Synthetic = { calls }
function noop() {}
</script>

<style scoped>
.doc115-preview-controls { display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem; }
.doc115-preview-controls select { border: 1px solid #7d8b9f; padding: 0.25rem; }
.doc115-preview-log pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
