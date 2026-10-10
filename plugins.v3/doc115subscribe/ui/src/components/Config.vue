<template>
  <v-card variant="outlined" class="doc115-config" :data-doc115-theme="darkTheme ? 'dark' : 'light'">
    <v-card-title class="text-subtitle-1 d-flex align-center">
      <span>115文档订阅与查询 · 设置 <small class="doc115-muted">前端 v0.10.5</small></span>
      <v-spacer />
      <v-btn icon size="small" variant="text" title="关闭" @click="close">
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </v-card-title>
    <v-card-text>
      <v-alert v-if="msg" :type="msgType" variant="tonal" density="comfortable" class="mb-3">{{ msg }}</v-alert>

      <v-alert
        :type="secrets.tencent_ready ? 'info' : 'warning'"
        variant="tonal"
        density="comfortable"
        class="mb-3"
      >
        腾讯文档 Cookie：{{ secrets.tencent_ready ? '已配置，保存时留空会保留' : '未配置，请在插件页面「设置」中扫码登录' }}
        ｜115 Cookie：{{ secrets.p115_ready ? '已配置，保存时留空会保留' : '未单独配置，可复用其它 115 插件' }}
      </v-alert>

      <v-row dense>
        <v-col cols="12" md="4">
          <v-switch v-model="cfg.enabled" label="启用插件" color="primary" hide-details />
        </v-col>
        <v-col cols="12" md="4">
          <v-switch v-model="cfg.subscribe_enabled" label="启用电影订阅同步" color="primary" hide-details />
        </v-col>
      </v-row>

      <v-row dense>
        <v-col cols="12">
          <v-switch
            v-model="cfg.create_subdir"
            color="primary"
            hide-details
            label="转存时按「片名 (年份)」建子目录（推荐开启，便于 MP 整理识别）"
          />
        </v-col>
      </v-row>
      <v-text-field
        v-model="cfg.doc_url"
        label="腾讯文档链接"
        variant="outlined"
        density="comfortable"
        placeholder="https://docs.qq.com/sheet/xxxx"
        class="mt-3"
        hide-details
      />

      <p class="doc115-muted">下载目录应对应 MP 已配置的 115 存储目录。本插件不修改 MP 监控或整理配置；未核实监控时不能保证保存后会自动整理。</p>
      <v-select v-if="movieDirectories.length" v-model="selectedMovieDirectory" :items="movieDirectories" label="选择已缓存的 MP 电影下载目录" variant="outlined" density="comfortable" @update:model-value="chooseDirectory('movie', $event)" />
      <v-select v-if="tvDirectories.length" v-model="selectedTvDirectory" :items="tvDirectories" label="选择已缓存的 MP 电视剧下载目录" variant="outlined" density="comfortable" @update:model-value="chooseDirectory('tv', $event)" />
      <v-row dense class="mt-3">
        <v-col cols="12" md="6">
          <v-text-field
            v-model="cfg.movie_path"
            label="115 电影下载目录"
            variant="outlined"
            density="comfortable"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-text-field
            v-model="cfg.tv_path"
            label="115 电视剧下载目录"
            variant="outlined"
            density="comfortable"
            hide-details
          />
        </v-col>
      </v-row>

      <details class="doc115-config-advanced">
      <summary>高级设置（链接策略、计划、Cookie）</summary>
      <v-select v-model="cfg.link_mode" :items="linkModes" label="自动订阅：同一资源的多个链接" variant="outlined" density="comfortable" class="mt-3" persistent-hint hint="默认镜像回退，仅明确失败后尝试下一来源。手动获取只使用确认面板选定的链接。分卷 / 全部提交只适用于确实需要全部资源的条目。" />
      <v-switch v-model="cfg.upgrade_enabled" color="primary" hide-details label="允许订阅获取更高画质版本" />
      <p class="doc115-muted">升级失败保留旧版本。画质无法确认时暂停自动升级判断，避免重复获取。</p>
      <v-text-field v-model.number="cfg.min_media_size_mb" type="number" min="0" max="1024" step="1" label="整理核对忽略小视频（MB）" variant="outlined" density="comfortable" class="mt-3" persistent-hint hint="默认 10，0 关闭。仅忽略已知体积小于阈值的附带视频；不删除文件，不改 MP 过滤规则。新任务使用新设置。" />

      <v-text-field
        v-model="cfg.magnet_staging_path"
        label="磁力 / ed2k 暂存目录"
        variant="outlined"
        density="comfortable"
        class="mt-3"
        hide-details
        hint="磁力/ed2k 先离线下载到这里，完成后由本插件走「115网盘Plus」搬到上面的电影/电视剧目录（115 分享链接不受影响，直接进最终目录）"
        persistent-hint
      />

      <v-row dense class="mt-3">
        <v-col cols="12" md="6">
          <v-text-field
            v-model="cfg.index_cron"
            label="索引刷新 cron"
            variant="outlined"
            density="comfortable"
            placeholder="0 6 * * *"
            hide-details
          />
        </v-col>
        <v-col cols="12" md="6">
          <v-text-field
            v-model="cfg.subscribe_cron"
            label="订阅同步 cron"
            variant="outlined"
            density="comfortable"
            placeholder="0 21 * * *"
            hide-details
          />
        </v-col>
      </v-row>
      <v-text-field v-model="cfg.tencent_cookie" label="替换腾讯文档 Cookie（留空保留）" type="password" autocomplete="new-password" variant="outlined" density="comfortable" class="mt-3" hide-details />
      <v-checkbox v-model="cfg.clear_tencent_cookie" label="清除已保存的腾讯文档 Cookie" color="warning" hide-details />
      <v-text-field v-model="cfg.p115_cookie" label="替换 115 Cookie（留空保留）" type="password" autocomplete="new-password" variant="outlined" density="comfortable" class="mt-3" hide-details />
      <v-checkbox v-model="cfg.clear_p115_cookie" label="清除单独保存的 115 Cookie（改为复用其它 115 插件）" color="warning" hide-details />
      </details>
    </v-card-text>
    <v-card-actions>
      <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="load(true)">重新读取配置</v-btn>
      <v-spacer />
      <v-btn variant="text" prepend-icon="mdi-close" @click="close">关闭</v-btn>
      <v-btn color="primary" :loading="saving" prepend-icon="mdi-content-save" @click="save">保存配置</v-btn>
    </v-card-actions>
  </v-card>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import '../styles/doc115.css'

const props = defineProps({
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
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
const directories = ref([])
const selectedMovieDirectory = ref(''), selectedTvDirectory = ref('')
const movieDirectories = computed(() => directoryOptions('movie'))
const tvDirectories = computed(() => directoryOptions('tv'))
function directoryOptions(type) {
  return directories.value.filter(d => (d.media_type === type || !d.media_type || d.media_type === 'all') && ['115', 'u115', '115网盘Plus'].includes(d.storage)).map(d => ({ title: `${d.name || d.storage} · ${d.path} · ${d.monitored === true ? '监控已启用' : '监控未确认'}`, value: d.path }))
}
function chooseDirectory(type, path) { if (directoryOptions(type).some(d => d.value === path)) cfg[type === 'tv' ? 'tv_path' : 'movie_path'] = path }
async function loadDirectories() {
  try { const res = unwrap(await props.api.get('plugin/Doc115Subscribe/directories')); const data = res.data || {}; if (res.code === 0 && Array.isArray(data.directories || data.records)) directories.value = data.directories || data.records }
  catch (_) { /* Older hosts can keep the explicit path fields. */ }
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
    // Credentials never enter the input controls, including older backend responses.
    for (const key of Object.keys(DEFAULTS)) cfg[key] = data[key] === undefined ? DEFAULTS[key] : data[key]
    cfg.tencent_cookie = ''
    cfg.p115_cookie = ''
    cfg.clear_tencent_cookie = false
    cfg.clear_p115_cookie = false
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

function close() {
  emit('close')
}

async function save() {
  if (saving.value || loading.value) return
  if ((cfg.clear_tencent_cookie && cfg.tencent_cookie.trim()) || (cfg.clear_p115_cookie && cfg.p115_cookie.trim())) {
    msg.value = '替换 Cookie 和清除 Cookie 不能同时选择'
    msgType.value = 'error'
    return
  }
  saving.value = true
  try {
    const minimum = Number(cfg.min_media_size_mb)
    if (cfg.min_media_size_mb === '' || cfg.min_media_size_mb == null || !Number.isInteger(minimum) || minimum < 0 || minimum > 1024) throw new Error('小视频阈值必须是 0 到 1024 的整数')
    const payload = { ...cfg, min_media_size_mb: minimum }
    const res = unwrap(await props.api.post('plugin/Doc115Subscribe/save_config', payload))
    if (res.code !== 0) throw new Error(res.msg || '配置校验未通过')
    secrets.tencent_ready = cfg.clear_tencent_cookie ? false : !!(cfg.tencent_cookie.trim() || secrets.tencent_ready)
    secrets.p115_ready = cfg.clear_p115_cookie ? false : !!(cfg.p115_cookie.trim() || secrets.p115_ready)
    cfg.tencent_cookie = ''
    cfg.p115_cookie = ''
    cfg.clear_tencent_cookie = false
    cfg.clear_p115_cookie = false
    msg.value = '配置已保存'
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

onMounted(() => { load(); loadDirectories() })
</script>

<style scoped>
.doc115-config-advanced { margin-top: 1rem; border-top: 1px solid var(--doc115-border); padding-top: 0.75rem; }
.doc115-config-advanced summary { color: var(--doc115-blue); cursor: pointer; padding: 0.5rem 0; }
.doc115-config .doc115-muted { font-size: 0.875rem; margin: 0.75rem 0; overflow-wrap: anywhere; }
</style>
