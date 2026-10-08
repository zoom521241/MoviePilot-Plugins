import { createApp } from 'vue'
import App from './App.vue'

// 只有本地开发（npm run dev）才装配完整的 Vuetify（全局注册组件 + 引入样式）。
// 线上插件是「联邦远程模块」：v-* 组件与样式都由 MoviePilot 宿主提供，
// 所以生产构建里这整块会被摇掉，产物不含 Vuetify 与全量组件。
if (import.meta.env.DEV) {
  const [vuetifyMod, components, directives, defaultsMod, themeMod, _styles] = await Promise.all([
    import('vuetify'),
    import('vuetify/components'),
    import('vuetify/directives'),
    import('./vuetify/defaults'),
    import('./vuetify/theme'),
    import('vuetify/styles'),
  ])
  const vuetify = vuetifyMod.createVuetify({
    components,
    directives,
    defaults: defaultsMod.default,
    theme: themeMod.default,
  })
  createApp(App).use(vuetify).mount('#app')
} else {
  createApp(App).mount('#app')
}
