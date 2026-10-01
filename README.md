# MoviePilot-Plugins

由 [zoom521241](https://github.com/zoom521241) 维护的 MoviePilot 插件仓库，收录 115 网盘相关插件与文档订阅插件在实际 V3 环境中的兼容性修复与稳定性加固。各插件基于下列原作者的作品继续维护，插件市场与插件页面统一以 `zoom521241` 显示作者。

## 插件一览

| 插件 | 版本 | 原作者 | 作用 |
| --- | --- | --- | --- |
| 115网盘储存 | 3.0.4 | [DDSRem](https://github.com/DDSRem) | 作为 MoviePilot 的存储模块接入 115 网盘，提供文件列表、上传下载、快照等能力 |
| 115网盘STRM助手 | 2.8.74.5 | [DDSRem](https://github.com/DDSRem) | 把 115 网盘资源整理到媒体库目录并生成 `.strm` 文件，供 Emby / Jellyfin 直链播放 |
| 115网盘订阅追更 | 1.5.9 | [mrtian2016](https://github.com/mrtian2016) | 结合 MoviePilot 订阅，自动搜索 115 网盘资源并转存缺失的电影与剧集 |
| Emby媒体库封面生成 | 1.0.2 | [Kioo / wio-ki](https://github.com/wio-ki) | 为 Emby / Jellyfin 媒体库生成动态或静态封面，内置多种样式 |
| 金山文档订阅添加 | 1.2.0 | [jinyuhao-886](https://github.com/jinyuhao-886) | 每天 21:01 扫描金山文档（KDocs）追剧表，自动把三个区段内的在播新剧添加到 MP 订阅 |

## Releases 发版

本仓库已为每个插件开启 Release 安装模式（清单里 `release: true`）。每次推送到 `main`，
GitHub Actions（`.github/workflows/release.yml`）会自动检测版本号，打包并发布 Release：

```sh
# 日常升级流程
1. 修改插件源码
2. 在对应清单里把 version 升一位，并在 history 里补一句说明
3. git push
# -> 工作流自动生成  <PluginId>_v<Version> 的 Release，附 zip / tar.gz / sha256
```

发布判定规则很简单：以 `<PluginId>_v<Version>` 作为 tag，**tag 不存在即发版**。
所以只改源码不改版本号不会产生重复发布；想重发某个版本，用 Actions 页面的
「手动触发」并勾选 force 即可覆盖。

现有 Release：

| 插件 | Release |
| --- | --- |
| 金山文档订阅添加 | `Doc911Subscribe_v1.2.0` |
| 115网盘储存 | `P115Disk_v3.0.4` |
| 115网盘STRM助手 | `P115StrmHelper_v2.8.74.5` |
| 115网盘订阅追更 | `P115StrgmSub_v1.5.9` |
| Emby媒体库封面生成 | `MediaCoverGenerator_v1.0.2` |

## 各插件与原版差异

### 金山文档订阅添加 1.2.0

原插件为 MoviePilot V2 插件，装到 V3 环境会直接失败。本仓库做了 V3 移植：

- **补依赖清单**（首要修复）。原插件目录里没有任何依赖清单，`import openpyxl` 失败导致
  插件加载报错 → MoviePilot 把安装回滚。现新增 `pyproject.toml`，按 PEP 621 声明
  `openpyxl>=3.1.0`，安装插件时由 MoviePilot 自动安装。
- 修复 `app.db.subscribe_oper.Subscribe`：V3 已把订阅模型收敛到 `app.db.models.subscribe`，
  旧写法是第二条致命错误，现改为优先从新位置导入并保留旧路径回退。
- `openpyxl` 改为运行时惰性导入：即使依赖缺失，插件也能正常加载、可在页面改配置，
  只在真正同步时报明确错误，而不是整个插件消失。
- 补齐类级默认配置（`_doc_url` / `_file_id`），修掉未传配置时的 AttributeError。
- 通知类型优先使用 V3 的 `MessageType`；数据库 Session 改为 `try/finally` 释放，
  避免长时间占用订阅表。
- 显示名称由「911文档订阅添加」更名为「金山文档订阅添加」，配置表单标签与日志前缀同步更新。
  插件 ID 仍为 `Doc911Subscribe`，已保存的配置不受影响。

### 115网盘储存 3.0.4

替换 MoviePilot 内置的 115 存储实现，要求 MoviePilot V3。相比原版的调整：

- 修复并发场景下限流等待时间不断翻倍（2 秒变 4、8、16 秒）导致整理卡住的问题。
- 云盘移动成功后改用稳定的文件 ID 完成重命名，不再依赖可能尚未更新的路径查询结果。
- 目录 ID 统一按整数处理，避免把非根目录误判为根目录；严格存在性查询直接读取远端状态，网络错误仍按未知处理。

### 115网盘STRM助手 2.8.74.5

负责资源整理与 STRM 生成。相比原版的调整：

- **修复 V3 启动即崩溃**（2.8.74.5）。原插件写的是 `from app.core import global_vars`，而 V3 把 `app.core` 收敛为只导出 `config`，该导入在 V3 下直接抛 `ImportError`，插件加载失败。现改为先尝试 `app.core.config.global_vars`，失败再回退 V2 的 `app.core.global_vars`，两个版本都能用同一份源码。
- 整目录转存时子文件往往延迟才可见，原先会因为少扫到文件而漏整理。改为先收集再复扫：每轮间隔 10 秒，至少观察 30 秒且连续两次完整比较不变才认定稳定，最多 6 轮并设 120 秒软时限；到时限仍未收敛就只提交已收集到的有效文件，保留记录待核查，不无限重试。
- 兼容 MoviePilot V3 的持久化整理结算，原先绕过宿主自行入队会导致同一任务被重复提交，现在交由宿主原生流程执行。
- 扫描进度持久化，停止后下次启动恢复未完成目录并跳过已受理的文件，即使选择 `latest` 模式也会恢复。

### 115网盘订阅追更 1.5.9

让订阅资源全部由 115 网盘供给。相比原版的调整（均为 V3 适配）：

- MoviePilot V3 把缺失剧集字典的键改成了带来源前缀的格式（如 `tmdb:95350`），原先按裸 ID 查不到键，会被误判为「没有缺失」而跳过整个订阅。现在依次尝试裸 ID、字符串 ID 和带前缀的键。
- 每轮同步以媒体库真实缺失回写 `lack_episode`，修正订阅页「已订阅集数」显示不准；删除剧集或重置订阅后，下一轮同步自动校准。
- 补齐 V3 显式数据库 Session 的事务提交，此前站点屏蔽只改内存事务、退出即丢，日志显示成功但实际未保存。
- 修复订阅站点与系统默认站点交集为空时 V3 回退为全部默认站点、导致「仅 115」屏蔽被绕过、PT 站抢先下载的问题。

### Emby媒体库封面生成 1.0.2

相比原版的调整：

- 入库事件交给可停止的后台队列处理，同一批次、同一媒体库合并生成，不再阻塞 V3 的整理后处理流程。
- Emby 无法下载远程背景图时，回退使用同一媒体项的海报，避免反复等待不可用的资源。
- 停止任务后取消待处理事件及后续上传，不影响用户已有的配置与封面样式。

## 仓库结构

```text
package.v2.json     V2 兼容清单（4 个 115/Emby 插件）
plugins.v2/         V2 布局的插件源码
package.v3.json     V3 清单（金山文档订阅添加）
plugins.v3/         V3 插件源码，按 PEP 621 带 pyproject.toml 依赖声明
tests/              离线回归测试
.github/workflows/  Releases 自动发版
```

`plugins.v3/` 下的插件会因为 `release: true` 走 Release 安装包安装，
`plugins.v2/` 下的插件在 V3 中通过兼容索引发现。其中 115网盘储存与 Emby媒体库封面生成
声明 `system_version >=3.0.0`，需要 V3 环境。

## 安装

在 MoviePilot 插件市场添加本仓库地址：

```text
https://github.com/zoom521241/MoviePilot-Plugins
```

## 115 插件依赖兼容

三个 115 插件统一固定 `p115client==0.0.9.6.5.1` 和 `python-concurrenttools==0.1.8`。`python-concurrenttools 0.1.9` 不再提供当前 p115client 使用的 `threadpool_map`、`taskgroup_map`，会导致存储与 STRM 助手加载失败，订阅追更则可能误报“p115client 未安装”。

此组合已在 Python 3.14.7 环境验证三个插件的 47 条 p115client 导入，以及同步、异步映射接口；这不等同于完整网盘业务端到端验证。安装后如常驻进程仍缓存旧依赖，需要重启容器。版本约束随插件一起保存，重建时应保留 `/config` 挂载和本仓库的插件来源绑定。依赖属于容器共享环境，其他插件若明确要求冲突版本，应先解决约束冲突。

## 验证

各插件的修复均配套离线回归测试：

```sh
python -m unittest discover -s tests -v
```

## 升级与持久化

拉取 Docker 新镜像不会直接改动正在运行的插件，重建容器时应保留原 `/config` 挂载。仓库推送也不会自动切换已安装插件的来源，需要在 MoviePilot V3 的插件来源选项中明确选择本仓库，刷新市场后重新安装，仅覆盖运行目录无法保证容器重建后仍生效。

## 来源

115网盘STRM助手与115网盘储存原作者为 [DDSRem](https://github.com/DDSRem)；115网盘订阅追更原作者为 [mrtian2016](https://github.com/mrtian2016)；Emby媒体库封面生成来自 [Kioo](https://github.com/wio-ki/MoviePilot-Plugins)，其目录内附原 GPL-3.0 许可证与本次修改说明；金山文档订阅添加原作者为 [jinyuhao-886](https://github.com/jinyuhao-886)。

本仓库版本由 **zoom521241** 维护并以此显示插件作者，原始作品来源在本 README 中署名。原许可证、源码版权声明以及 `wheels/` 中依赖包各自的发行元数据继续保留。
