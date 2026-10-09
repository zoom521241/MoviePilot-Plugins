# MoviePilot-Plugins

由 [zoom521241](https://github.com/zoom521241) 维护的 MoviePilot V3 插件仓库，主要收录 115 网盘相关插件与文档订阅插件。

## 插件一览

| 插件 | 版本 | 一句话说明 |
| --- | --- | --- |
| 115文档订阅与查询 | 0.8.0 | 直读腾讯文档追更表，按 MP 电影订阅自动转存到 115；支持插件内跨表搜索、一键转存、磁力/ed2k 离线下载 |
| 115网盘STRM助手 | 2.8.74.9 | 把 115 网盘资源整理到媒体库目录并生成 `.strm`，供 Emby / Jellyfin 直链播放 |
| 115网盘储存 | 3.0.5 | 作为 MoviePilot 的存储模块接入 115 网盘（文件列表、上传下载、移动等） |
| 115网盘订阅追更 | 1.5.9 | 结合 MoviePilot 订阅自动搜索 115 资源并转存缺失的电影与剧集 |
| 金山文档订阅添加 | 1.2.0 | 每天扫描金山文档追剧表，自动把在播新剧加入 MP 订阅 |
| Emby媒体库封面生成 | 1.0.2 | 为 Emby / Jellyfin 媒体库生成动态或静态封面 |
| 夸克网盘搬家 | 0.1.0 | 把夸克网盘指定目录中的影片搬迁到 115 网盘指定目录 |

## 安装

在 MoviePilot 插件市场添加本仓库地址：

```text
https://github.com/zoom521241/MoviePilot-Plugins
```

插件采用 Release 安装模式，每个插件只保留**最新版本**的 Release（旧版本 Release 已清理，tag 仍在）。

## 发版

改源码 → 升 `package.v3.json` 里对应插件的 `version` 并在 `history` 补一句说明 → push `main`；
`.github/workflows/release.yml` 会自动以 `<PluginId>_v<Version>` 为 tag 生成 Release（tag 已存在则跳过）。

## 依赖与持久化

- 三个 115 插件固定 `p115client==0.0.9.6.5.1` 与 `python-concurrenttools==0.1.8`；
  0.1.9 不再提供 `threadpool_map` / `taskgroup_map`，会导致存储与 STRM 助手加载失败。
- 仓库推送不会自动切换已安装插件的来源：需在 MP 的插件来源中选择本仓库、刷新市场后重装；
  重建容器请保留 `/config` 挂载，否则配置与索引丢失。

## 测试

```sh
python -m unittest discover -s tests -v
```

## 来源与许可

115网盘STRM助手、115网盘储存原作者 [DDSRem](https://github.com/DDSRem)；115网盘订阅追更原作者 [mrtian2016](https://github.com/mrtian2016)；
Emby媒体库封面生成来自 [Kioo](https://github.com/wio-ki/MoviePilot-Plugins)；金山文档订阅添加原作者 [jinyuhao-886](https://github.com/jinyuhao-886)。

本仓库版本由 **zoom521241** 维护并以此显示插件作者；原许可证、源码版权声明与 `wheels/` 中依赖包各自的发行元数据继续保留。
