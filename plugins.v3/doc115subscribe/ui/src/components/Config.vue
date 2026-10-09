<template>
  <v-card variant="outlined">
    <v-card-title class="text-subtitle-1 d-flex align-center">
      <span>115文档订阅与查询 · 设置</span>
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
        腾讯文档 Cookie：{{ secrets.tencent_ready ? '已配置，保存时留空会保留' : '未配置，请到「详情」页扫码登录或在此粘贴' }}
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
      <v-select v-model="cfg.link_mode" :items="linkModes" label="同一资源的多个链接" variant="outlined" density="comfortable" class="mt-3" persistent-hint hint="默认按镜像回退，首个成功即停止；只有明确属于分卷或多份必要文件时才选择全部提交。" />
      <v-switch v-model="cfg.upgrade_enabled" color="primary" hide-details label="允许订阅获取新资源版本" />
      <div class="text-caption text-medium-emphasis">开启后，同一影片出现不同资源链接时可以重新获取，可能产生多个版本。</div>

      <v-text-field
        v-model="cfg.doc_url"
        label="腾讯文档链接"
        variant="outlined"
        density="comfortable"
        placeholder="https://docs.qq.com/sheet/xxxx"
        class="mt-3"
        hide-details
      />

      <v-text-field
        v-model="cfg.tencent_cookie"
        label="替换腾讯文档 Cookie（留空保留）"
        type="password"
        autocomplete="new-password"
        variant="outlined"
        density="comfortable"
        class="mt-3"
        hide-details
        hint="推荐在「详情」页扫码登录；已有 Cookie 不会回显。"
        persistent-hint
      />
      <v-checkbox v-model="cfg.clear_tencent_cookie" label="清除已保存的腾讯文档 Cookie" color="warning" hide-details />

      <v-text-field
        v-model="cfg.p115_cookie"
        label="替换 115 Cookie（留空保留）"
        type="password"
        autocomplete="new-password"
        variant="outlined"
        density="comfortable"
        class="mt-4"
        hide-details
      />
      <v-checkbox v-model="cfg.clear_p115_cookie" label="清除单独保存的 115 Cookie（改为复用其它 115 插件）" color="warning" hide-details />

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
import { onMounted, reactive, ref } from 'vue'

const props = defineProps({
  model: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({ get: async () => ({}), post: async () => ({}) }) },
})
const emit = defineEmits(['action', 'close'])

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
  subscribe_enabled: true,
  subscribe_cron: '0 21 * * *',
  index_cron: '0 6 * * *',
  create_subdir: true,
  link_mode: 'first',
  upgrade_enabled: false,
}
const linkModes = [{ title: '镜像回退（推荐）', value: 'first' }, { title: '分卷 / 多份文件：全部提交', value: 'all' }]

const cfg = reactive({ ...DEFAULTS })
const secrets = reactive({ tencent_ready: false, p115_ready: false })
const msg = ref('')
const msgType = ref('info')
const saving = ref(false)
const loading = ref(false)

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
    const payload = { ...cfg }
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

onMounted(() => load())
</script>
