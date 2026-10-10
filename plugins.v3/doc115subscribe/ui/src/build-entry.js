// 生产构建入口：只为满足 Rollup 需要至少一个 input。
// 联邦远程模块（Page / Config）由 vite.config.ts 的 exposes 产出；开发预览壳 App.vue 不进入 dist。
export {}
