<template>
  <v-card variant="outlined">
    <v-card-title class="text-subtitle-1">115文档订阅与查询 · 设置</v-card-title>
    <v-card-text>
      <v-alert v-if="msg" :type="msgType" variant="tonal" density="comfortable" class="mb-3">{{ msg }}</v-alert>

      <v-alert
        :type="cfg.tencent_cookie ? 'success' : 'warning'"
        variant="tonal"
        density="comfortable"
        class="mb-3"
      >
        腾讯文档 Cookie：{{ cfg.tencent_cookie ? `已配置（${cfg.tencent_cookie.length} 字符）` : '未配置 —— 请到「详情」页扫码登录，或在此手动粘贴' }}
        <span v-if="cfg.tencent_cookie" class="text-medium-emphasis">｜开头：{{ cfg.tencent_cookie.slice(0, 24) }}…</span>
      </v-alert>

      <v-row dense>
        <v-col cols="12" md="4">
          <v-switch v-model="cfg.enabled" label="启用插件" color="primary" hide-details />
        </v-col>
        <v-col cols="12" md="4">
          <v-switch v-model="cfg.subscribe_enabled" label="启用电影订阅同步" color="primary" hide-details />
        </v-col>
        <v-col cols="12" md="4">
          <v-switch v-model="cfg.use_agent" label="类型不确定时调用 MP 智能体" color="primary" hide-details />
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

      <v-textarea
        v-model="cfg.tencent_cookie"
        label="腾讯文档 Cookie"
        variant="outlined"
        density="comfortable"
        rows="3"
        class="mt-3"
        hide-details
        hint="推荐在「详情」页用扫码登录自动获取；也可手动粘贴。仅本地保存。"
        persistent-hint
      />

      <v-textarea
        v-model="cfg.p115_cookie"
        label="115 Cookie（留空则自动复用其它115插件）"
        variant="outlined"
        density="comfortable"
        rows="2"
        class="mt-4"
        hide-details
      />

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
const emit = defineEmits(['save', 'action'])

const DEFAULTS = {
  enabled: false,
  doc_url: 'https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo',
  tencent_cookie: '',
  p115_cookie: '',
  movie_path: '/115-影视/115-downloads/电影',
  tv_path: '/115-影视/115-downloads/电视剧',
  magnet_staging_path: '/115-影视/115-downloads/磁力链接',
  subscribe_enabled: true,
  subscribe_cron: '0 21 * * *',
  index_cron: '0 6 * * *',
  use_agent: true,
  create_subdir: true,
}

const cfg = reactive({ ...DEFAULTS })
const msg = ref('')
const msgType = ref('info')
const saving = ref(false)
const loading = ref(false)

async function load(showTip = false) {
  loading.value = true
  try {
    const res = await props.api.get('plugin/Doc115Subscribe/get_config')
    const data = res && res.data !== undefined ? res.data : res
    if (data && typeof data === 'object') Object.assign(cfg, { ...DEFAULTS, ...data })
    if (showTip) {
      msg.value = cfg.tencent_cookie
        ? `已读取到最新配置：腾讯文档 Cookie 已配置（${cfg.tencent_cookie.length} 字符）`
        : '已读取到最新配置：腾讯文档 Cookie 仍为空（请到「详情」页扫码登录）'
      msgType.value = cfg.tencent_cookie ? 'success' : 'warning'
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = { ...cfg }
    await props.api.post('plugin/Doc115Subscribe/save_config', payload)
    msg.value = '配置已保存'
    msgType.value = 'success'
    emit('save', payload)
  } catch (e) {
    msg.value = `保存失败：${e.message || e}`
    msgType.value = 'error'
  } finally {
    saving.value = false
    emit('action')
  }
}

onMounted(load)
</script>
