<template>
  <v-card variant="outlined" class="doc115-config" :data-doc115-theme="darkTheme ? 'dark' : 'light'">
    <v-card-title class="text-subtitle-1 d-flex align-center">
      <span>{{ embedded ? '设置' : '115文档订阅与查询 · 设置' }}</span>
      <v-spacer />
      <v-btn icon size="small" variant="text" title="关闭设置" aria-label="关闭设置" @click="close"><v-icon>mdi-close</v-icon></v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert v-if="msg" :type="msgType" variant="tonal" density="comfortable" class="mb-3" role="status">{{ msg }}</v-alert>
      <div class="doc115-config-switches">
        <v-switch v-model="cfg.enabled" label="启用插件" color="primary" hide-details />
        <v-switch v-model="cfg.subscribe_enabled" label="启用电影订阅同步" color="primary" hide-details />
      </div>

      <v-form ref="formRef" validate-on="input" @submit.prevent="save">
      <v-expansion-panels v-model="openPanels" multiple variant="accordion" class="doc115-config-groups">
        <v-expansion-panel value="tencent">
          <v-expansion-panel-title>腾讯文档<span class="doc115-group-state" :class="secrets.tencent_ready ? 'doc115-green' : 'doc115-amber'">{{ secrets.tencent_ready ? '已登录' : '未登录' }}</span></v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-text-field v-model="cfg.doc_url" label="腾讯文档链接" variant="outlined" density="comfortable" placeholder="https://docs.qq.com/sheet/xxxx" :rules="[rules.docUrl]" hide-details="auto" />
            <p class="doc115-muted">{{ tencentHint }}</p>
            <slot name="tencent" />
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="p115">
          <v-expansion-panel-title>115 网盘<span class="doc115-group-state" :class="secrets.p115_ready ? 'doc115-green' : 'doc115-neutral'">{{ secrets.p115_ready ? '已配置' : '复用其它插件' }}</span></v-expansion-panel-title>
          <v-expansion-panel-text>
            <p class="doc115-muted">{{ secrets.p115_ready ? '115 Cookie 已配置，保存时留空会保留。' : '未单独配置 115 Cookie，会复用其它 115 插件的登录。' }}</p>
            <v-text-field v-model="cfg.p115_cookie" label="替换 115 Cookie（留空保留）" type="password" autocomplete="new-password" variant="outlined" density="comfortable" :disabled="cfg.clear_p115_cookie" hide-details />
            <v-checkbox v-model="cfg.clear_p115_cookie" label="清除单独保存的 115 Cookie（改为复用其它 115 插件）" color="warning" hide-details />
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="paths">
          <v-expansion-panel-title>保存目录</v-expansion-panel-title>
          <v-expansion-panel-text>
            <p class="doc115-muted">下载目录应对应 MP 已配置的 115 存储目录。本插件不修改 MP 监控或整理配置；未核实监控时不能保证保存后会自动整理。</p>
            <v-select v-if="movieDirectories.length" v-model="selectedMovieDirectory" :items="movieDirectories" label="选择已缓存的 MP 电影下载目录" variant="outlined" density="comfortable" hide-details class="mb-3" @update:model-value="chooseDirectory('movie', $event)" />
            <v-select v-if="tvDirectories.length" v-model="selectedTvDirectory" :items="tvDirectories" label="选择已缓存的 MP 电视剧下载目录" variant="outlined" density="comfortable" hide-details class="mb-3" @update:model-value="chooseDirectory('tv', $event)" />
            <v-row dense>
              <v-col cols="12" md="6"><v-text-field v-model="cfg.movie_path" label="115 电影下载目录" variant="outlined" density="comfortable" :rules="[rules.path]" hide-details="auto" /></v-col>
              <v-col cols="12" md="6"><v-text-field v-model="cfg.tv_path" label="115 电视剧下载目录" variant="outlined" density="comfortable" :rules="[rules.path]" hide-details="auto" /></v-col>
            </v-row>
            <v-text-field v-model="cfg.magnet_staging_path" label="磁力 / ed2k 暂存目录" variant="outlined" density="comfortable" class="mt-2" :rules="[rules.path, rules.staging]" hide-details="auto" persistent-hint hint="磁力 / ed2k 先离线下载到这里，完成后由本插件借助 115网盘Plus 搬到电影 / 电视剧目录；115 分享链接直接进最终目录。不能与电影或电视剧目录相同或互相嵌套。" />
            <v-switch v-model="cfg.create_subdir" color="primary" hide-details class="mt-2" label="保存时按「片名 (年份)」建子目录（推荐，便于 MP 识别）" />
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="subscribe">
          <v-expansion-panel-title>电影订阅</v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-text-field v-model="cfg.subscribe_cron" label="订阅同步计划（cron）" variant="outlined" density="comfortable" placeholder="0 21 * * *" :rules="[rules.cron]" hide-details="auto" persistent-hint hint="5 段 cron：分 时 日 月 周，例如 0 21 * * * 表示每天 21:00。" />
            <v-select v-model="cfg.link_mode" :items="linkModes" label="同一资源有多个链接时" variant="outlined" density="comfortable" class="mt-3" persistent-hint hint="镜像回退：仅明确失败后才尝试下一来源。分卷 / 全部提交只适用于确实需要全部文件的条目。手动获取只使用确认对话框里选定的链接。" />
            <v-switch v-model="cfg.upgrade_enabled" color="primary" hide-details class="mt-2" label="允许订阅获取更高画质版本" />
            <p class="doc115-muted">升级失败保留旧版本；画质无法确认时暂停自动升级，避免重复获取。</p>
          </v-expansion-panel-text>
        </v-expansion-panel>

        <v-expansion-panel value="advanced">
          <v-expansion-panel-title>高级</v-expansion-panel-title>
          <v-expansion-panel-text>
            <v-text-field v-model="cfg.index_cron" label="索引刷新计划（cron）" variant="outlined" density="comfortable" placeholder="0 6 * * *" :rules="[rules.cron]" hide-details="auto" />
            <v-text-field v-model.number="cfg.min_media_size_mb" type="number" min="0" max="1024" step="1" label="整理核对忽略小视频（MB）" variant="outlined" density="comfortable" class="mt-3" :rules="[rules.minSize]" hide-details="auto" persistent-hint hint="默认 10，0 关闭。只忽略已知体积小于阈值的附带视频；不删除文件，不改 MP 过滤规则。新任务使用新设置。" />
            <v-text-field v-model="cfg.tencent_cookie" label="手动替换腾讯文档 Cookie（留空保留）" type="password" autocomplete="new-password" variant="outlined" density="comfortable" class="mt-3" :disabled="cfg.clear_tencent_cookie" hide-details />
            <v-checkbox v-model="cfg.clear_tencent_cookie" label="清除已保存的腾讯文档 Cookie" color="warning" hide-details />
            <slot name="advanced" />
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
      </v-form>
      <p class="doc115-muted doc115-config-version">前端 v{{ UI_BUILD }}<template v-if="shownBackendVersion"> · 后端 v{{ shownBackendVersion }}</template></p>
    </v-card-text>
    <v-card-actions>
      <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" :disabled="saving" @click="load(true)">重新读取</v-btn>
      <v-spacer />
      <v-btn variant="text" @click="close">关闭</v-btn>
      <v-btn color="primary" variant="flat" :loading="saving" :disabled="loading" prepend-icon="mdi-content-save" @click="save">保存设置</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import { UI_BUILD } from '../version.js'
import '../styles/doc115.css'

const props = defineProps({
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
  // 嵌在插件详情页「设置」里时为 true：扫码登录、刷新索引、诊断通过插槽放进对应分组
  embedded: { type: Boolean, default: false },
  backendVersion: { type: String, default: '' },
})
const emit = defineEmits(['action', 'close'])
const hostTheme = inject(Symbol.for('vuetify:theme'), null)
const darkTheme = computed(() => !!(props.model?.dark ?? hostTheme?.current?.value?.dark))

const DEFAULTS = {
  enabled: false,
  doc_url: 'https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo',
  tencent_cookie: '',
  p115_cookie: '',
  clear_tencent_cookie: false,
  clear_p115_cookie: false,
  movie_path: '/115-影视/115-downloads/电影',
  tv_path: '/115-影视/115-downloads/电视剧',
  magnet_staging_path: '/115-影视/115-downloads/磁力链接',
  subscribe_enabled: false,
  subscribe_cron: '0 21 * * *',
  index_cron: '0 6 * * *',
  create_subdir: true,
  link_mode: 'first',
  upgrade_enabled: false,
  min_media_size_mb: 10,
}
const linkModes = [{ title: '镜像回退（推荐）', value: 'first' }, { title: '分卷 / 多份文件：全部提交', value: 'all' }]

const cfg = reactive({ ...DEFAULTS })
const secrets = reactive({ tencent_ready: false, p115_ready: false })
const msg = ref('')
const msgType = ref('info')
const saving = ref(false)
const loading = ref(false)
const formRef = ref(null)
const openPanels = ref(['tencent', 'paths'])
const fetchedVersion = ref('')
const shownBackendVersion = computed(() => props.backendVersion || fetchedVersion.value)
const directories = ref([])
const selectedMovieDirectory = ref(''), selectedTvDirectory = ref('')
const movieDirectories = computed(() => directoryOptions('movie'))
const tvDirectories = computed(() => directoryOptions('tv'))
const tencentHint = computed(() => secrets.tencent_ready
  ? '腾讯文档 Cookie 已配置。'
  : props.embedded ? '腾讯文档 Cookie 未配置，请用下方「扫码登录腾讯文档」登录。' : '腾讯文档 Cookie 未配置。请打开插件详情页，在「设置」的腾讯文档分组中扫码登录。')

// ---- 校验：返回 true 或错误文案（Vuetify rules 约定），保存前统一再跑一遍 ----
function normPath(value) { return String(value || '').trim().replace(/\\/g, '/').replace(/\/+$/, '') }
function isNested(a, b) { return a === b || a.startsWith(b + '/') || b.startsWith(a + '/') }
const CRON_FIELD = /^(\*|\?|[0-9A-Za-z]+(-[0-9A-Za-z]+)?)(\/\d+)?(,(\*|[0-9A-Za-z]+(-[0-9A-Za-z]+)?)(\/\d+)?)*$/
const rules = {
  docUrl: v => { const value = String(v || '').trim(); if (!value) return '请填写腾讯文档链接'; return /^https:\/\/docs\.qq\.com\/sheet\/[A-Za-z0-9_-]+/.test(value) || '必须是 https://docs.qq.com/sheet/ 开头的表格链接' },
  cron: v => { const value = String(v || '').trim(); if (!value) return '请填写 cron 表达式'; const parts = value.split(/\s+/); return (parts.length === 5 && parts.every(p => CRON_FIELD.test(p))) || '格式应为 5 段：分 时 日 月 周，例如 0 6 * * *' },
  path: v => { const value = normPath(v); if (!value) return '请填写目录'; if (!value.startsWith('/')) return '目录必须以 / 开头'; if (value.split('/').some(p => p === '.' || p === '..')) return '目录不能包含 . 或 ..'; if ([...value].some(c => c.charCodeAt(0) < 32)) return '目录含有非法字符'; return true },
  staging: v => { const value = normPath(v); if (!value) return true; for (const [key, name] of [['movie_path', '电影'], ['tv_path', '电视剧']]) { const other = normPath(cfg[key]); if (other && isNested(value, other)) return `暂存目录不能与${name}目录相同或互相嵌套` }; return true },
  minSize: v => { const n = Number(v); return (v !== '' && v != null && Number.isInteger(n) && n >= 0 && n <= 1024) || '小视频阈值必须是 0 到 1024 的整数' },
}
function validateAll() {
  const checks = [[rules.docUrl, cfg.doc_url], [rules.cron, cfg.index_cron], [rules.cron, cfg.subscribe_cron], [rules.path, cfg.movie_path], [rules.path, cfg.tv_path], [rules.path, cfg.magnet_staging_path], [rules.staging, cfg.magnet_staging_path], [rules.minSize, cfg.min_media_size_mb]]
  for (const [rule, value] of checks) { const result = rule(value); if (result !== true) return result }
  return ''
}

function directoryOptions(type) {
  return directories.value.filter(d => (d.media_type === type || !d.media_type || d.media_type === 'all') && ['115', 'u115', '115网盘Plus'].includes(d.storage)).map(d => ({ title: `${d.name || d.storage} · ${d.path}${d.monitored === true ? ' · 监控已启用' : d.monitored === false ? ' · 未开启监控' : ''}`, value: d.path }))
}
function chooseDirectory(type, path) { if (directoryOptions(type).some(d => d.value === path)) cfg[type === 'tv' ? 'tv_path' : 'movie_path'] = path }
async function loadDirectories() {
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/directories')); const data = res.data || {}; if (res.code === 0 && Array.isArray(data.directories || data.records)) directories.value = data.directories || data.records }
  catch (_) { /* 旧后端没有目录接口时保留手填路径 */ }
}
async function loadVersion() {
  if (props.embedded) return
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/status')); if (res.code === 0 && res.data?.version) fetchedVersion.value = String(res.data.version) } catch (_) { /* 版本号仅用于展示 */ }
}

// 把后端返回的配置填回表单；Cookie 明文永远不进输入框（兼容旧后端返回明文）
function applyConfig(data) {
  for (const key of Object.keys(DEFAULTS)) if (data[key] !== undefined) cfg[key] = data[key]
  cfg.tencent_cookie = ''
  cfg.p115_cookie = ''
  cfg.clear_tencent_cookie = false
  cfg.clear_p115_cookie = false
}

async function load(showTip = false) {
  if (loading.value || saving.value) return
  loading.value = true
  try {
    const res = unwrap(await props.api.get('plugin/Doc115Subscribe/get_config'))
    if (res.code !== 0) throw new Error(res.msg || '读取配置失败')
    const data = res.data
    if (!data || typeof data !== 'object') throw new Error('配置响应格式错误')
    secrets.tencent_ready = !!(data.tencent_cookie_ready || data.cookie_ready || data.tencent_cookie)
    secrets.p115_ready = 'p115_cookie_ready' in data ? !!data.p115_cookie_ready : !!(data.p115_ready || data.p115_cookie)
    for (const key of Object.keys(DEFAULTS)) cfg[key] = DEFAULTS[key]
    applyConfig(data)
    if (showTip === true) {
      msg.value = secrets.tencent_ready ? '已读取最新配置，腾讯文档 Cookie 已配置' : '已读取最新配置，腾讯文档 Cookie 未配置'
      msgType.value = secrets.tencent_ready ? 'info' : 'warning'
    }
  } catch (e) {
    msg.value = `读取失败：${e.message || e}`
    msgType.value = 'error'
  } finally {
    loading.value = false
  }
}

function close() { emit('close') }

async function save() {
  if (saving.value || loading.value) return
  if ((cfg.clear_tencent_cookie && cfg.tencent_cookie.trim()) || (cfg.clear_p115_cookie && cfg.p115_cookie.trim())) {
    msg.value = '替换 Cookie 和清除 Cookie 不能同时选择'
    msgType.value = 'error'
    return
  }
  const invalid = validateAll()
  if (invalid) {
    msg.value = `请先修正：${invalid}`
    msgType.value = 'error'
    formRef.value?.validate?.()
    return
  }
  saving.value = true
  try {
    const payload = { ...cfg, min_media_size_mb: Number(cfg.min_media_size_mb), doc_url: String(cfg.doc_url).trim(), index_cron: String(cfg.index_cron).trim(), subscribe_cron: String(cfg.subscribe_cron).trim() }
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/save_config', payload))
    if (res.code !== 0) throw new Error(res.msg || '配置校验未通过')
    const data = res.data && typeof res.data === 'object' ? res.data : null
    if (data && ('tencent_cookie_ready' in data || 'p115_cookie_ready' in data)) {
      secrets.tencent_ready = !!data.tencent_cookie_ready
      secrets.p115_ready = !!data.p115_cookie_ready
    } else {
      secrets.tencent_ready = cfg.clear_tencent_cookie ? false : !!(cfg.tencent_cookie.trim() || secrets.tencent_ready)
      secrets.p115_ready = cfg.clear_p115_cookie ? false : !!(cfg.p115_cookie.trim() || secrets.p115_ready)
    }
    // 后端会规范化路径（去尾部 /、统一分隔符），用返回值回填，界面与实际生效值一致
    if (data) applyConfig(data)
    else applyConfig({})
    msg.value = '设置已保存'
    msgType.value = 'success'
  } catch (e) {
    msg.value = `保存失败：${e.message || e}`
    msgType.value = 'error'
  } finally {
    saving.value = false
    emit('action')
  }
}

function unwrap(res) {
  if (res && typeof res === 'object' && 'code' in res) return res
  return { code: 0, data: res }
}

onMounted(() => { load(); loadDirectories(); loadVersion() })
</script>

<style scoped>
.doc115-config .doc115-muted { font-size: 0.875rem; margin: 0.75rem 0; overflow-wrap: anywhere; }
.doc115-config-switches { display: flex; flex-wrap: wrap; column-gap: 1.5rem; }
.doc115-config-groups { margin-top: 0.5rem; }
.doc115-group-state { margin-left: auto; padding-right: 0.75rem; font-size: 0.825rem; font-weight: 400; }
.doc115-config .doc115-config-version { margin: 1rem 0 0; font-size: 0.8rem; }
</style>
