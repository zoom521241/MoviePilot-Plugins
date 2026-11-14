"""
复用 MoviePilot 原生订阅过滤（v3）

MP 的选片是两步：
  1. TorrentHelper.filter_torrent(...)  —— 按订阅的 quality / resolution / effect / include / exclude 做硬过滤
  2. FilterModule.filter_torrents(...)  —— 按规则组（DSL 表达式）打优先级 pri_order

本模块把这两步包成「对单个文件名打分」，供插件在匹配 115 分享内的文件时复用，
保证插件与 MP 的选片口径完全一致（分辨率门槛、规则组优先级、洗版规则组切换）。

MP 侧不可用时返回 None，由调用方回退到插件自己的简易正则逻辑。
"""
from typing import Any, Dict, List, Optional, Tuple

from app.log import logger

_MP: Optional[Dict[str, Any]] = None          # None=未探测，False=不可用，dict=可用
_FILTER_MODULE: Any = None


def _load_mp() -> Optional[Dict[str, Any]]:
    """惰性加载 MP 的过滤组件（依赖运行期已初始化的系统配置服务）"""
    global _MP
    if _MP is not None:
        return _MP or None
    try:
        from app.schemas import TorrentInfo
        from app.application.torrent.download import TorrentHelper
        from app.modules.filter import FilterModule
        from app.schemas.types import SystemConfigKey
        from app.db.systemconfig_oper import SystemConfigOper

        _MP = {
            "TorrentInfo": TorrentInfo,
            "TorrentHelper": TorrentHelper,
            "FilterModule": FilterModule,
            "SystemConfigKey": SystemConfigKey,
            "SystemConfigOper": SystemConfigOper,
        }
        logger.debug("MP 原生过滤器加载成功")
    except Exception as e:
        logger.warning(f"MP 原生过滤器不可用，回退插件内置规则：{e}")
        _MP = False
    return _MP or None


def _filter_module():
    """FilterModule 单例（内部会加载规则组与 Rust 加速器）"""
    global _FILTER_MODULE
    mp = _load_mp()
    if not mp:
        return None
    if _FILTER_MODULE is None:
        try:
            module = mp["FilterModule"]()
            # 关键：init_module() 才会把内置规则集（37 条）灌进 rule_set。
            # 少了这一步 rule_set 为空，任何关键词都判定不存在，规则组会拒掉全部文件。
            module.init_module()
            _FILTER_MODULE = module
            logger.debug(f"FilterModule 就绪，规则集 {len(getattr(module, 'rule_set', {}) or {})} 条")
        except Exception as e:
            logger.warning(f"FilterModule 初始化失败：{e}")
            return None
    return _FILTER_MODULE


def is_available() -> bool:
    """MP 原生过滤是否可用"""
    return _load_mp() is not None


def build_filter_params(subscribe: Any) -> Dict[str, Any]:
    """
    从订阅对象取出 MP 硬过滤参数（与 MP 的 get_params 对齐的常用子集）
    """
    if subscribe is None:
        return {}
    params: Dict[str, Any] = {}
    for key in ("quality", "resolution", "effect", "include", "exclude"):
        value = getattr(subscribe, key, None)
        if value:
            params[key] = value
    return params


def resolve_rule_groups(subscribe: Any, is_best_version: bool = False,
                        systemconfig: Any = None) -> List[str]:
    """
    解析订阅使用的规则组

    与 MP 一致：订阅级 filter_groups 优先；否则普通订阅取 SubscribeFilterRuleGroups，
    洗版订阅取 BestVersionFilterRuleGroups。
    """
    mp = _load_mp()
    if not mp:
        return []

    groups = getattr(subscribe, "filter_groups", None) if subscribe is not None else None
    if isinstance(groups, str):
        groups = [g.strip() for g in groups.split(",") if g.strip()]
    if groups:
        return list(groups)

    key = mp["SystemConfigKey"].BestVersionFilterRuleGroups if is_best_version \
        else mp["SystemConfigKey"].SubscribeFilterRuleGroups
    oper = systemconfig
    if oper is None or not hasattr(oper, "get"):
        try:
            oper = mp["SystemConfigOper"]()
        except Exception as e:
            logger.debug(f"系统配置服务不可用：{e}")
            return []
    try:
        value = oper.get(key)
    except Exception as e:
        logger.warning(f"读取过滤规则组失败（{key}）：{e}")
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",") if v.strip()]
    return list(value or [])


def match_file(
        file_name: str,
        params: Optional[Dict[str, Any]] = None,
        rule_groups: Optional[List[str]] = None,
        mediainfo: Any = None,
        size: int = 0,
) -> Optional[Tuple[bool, int]]:
    """
    按 MP 口径判定单个文件名

    :return: (是否通过, 优先级分数)；返回 None 表示 MP 侧不可用，调用方应回退
             优先级分数越大越优（由 pri_order 反转而来，pri_order 越小越优先）
    """
    mp = _load_mp()
    if not mp or not file_name:
        return None

    params = params or {}
    rule_groups = rule_groups or []

    try:
        torrent = mp["TorrentInfo"](title=file_name, size=int(size or 0))
    except Exception as e:
        logger.debug(f"构造 TorrentInfo 失败（{file_name}）：{e}")
        return None

    # ① 硬过滤：订阅的 quality / resolution / effect / include / exclude
    try:
        if params and not mp["TorrentHelper"].filter_torrent(torrent, params):
            return False, 0
    except Exception as e:
        logger.debug(f"MP 硬过滤异常，回退：{e}")
        return None

    # ② 规则组优先级
    if not rule_groups:
        return True, 0
    fm = _filter_module()
    if fm is None:
        return True, 0
    try:
        result = fm.filter_torrents(rule_groups=rule_groups, torrent_list=[torrent], mediainfo=mediainfo)
    except Exception as e:
        # 硬过滤已通过，规则组不可用时按「无优先级」放行，避免整源失效
        logger.warning(f"规则组匹配异常，本次按无优先级放行：{e}")
        return True, 0
    if result is None:
        return True, 0
    if not result:
        # 命中不了任何规则组 = 不符合该订阅的优先级规则
        return False, 0
    # MP 的优先级从 100 起、每降一层减 1；换算成「越大越优」的分数
    pri_order = getattr(result[0], "pri_order", 0) or 0
    return True, 9900 + min(int(pri_order), 100)


def describe(subscribe: Any, is_best_version: bool = False, systemconfig: Any = None) -> str:
    """生成便于日志排查的口径描述"""
    params = build_filter_params(subscribe)
    groups = resolve_rule_groups(subscribe, is_best_version, systemconfig)
    hard = "、".join(f"{k}={v}" for k, v in params.items()) or "无"
    group_text = " > ".join(groups) if groups else "未配置规则组"
    return f"硬过滤[{hard}]，规则组[{group_text}]"
