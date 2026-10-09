<template>
  <div class="doc115-page">
    <v-row dense align="center" class="mb-1">
      <v-col cols="10">
        <div class="text-subtitle-1 font-weight-medium">
          115文档订阅与查询
          <v-chip v-if="status.version" size="x-small" color="grey-darken-1" variant="flat" class="ml-1">
            前端 v{{ status.version }}
          </v-chip>
        </div>
      </v-col>
      <v-col cols="2" class="text-right">
        <v-btn icon size="small" variant="text" title="关闭" @click="close">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-col>
    </v-row>

    <v-alert :type="cookieAlertType" variant="tonal" density="comfortable" class="mb-3">
      <div>
        腾讯文档 Cookie：{{ cookieText }}
        <span v-if="cookieDays !== null && cookieDays <= 5" class="font-weight-medium">
          —— 即将到期，请重新扫码登录
        </span>
      </div>
      <div>
        本地索引：<span class="text-primary font-weight-medium">{{ status.record_count }}</span> 条 /
        <span class="text-primary font-weight-medium">{{ status.sheet_count }}</span> 张表， 更新于
        {{ status.built_at_text }} ｜115 Cookie：<span
          :class="status.p115_ready ? 'text-green-darken-2' : 'text-red-darken-2'"
        >{{ status.p115_ready ? '已配置' : '未检测到' }}</span>
      </div>
    </v-alert>

    <v-alert v-if="indexWarnings.length" type="warning" variant="tonal" class="mb-3" style="white-space: pre-wrap">
      <div>索引存在未更新的工作表，部分结果可能已过时：</div>{{ indexWarnings.join('\n') }}
    </v-alert>
    <v-alert v-if="status.last_subscribe && status.last_subscribe.success === false" type="error" variant="tonal" class="mb-3">
      最近订阅同步失败：{{ status.last_subscribe.msg || status.last_subscribe.error || '请手动同步查看原因' }}
    </v-alert>
    <v-alert v-if="status.last_refresh && status.last_refresh.success === false" type="error" variant="tonal" class="mb-3">
      最近索引刷新失败：{{ status.last_refresh.msg || status.last_refresh.error || '请刷新索引查看原因' }}
    </v-alert>

    <v-alert
      v-if="msg"
      :type="msgType"
      variant="tonal"
      density="comfortable"
      class="mb-3"
      style="white-space: pre-wrap"
    >{{ msg }}</v-alert>

    <v-row dense class="mb-2">
      <v-col cols="6" md="2">
        <v-btn block color="primary" :loading="busy.refresh" prepend-icon="mdi-database-refresh" @click="refreshIndex">
          刷新索引
        </v-btn>
      </v-col>
      <v-col cols="6" md="2">
        <v-btn block color="primary" :loading="busy.qr" :disabled="busy.check" prepend-icon="mdi-qrcode" @click="startQr()">
          {{ qrImage ? '换一张二维码' : '获取登录二维码' }}
        </v-btn>
      </v-col>
      <v-col cols="6" md="2">
        <v-btn block color="secondary" :loading="busy.check" :disabled="busy.qr || !qrSessionId" prepend-icon="mdi-check-decagram" @click="checkQr()">
          检查扫码状态
        </v-btn>
      </v-col>
      <v-col cols="6" md="3">
        <v-btn block color="secondary" :loading="busy.offline" prepend-icon="mdi-download-network" @click="checkOffline">
          检查离线下载与搬运
        </v-btn>
      </v-col>
      <v-col cols="6" md="3">
        <v-btn block color="secondary" :loading="busy.subscribe" prepend-icon="mdi-sync" @click="runSubscribe">
          手动同步电影订阅
        </v-btn>
      </v-col>
    </v-row>

    <v-tabs v-model="tab" density="comfortable" class="mb-3">
      <v-tab value="search">搜索</v-tab>
      <v-tab value="records">转存记录</v-tab>
    </v-tabs>

    <template v-if="tab === 'search'">
    <v-card v-if="qrImage" variant="outlined" class="mb-3">
      <v-card-text class="text-center">
        <img
          :src="qrImage"
          style="width: 220px; height: 220px; display: block; margin: 0 auto"
          alt="扫码登录"
        />
        <div class="text-caption mt-2">用微信扫码登录腾讯文档（{{ qrTip }}）</div>
        <div class="text-caption text-medium-emphasis">
          二维码过期后请点「换一张二维码」；请只扫描当前页面显示的二维码。
        </div>
      </v-card-text>
    </v-card>

    <v-card variant="outlined" class="mb-3">
      <v-card-text>
        <v-row dense align="center">
          <v-col cols="12" md="8">
            <v-text-field
              v-model="keyword"
              label="输入影视名称搜索（跨全部工作表）"
              variant="outlined"
              density="comfortable"
              hide-details
              clearable
              @keyup.enter="doSearch"
            />
          </v-col>
          <v-col cols="12" md="4">
            <v-btn block color="primary" prepend-icon="mdi-magnify" :loading="busy.search" @click="doSearch">
              搜索
            </v-btn>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card v-if="searched" variant="outlined">
      <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap">
        <span>「{{ searchedKeyword }}」的搜索结果</span>
        <v-chip size="x-small" color="primary" class="ml-2">共 {{ total }} 条</v-chip>
        <v-spacer />
        <v-btn-toggle v-model="filterType" density="compact" variant="outlined" mandatory class="mr-2">
          <v-btn size="small" value="all">全部</v-btn>
          <v-btn size="small" value="movie">电影</v-btn>
          <v-btn size="small" value="tv">电视剧</v-btn>
        </v-btn-toggle>
        <v-btn-toggle v-model="filterQuality" density="compact" variant="outlined" mandatory class="mr-2">
          <v-btn size="small" value="all">不限画质</v-btn>
          <v-btn size="small" value="4k">4K</v-btn>
          <v-btn size="small" value="cn">中文字幕</v-btn>
        </v-btn-toggle>
        <v-btn-toggle v-model="filterLink" density="compact" variant="outlined" mandatory>
          <v-btn size="small" value="all">不限来源</v-btn>
          <v-btn size="small" value="share">115转存</v-btn>
          <v-btn size="small" value="magnet">磁力</v-btn>
          <v-btn size="small" value="ed2k">ed2k</v-btn>
          <v-btn size="small" value="doc">仅文档</v-btn>
        </v-btn-toggle>
      </v-card-title>
      <v-card-text>
        <v-progress-linear v-if="busy.search" indeterminate color="primary" class="mb-2" />
        <v-alert v-else-if="!results.length" type="info" variant="tonal" class="mb-2">没有找到匹配的资源，可调整筛选或换个关键词。</v-alert>
        <v-card v-for="r in results" :key="r.record_id" variant="tonal" class="mb-2">
          <v-card-text class="py-2">
            <v-row dense align="center">
              <v-col cols="12" md="8">
                <div class="font-weight-bold text-body-1 text-primary">
                  {{ r.title }}
                  <span v-if="r.year" class="text-medium-emphasis font-weight-regular">（{{ r.year }}）</span>
                </div>
                <div class="text-caption mt-1">
                  <v-chip size="x-small" variant="flat" :color="r.media_type === 'movie' ? 'deep-purple' : 'blue-darken-2'" class="mr-1">
                    {{ mediaTypeName(r.media_type) }}
                  </v-chip>
                  <v-chip v-if="r.bundle" size="x-small" color="deep-orange" class="mr-1">打包链接</v-chip>
                  <span class="text-purple-darken-2">来源：{{ r.sheet }}</span>
                  <span v-if="r.tmdbid" class="text-grey-darken-1">｜TMDB：{{ r.tmdbid }}</span>
                </div>
                <div class="text-caption mt-1">
                  <span class="text-medium-emphasis">规格：</span>
                  <span
                    v-for="(tk, ti) in specTokens(r.qtext)"
                    :key="ti"
                    :class="tk.color ? tk.color + ' font-weight-bold' : 'text-medium-emphasis'"
                  >{{ tk.text }}</span>
                </div>
                <div class="text-caption mt-1">
                  <span class="text-medium-emphasis">链接：</span>
                  <v-chip
                    v-for="(lk, li) in (r.links || [])"
                    :key="li"
                    size="small"
                    variant="flat"
                    :color="linkColor(lk.kind)"
                    :prepend-icon="linkIcon(lk.kind)"
                    :href="linkHref(lk.url)"
                    target="_blank"
                    rel="noopener"
                    class="mr-1"
                  >{{ linkName(lk.kind) }} {{ shortUrl(lk.url) }}</v-chip>
                </div>
              </v-col>
              <template v-if="r.sheet_bundle || r.no_link || r.bundle">
                <v-col cols="12" md="4">
                  <div class="text-caption text-medium-emphasis">
                    {{ r.no_link
                      ? '该表为纯列表，资源在外部文档：请点上方的链接自行查看（本插件不转存）'
                      : '该条目是打包链接（大包），已关闭一键转存：请点上方的 115/磁力 链接自行查看或转存' }}
                  </div>
                </v-col>
              </template>
              <template v-else>
                <v-col cols="6" md="2">
                  <v-btn block size="small" color="primary" :loading="!!transferring[r.record_id]" :disabled="busy.search || !!transferring[r.record_id] || !r.record_id" @click="transfer(r, 'movie')">转存到电影</v-btn>
                </v-col>
                <v-col cols="6" md="2">
                  <v-btn block size="small" color="secondary" :disabled="busy.search || !!transferring[r.record_id] || !r.record_id" @click="transfer(r, 'tv')">转存到电视剧</v-btn>
                </v-col>
              </template>
            </v-row>
          </v-card-text>
        </v-card>
        <v-row dense align="center" class="mt-2">
          <v-col cols="12" md="6" class="text-caption text-medium-emphasis">
            第 {{ page }} / {{ pageCount }} 页，每页 {{ pageSize }} 条（共 {{ total }} 条）
          </v-col>
          <v-col cols="12" md="6">
            <v-pagination
              :model-value="page"
              :length="pageCount"
              :disabled="busy.search"
              :total-visible="6"
              density="comfortable"
              size="small"
              @update:model-value="changePage"
            />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
    </template>

    <template v-else>
      <v-card variant="outlined">
        <v-card-title class="text-subtitle-1 d-flex align-center flex-wrap">
          <span>转存记录</span>
          <v-chip size="x-small" color="primary" class="ml-2">{{ records.length }} 条</v-chip>
          <v-spacer />
          <v-btn-group variant="text" density="comfortable" divided>
            <v-btn size="small" prepend-icon="mdi-refresh" :loading="busy.records" @click="loadRecords(true)">
              刷新
            </v-btn>
            <v-btn
              size="small"
              color="error"
              prepend-icon="mdi-delete-sweep"
              :disabled="!records.length"
              @click="clearRecords"
            >
              清空
            </v-btn>
          </v-btn-group>
        </v-card-title>
        <v-card-subtitle class="text-caption pt-0">
          点「刷新」会一并按 MoviePilot 的「整理记录」核对整理结果；最多保留最近 200 条。
        </v-card-subtitle>
        <v-card-text>
          <v-alert v-if="!records.length" type="info" variant="tonal">
            还没有转存 / 离线下载记录。去「搜索」页转存一条试试。
          </v-alert>
          <v-card v-for="(r, i) in records" :key="i" variant="tonal" class="mb-2">
            <v-card-text class="py-2">
              <div class="d-flex align-center flex-wrap">
                <span class="font-weight-bold text-body-1 text-primary">{{ r.title }}</span>
                <v-chip size="x-small" variant="flat" :color="r.type === 'movie' ? 'deep-purple' : 'blue-darken-2'" class="ml-2">
                  {{ mediaTypeName(r.type) }}
                </v-chip>
                <v-chip size="x-small" variant="flat" :color="kindColor(r.kind)" class="ml-1">
                  {{ kindName(r.kind) }}
                </v-chip>
                <v-chip size="x-small" variant="flat" :color="statusColor(r.status)" class="ml-1">
                  {{ statusName(r.status) }}
                </v-chip>
                <v-spacer />
                <span class="text-caption text-medium-emphasis">{{ r.submitted_at }}</span>
                <v-btn v-if="isActiveTask(r)" size="x-small" variant="text" color="warning" :disabled="busy.records" @click="cancelTask(r)">停止自动搬运</v-btn>
                <v-btn v-if="['failed', 'missing'].includes(r.status)" size="x-small" variant="text" color="primary" :disabled="busy.records || !!retrying[r.id]" :loading="!!retrying[r.id]" @click="retryTask(r)">重试</v-btn>
                <v-btn
                  icon
                  size="x-small"
                  variant="text"
                  color="error"
                  class="ml-1"
                  title="删除这条记录"
                  @click="deleteRecord(r)"
                >
                  <v-icon>mdi-delete</v-icon>
                </v-btn>
              </div>
              <div class="text-caption mt-1 text-medium-emphasis" style="word-break: break-all">
                目标：{{ r.final_path }}
                <template v-if="r.kind !== '115_share' && r.staging_path && r.staging_path !== r.final_path">
                  （离线先落 {{ r.staging_path }}）
                </template>
              </div>
              <v-progress-linear
                class="mt-2"
                :model-value="(r.status === 'done' || r.status === 'organized') ? 100 : (r.progress || 0)"
                :color="statusColor(r.status)"
                height="8"
                rounded
              />
              <div
                v-if="r.status === 'downloading' && (r.progress || 0) >= 100"
                class="text-caption mt-1"
                style="border-radius: 6px; padding: 6px 8px; background: rgba(255, 180, 0, 0.14)"
              >
                {{ r.message || '离线任务已完成，但文件未出现在暂存目录' }}
              </div>
              <div v-else class="text-caption mt-1">
                <span class="text-medium-emphasis">{{ r.message || '' }}</span>
                <span v-if="r.status === 'downloading'" class="ml-2">{{ r.progress || 0 }}%</span>
              </div>
            </v-card-text>
          </v-card>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
})
const emit = defineEmits(['action', 'close'])

const pageSize = 10

const status = reactive({
  version: '', cookie_ready: false, p115_ready: false, cookie_days_left: null,
  record_count: 0, sheet_count: 0, built_at_text: '尚未建立',
  index_errors: [], stale_sheets: [], last_refresh: null, last_subscribe: null,
})
const msg = ref('')
const msgType = ref('info')
const busy = reactive({ refresh: false, qr: false, search: false, subscribe: false, check: false, offline: false, records: false })
const qrImage = ref('')
const qrTip = ref('等待扫码')
const qrSessionId = ref('')
const keyword = ref('')
const results = ref([])
const searched = ref(false)
const searchedKeyword = ref('')
const total = ref(0)
const resultVersion = ref('')
const transferring = reactive({})
const retrying = reactive({})
let searchSerial = 0
let disposed = false

// ---- 页签：搜索 / 转存记录 ----
const tab = ref('search')
const records = ref([])

// ---- 筛选与分页 ----
const page = ref(1)
const filterType = ref('all')
const filterQuality = ref('all')
// 链接类型筛选：区分「115 转存 / 磁力 / ed2k / 纯文档（没有可转存的资源链接）」
const filterLink = ref('all')

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
watch([filterType, filterQuality, filterLink], () => {
  if (searchedKeyword.value) searchPage(searchedKeyword.value, 1)
})
const indexWarnings = computed(() => [...new Set([
  ...(status.index_errors || []).map(String),
  ...(status.stale_sheets || []).map((s) => typeof s === 'string' ? `保留旧索引：${s}` : `保留旧索引：${s.title || s.name || s.sheet_id || '未知工作表'}`),
])])
function mediaTypeName(type) { return ({ movie: '电影', tv: '电视剧' })[type] || '类型待确认' }

// ---- Cookie 状态文案 ----
const cookieDays = computed(() => {
  const d = status.cookie_days_left
  return (d === null || d === undefined) ? null : Math.floor(d)
})
const cookieText = computed(() => {
  if (!status.cookie_ready) return '未配置（请用下方扫码登录）'
  return cookieDays.value === null ? '已配置' : `已配置（剩余约 ${cookieDays.value} 天）`
})
const cookieAlertType = computed(() => {
  if (!status.cookie_ready) return 'warning'
  if (cookieDays.value !== null && cookieDays.value <= 5) return 'warning'
  return 'info'
})

// ---- 字段配色 ----
// 链接类型：颜色 + 图标双重区分，一眼能看出是 115 分享还是磁力
const LINK_STYLE = {
  '115_share': { color: 'deep-purple', name: '115分享', icon: 'mdi-cloud-download' },
  magnet: { color: 'blue-darken-3', name: '磁力', icon: 'mdi-magnet' },
  ed2k: { color: 'teal-darken-3', name: 'ed2k', icon: 'mdi-link-variant' },
  http: { color: 'grey-darken-2', name: '网页', icon: 'mdi-web' },
}
function linkColor(kind) { return (LINK_STYLE[kind] || {}).color || 'grey' }
function linkName(kind) { return (LINK_STYLE[kind] || {}).name || kind }
function linkIcon(kind) { return (LINK_STYLE[kind] || {}).icon || 'mdi-link' }

function shortUrl(u) {
  let t = String(u || '')
  t = t.replace(/^https?:\/\//i, '')
  if (/^ed2k:\/\//i.test(t)) { const p = t.split('|'); return p.length > 2 ? p[2] : t }
  return t.length > 44 ? t.slice(0, 44) + '…' : t
}
function linkHref(u) {
  let t = String(u || '')
  if (/^(ed2k:\/\/|magnet:)/i.test(t)) return t
  if (!/^https?:\/\//i.test(t)) t = 'https://' + t
  return t
}

const SPEC_RE = /(4K|2160[pP]|1080[pP]|720[pP]|REMUX|UHD|HDR10\+?|HDR|杜比视界|Dolby\s?Vision|Atmos|蓝光原盘|原盘|中文字幕|简繁|简体|繁体|国语|双语|粤语|无中字)/gi
function specTokens(text) {
  const t = (text || '').slice(0, 100)
  if (!t) return [{ text: '—', color: '' }]
  const parts = []
  let last = 0
  let m
  SPEC_RE.lastIndex = 0
  while ((m = SPEC_RE.exec(t)) !== null) {
    if (m.index > last) parts.push({ text: t.slice(last, m.index), color: '' })
    const w = m[0].toUpperCase()
    let color
    if (/无中字/.test(w)) color = 'red-darken-2'
    else if (/4K|2160P|REMUX|UHD|HDR|杜比|DOLBY|ATMOS|原盘/.test(w)) color = 'amber-darken-3'
    else if (/中文字幕|简繁|简体|繁体|国语|双语|粤语/.test(w)) color = 'green-darken-2'
    else if (/1080P|720P/.test(w)) color = 'blue-darken-1'
    else color = 'grey-darken-1'
    parts.push({ text: m[0], color })
    last = m.index + m[0].length
  }
  if (last < t.length) parts.push({ text: t.slice(last), color: '' })
  return parts
}

function setMsg(text, type = 'info') {
  msg.value = text
  msgType.value = type
}

// ---- 转存记录 ----
const KIND_STYLE = {
  '115_share': { name: '115分享', color: 'deep-purple' },
  magnet: { name: '磁力', color: 'blue-darken-3' },
  ed2k: { name: 'ed2k', color: 'teal-darken-3' },
}
const STATUS_STYLE = {
  submitting: { name: '提交中', color: 'blue-darken-2' },
  submitted: { name: '已提交', color: 'blue-darken-2' },
  downloading: { name: '下载中', color: 'blue-darken-2' },
  waiting: { name: '等待文件', color: 'amber-darken-3' },
  awaiting_move: { name: '等待搬运', color: 'amber-darken-3' },
  moving: { name: '搬运中', color: 'amber-darken-3' },
  done: { name: '已搬入下载目录', color: 'amber-darken-3' },
  moved: { name: '已搬入下载目录', color: 'amber-darken-3' },
  missing: { name: '原目录未找到，整理待确认', color: 'amber-darken-3' },
  unverified: { name: '整理待确认', color: 'amber-darken-3' },
  partial: { name: '部分整理失败', color: 'deep-orange-darken-2' },
  organized: { name: '已整理入库', color: 'green-darken-2' },
  failed: { name: '失败', color: 'red-darken-2' },
  cancelled: { name: '已停止自动搬运', color: 'grey' },
}
function kindName(k) { return (KIND_STYLE[k] || {}).name || k }
function kindColor(k) { return (KIND_STYLE[k] || {}).color || 'grey' }
function statusName(s) { return (STATUS_STYLE[s] || {}).name || s }
function statusColor(s) { return (STATUS_STYLE[s] || {}).color || 'grey' }

async function loadRecords(force = false) {
  if (busy.records || disposed) return
  busy.records = true
  try {
    // 读取记录；force=true（点「刷新」）时让后端**强制**用 MP 整理记录核对一次整理结果，
    // 否则走后端 30 秒节流（打开页面 / 定时轮询）。
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/records', {
      params: force ? { verify: 1 } : undefined,
      timeout: 180000,
    }))
    if (res.code === 0) records.value = res.data || []
    else setMsg(res.msg || '读取转存记录失败', 'error')
  } catch (e) {
    setMsg(`读取转存记录失败：${describeError(e)}`, 'error')
  } finally {
    busy.records = false
  }
}

// 记录页有活动任务时轮询读取后台检查结果。
let recTimer = null
function stopRecTimer() {
  if (recTimer) { clearInterval(recTimer); recTimer = null }
}
function startRecTimer() {
  stopRecTimer()
  recTimer = setInterval(() => {
    if (tab.value !== 'records') return
    if (!records.value.some(isActiveTask)) return
    loadRecords()
  }, 20000)
}

async function deleteRecord(r) {
  if (!window.confirm(`删除这条历史记录？下载与自动搬运任务继续执行。\n${r.title}`)) return
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/records_delete', { id: r.id }))
    if (res.code === 0) {
      setMsg('已删除该条记录', 'success')
      await loadRecords()
    } else {
      setMsg(res.msg || '删除失败', 'error')
    }
  } catch (e) {
    setMsg(`删除失败：${describeError(e)}`, 'error')
  }
}

async function clearRecords() {
  if (!window.confirm('清空全部转存历史记录？网盘文件、下载与自动搬运任务不受影响。')) return
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/records_delete', {}))
    if (res.code === 0) {
      setMsg('已清空转存记录', 'success')
      await loadRecords()
    } else {
      setMsg(res.msg || '清空失败', 'error')
    }
  } catch (e) {
    setMsg(`清空失败：${describeError(e)}`, 'error')
  }
}

function isActiveTask(r) { return ['submitting', 'submitted', 'downloading', 'waiting', 'awaiting_move', 'moving'].includes(r.status) && r.kind !== '115_share' }
async function retryTask(r) {
  if (retrying[r.id]) return
  retrying[r.id] = true
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/retry_task', { id: r.id }, { timeout: 300000 }))
    setMsg(res.msg || (res.code === 0 ? '已重新尝试该任务' : '重试失败'), res.code === 0 ? 'success' : 'error')
    if (res.code === 0) await loadRecords()
  } catch (e) { setMsg(`重试失败：${describeError(e)}`, 'error') }
  finally { delete retrying[r.id] }
}
async function cancelTask(r) {
  if (!window.confirm(`停止「${r.title}」的自动跟踪与搬运？\n115 中的下载和文件会保留，完成后需要你手动搬运。`)) return
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/cancel_task', { id: r.id }))
    setMsg(res.msg || (res.code === 0 ? '已停止自动搬运' : '停止失败'), res.code === 0 ? 'success' : 'error')
    if (res.code === 0) await loadRecords()
  } catch (e) { setMsg(`停止失败：${describeError(e)}`, 'error') }
}

function close() {
  disposed = true
  searchSerial += 1
  stopQrTimer()
  stopRecTimer()
  emit('close')
}

function describeError(e) {
  if (!e) return '未知错误'
  const parts = []
  if (e.message) parts.push(e.message)
  if (e.response && e.response.status) parts.push(`HTTP ${e.response.status}`)
  if (e.response && e.response.data) {
    try { parts.push(JSON.stringify(e.response.data).slice(0, 200)) } catch (_) { /* ignore */ }
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
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/status'))
    if (res.code === 0 && res.data) Object.assign(status, res.data)
  } catch (e) {
    console.error(e)
  }
}

async function refreshIndex() {
  if (busy.refresh) return
  busy.refresh = true
  setMsg('正在读取所有工作表并刷新索引，可能需要数分钟，请稍候…')
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/refresh_index', {}, { timeout: 900000 }))
    if (res.code === 0) {
      const d = res.data || {}
      const errors = d.errors || d.index_errors || []
      setMsg(`索引${errors.length ? '部分更新' : '刷新完成'}：${d.record_count || 0} 条记录 / ${d.sheet_count || 0} 张表${errors.length ? '\n' + errors.join('\n') : ''}`, errors.length ? 'warning' : 'success')
      await loadStatus()
    } else {
      setMsg(res.msg || '索引刷新失败', 'error')
      await loadStatus()
    }
  } catch (e) {
    setMsg(`索引刷新失败：${describeError(e)}`, 'error')
  } finally {
    busy.refresh = false
    emit('action')
  }
}

// ---- 扫码登录 -----------------------------------------------------------
let qrTimer = null
let qrGeneration = 0

function stopQrTimer() {
  qrGeneration += 1
  if (qrTimer) {
    clearTimeout(qrTimer)
    qrTimer = null
  }
}

function startQrTimer() {
  if (disposed || !qrSessionId.value || qrTimer) return
  const generation = qrGeneration
  qrTimer = setTimeout(async () => {
    qrTimer = null
    await checkQr(true)
    if (generation === qrGeneration) startQrTimer()
  }, 3000)
}

async function startQr(silent = false) {
  if (busy.qr || busy.check || disposed) return
  if (silent !== true) silent = false
  busy.qr = true
  stopQrTimer()
  const generation = qrGeneration
  qrSessionId.value = ''
  qrImage.value = ''
  if (!silent) setMsg('正在打开登录页并生成二维码（约 10~20 秒），请稍候…')
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_start', { params: { force: true }, timeout: 180000 }))
    if (generation !== qrGeneration || disposed) return
    const data = res.data || {}
    if (res.code === 0 && data.state === 'confirmed') {
      await qrConfirmed()
    } else if (res.code === 0 && data.qr_base64 && data.session_id) {
      qrSessionId.value = data.session_id
      qrImage.value = data.qr_base64
      qrTip.value = '等待扫码'
      setMsg('二维码已生成，请用微信扫码（扫完会自动完成登录）')
      startQrTimer()
    } else {
      setMsg(res.msg || '获取二维码失败', 'error')
    }
  } catch (e) {
    setMsg(`获取二维码失败：${describeError(e)}`, 'error')
  } finally {
    busy.qr = false
  }
}

async function checkQr(silent = false) {
  if (busy.check || busy.qr || !qrSessionId.value || disposed) return
  if (silent !== true) silent = false
  busy.check = true
  const generation = qrGeneration
  const sessionId = qrSessionId.value
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/qr_status', { params: { session_id: sessionId }, timeout: 120000 }))
    if (generation !== qrGeneration || disposed) return
    const data = res.data || {}
    if (res.code === 0 && data.state === 'confirmed') {
      await qrConfirmed()
      return
    }
    if (data.qr_base64) {
      qrImage.value = data.qr_base64
      qrTip.value = '已换新码，请重新扫码'
    }
    if (res.code !== 0) {
      setMsg(res.msg || '检查失败', 'error')
      stopQrTimer()
      return
    }
    const map = {
      wait: '等待扫码',
      scanned: '已扫描，请在手机上确认登录',
      expired: '二维码已过期，请获取新二维码',
      failed: '本次登录失败，请获取新二维码',
      error: '登录检查失败，请获取新二维码',
    }
    qrTip.value = map[data.state] || '等待扫码'
    if (['expired', 'failed', 'error'].includes(data.state)) {
      stopQrTimer()
      qrSessionId.value = ''
      setMsg(data.msg || qrTip.value, 'warning')
      return
    }
    if (!silent && data.state) setMsg(map[data.state] || '')
  } catch (e) {
    if (!silent) setMsg(`检查失败：${describeError(e)}`, 'error')
  } finally {
    busy.check = false
  }
}

async function qrConfirmed() {
  stopQrTimer()
  qrSessionId.value = ''
  qrImage.value = ''
  setMsg('登录成功，Cookie 已保存。可刷新索引查看文档读取结果。', 'success')
  await loadStatus()
}

// ---- 其它 ---------------------------------------------------------------
async function checkOffline() {
  if (busy.offline) return
  busy.offline = true
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/check_offline', {}, { timeout: 180000 }))
    if (res.code === 0) {
      const d = res.data || {}
      setMsg(`离线任务检查完成：本轮搬运 ${d.finished || 0} 条，待完成 ${d.pending || 0} 条${d.failed ? `，失败 ${d.failed} 条（请查看转存记录）` : ''}`, d.failed ? 'warning' : 'success')
      await loadRecords()
    } else {
      setMsg(res.msg || '检查离线任务失败', 'error')
    }
  } catch (e) {
    setMsg(`检查离线任务失败：${describeError(e)}`, 'error')
  } finally {
    busy.offline = false
  }
}

async function runSubscribe() {
  if (busy.subscribe) return
  busy.subscribe = true
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/run_subscribe', {}, { timeout: 900000 }))
    if (res.code === 0) {
      const d = res.data || {}
      const errors = d.errors || []
      setMsg(`订阅同步完成：命中 ${d.matched || 0} 条，成功提交 ${d.transferred || 0} 条${errors.length ? '\n' + errors.join('\n') : ''}`, errors.length ? 'warning' : 'success')
    } else {
      setMsg(res.msg || '订阅同步失败', 'error')
    }
  } catch (e) {
    setMsg(`订阅同步失败：${describeError(e)}`, 'error')
  } finally {
    busy.subscribe = false
    await loadStatus()
    emit('action')
  }
}

async function doSearch() {
  const kw = (keyword.value || '').trim()
  if (!kw) {
    setMsg('请输入影视名称', 'warning')
    return
  }
  await searchPage(kw, 1)
}

function changePage(value) {
  if (searchedKeyword.value && !busy.search) searchPage(searchedKeyword.value, value)
}

async function searchPage(kw, requestedPage) {
  const serial = ++searchSerial
  const mediaType = filterType.value
  const quality = filterQuality.value
  const linkKind = filterLink.value
  searchedKeyword.value = kw
  busy.search = true
  searched.value = true
  results.value = []
  total.value = 0
  resultVersion.value = ''
  page.value = requestedPage
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/search', {
      keyword: kw, media_type: mediaType, quality, link_kind: linkKind,
      page: requestedPage, page_size: pageSize,
    }, { timeout: 120000 }))
    if (serial !== searchSerial || disposed) return
    if (res.code === 0) {
      const data = res.data || {}
      if (!Array.isArray(data.records) || !data.index_version) throw new Error('搜索响应无有效索引版本，请更新插件后重试')
      results.value = data.records
      total.value = data.total || 0
      page.value = data.page || requestedPage
      resultVersion.value = data.index_version
      setMsg(`「${kw}」符合当前筛选的结果共 ${total.value} 条`)
    } else {
      results.value = []
      setMsg(res.msg || '搜索失败', 'error')
    }
  } catch (e) {
    if (serial === searchSerial && !disposed) setMsg(`搜索失败：${describeError(e)}`, 'error')
  } finally {
    if (serial === searchSerial) {
      busy.search = false
      emit('action')
    }
  }
}

async function transfer(rec, to) {
  if (!rec || !rec.record_id || !resultVersion.value || busy.search || transferring[rec.record_id]) return
  const recordId = rec.record_id
  const indexVersion = resultVersion.value
  transferring[recordId] = true
  setMsg(`正在转存「${rec.title}」，请稍候…`)
  try {
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/transfer', {
      record_id: recordId, index_version: indexVersion, to,
    }, { timeout: 300000 }))
    setMsg(res.msg || (res.code === 0 ? '转存完成' : '转存失败'), res.code === 0 ? 'success' : 'error')
  } catch (e) {
    setMsg(`转存失败：${describeError(e)}`, 'error')
  } finally {
    delete transferring[recordId]
    emit('action')
  }
}

onMounted(() => {
  loadStatus()
  loadRecords()
  startRecTimer()
})
watch(tab, (v) => {
  if (v === 'records') loadRecords()
})
onBeforeUnmount(() => {
  disposed = true
  searchSerial += 1
  stopQrTimer()
  stopRecTimer()
})
</script>

<style>
.doc115-page {
  width: 100%;
}
</style>
