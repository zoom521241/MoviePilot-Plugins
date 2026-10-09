<template>
  <section class="doc115-page" :data-doc115-theme="darkTheme ? 'dark' : 'light'" aria-label="115文档订阅与查询">
    <header class="doc115-header">
      <div><h2>115文档订阅与查询</h2><p class="doc115-muted">本地索引 {{ status.record_count || 0 }} 条 · {{ status.sheet_count || 0 }} 张表 · {{ status.enabled === false ? '插件已暂停' : '文档搜索与任务跟踪' }}</p></div>
      <div class="doc115-actions">
        <span class="doc115-muted doc115-version">前端 v{{ UI_BUILD }}<template v-if="status.version"> · 后端 v{{ status.version }}</template></span>
        <v-btn variant="text" size="small" prepend-icon="mdi-cog-outline" @click="settingsOpen = !settingsOpen">设置</v-btn>
        <v-btn icon size="small" variant="text" title="关闭" aria-label="关闭插件页面" @click="close"><v-icon>mdi-close</v-icon></v-btn>
      </div>
    </header>

    <v-alert v-if="msg" :type="msgType" variant="tonal" density="comfortable" class="doc115-feedback" role="status">{{ msg }}</v-alert>
    <v-alert v-if="status.version && status.version !== UI_BUILD" type="warning" variant="tonal" density="compact" class="doc115-feedback">前后端版本不同，请重新打开插件页面；若仍不同，请检查插件更新是否完成。</v-alert>
    <v-alert v-if="indexWarnings.length" type="warning" variant="tonal" density="compact" class="doc115-feedback">部分索引尚未更新：{{ indexWarnings.join('；') }}</v-alert>

    <section v-if="settingsOpen" class="doc115-panel doc115-settings-panel" aria-label="设置与维护">
      <Config :api="api" :model="model" @action="loadStatus" @close="settingsOpen = false" />
      <details class="doc115-maintenance" open>
        <summary>登录与维护</summary>
        <p class="doc115-muted">腾讯文档：{{ cookieText }} · 115：{{ status.p115_ready ? '已配置' : '未检测到' }} · 索引更新：{{ status.built_at_text || '尚未建立' }}</p>
        <div class="doc115-actions doc115-wrap">
          <v-btn size="small" variant="outlined" :loading="busy.qr" :disabled="busy.check" prepend-icon="mdi-qrcode" @click="startQr()">{{ qrImage ? '换一张二维码' : '扫码登录文档' }}</v-btn>
          <v-btn v-if="qrSessionId" size="small" variant="text" :loading="busy.check" :disabled="busy.qr" @click="checkQr()">检查扫码状态</v-btn>
          <v-btn size="small" variant="outlined" :loading="busy.refresh" @click="refreshIndex">刷新文档索引</v-btn>
          <v-btn size="small" variant="text" :loading="busy.diagnostics" @click="loadDiagnostics">查看本地诊断</v-btn>
        </div>
        <div v-if="qrImage" class="doc115-qr"><img :src="qrImage" alt="微信扫码登录腾讯文档" /><p>{{ qrTip }}</p><p class="doc115-muted">只扫描当前二维码；关闭设置后停止扫码状态检查。</p></div>
        <div v-if="diagnostics" class="doc115-diagnostic"><strong>本地诊断</strong><p>{{ diagnosticText }}</p><p class="doc115-muted">此操作只读取本插件状态，不测试真实转存。</p></div>
      </details>
    </section>

    <nav class="doc115-tabs" aria-label="插件功能">
      <button v-for="item in tabs" :key="item.value" type="button" :class="{ 'doc115-tab-active': tab === item.value }" :aria-current="tab === item.value ? 'page' : undefined" @click="tab = item.value">{{ item.label }}</button>
    </nav>

    <section v-if="tab === 'search'" aria-label="文档搜索">
      <div class="doc115-panel doc115-search-input">
        <v-text-field v-model="keyword" label="输入影视名称（跨全部工作表）" variant="outlined" density="comfortable" hide-details clearable @keyup.enter="doSearch" />
        <v-btn color="primary" prepend-icon="mdi-magnify" :loading="busy.search" @click="doSearch">搜索</v-btn>
      </div>
      <section v-if="searched" class="doc115-panel">
        <div class="doc115-section-heading"><h3>「{{ searchedKeyword }}」</h3><span class="doc115-chip doc115-blue">共 {{ total }} 条</span></div>
        <div class="doc115-filters">
          <label>媒体类型<select v-model="filterType"><option value="all">全部</option><option value="movie">电影</option><option value="tv">电视剧</option></select></label>
          <label>画质<select v-model="filterQuality"><option value="all">不限画质</option><option value="4k">4K</option></select></label>
          <label>字幕<select v-model="filterSubtitle"><option value="all">不限字幕</option><option value="cn">中文字幕 / 国语</option></select></label>
          <label>包含的链接<select v-model="filterLink"><option value="all">不限来源</option><option value="share">115分享</option><option value="magnet">磁力</option><option value="ed2k">ed2k</option><option value="doc">仅文档</option></select></label>
        </div>
        <p class="doc115-muted doc115-small">来源筛选表示条目包含此类链接；获取前会确认本次实际使用的来源和电影 / 电视剧目录。</p>
        <v-progress-linear v-if="busy.search" indeterminate color="primary" class="mb-2" />
        <p v-else-if="!results.length" class="doc115-empty">没有匹配资源，可调整筛选或关键词。</p>
        <article v-for="r in results" :key="r.record_id" class="doc115-resource-card">
          <h3 class="doc115-title">{{ r.title }} <span v-if="r.year" class="doc115-blue doc115-year">（{{ r.year }}）</span></h3>
          <div class="doc115-meta"><span class="doc115-chip" :class="r.media_type === 'movie' ? 'doc115-purple' : 'doc115-blue'">{{ mediaTypeName(r.media_type) }}</span><span v-if="r.bundle" class="doc115-chip doc115-orange">大包链接</span><span class="doc115-purple">来源：{{ r.sheet || '文档' }}</span><span v-if="r.tmdbid" class="doc115-muted">TMDB {{ r.tmdbid }}</span></div>
          <p class="doc115-spec"><span class="doc115-muted">规格：</span><span v-for="(token, i) in specTokens(r.qtext)" :key="i" :class="token.color || 'doc115-muted'">{{ token.text }}</span></p>
          <div class="doc115-links"><a v-for="(link, i) in r.links || []" :key="i" class="doc115-chip" :class="linkColor(link.kind)" :href="linkHref(link.url)" target="_blank" rel="noopener noreferrer"><v-icon size="small">{{ linkIcon(link.kind) }}</v-icon>{{ linkName(link.kind) }} · {{ shortUrl(link.url) }}</a></div>
          <div class="doc115-card-footer"><p v-if="r.sheet_bundle || r.no_link || r.bundle" class="doc115-muted">{{ r.no_link ? '此条目仅提供文档，请打开上方链接查看。' : '此条目是大包，已关闭一键获取，请打开原链接确认范围。' }}</p><template v-else><p class="doc115-muted">默认保存到{{ mediaTypeName(r.media_type === 'tv' ? 'tv' : 'movie') }}目录，可手动修改。</p><v-btn size="small" color="primary" :disabled="busy.search || !r.record_id || !!transferring[r.record_id]" :loading="!!transferring[r.record_id]" @click="prepareTransfer(r)">选择来源与保存目录</v-btn></template></div>
        </article>
        <div class="doc115-pagination"><span class="doc115-muted">第 {{ page }} / {{ pageCount }} 页 · 每页 {{ pageSize }} 条</span><v-pagination :model-value="page" :length="pageCount" :disabled="busy.search" :total-visible="3" density="comfortable" size="small" @update:model-value="changePage" /></div>
      </section>
    </section>

    <section v-else-if="tab === 'subscriptions'" class="doc115-panel" aria-label="电影订阅">
      <div class="doc115-section-heading"><h3>电影订阅</h3><span class="doc115-chip" :class="status.subscribe_enabled ? 'doc115-green' : 'doc115-neutral'">{{ status.subscribe_enabled ? '自动同步已启用' : '自动同步已关闭' }}</span></div>
      <p class="doc115-muted">读取已缓存的 MP 电影订阅和文档匹配结果。订阅创建、编辑和整理由 MP 处理。</p>
      <div class="doc115-actions doc115-wrap"><v-btn variant="outlined" size="small" :loading="busy.preview" @click="loadSubscriptions">刷新匹配预演（只读）</v-btn><v-btn variant="outlined" size="small" :loading="busy.subscribe" :disabled="status.enabled === false || !status.subscribe_enabled" @click="runSubscribe">同步并获取匹配资源</v-btn></div>
      <p v-if="status.last_subscribe" class="doc115-small" :class="status.last_subscribe.success === false ? 'doc115-red' : 'doc115-muted'">最近同步：{{ status.last_subscribe.msg || status.last_subscribe.error || '已完成' }}</p>
      <p class="doc115-muted doc115-small">{{ subscriptionNote }}</p>
      <article v-for="(s, i) in subscriptions" :key="s.id || i" class="doc115-resource-card"><h3 class="doc115-title">{{ s.title || s.name || '电影订阅' }} <span v-if="s.year" class="doc115-blue">{{ s.year }}</span></h3><p :class="s.matched ? 'doc115-green' : 'doc115-amber'">{{ s.reason || s.message || (s.matched ? '匹配到可用资源' : '当前没有匹配资源') }}</p><p class="doc115-spec"><span v-for="(token, j) in specTokens(s.qtext || s.quality || '')" :key="j" :class="token.color || 'doc115-muted'">{{ token.text }}</span></p><p v-if="s.next_check_at" class="doc115-muted">下次计划：{{ formatTime(s.next_check_at) }}</p></article>
    </section>

    <section v-else class="doc115-panel" aria-label="任务记录">
      <div class="doc115-section-heading"><h3>任务</h3><span class="doc115-chip doc115-blue">{{ recordsTotal }} 条</span><v-btn size="small" variant="text" :loading="busy.records" @click="loadRecords">刷新状态</v-btn></div>
      <div class="doc115-filters"><label>任务范围<select v-model="recordsFilter"><option value="all">全部</option><option value="active">进行中</option><option value="needs_attention">需要处理</option><option value="completed">已完成</option></select></label></div>
      <p class="doc115-muted doc115-small">页面刷新只读取本地任务。获取、搬运与 MP 整理分别确认；MP 整理成功不代表媒体服务器已收录。</p>
      <p v-if="!records.length" class="doc115-empty">此范围暂无任务。</p>
      <article v-for="r in records" :key="r.id" class="doc115-resource-card doc115-record-row" :style="{ '--doc115-status-color': statusCss(r) }">
        <div class="doc115-section-heading"><h3 class="doc115-title">{{ r.title }} <span v-if="r.year" class="doc115-blue doc115-year">（{{ r.year }}）</span></h3><span class="doc115-chip" :class="kindColor(r.kind)">{{ kindName(r.kind) }}</span></div>
        <div class="doc115-stage"><span class="doc115-chip" :class="statusColor(acquisitionState(r))">{{ statusName(acquisitionState(r)) }}</span><span aria-hidden="true">→</span><span class="doc115-chip" :class="statusColor(organizationState(r))">{{ organizationSummary(r) }}</span></div>
        <p class="doc115-cyan doc115-path">目标：{{ r.final_path || '待确认' }}</p>
        <div v-if="acquisitionState(r) === 'downloading'" class="doc115-download"><label>115 下载进度：{{ progressValue(r) }}%<progress :value="progressValue(r)" max="100" /></label><p v-if="progressValue(r) === 100" class="doc115-amber">下载已显示 100%，文件落盘与搬运仍需确认。</p></div>
        <p v-if="r.message" class="doc115-small doc115-message">{{ r.message }}</p><p v-if="r.query_error || r.last_error" class="doc115-red doc115-small">{{ r.query_error ? '核对查询失败：' : '最近错误：' }}{{ r.query_error || r.last_error }}</p>
        <div class="doc115-meta doc115-small doc115-muted"><span>{{ formatTime(r.updated_at || r.submitted_at) }}</span><span v-if="r.next_check_at">下次核对：{{ formatTime(r.next_check_at) }}</span><span v-if="r.pause_reason">暂停：{{ r.pause_reason }}</span></div>
        <div class="doc115-actions doc115-wrap doc115-task-actions">
          <v-btn v-if="needsVerify(r)" size="small" variant="outlined" :loading="!!verifying[r.id]" :disabled="busy.records || !!verifying[r.id]" @click="verifyOne(r)">核对 MP 整理</v-btn>
          <v-btn v-if="hasAction(r, 'check_download')" size="small" variant="text" :loading="!!retrying[r.id]" @click="taskAction(r, 'check_download')">重查下载状态</v-btn>
          <v-btn v-if="hasAction(r, 'retry_move')" size="small" variant="text" :loading="!!retrying[r.id]" @click="taskAction(r, 'retry_move')">重试搬运</v-btn>
          <v-btn v-if="hasAction(r, 'retry_submit')" size="small" variant="text" :loading="!!retrying[r.id]" @click="retrySubmit(r)">重新获取（此前未获取成功）</v-btn>
          <a v-if="hasAction(r, 'mp_history') && safeMpUrl(r.mp_url)" class="doc115-native-link doc115-blue" :href="safeMpUrl(r.mp_url)">前往 MP 处理</a>
          <v-btn v-if="hasAction(r, 'stop_tracking')" size="small" variant="text" @click="cancelTask(r)">停止自动跟踪</v-btn>
        </div>
        <details class="doc115-details"><summary>查看详情</summary><p v-if="r.sheet" class="doc115-purple">文档来源：{{ r.sheet }}</p><p class="doc115-spec"><span v-for="(token, i) in specTokens(r.qtext || r.quality || '')" :key="i" :class="token.color || 'doc115-muted'">{{ token.text }}</span></p><p v-if="r.staging_path && r.staging_path !== r.final_path" class="doc115-cyan doc115-path">离线暂存：{{ r.staging_path }}</p><p class="doc115-muted">{{ manifestText(r) }}</p><ul v-if="fileDetails(r).length"><li v-for="(file, i) in fileDetails(r)" :key="file.id || file.file_id || i"><span :class="file.status === 'success' ? 'doc115-green' : file.status === 'failed' || file.status === 'missing' ? 'doc115-red' : 'doc115-neutral'">{{ file.name || file.path || '媒体文件' }} · {{ file.message || statusName(file.status) }}</span></li></ul><p v-if="r.ignored_files?.length" class="doc115-muted">附带小视频 {{ r.ignored_files.length }} 个，不计入必要整理数；删除这些文件不影响主要资源状态。</p><ul v-if="r.ignored_files?.length"><li v-for="(file, i) in r.ignored_files" :key="i" class="doc115-muted">{{ file.name }} · {{ file.reason }}</li></ul><v-btn size="small" variant="text" @click="deleteRecord(r)">删除展示记录</v-btn></details>
      </article>
      <div class="doc115-pagination"><span class="doc115-muted">第 {{ recordsPage }} / {{ recordsPageCount }} 页</span><v-pagination :model-value="recordsPage" :length="recordsPageCount" :disabled="busy.records" :total-visible="3" size="small" @update:model-value="changeRecordsPage" /></div>
      <details class="doc115-maintenance"><summary>任务管理</summary><p class="doc115-muted">以下处理只针对本插件任务。处理待搬运任务会移动其已确认的云端文件，遵守后台预算和冷却。</p><div class="doc115-actions doc115-wrap"><v-btn size="small" variant="outlined" :loading="busy.offline" @click="checkOffline">处理待搬运任务（会移动文件）</v-btn><v-btn size="small" variant="text" :disabled="!recordsTotal" @click="clearRecords">清空展示记录</v-btn></div></details>
    </section>

    <v-dialog v-model="transferOpen" max-width="560">
      <section class="doc115-page doc115-confirm" :data-doc115-theme="darkTheme ? 'dark' : 'light'">
        <h3>确认获取资源</h3><p class="doc115-title">{{ transferRecord?.title }}</p>
        <label class="doc115-form-label">保存到<select v-model="transferTarget"><option value="movie">电影目录</option><option value="tv">电视剧目录</option></select></label>
        <p class="doc115-cyan doc115-path">{{ transferTarget === 'tv' ? status.tv_path : status.movie_path || '使用已配置的下载目录' }}</p>
        <label class="doc115-form-label">本次实际来源<select v-model="transferSource"><option v-for="option in sourceOptions(transferRecord)" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
        <p class="doc115-muted doc115-small">只提交所选链接，不自动切换其它来源。磁力 / ed2k 先由 115 下载，完成后借助 Plus 搬到所选目录；整理交由 MP 已配置的流程处理。</p>
        <div class="doc115-actions doc115-wrap"><v-btn variant="text" @click="transferOpen = false">取消</v-btn><v-btn color="primary" :disabled="!transferSource || !transferRecord" :loading="!!transferring[transferRecord?.record_id]" @click="confirmTransfer">确认获取</v-btn></div>
      </section>
    </v-dialog>
  </section>
</template>

<script setup>
import { computed, inject, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import Config from './Config.vue'
import '../styles/doc115.css'

const props = defineProps({ model: { type: Object, default: () => ({}) }, api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) } })
const emit = defineEmits(['action', 'close'])
const UI_BUILD = '0.10.0'
const hostTheme = inject(Symbol.for('vuetify:theme'), null)
const darkTheme = computed(() => !!(props.model?.dark ?? hostTheme?.current?.value?.dark))
const pageSize = 10
const status = reactive({ version: '', enabled: null, subscribe_enabled: false, cookie_ready: false, p115_ready: false, cookie_days_left: null, record_count: 0, sheet_count: 0, built_at_text: '尚未建立', index_errors: [], stale_sheets: [], last_refresh: null, last_subscribe: null })
const msg = ref(''), msgType = ref('info')
const busy = reactive({ refresh: false, qr: false, search: false, subscribe: false, check: false, offline: false, records: false, preview: false, diagnostics: false })
const qrImage = ref(''), qrTip = ref('等待扫码'), qrSessionId = ref('')
const settingsOpen = ref(false), diagnostics = ref(null)
const keyword = ref(''), results = ref([]), searched = ref(false), searchedKeyword = ref(''), total = ref(0), resultVersion = ref('')
const transferring = reactive({}), retrying = reactive({}), verifying = reactive({})
const tabs = [{ value: 'search', label: '搜索' }, { value: 'subscriptions', label: '电影订阅' }, { value: 'records', label: '任务' }]
const tab = ref('search'), records = ref([]), recordsTotal = ref(0), recordsPage = ref(1), recordsFilter = ref('all')
const subscriptions = ref([]), subscriptionNote = ref('匹配预演只读取本地缓存，不提交资源。')
const page = ref(1), filterType = ref('all'), filterQuality = ref('all'), filterSubtitle = ref('all'), filterLink = ref('all')
const transferOpen = ref(false), transferRecord = ref(null), transferTarget = ref('movie'), transferSource = ref(''), transferIndexVersion = ref('')
let searchSerial = 0, searchController = null, searchDebounce = null, disposed = false, componentActive = true
let recTimer = null, recFailures = 0, recUnchanged = 0, lastRecordsSnapshot = '', recordsSerial = 0, recController = null
let qrTimer = null, qrGeneration = 0
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const recordsPageCount = computed(() => Math.max(1, Math.ceil(recordsTotal.value / pageSize)))
const indexWarnings = computed(() => [...new Set([...(status.index_errors || []).map(String), ...(status.stale_sheets || []).map(s => typeof s === 'string' ? `保留旧索引：${s}` : `保留旧索引：${s.title || s.name || s.sheet_id || '未知工作表'}`)])])
const cookieText = computed(() => !status.cookie_ready ? '未配置，请扫码登录' : status.cookie_days_left == null ? '已配置' : `已配置，剩余约 ${Math.floor(status.cookie_days_left)} 天`)
const diagnosticText = computed(() => {
  const data = diagnostics.value || {}, cloud = data.cloud || {}, mp = data.mp || {}
  if (data.summary || data.message || data.msg) return data.summary || data.message || data.msg
  return `活动任务 ${data.active_tasks || 0} 个 · 115：${cloud.reason || cloud.state || '按预算处理'} · MP：${mp.last_error || mp.state || (mp.port_ready ? '只读接口已确认' : '只读接口待验证')}${cloud.reason && cloud.retry_at ? ` · 下次允许请求：${formatTime(cloud.retry_at)}` : ''}`
})
function mediaTypeName(type) { return ({ movie: '电影', tv: '电视剧' })[type] || '类型待确认' }
function setMsg(text, type = 'info') { if (!disposed) { msg.value = text; msgType.value = type } }
function unwrap(res) { return res && typeof res === 'object' && 'code' in res ? res : { code: 0, msg: '', data: res } }
function describeError(e) { return e?.response?.status === 403 ? '当前账号没有权限' : e?.message || '请求失败，请稍后重试' }
function formatTime(value) { if (!value) return '时间待确认'; if (typeof value === 'number') return new Date(value < 1e12 ? value * 1000 : value).toLocaleString(); return String(value) }

const LINK_STYLE = { '115_share': { color: 'doc115-cyan', name: '115分享', icon: 'mdi-cloud-download' }, magnet: { color: 'doc115-orange', name: '磁力', icon: 'mdi-magnet' }, ed2k: { color: 'doc115-brown', name: 'ed2k', icon: 'mdi-link-variant' }, http: { color: 'doc115-neutral', name: '文档 / 网页', icon: 'mdi-web' } }
function linkColor(kind) { return LINK_STYLE[kind]?.color || 'doc115-neutral' }
function linkName(kind) { return LINK_STYLE[kind]?.name || kind || '来源待确认' }
function linkIcon(kind) { return LINK_STYLE[kind]?.icon || 'mdi-link' }
function kindName(kind) { return linkName(kind) }
function kindColor(kind) { return linkColor(kind) }
function shortUrl(url) { const value = String(url || '').replace(/^https?:\/\//i, ''); return value.length > 44 ? value.slice(0, 44) + '…' : value }
function linkHref(url) {
  const value = String(url || '').trim()
  if (/^(https?:\/\/|magnet:\?|ed2k:\/\/)/i.test(value)) return value
  if (/^(?:www\.)?(?:115\.com|115cdn\.com|anxia\.com|docs\.qq\.com)\//i.test(value)) return 'https://' + value
  return undefined
}
function safeMpUrl(url) { const value = String(url || ''); return /^\/(?!\/)[^\\]*$/.test(value) && !/[\u0000-\u001f]/.test(value) ? value : undefined }
const SPEC_RE = /(4K|2160[pP]|1080[pP]|720[pP]|REMUX|UHD|HDR10\+?|HDR|杜比视界|Dolby\s?Vision|Atmos|蓝光原盘|原盘|中文字幕|简繁|简体|繁体|国语|双语|粤语|无中字)/gi
function specTokens(text) {
  const value = String(text || '')
  if (!value) return [{ text: '规格待确认', color: 'doc115-neutral' }]
  const parts = []; let last = 0, match; SPEC_RE.lastIndex = 0
  while ((match = SPEC_RE.exec(value)) !== null) {
    if (match.index > last) parts.push({ text: value.slice(last, match.index), color: '' })
    const word = match[0].toUpperCase()
    const color = /无中字/.test(word) ? 'doc115-red' : /中文字幕|简繁|简体|繁体|国语|双语|粤语/.test(word) ? 'doc115-green' : 'doc115-amber'
    parts.push({ text: match[0], color }); last = match.index + match[0].length
  }
  if (last < value.length) parts.push({ text: value.slice(last), color: '' })
  return parts
}
const STATUS_STYLE = {
  submitting: ['提交中', 'blue'], submitted: ['115已接受，结果待确认', 'blue'], uncertain: ['提交结果待确认', 'amber'], downloading: ['115下载中', 'blue'], waiting: ['等待文件落盘', 'amber'], awaiting_move: ['等待搬运', 'amber'], moving: ['搬运中', 'blue'], queued: ['已排队', 'blue'], done: ['已保存到下载目录', 'green'], moved: ['已保存到下载目录', 'green'], saved: ['已保存到下载目录', 'green'], acquired: ['云端已保存', 'green'], missing: ['文件位置待核实', 'amber'], unverified: ['MP整理待核实', 'neutral'], pending: ['MP整理待核实', 'neutral'], unknown: ['证据不足，待核实', 'neutral'], incomplete: ['清单不完整，待核实', 'amber'], organizing: ['MP整理中', 'blue'], partial: ['MP部分整理成功', 'orange'], unfound: ['暂无本批次整理证据', 'neutral'], organized: ['MP整理成功', 'green'], success: ['MP整理成功', 'green'], confirmed: ['MP整理成功', 'green'], failed: ['失败，需要处理', 'red'], query_error: ['核对查询失败', 'red'], paused: ['自动核对已暂停', 'neutral'], cancelled: ['已停止自动跟踪', 'neutral'], stopped: ['已停止自动跟踪', 'neutral'], not_started: ['MP整理待核实', 'neutral'], not_applicable: ['暂不核对整理', 'neutral']
}
function statusName(value) { return STATUS_STYLE[value]?.[0] || value || '待核实' }
function statusColor(value) { return 'doc115-' + (STATUS_STYLE[value]?.[1] || 'neutral') }
function acquisitionState(r) { const state = r.acquisition_status || r.acquisition?.status || (r.organization_confirmed || r.status === 'organized' ? 'done' : r.status); return state === 'success' ? 'saved' : state }
function organizationState(r) { return r.organization_status || r.organization?.status || (r.organization_confirmed ? 'organized' : ['partial', 'unverified', 'unfound'].includes(r.status) ? r.status : 'pending') }
function statusCss(r) { const state = r.query_error ? 'query_error' : acquisitionState(r) === 'failed' ? 'failed' : isActiveTask(r) || ['pending', 'not_applicable', 'not_started'].includes(organizationState(r)) ? acquisitionState(r) : organizationState(r); return `var(--doc115-${STATUS_STYLE[state]?.[1] || 'neutral'})` }
function organizationCounts(r) { const o = r.organization || {}; return { confirmed: Number(o.confirmed ?? r.organization_count ?? r.organized_count ?? 0), expected: Number(o.expected ?? r.expected_count ?? r.organized_total ?? 0), failed: Number(o.failed ?? r.organization_failed_count ?? r.organized_failed ?? 0), missing: Number(o.missing ?? r.organized_missing ?? 0), complete: !!(o.manifest_complete ?? r.manifest_complete) } }
function organizationSummary(r) { const counts = organizationCounts(r); return statusName(organizationState(r)) + (counts.expected ? ` · ${counts.confirmed}/${counts.expected}` : counts.confirmed ? ` · 已确认 ${counts.confirmed} 个` : '') + (counts.missing ? ` · ${counts.missing} 个待核实` : '') }
function manifestText(r) { const counts = organizationCounts(r); return counts.complete ? `必要清单完整：已确认 ${counts.confirmed}/${counts.expected} 个${counts.failed ? `，失败 ${counts.failed} 个` : ''}${counts.missing ? `，${counts.missing} 个暂无整理证据` : ''}` : `已确认 ${counts.confirmed} 个，必要文件清单完整性待核实。` }
function fileDetails(r) { return Array.isArray(r.files) ? r.files : Array.isArray(r.organization?.files) ? r.organization.files : [] }
function progressValue(r) { return Math.max(0, Math.min(100, Number(r.progress) || 0)) }
function hasAction(r, action) { return Array.isArray(r.allowed_actions) && r.allowed_actions.some(a => (typeof a === 'string' ? a : a.action || a.name) === action) }
function needsVerify(r) { return Array.isArray(r.allowed_actions) ? hasAction(r, 'verify') || hasAction(r, 'verify_organization') : !r.organization_confirmed && r.status !== 'failed' }
function isActiveTask(r) { return r.tracking_enabled !== false && !['cancelled', 'stopped', 'paused'].includes(acquisitionState(r)) && ['submitting', 'submitted', 'uncertain', 'downloading', 'waiting', 'awaiting_move', 'moving', 'queued'].includes(acquisitionState(r)) }
function isPendingOrganize(r) { return r.tracking_enabled !== false && !r.org_giveup && !r.tracking_stopped && !['organized', 'success', 'confirmed', 'paused', 'cancelled', 'stopped', 'not_applicable'].includes(organizationState(r)) && ['done', 'moved', 'saved', 'acquired'].includes(acquisitionState(r)) }

function resultFeedback(res, fallback) {
  const data = res.data || {}
  if (res.code !== 0 || data.query_error || Number(data.query_errors) > 0 || (Array.isArray(data.query_errors) && data.query_errors.length) || data.result === 'query_error') return [res.msg || data.message || '核对查询失败，已获取的资源保持不变。', 'error']
  if (data.failed || data.result === 'failed') return [res.msg || data.message || '发现失败项目，请查看任务详情并前往 MP 处理。', 'error']
  if (data.partial || data.result === 'partial') return [res.msg || data.message || '部分完成，尚有文件需要处理；不会重新获取已保存资源。', 'warning']
  if (data.confirmed || data.result === 'organized') return [res.msg || data.message || '本批次必要文件已确认 MP 整理成功。', 'success']
  if (data.queued || data.result === 'queued' || data.state === 'queued' || data.operation_id) return [res.msg || data.message || '已加入后台队列，任务页可查看进度。', 'info']
  if (data.paused || data.result === 'paused') return [res.msg || data.message || '自动核对已暂停，请查看暂停原因。', 'warning']
  if (data.unfound || data.result === 'unverified') return [res.msg || data.message || '暂无本批次整理证据，不能据此判断文件丢失。', 'warning']
  if (data.skipped || data.result === 'skipped') return [res.msg || data.message || '当前无需执行此操作。', 'info']
  return [res.msg || data.message || fallback, 'info']
}
function showResult(res, fallback) { setMsg(...resultFeedback(res, fallback)) }
async function verifyOne(r) {
  if (!r?.id || verifying[r.id]) return
  verifying[r.id] = true
  try { showResult(unwrap(await props.api.post('plugin/Doc115Subscribe/records_verify', { id: r.id }, { timeout: 30000 })), '核对已完成，详细结果请查看任务。') }
  catch (e) { setMsg(`核对失败：${describeError(e)}`, 'error') }
  finally { verifying[r.id] = false }
  await loadRecords()
}
async function loadRecords() {
  if (busy.records || disposed) return false
  const serial = ++recordsSerial
  busy.records = true
  recController = typeof AbortController === 'function' ? new AbortController() : null
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/records', { params: { page: recordsPage.value, page_size: pageSize, filter: recordsFilter.value }, signal: recController?.signal, timeout: 30000 }))
    if (disposed || serial !== recordsSerial) return false
    if (res.code !== 0) throw new Error(res.msg || '读取任务失败')
    const data = res.data || []
    if (Array.isArray(data)) { records.value = data; recordsTotal.value = data.length }
    else { records.value = Array.isArray(data.records) ? data.records : []; recordsTotal.value = Number(data.total) || 0; recordsPage.value = Number(data.page) || recordsPage.value }
    const snapshot = JSON.stringify(records.value.map(r => [r.id, r.status, r.acquisition_status, r.organization_status, r.progress, r.organization, r.query_error, r.last_error, r.updated_at, r.allowed_actions]))
    recUnchanged = snapshot === lastRecordsSnapshot ? recUnchanged + 1 : 0
    lastRecordsSnapshot = snapshot
    recFailures = 0
    return true
  } catch (e) { if (!disposed && serial === recordsSerial && e.name !== 'AbortError' && e.code !== 'ERR_CANCELED') { recFailures += 1; setMsg(`读取任务失败：${describeError(e)}`, 'error') }; return false }
  finally { if (serial === recordsSerial) { busy.records = false; recController = null; scheduleRecTimer() } }
}
function pageVisible() { return typeof document === 'undefined' || document.visibilityState !== 'hidden' }
function shouldPoll() { return !disposed && componentActive && pageVisible() && tab.value === 'records' && records.value.some(r => isActiveTask(r) || isPendingOrganize(r)) }
function stopRecTimer() { if (recTimer) { clearTimeout(recTimer); recTimer = null } }
function scheduleRecTimer() { stopRecTimer(); if (!shouldPoll()) return; recTimer = setTimeout(() => { recTimer = null; if (shouldPoll()) loadRecords() }, Math.min(300000, 20000 * 2 ** Math.min(Math.max(recFailures, recUnchanged), 4))) }
function visibilityChanged() { stopRecTimer(); stopQrTimer(); if (!pageVisible() || !componentActive || disposed) return; if (tab.value === 'records') loadRecords(); if (settingsOpen.value && qrSessionId.value) startQrTimer() }
function abortSearch() { if (searchDebounce) { clearTimeout(searchDebounce); searchDebounce = null }; searchController?.abort(); searchController = null }
function dispose() { disposed = true; searchSerial += 1; abortSearch(); stopQrTimer(); stopRecTimer(); recordsSerial += 1; recController?.abort(); if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visibilityChanged) }
function close() { dispose(); emit('close') }
async function deleteRecord(r) { if (!window.confirm(`删除「${r.title}」的展示记录？任务、网盘文件与防重复获取记录会保留。`)) return; await manageRecord('records_delete', { id: r.id }, '已删除展示记录。') }
async function clearRecords() { if (!window.confirm('清空展示记录？任务、网盘文件与防重复获取记录会保留。')) return; await manageRecord('records_delete', {}, '已清空展示记录。') }
async function manageRecord(endpoint, payload, fallback) { try { const res = unwrap(await props.api.post(`plugin/Doc115Subscribe/${endpoint}`, payload)); showResult(res, fallback); await loadRecords() } catch (e) { setMsg(describeError(e), 'error') } }
async function taskAction(r, action) {
  if (!r?.id || !hasAction(r, action) || retrying[r.id]) return
  retrying[r.id] = true
  try { showResult(unwrap(await props.api.post('plugin/Doc115Subscribe/task_action', { id: r.id, action }, { timeout: 30000 })), '操作已提交。'); await loadRecords() }
  catch (e) { setMsg(`操作失败：${describeError(e)}`, 'error'); await loadRecords() }
  finally { delete retrying[r.id] }
}
async function cancelTask(r) { if (!hasAction(r, 'stop_tracking') || !window.confirm(`停止「${r.title}」的自动跟踪？已有下载与文件会保留。`)) return; await taskAction(r, 'stop_tracking') }
async function retrySubmit(r) { if (!hasAction(r, 'retry_submit') || !window.confirm(`重新获取「${r.title}」？此操作会再次提交115转存或离线下载，只适用于此前已明确获取失败的任务。`)) return; await taskAction(r, 'retry_submit') }
function changeRecordsPage(value) { if (busy.records) return; recordsPage.value = value; loadRecords() }
async function loadStatus() { try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/status')); if (!disposed && res.code === 0 && res.data) Object.assign(status, res.data) } catch (e) { setMsg(`读取插件状态失败：${describeError(e)}`, 'error') } }
async function loadDiagnostics() { if (busy.diagnostics) return; busy.diagnostics = true; try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/diagnostics')); if (res.code !== 0) throw new Error(res.msg || '本地诊断不可用'); diagnostics.value = res.data || {} } catch (e) { setMsg(`本地诊断：${describeError(e)}`, 'warning') } finally { busy.diagnostics = false } }
async function loadSubscriptions() { if (busy.preview || disposed) return; busy.preview = true; try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/subscriptions_preview')); if (res.code !== 0) throw new Error(res.msg || '匹配预演不可用'); const data = res.data || {}; subscriptions.value = Array.isArray(data) ? data : data.subscriptions || data.records || []; subscriptionNote.value = (data.message || data.note || data.msg || '已读取本地匹配快照') + (data.updated_at || data.cached_at ? `，更新于 ${formatTime(data.updated_at || data.cached_at)}。` : '，尚未建立 MP 订阅缓存。') } catch (e) { subscriptionNote.value = `匹配预演暂不可用：${describeError(e)}。没有提交资源。` } finally { busy.preview = false } }
async function refreshIndex() { if (busy.refresh) return; busy.refresh = true; try { const res = unwrap(await props.api.post('plugin/Doc115Subscribe/refresh_index', {}, { timeout: 30000 })); showResult(res, '文档索引已更新。'); await loadStatus() } catch (e) { setMsg(`刷新索引失败：${describeError(e)}`, 'error') } finally { busy.refresh = false; emit('action') } }
async function runSubscribe() { if (busy.subscribe || !window.confirm('现在同步电影订阅并获取匹配资源？此操作可能提交115转存或离线下载。')) return; busy.subscribe = true; try { const res = unwrap(await props.api.post('plugin/Doc115Subscribe/run_subscribe', {}, { timeout: 30000 })); showResult(res, '电影订阅同步已完成。') } catch (e) { setMsg(`订阅同步失败：${describeError(e)}`, 'error') } finally { busy.subscribe = false; await loadStatus(); emit('action') } }
async function checkOffline() { if (busy.offline || !window.confirm('处理本插件待搬运任务？会通过Plus移动已确认的文件到所选下载目录。')) return; busy.offline = true; try { showResult(unwrap(await props.api.post('plugin/Doc115Subscribe/check_offline', {}, { timeout: 30000 })), '任务处理已完成。'); await loadRecords() } catch (e) { setMsg(`任务处理失败：${describeError(e)}`, 'error') } finally { busy.offline = false } }

function stopQrTimer() { qrGeneration += 1; if (qrTimer) { clearTimeout(qrTimer); qrTimer = null } }
function startQrTimer() { if (disposed || !componentActive || !pageVisible() || !settingsOpen.value || !qrSessionId.value || qrTimer) return; const generation = qrGeneration; qrTimer = setTimeout(async () => { qrTimer = null; await checkQr(true); if (generation === qrGeneration) startQrTimer() }, 3000) }
async function startQr(silent = false) {
  if (busy.qr || busy.check || disposed) return
  busy.qr = true; stopQrTimer(); const generation = qrGeneration; qrSessionId.value = ''; qrImage.value = ''
  if (silent !== true) setMsg('正在生成文档登录二维码，请稍候。')
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_start', { params: { force: true }, timeout: 180000 })); if (generation !== qrGeneration || disposed) return; const data = res.data || {}; if (res.code === 0 && data.state === 'confirmed') await qrConfirmed(); else if (res.code === 0 && data.qr_base64 && data.session_id) { qrSessionId.value = data.session_id; qrImage.value = data.qr_base64; qrTip.value = '等待扫码'; setMsg('二维码已生成，请用微信扫码。'); startQrTimer() } else setMsg(res.msg || '获取二维码失败', 'error') } catch (e) { setMsg(`获取二维码失败：${describeError(e)}`, 'error') } finally { busy.qr = false }
}
async function checkQr(silent = false) {
  if (busy.check || busy.qr || !qrSessionId.value || disposed) return
  busy.check = true; const generation = qrGeneration, sessionId = qrSessionId.value
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_status', { params: { session_id: sessionId }, timeout: 30000 })); if (generation !== qrGeneration || disposed) return; const data = res.data || {}; if (res.code === 0 && data.state === 'confirmed') { await qrConfirmed(); return }; if (res.code !== 0) { setMsg(res.msg || '扫码检查失败', 'error'); stopQrTimer(); return }; if (data.qr_base64) qrImage.value = data.qr_base64; const states = { wait: '等待扫码', scanned: '已扫描，请在手机上确认', expired: '二维码已过期，请获取新码', failed: '登录失败，请获取新码', error: '登录检查失败，请获取新码' }; qrTip.value = states[data.state] || '等待扫码'; if (['expired', 'failed', 'error'].includes(data.state)) { stopQrTimer(); qrSessionId.value = ''; setMsg(qrTip.value, 'warning') } else if (silent !== true) setMsg(qrTip.value) } catch (e) { if (silent !== true) setMsg(`扫码检查失败：${describeError(e)}`, 'error') } finally { busy.check = false }
}
async function qrConfirmed() { stopQrTimer(); qrSessionId.value = ''; qrImage.value = ''; setMsg('文档登录成功，Cookie已保存。', 'success'); await loadStatus() }
async function doSearch() { const kw = (keyword.value || '').trim(); if (!kw) { setMsg('请输入影视名称', 'warning'); return }; abortSearch(); await searchPage(kw, 1) }
function changePage(value) { if (searchedKeyword.value && !busy.search) searchPage(searchedKeyword.value, value) }
async function searchPage(kw, requestedPage) {
  searchController?.abort(); const controller = typeof AbortController === 'function' ? new AbortController() : null; searchController = controller
  const serial = ++searchSerial; searchedKeyword.value = kw; busy.search = true; searched.value = true; results.value = []; total.value = 0; resultVersion.value = ''; page.value = requestedPage
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/search', { keyword: kw, media_type: filterType.value, quality: filterQuality.value, subtitle: filterSubtitle.value, link_kind: filterLink.value, page: requestedPage, page_size: pageSize }, { timeout: 30000, signal: controller?.signal }))
    if (serial !== searchSerial || disposed) return
    if (res.code !== 0) throw new Error(res.msg || '搜索失败')
    const data = res.data || {}; if (!Array.isArray(data.records) || !data.index_version) throw new Error('搜索响应缺少有效索引版本')
    results.value = data.records; total.value = data.total || 0; page.value = data.page || requestedPage; resultVersion.value = data.index_version; setMsg(`「${kw}」符合筛选的结果共 ${total.value} 条`)
  } catch (e) { if (serial === searchSerial && !disposed && e.name !== 'AbortError' && e.code !== 'ERR_CANCELED') setMsg(`搜索失败：${describeError(e)}`, 'error') }
  finally { if (serial === searchSerial) { busy.search = false; searchController = null } }
}
function sourceOptions(rec) { return (rec?.links || []).map((link, index) => ({ value: String(index), kind: link.kind, label: `${linkName(link.kind)} · ${shortUrl(link.url)}` })).filter(o => ['115_share', 'magnet', 'ed2k'].includes(o.kind)) }
function prepareTransfer(rec) { if (!rec?.record_id || busy.search || transferring[rec.record_id] || rec.bundle || rec.sheet_bundle || rec.no_link) return; const options = sourceOptions(rec); if (!options.length) { setMsg('此条目没有可获取的链接', 'warning'); return }; transferRecord.value = rec; transferIndexVersion.value = resultVersion.value; transferTarget.value = rec.media_type === 'tv' ? 'tv' : 'movie'; const selectedKind = filterLink.value === 'share' ? '115_share' : filterLink.value; transferSource.value = (options.find(o => o.kind === selectedKind) || options[0]).value; transferOpen.value = true }
async function confirmTransfer() { const rec = transferRecord.value; const index = Number(transferSource.value); if (!rec || !Number.isInteger(index) || !rec.links?.[index]) return; if (transferIndexVersion.value !== resultVersion.value) { setMsg('搜索索引已变化，请重新选择来源与目录。', 'warning'); transferOpen.value = false; return }; await transfer(rec, transferTarget.value, index); transferOpen.value = false }
async function transfer(rec, to, sourceIndex) {
  if (!rec?.record_id || !resultVersion.value || busy.search || transferring[rec.record_id]) return
  const payload = { record_id: rec.record_id, index_version: resultVersion.value, to }
  if (sourceIndex !== undefined) { if (!Number.isInteger(sourceIndex) || !['115_share', 'magnet', 'ed2k'].includes(rec.links?.[sourceIndex]?.kind)) { setMsg('所选来源已经失效，请重新搜索', 'warning'); return }; payload.link_kind = rec.links[sourceIndex].kind; payload.link_index = sourceIndex }
  transferring[rec.record_id] = true
  try { showResult(unwrap(await props.api.post('plugin/Doc115Subscribe/transfer', payload, { timeout: 30000 })), '获取请求已受理，请到任务页查看进度。') } catch (e) { setMsg(`获取请求失败：${describeError(e)}。提交结果请先查看任务，避免重复获取。`, 'error') }
  finally { delete transferring[rec.record_id]; emit('action') }
}
watch([filterType, filterQuality, filterSubtitle, filterLink], () => { if (!searchedKeyword.value || disposed) return; searchSerial += 1; abortSearch(); busy.search = true; searchDebounce = setTimeout(() => { searchDebounce = null; if (!disposed) searchPage(searchedKeyword.value, 1) }, 220) })
watch(tab, value => { stopRecTimer(); if (value === 'records') loadRecords(); else if (value === 'subscriptions') loadSubscriptions() })
watch(recordsFilter, () => { recordsPage.value = 1; if (busy.records) { recordsSerial += 1; recController?.abort(); busy.records = false }; loadRecords() })
watch(settingsOpen, value => { stopQrTimer(); if (value && pageVisible()) startQrTimer() })
onMounted(() => { loadStatus(); if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visibilityChanged) })
onActivated(() => { componentActive = true; visibilityChanged() })
onDeactivated(() => { componentActive = false; stopRecTimer(); stopQrTimer() })
onBeforeUnmount(dispose)
</script>
