# MoviePilot-Plugins

由 [zoom521241](https://github.com/zoom521241) 维护的 MoviePilot 插件仓库，收录 115 网盘相关插件与文档订阅插件在实际 V3 环境中的兼容性修复与稳定性加固。各插件基于下列原作者的作品继续维护，插件市场与插件页面统一以 `zoom521241` 显示作者。

## 插件一览

| 插件 | 版本 | 原作者 | 作用 |
| --- | --- | --- | --- |
| 115网盘储存 | 3.0.5 | [DDSRem](https://github.com/DDSRem) | 作为 MoviePilot 的存储模块接入 115 网盘，提供文件列表、上传下载、快照等能力 |
| 115网盘STRM助手 | 2.8.74.9 | [DDSRem](https://github.com/DDSRem) | 把 115 网盘资源整理到媒体库目录并生成 `.strm` 文件，供 Emby / Jellyfin 直链播放 |
| 115网盘订阅追更 | 1.5.9 | [mrtian2016](https://github.com/mrtian2016) | 结合 MoviePilot 订阅，自动搜索 115 网盘资源并转存缺失的电影与剧集 |
| Emby媒体库封面生成 | 1.0.2 | [Kioo / wio-ki](https://github.com/wio-ki) | 为 Emby / Jellyfin 媒体库生成动态或静态封面，内置多种样式 |
| 金山文档订阅添加 | 1.2.0 | [jinyuhao-886](https://github.com/jinyuhao-886) | 每天 21:01 扫描金山文档（KDocs）追剧表，自动把三个区段内的在播新剧添加到 MP 订阅 |
| 夸克网盘搬家 | 0.1.0 | zoom521241 | 把夸克网盘指定目录中的影片搬迁到 115 网盘指定目录，扫码登录、串行限速 |
| 115文档订阅与查询 | 0.2.4 | zoom521241 | 直读腾讯文档追更表（禁用导出也能读），定时为**电影订阅**转存到 115，并支持插件内跨表搜索、一键转存；支持微信扫码登录、磁力/ed2k 离线下载 |

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
| 115网盘储存 | `P115Disk_v3.0.5` |
| 115网盘STRM助手 | `P115StrmHelper_v2.8.74.9` |
| 115网盘订阅追更 | `P115StrgmSub_v1.5.9` |
| Emby媒体库封面生成 | `MediaCoverGenerator_v1.0.2` |
| 夸克网盘搬家 | `QuarkTo115_v0.1.0` |
| 115文档订阅与查询 | `Doc115Subscribe_v0.2.4` |

## 仓库结构

```text
package.v3.json     V3 清单，全部 7 个插件都在这里
plugins.v3/         V3 插件源码，依赖按 PEP 621 写在各自的 pyproject.toml
package.v2.json     已置空，只保留 V2 回退位
tests/              离线回归测试
.github/workflows/  Releases 自动发版
```

全部插件都是面向 MoviePilot V3 的，源码统一放在 `plugins.v3/`。MoviePilot 在 V3 上会先查
`package.v3.json`，查不到才按代际回退到 `package.v2.json`，所以把条目放回
`package.v2.json` 即可让插件重新被 V2 识别。

Release 的 tag 格式是 `<插件ID>_v<版本号>`，**只认版本号、与清单写在 v2 还是 v3 无关**。
因此只搬目录和清单、不动版本号时，已发布安装包的 URL 与内容完全不变，MoviePilot 不会
判定有更新；只有真正改了依赖或代码并升版本号才会重新打包。

## 仅支持 V3

本仓库全部插件限定 MoviePilot V3，V2 环境下**不会出现在插件市场里**。这是两道闸门叠加的结果：

| 闸门 | 位置 | 作用 |
| --- | --- | --- |
| `system_version: ">=3.0.0"` | 每个插件条目 | 版本不满足直接拒绝安装 |
| `v2: false` | 每个插件条目 | MP 的 `is_plugin_generation_compatible()` 在 V2 环境读到该条目时剔除它 |
| 清单位于 `package.v3.json` | 仓库结构 | V2 不会主动读取 v3 清单 |

三条都在容器里用 MoviePilot 自己的函数实测过：V3（v3.0.10-1）下 7 个插件全部可见可装，
模拟 V2 环境下 7 个全部隐藏。要恢复 V2 可见性，把条目放回 `package.v2.json` 并去掉 `v2: false`
即可，但源码里的 V3 专有写法（如 `MessageType`、新的 Subscribe 导入路径）需要另行处理。

## 依赖清单必须写全

MoviePilot 的插件依赖清单是**二选一，不是合并**：

```python
# app/adapters/system/plugin/manifest.py
def select_dependency_manifest(plugin_dir):
    pyproject_file = plugin_dir / PYPROJECT_FILENAME
    if pyproject_file.is_file():
        return pyproject_file        # 有 pyproject.toml 就直接返回，不看 requirements.txt
```

也就是说只要插件目录下存在 `pyproject.toml`，同目录的 `requirements.txt` 会被**完全忽略**
且不会回退。曾经因为 115网盘储存 的 `pyproject.toml` 漏写了 `python-concurrenttools`，
而它同时又有 `requirements.txt`，导致这条关键约束从未生效。改动依赖后请确认写在了生效的
那份清单里，并且**记得升版本号**，否则不会重新打包。

## 各插件与原版差异

### 115文档订阅与查询 0.2.4

全新插件（非移植）。目标文档是一份**关闭了「导出/下载」**的腾讯文档在线表格，
且表格为 canvas 渲染（浏览器自动化和无障碍树都取不到单元格）。本插件的做法：

- **直读前端内部接口**：调用文档自身的 `dop-api/opendoc`，取出 `related_sheet`
  数据块（base64 + zlib + protobuf）再解码，因此**不需要导出权限、不需要浏览器**，
  只依赖 Python 标准库。解析逻辑已独立成模块（`doc_client.py` / `doc_parser.py`）便于维护。
- **超链接单元格**：部分工作表（如剧集表）的链接是「点击转存」超链接而非文本，
  已能取到 URL 并**精确绑定到所在行**。
- **微信扫码登录**：插件详情页可生成二维码，扫码后自动换取并保存腾讯文档 Cookie
  （纯 HTTP 实现，不依赖浏览器）。
- **本地索引**：文档有 90 个工作表、单表上千行，实时全量抓取过慢，改为**每天刷新一次本地索引**，
  搜索走缓存。
- **链接类型自动分派**：115 分享链接走 `share_receive` 转存；`magnet:` / `ed2k://`
  走 115 离线下载；`themoviedb.org` 等非资源链接自动忽略。
- **仅电影参与订阅**：订阅同步只处理电影，优先用表内 **TMDBID** 与 MP 订阅精确匹配，
  其次按「片名+年份」；同一片多条资源时按 `4K+中文 > 4K > 中文 > 其他` 排序，
  都不满足则取最新一条。
- **115 Cookie 复用**：留空时自动复用其它 115 插件已保存的 Cookie（115网盘STRM助手 → 115网盘储存 → 115网盘订阅追更），无需重复填写。

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

### 115网盘储存 3.0.5

替换 MoviePilot 内置的 115 存储实现，要求 MoviePilot V3。相比原版的调整：

- **修好依赖约束被吞的问题**（3.0.5）。本插件同时带 `pyproject.toml` 和 `requirements.txt`，而 MoviePilot 二选一只认 `pyproject.toml`，里面却漏了 `python-concurrenttools==0.1.8`。这是三个 115 插件里唯一没锁住 concurrenttools 的，容器重建或重装依赖时一旦装到 0.1.9，p115client 依赖的 `threadpool_map` / `taskgroup_map` 就没了，115 调用会失效。现已补进 `pyproject.toml`。
- 修复并发场景下限流等待时间不断翻倍（2 秒变 4、8、16 秒）导致整理卡住的问题。
- 云盘移动成功后改用稳定的文件 ID 完成重命名，不再依赖可能尚未更新的路径查询结果。
- 目录 ID 统一按整数处理，避免把非根目录误判为根目录；严格存在性查询直接读取远端状态，网络错误仍按未知处理。

### 115网盘STRM助手 2.8.74.9

负责资源整理与 STRM 生成。相比原版的调整：

- **同步删除适配 MoviePilot V3 的转移记录查询**（2.8.74.7）。V3 的 `TransferHistoryOper.get_by()` 已移除 `tmdbid` 参数，`transferhistory` 表改用 `media_source` + `media_id` 记录媒体身份，插件继续传 `tmdbid` 会抛 `TypeError: unexpected keyword argument 'tmdbid'`，表现为「Emby 里删了媒体、网盘文件却删不掉」。现在优先按 `MediaSource.TMDB` + `media_id` 查询，失败回退旧参数，V2/V3 通用；同时修正 `transfer_chain` 补丁里同样失效的 `get_by_type_tmdbid` 与 `transferhis.tmdbid` 读取。
- **同步删除时一并清理附属文件与空目录**（2.8.74.8）。原先只删除媒体文件本身，同目录的字幕（ass/srt 等）、图片、nfo、mediainfo.json 会残留；且 MoviePilot 的 `delete_media_file` 在目录位于媒体库结构中时会跳过空目录清理，导致删完媒体后网盘留下空目录。现于删除媒体文件后补充清理。
- **附属文件清理按归属精准匹配**（2.8.74.9）。上一版在目录存在其它媒体文件时整体跳过清理，导致被删那一集的字幕清不掉，也无法区分「同目录其它集」与「同片多版本」。现改为只清理与被删媒体同名的附属文件（`xxx.ass` / `xxx.zh.ass` / `xxx-thumb.jpg` / `xxx.nfo` / `xxx-mediainfo.json`），同目录存在同一媒体的其它版本（`1080p` 与 `1080p(1)`）时保守跳过，目录里还有其它集或其它影片时只保留目录、绝不触碰其它文件；仅当目录已无任何媒体文件时才清理无主附属文件并删除空目录。集号边界（`S01E01` 不误匹配 `S01E02` / `S01E010`）已用离线用例覆盖。
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
