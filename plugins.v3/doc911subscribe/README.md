# Doc911Subscribe — 金山文档订阅同步（MoviePilot V3 版）

> 从 KDocs（金山文档）xlsx 表格自动解析在播剧集并添加 MP 订阅。

**上游原作者：** [jinyuhao-886](https://github.com/jinyuhao-886)
**V3 移植维护：** zoom521241

---

## 🔧 本版本相对上游的修复

| # | 问题 | 修复 |
|---|------|------|
| 1 | 插件顶层 `import openpyxl`，但插件目录**没有任何依赖清单**，MoviePilot 不会自动安装 `openpyxl`。结果：**加载失败 → 安装被回滚**，日志为 `加载插件 doc911subscribe 失败：No module named 'openpyxl'` | 新增 `pyproject.toml`，按 PEP 621 在 `[project].dependencies` 声明 `openpyxl>=3.1.0`，MP V3 安装插件时会自动解析并安装；同时把 `openpyxl` 改为**运行时惰性导入**，即使依赖缺失也只影响同步动作，插件本身仍可正常加载、可在页面看到配置 |
| 2 | V3 已从 `app.db.subscribe_oper` 移除 `Subscribe` 模型（只保留 `SubscribeOper`），旧写法 `from app.db.subscribe_oper import Subscribe, SubscribeOper` 会直接 ImportError | 改为优先 `from app.db.models.subscribe import Subscribe`，并保留旧路径回退，V2 / V3 通用 |
| 3 | `_doc_url` 只在读到配置时才赋值，未传配置时访问会 AttributeError | 补齐 `_doc_url` / `_file_id` 类级默认值，`init_plugin` 里先把状态复位 |
| 4 | 通知类型使用 V2 命名 `NotificationType` | 统一优先 `MessageType`，保留 `NotificationType` 回退 |
| 5 | `_add_subscription` 里 `Session` 在多个分支各自 `close()`，异常路径可能漏释放 | 改为 `try/finally` 统一释放，避免长时间占用订阅表 |
| 6 | 配置表单没有「名称别名映射」输入框（代码里支持但该从 sudah DEBUG 层面写入） | 表单补齐 `name_aliases` 文本框 |

---

## 📋 功能

从内部共享的 KDocs 追剧表（xlsx）中，每天 21:01 自动拉取最新数据，解析出三个区段的**在播剧集**，添加到 MP 订阅：

| 区段 | 来源 |
|------|------|
| 🏮 本月更新【国产剧】 | KDocs 文档区段 |
| 🌍 本月更新【国外剧】 | KDocs 文档区段 |
| 🎪 本月更新【综艺】 | KDocs 文档区段 |

> 自动过滤已完结（"全\d+集"、"已完结"）和未开始的条目，只追**更新中**的剧集。

---

## ✨ 特性

| 特性 | 说明 |
|------|------|
| ⏰ 定时执行 | APScheduler CronTrigger(hour=21, minute=1)，每天自动 |
| 📥 xlsx 自动下载 | 通过 KDocs API 下载最新文档，本地缓存 |
| 🧩 智能区段解析 | openpyxl 解析合并单元格，三个区段独立过滤 |
| 🔍 在播识别 | 行内容含"更新"二字即视为在播，跳过已完结 |
| 📺 季数自动提取 | 支持4种格式：「第X季」「第1季」「S01」「Season 1」 |
| 🔗 文档链接可配置 | 插件设置页填入金山文档分享链接即可更换文档源 |
| ⚠️ 识别失败通知 | TMDB 匹配失败的条目会发送 MP 通知提醒 |

---

## ⚙️ 配置

| 字段 | 说明 |
|------|------|
| 金山文档链接 | 金山文档的分享链接（默认已填好当前文档链接） |
| KDocs Cookie | 浏览器登录金山文档后复制的 Cookie（必填） |
| 仅执行一次 | 勾选后仅执行一轮，不注册定时任务 |
| 名称别名（每行一条） | 可选的手动映射表，格式见下方说明 |

### 名称别名格式

```
乘风 (2026)=乘风破浪的姐姐 第七季
歌手=我是歌手|11
```

> 别名映射仅是辅助 TMDB 搜索时的名称替换，TMDB 搜不到仍然会跳过。

---

## 📜 版本历史

### v1.2.0（更名 + V3 移植）
- 插件显示名称由「911文档订阅添加」更名为「金山文档订阅添加」，配置表单与日志前缀同步更新
  （插件 ID `Doc911Subscribe` 保持不变，已保存的配置不会丢失）
- 添加 `pyproject.toml` 声明 `openpyxl` 依赖，修复 V3 下因缺少依赖导致插件加载失败、安装被回滚的问题
- 修复 `Subscribe` 导入路径（`app.db.subscribe_oper` → `app.db.models.subscribe`）
- `openpyxl` 改为惰性导入，缺依赖时给出明确日志而非直接崩溃
- 补齐类级默认配置、`try/finally` 释放 Session
- 通知类型优先使用 V3 的 `MessageType`

### 上游历史（继承）
- **v1.0.01** 新增文档链接配置项，用 `doc_url` 替换 `file_id`
- **v1.0.0** 识别失败发送通知提醒；移除 AI 辅助订阅调用；版本号体系重置
- **v1.2.1** 扩展季数识别（第1季 / S01 / Season 1）；有季数时不传 year 给 TMDB
- **v1.2.0** 修复季节订阅错误，从剧名提取"第X季"传 `chain.add(season=X)`
- **v1.1.0** 初始版本：每天 21:01 扫描 KDocs 文档三个区段
