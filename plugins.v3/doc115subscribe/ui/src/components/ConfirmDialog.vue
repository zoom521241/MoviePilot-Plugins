<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="value => { if (!value) $emit('cancel') }">
    <section class="doc115-page doc115-confirm" :data-doc115-theme="dark ? 'dark' : 'light'" role="alertdialog" :aria-labelledby="ids.title" :aria-describedby="ids.text">
      <h3 :id="ids.title">{{ title }}</h3>
      <p :id="ids.text" class="doc115-confirm-text">{{ text }}</p>
      <label v-if="check" class="doc115-confirm-check"><input v-model="checked" type="checkbox" /> {{ check }}</label>
      <div class="doc115-actions doc115-confirm-actions">
        <v-btn variant="text" @click="$emit('cancel')">取消</v-btn>
        <v-btn variant="flat" :class="tone === 'danger' ? 'doc115-cta doc115-cta-danger' : 'doc115-cta'" :disabled="!!check && !checked" @click="$emit('confirm')">{{ confirmText }}</v-btn>
      </div>
    </section>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'

// 统一确认弹窗：替代浏览器原生确认框。v-dialog 会传送到 body，所以根节点自带 data-doc115-theme。
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  text: { type: String, default: '' },
  confirmText: { type: String, default: '确认' },
  tone: { type: String, default: 'primary' },
  // 非空时需要先勾选这句说明才能确认（用于「人工确认已转存」这类二次确认）
  check: { type: String, default: '' },
  dark: { type: Boolean, default: false },
})
defineEmits(['confirm', 'cancel'])
const uid = Math.random().toString(36).slice(2, 8)
const ids = { title: `doc115-confirm-title-${uid}`, text: `doc115-confirm-text-${uid}` }
const checked = ref(false)
watch(() => props.modelValue, value => { if (value) checked.value = false })
</script>
