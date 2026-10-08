# Doc115Subscribe 插件前端（UI 源码工程）

MoviePilot V3 插件「115文档订阅与查询」的详情页 / 设置页前端。
技术栈：**Vue 3 + Vuetify 3 + Vite 5 + @originjs/vite-plugin-federation**（模块联邦）。

## 为什么需要这个工程

插件在 MoviePilot 里是**模块联邦远程模块**：
- 后端 `get_render_mode() -> ("vue", "dist/assets")`，MP 前端通过
  `GET /api/v1/plugin/remotes?token=moviepilot` 拿到 `dist/assets/remoteEntry.js` 再动态加载。
- 所以**运行期只需要 `dist/`（编译产物）**；本目录是它的源码，用来重新构建 `dist/`。

> ⚠️ 历史上这个工程只存在于开发机的临时目录（`mp-plugin-ui`），仓库里只有 `dist/` 产物，
> 导致**只能手改编译产物**。现在源码已入库，改 UI 请改这里再 `npm run build`。

## 联邦约定（改了会加载不出来）

| 项 | 值 |
|---|---|
| 远程名 `name` | `Doc115Subscribe`（与 MP 插件 ID 一致） |
| 入口文件 `filename` | `remoteEntry.js` |
| 暴露模块 | `./Page` → `src/components/Page.vue`；`./Config` → `src/components/Config.vue` |
| 共享依赖 | `vue`、`vuetify`（由 MP 宿主提供，插件不重复打包完整 Vuetify 样式） |

组件与宿主的交互约定：
- 组件 props：`api`（宿主注入的 axios，自带鉴权）、`model`
- 组件 emits：`action`（数据变化通知宿主刷新）、`close`（关闭详情页）
- 调后端：`props.api.get/post('plugin/Doc115Subscribe/<path>')`
- 后端接口返回 `{code, msg, data}`

## 安装与构建

```bash
npm install --ignore-scripts   # 直接 npm install 可能因 esbuild postinstall 在 Windows 报 EBUSY
npm run build
```

构建产物在 `ui/dist/assets/`。发布时把 `ui/dist/assets/*` 复制到插件目录
`plugins.v3/doc115subscribe/dist/assets/`（覆盖旧产物），再按根 README 的发版流程升版本、推仓库。

## 本地预览

```bash
npm run dev
```
`src/App.vue` 是开发态壳子（注入桩 api）；真实数据要在 MoviePilot 里看。

## 目录结构

```
ui/
├── index.html                     开发/构建入口
├── vite.config.ts                 联邦配置 + 过滤 Vuetify 组件样式（css.postcss）
├── package.json
└── src/
    ├── main.js                    开发态挂载（createVuetify）
    ├── App.vue                    开发态壳子
    ├── components/
    │   ├── Page.vue               详情页：状态/工具/搜索/筛选/分页/结果卡片
    │   └── Config.vue             设置页：开关/路径/cron/Cookie
    └── vuetify/
        ├── defaults.ts            组件默认值
        └── theme.ts               主题（light/dark/purple/transparent）
```

## 注意

- `vite.config.ts` 里的 `dropVuetifyComponents`（postcss 插件）必须挂在 `css.postcss` 下才生效；
  它把 `.v-*`（Vuetify 组件样式）过滤掉，避免与宿主重复。
- 构建保持 `minify: false`：产物未压缩、可读，便于线上排查与紧急热修（与历史产物一致）。
- 结果卡片里「大包」（`sheet_bundle` / `bundle` / `no_link`）条目**不显示转存按钮**，
  只显示可点击的 115/磁力 链接与提示文案（与后端 `do_transfer` 的拦截保持一致）。
