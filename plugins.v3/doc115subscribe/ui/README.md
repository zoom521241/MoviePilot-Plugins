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
npm run build                  # 生产构建（联邦远程模块，不含 Vuetify 样式）
npm run build:preview          # 独立可打开的预览版（自带 Vuetify，产物在 dist-preview/）
```

构建产物在 `ui/dist/assets/`。发布时把 `ui/dist/assets/*` 复制到插件目录
`plugins.v3/doc115subscribe/dist/assets/`（覆盖旧产物），再按根 README 的发版流程升版本、推仓库。

## 本地预览

```bash
npm run dev            # 开发态（Vite dev server，自动带 Vuetify）
npm run build:preview  # 或构建成一份可离线打开的静态页（dist-preview/index.html）
```
`src/App.vue` 是开发态合成测试壳子：注入完全本地的桩 API，搜索、提交与核对都不访问 MP、115 或腾讯文档。提供明暗主题、320/360/390px 宽度与 200% 字体选项，包含 20 集中 1 集整理前被删除的任务。合成接口调用记录可验证选定的链接来源与电影/电视剧目录。不要把预览里的成功响应当作真实转存验证。

Node 合成测试：在仓库根运行 `node --test tests/test_doc115subscribe_frontend.mjs`。覆盖请求身份、成功/失败/部分/查询错误结果、确认面板、轮询生命周期、取消旧搜索请求和样式对比度；发布前还需通过浏览器读取实际联邦产物的计算样式与窄屏布局。

## 目录结构

```
ui/
├── index.html                     开发/构建入口
├── vite.config.ts                 联邦配置（远程名 / exposes / shared）
├── package.json
└── src/
    ├── main.js                    开发态挂载（createVuetify）
    ├── App.vue                    开发态壳子（合成桩数据，不进入生产 dist）
    ├── build-entry.js             生产构建的空入口：dist 只含联邦 exposes
    ├── version.js                 UI_BUILD 版本常量（Page / Config 共用，测试守护与 package.json 一致）
    ├── components/
    │   ├── Page.vue               搜索/电影订阅/任务；来源与保存目录确认
    │   ├── Config.vue             分组设置（腾讯文档 / 115 / 保存目录 / 电影订阅 / 高级），实时校验
    │   └── ConfirmDialog.vue      统一确认弹窗（替代浏览器原生确认框，跟随插件深浅主题）
    ├── styles/doc115.css          插件命名空间语义颜色与响应式布局
    └── vuetify/
        ├── defaults.ts            组件默认值
        └── theme.ts               主题（light/dark/purple/transparent）
```

## 注意

- **样式来源**：线上 `v-*` 组件的样式与 Vue/Vuetify 运行时都由 MoviePilot 宿主提供（联邦共享）。
  所以 `src/main.js` 里装配 Vuetify 的那段**只在 DEV 生效**，生产构建会被摇掉，
  产物里不含 Vuetify 全量样式（否则会与宿主重复、体积多几百 KB）。
  组件里的 `v-btn` / `v-card` 等是 `resolveComponent` 解析宿主全局注册的组件，无需自己 import。
- 字段和状态使用 `doc115-*` 类与 CSS 变量，不依赖宿主材质颜色 utility；根节点通过宿主 `dark` 布尔属性选择主题，兼容自定义主题名。
- 页面刷新只读本地任务，活动任务页可见时从 20 秒开始轮询，无变化或失败会延长间隔；切页、隐藏、失活、关闭会停止轮询。扫码轮询仅在设置面板可见时运行。
- 写操作使用宿主注入的会话 API，动作由后端 `allowed_actions` 提供并在执行时再次授权校验，不把后台 Token 发给浏览器。
- 构建保持 `minify: false`：产物未压缩、可读，便于线上排查与紧急热修（与历史产物一致）。
- 结果卡片里「大包」（`sheet_bundle` / `bundle` / `no_link`）条目**不显示转存按钮**，
  只显示可点击的 115/磁力 链接与提示文案（与后端 `do_transfer` 的拦截保持一致）。
