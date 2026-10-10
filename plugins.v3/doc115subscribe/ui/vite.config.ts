import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

export default defineConfig(({ command, mode }) => ({
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
    // 生产构建不以 index.html 为入口，build:preview（--mode development）仍用 index.html；避免把合成预览（App.vue 与桩数据）打进 dist
    rollupOptions: command === 'build' && mode !== 'development' ? { input: 'src/build-entry.js' } : {},
  },
}))
