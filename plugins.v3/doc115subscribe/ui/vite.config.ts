import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

/**
 * 兜底过滤：把打包进来的 Vuetify 组件样式（`.v-*`）删掉。
 * 线上 Vuetify 样式由 MoviePilot 宿主提供（联邦共享），插件里不该再打一份。
 * （正常路径下 `src/main.js` 只在 DEV 引入 vuetify/styles，构建产物本就没有它；
 *  这里再加一层保险，防止以后有人误在组件里 import。）
 *
 * ⚠️ 该 postcss 插件必须挂在 vite 配置的 `css.postcss` 下才生效（放在根级 postcss.config 不生效）。
 */
function dropVuetifyComponents() {
  return {
    postcssPlugin: 'drop-vuetify-components',
    Once(root) {
      root.walkRules((rule) => {
        const sel = rule.selector || ''
        if (/(^|[\s,>+~])\.v-[a-z]/.test(sel)) rule.remove()
      })
    },
  }
}
dropVuetifyComponents.postcss = true

export default defineConfig({
  plugins: [
    vue(),
    federation({
      // 远程模块名必须与后端 get_render_mode()/MP 联邦清单一致
      name: 'Doc115Subscribe',
      filename: 'remoteEntry.js',
      exposes: {
        './Page': './src/components/Page.vue',
        './Config': './src/components/Config.vue',
      },
      shared: {
        vue: {},
        vuetify: {},
      },
    }),
  ],
  build: {
    target: 'esnext',
    // 产物保持未压缩：与线上一致（未混淆、可读，便于排查与紧急热修）
    minify: false,
    cssCodeSplit: false,
    modulePreload: false,
    outDir: 'dist',
    emptyOutDir: true,
  },
  css: {
    postcss: {
      plugins: [dropVuetifyComponents()],
    },
  },
})
