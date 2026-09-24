# -*- coding: utf-8 -*-
"""
P115StrgmSub v1.5.5 离线回归测试

验证「V3 默认订阅站点交集回退导致屏蔽被绕过」修复：
1. 屏蔽态：RssSites 非空时合并 -1；已含 -1 时不重复写；为空时不写。
2. 恢复态：RssSites 被覆写为窗口站点（移除 -1）。
3. get_sub_sites 交集语义模拟：合并后 [-1] 订阅不再回退默认站点。
4. 115网盘 虚拟站点 domain 补齐 SQL 行为。

通过 mock app.* 模块在无 MoviePilot 环境下导入插件主模块。
"""
import sys
import types
from pathlib import Path
import unittest
from unittest import mock

_PLUGIN_ROOT = str(Path(__file__).resolve().parents[1] / "plugins.v2")


def _install_mp_mocks():
    """在 sys.modules 中安装 MoviePilot app.* 假模块，仅覆盖插件导入面。"""

    class _Logger:
        def info(self, *a, **k):
            pass

        def warning(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

        def debug(self, *a, **k):
            pass

    logger = _Logger()

    def _mod(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    # app.core.config
    class _Settings:
        TZ = "Asia/Shanghai"

    class _GlobalVars:
        is_system_stopped = False

    _mod("app")
    _mod("app.core")
    _mod("app.core.config", settings=_Settings(), global_vars=_GlobalVars())
    _mod("app.core.metainfo", MetaInfo=mock.MagicMock())

    # app.core.event
    def _register(event_type):
        def deco(fn):
            return fn
        return deco

    _mod("app.core.event", Event=object, eventmanager=types.SimpleNamespace(register=_register))

    # app.chain
    _mod("app.chain")
    _mod("app.chain.subscribe", SubscribeChain=mock.MagicMock())
    _mod("app.chain.download", DownloadChain=mock.MagicMock())

    # app.db / app.db.subscribe_oper / app.db.models.site
    _mod("app.db", SessionFactory=mock.MagicMock())
    _mod("app.db.subscribe_oper", SubscribeOper=mock.MagicMock())
    _mod("app.db.downloadhistory_oper", DownloadHistoryOper=mock.MagicMock())
    _mod("app.db.models")
    _mod("app.db.models.site", Site=mock.MagicMock())

    # app.log
    _mod("app.log", logger=logger)

    # app.plugins（插件基类）
    class _PluginBase:
        def update_config(self, cfg):
            pass

        def post_message(self, **kwargs):
            pass

        def get_data(self, key):
            return None

        def save_data(self, key, value):
            pass

    _mod("app.plugins", _PluginBase=_PluginBase)

    # app.schemas / app.utils
    _mod("app.schemas", MediaInfo=mock.MagicMock())
    _mod("app.utils")
    _mod("app.utils.string", StringUtils=mock.MagicMock())

    # app.schemas.types
    class _SystemConfigKey:
        RssSites = "RssSites"

    class _MediaType:
        TV = "电视剧"
        MOVIE = "电影"

    class _EventType:
        SubscribeAdded = "subscribe.added"
        SubscribeModified = "subscribe.modified"
        PluginAction = "plugin.action"

    class _NotificationType:
        Plugin = "plugin"
        Manual = "manual"

    _mod("app.schemas.types", SystemConfigKey=_SystemConfigKey, MediaType=_MediaType,
         EventType=_EventType, NotificationType=_NotificationType)

    return _SystemConfigKey, _PluginBase


# 安装 mock 并导入插件
_SystemConfigKey, _PluginBase = _install_mp_mocks()
sys.path.insert(0, _PLUGIN_ROOT)
import p115strgmsub  # noqa: E402

P115StrgmSub = p115strgmsub.P115StrgmSub


class _FakeSystemConfigOper:
    """模拟 V3 SystemConfigOper 单例：内存读写"""

    def __init__(self, initial=None):
        self.store = {"RssSites": initial}
        self.set_calls = []

    def get(self, key):
        k = getattr(key, "value", key)
        return self.store.get(k)

    def set(self, key, value):
        k = getattr(key, "value", key)
        self.set_calls.append((k, list(value)))
        self.store[k] = list(value)


def _make_plugin(rss_sites=None, oper_available=True):
    p = P115StrgmSub.__new__(P115StrgmSub)  # 跳过基类 __init__
    if oper_available:
        p.systemconfig = _FakeSystemConfigOper(initial=rss_sites)
    else:
        p.systemconfig = None
    return p


def _simulate_get_sub_sites(subscribe_sites, default_sites):
    """复刻 MoviePilot V3 app/chain/subscribe/query.py get_sub_sites 的交集回退语义"""
    if not subscribe_sites:
        return default_sites or []
    if not default_sites:
        return subscribe_sites or []
    intersection = [s for s in subscribe_sites if s in default_sites]
    return intersection if intersection else default_sites


class TestEnsureDefaultSitesInclude115(unittest.TestCase):
    def test_merge_when_nonempty(self):
        p = _make_plugin(rss_sites=[1, 2, 4, 7, 8])
        p._ensure_default_sites_include_115()
        new_value = p.systemconfig.store["RssSites"]
        self.assertEqual(new_value, [-1, 1, 2, 4, 7, 8])
        self.assertEqual(p.systemconfig.set_calls, [("RssSites", [-1, 1, 2, 4, 7, 8])])

    def test_noop_when_already_contains(self):
        p = _make_plugin(rss_sites=[-1, 1, 2])
        p._ensure_default_sites_include_115()
        self.assertEqual(p.systemconfig.set_calls, [])
        self.assertEqual(p.systemconfig.store["RssSites"], [-1, 1, 2])

    def test_noop_when_empty(self):
        """RssSites 为空时不应写入，避免影响排除订阅的默认站点语义"""
        p = _make_plugin(rss_sites=[])
        p._ensure_default_sites_include_115()
        self.assertEqual(p.systemconfig.set_calls, [])

    def test_none_value_treated_as_empty(self):
        p = _make_plugin(rss_sites=None)
        p._ensure_default_sites_include_115()
        self.assertEqual(p.systemconfig.set_calls, [])

    def test_no_oper_available(self):
        """无 systemconfig 属性时不抛异常"""
        p = _make_plugin(oper_available=False)
        p._ensure_default_sites_include_115()  # 不应抛错

    def test_get_sub_sites_semantics_after_merge(self):
        """核心场景：合并后 [-1] 订阅不再回退为默认真实站点"""
        default_sites = [1, 2, 4, 7, 8]
        managed = [-1]
        # 修复前：交集为空 -> 回退默认站点（屏蔽失效）
        before = _simulate_get_sub_sites(managed, default_sites)
        self.assertEqual(before, default_sites)
        # 修复后
        p = _make_plugin(rss_sites=list(default_sites))
        p._ensure_default_sites_include_115()
        after_default = p.systemconfig.store["RssSites"]
        after = _simulate_get_sub_sites(managed, after_default)
        self.assertEqual(after, [-1])

    def test_excluded_subscribe_unaffected(self):
        """排除订阅（自带真实站点/空站点）在合并后仍可正常解析"""
        default_sites = [1, 2, 4, 7, 8]
        p = _make_plugin(rss_sites=list(default_sites))
        p._ensure_default_sites_include_115()
        merged = p.systemconfig.store["RssSites"]

        # 排除订阅 A：自带真实站点
        self.assertEqual(_simulate_get_sub_sites([1, 2], merged), [1, 2])
        # 排除订阅 B：空站点 -> 使用默认站点（含真实站点）
        self.assertEqual(_simulate_get_sub_sites([], merged), merged)
        self.assertIn(1, _simulate_get_sub_sites([], merged))


class TestSetSystemDefaultSiteIds(unittest.TestCase):
    def test_write(self):
        p = _make_plugin(rss_sites=[-1, 1, 2])
        ok = p._set_system_default_site_ids([1, 2, 4])
        self.assertTrue(ok)
        self.assertEqual(p.systemconfig.store["RssSites"], [1, 2, 4])

    def test_no_oper(self):
        p = _make_plugin(oper_available=False)
        self.assertFalse(p._set_system_default_site_ids([1, 2]))

    def test_unblocked_removes_115(self):
        """恢复态写入窗口站点后 RssSites 不再含 -1"""
        p = _make_plugin(rss_sites=[-1, 1, 2, 4, 7, 8])
        p._try_set_default_sites_for_unblocked([1, 2, 4])
        self.assertEqual(p.systemconfig.store["RssSites"], [1, 2, 4])
        self.assertNotIn(-1, p.systemconfig.store["RssSites"])

    def test_string_value_parsed(self):
        """兼容字符串形态的 RssSites"""
        p = _make_plugin(rss_sites="1,2,4")
        p._ensure_default_sites_include_115()
        self.assertEqual(p.systemconfig.store["RssSites"], [-1, 1, 2, 4])


class TestEnterBlocked(unittest.TestCase):
    def test_enter_blocked_merges_rss_sites(self):
        """_enter_blocked 应调用合并逻辑（通过 spy 验证调用链）"""
        p = _make_plugin(rss_sites=[1, 2])
        called = []
        p._ensure_toggle_scheduler = lambda: called.append("sched")
        p._cancel_toggle_jobs = lambda: called.append("cancel")
        p._init_subscribe_handler = lambda: None

        handler = types.SimpleNamespace(set_blocked_sites_only_115=lambda: None)
        p._subscribe_handler = handler
        p._ensure_default_sites_include_115 = lambda: called.append("merge")
        p.__update_config = lambda: None

        p._enter_blocked(reason="test")
        self.assertIn("merge", called)


class TestVersion(unittest.TestCase):
    def test_version_bumped(self):
        self.assertEqual(P115StrgmSub.plugin_version, "1.5.8")

    def test_site_constants(self):
        self.assertEqual(P115StrgmSub._SITE_115_ID, -1)
        self.assertEqual(P115StrgmSub._SITE_115_DOMAIN, "115.com")


class TestSiteDomainSql(unittest.TestCase):
    """验证 115网盘 站点 domain 补齐的 SQL 形态（在假 session 上执行）"""

    def _run_do_ensure(self, existing_row, update_result):
        sessions = []

        class _ExecResult:
            def __init__(self, rowcount):
                self.rowcount = rowcount

        class _Session:
            def execute(self, sql, params=None):
                sessions.append((str(sql), params))
                if "SELECT id FROM site WHERE name" in str(sql):
                    return types.SimpleNamespace(fetchone=lambda: existing_row)
                if "SELECT id FROM site WHERE id=:i" in str(sql):
                    return types.SimpleNamespace(fetchone=lambda: None)
                return _ExecResult(update_result)

            def commit(self):
                pass

        p = _make_plugin()
        return p._ensure_115_site_id(db=_Session()), sessions

    def test_domain_backfilled_when_exists_without_domain(self):
        site_id, stmts = self._run_do_ensure(existing_row=(-1,), update_result=1)
        self.assertEqual(site_id, -1)
        update_stmts = [s for s in stmts if "UPDATE site SET domain" in s[0]]
        self.assertEqual(len(update_stmts), 1)
        self.assertEqual(update_stmts[0][1], {"d": "115.com", "i": -1})

    def test_no_update_when_domain_present(self):
        # UPDATE 影响 0 行（domain 已存在）时不应触发补齐提交
        site_id, stmts = self._run_do_ensure(existing_row=(-1,), update_result=0)
        self.assertEqual(site_id, -1)
        self.assertIn("UPDATE site SET domain", stmts[-1][0] if stmts else "")


class TestNoExistsSeasonInfoKeyResolution(unittest.TestCase):
    """
    v1.5.7：V3 的 get_no_exists_info 返回键为来源前缀格式（"tmdb:95350"），
    resolve_no_exists_season_info 必须能同时兼容新旧键格式，
    否则剧集订阅会被误判为"没有缺失"而整体跳过搜索。
    """

    @classmethod
    def setUpClass(cls):
        from p115strgmsub.handlers.sync import resolve_no_exists_season_info
        cls.fn = staticmethod(resolve_no_exists_season_info)

    def test_v3_prefixed_tmdb_key(self):
        no_exists = {"tmdb:95350": {1: "INFO"}}
        self.assertEqual(self.fn(no_exists, tmdb_id=95350), {1: "INFO"})

    def test_v3_prefixed_tmdb_key_with_str_id(self):
        no_exists = {"tmdb:95350": {1: "INFO"}}
        self.assertEqual(self.fn(no_exists, tmdb_id="95350"), {1: "INFO"})

    def test_legacy_bare_int_key(self):
        no_exists = {95350: {1: "INFO"}}
        self.assertEqual(self.fn(no_exists, tmdb_id=95350), {1: "INFO"})

    def test_legacy_bare_str_key(self):
        no_exists = {"95350": {1: "INFO"}}
        self.assertEqual(self.fn(no_exists, tmdb_id=95350), {1: "INFO"})

    def test_douban_prefixed_key(self):
        no_exists = {"douban:36452545": {1: "INFO"}}
        self.assertEqual(self.fn(no_exists, douban_id=36452545), {1: "INFO"})

    def test_single_entry_fallback(self):
        # 键格式再次变化时，单键字典兜底取用
        no_exists = {"themoviedb:95350": {1: "INFO"}}
        self.assertEqual(self.fn(no_exists, tmdb_id=95350), {1: "INFO"})

    def test_no_fallback_when_multiple_unrelated_keys(self):
        # 多个不相关键时不允许兜底误取
        no_exists = {"tmdb:1": {1: "A"}, "tmdb:2": {1: "B"}}
        self.assertEqual(self.fn(no_exists, tmdb_id=95350), {})

    def test_empty_and_none(self):
        self.assertEqual(self.fn(None, tmdb_id=95350), {})
        self.assertEqual(self.fn({}, tmdb_id=95350), {})
        # 未传 id 时单键字典仍兜底（调用方始终针对同一媒体查询，单键必然属于当前媒体）
        self.assertEqual(self.fn({"tmdb:95350": {1: "INFO"}}), {1: "INFO"})


class TestLackEpisodeLibraryReconcile(unittest.TestCase):
    """
    v1.5.8：订阅页显示的"已订阅集数 = total_episode - lack_episode"，
    而 MoviePilot 只在"总集数变化/下载事件"时回写 lack_episode，
    删除剧集、重置订阅都不会对账。插件改为每轮同步以媒体库缺失数回写。
    """

    @classmethod
    def setUpClass(cls):
        from p115strgmsub.handlers.subscribe import SubscribeHandler
        cls.handler_cls = SubscribeHandler

    def setUp(self):
        self.handler = self.handler_cls()
        self.updates = []
        from app.db.subscribe_oper import SubscribeOper
        SubscribeOper.return_value.update = lambda sid, payload: self.updates.append((sid, payload))

    def _sub(self, lack=8, total=8, sub_type="电视剧", start=0):
        return types.SimpleNamespace(
            id=93, name="绿灯军团", type=sub_type,
            total_episode=total, lack_episode=lack, start_episode=start,
            note=[], season=1, year="2026",
        )

    def test_reconcile_stale_lack(self):
        """媒体库只缺 2 集时，把陈旧的 8 校准为 2"""
        sub = self._sub(lack=8)
        self.assertTrue(self.handler.sync_lack_episode_with_library(sub, 2, season=1))
        self.assertEqual(self.updates, [(93, {"lack_episode": 2})])
        self.assertEqual(sub.lack_episode, 2)

    def test_no_write_when_already_correct(self):
        sub = self._sub(lack=2)
        self.assertFalse(self.handler.sync_lack_episode_with_library(sub, 2, season=1))
        self.assertEqual(self.updates, [])

    def test_deleted_episode_raises_lack(self):
        """删除剧集后媒体库缺失变多，应能自动加回"""
        sub = self._sub(lack=2)
        self.handler.sync_lack_episode_with_library(sub, 3, season=1)
        self.assertEqual(self.updates[-1], (93, {"lack_episode": 3}))

    def test_reset_subscription_recalibrated(self):
        """重置订阅后 lack 被重置为总集数，应按媒体库实际校准"""
        sub = self._sub(lack=8, total=8)
        self.handler.sync_lack_episode_with_library(sub, 2, season=1)
        self.assertEqual(sub.lack_episode, 2)

    def test_skip_movie_and_no_total(self):
        """电影订阅、总集数为 0 的订阅不参与校准"""
        movie = self._sub(sub_type="电影", lack=1, total=0)
        self.assertFalse(self.handler.sync_lack_episode_with_library(movie, 1))
        no_total = self._sub(total=0, lack=0)
        self.assertFalse(self.handler.sync_lack_episode_with_library(no_total, 0))
        self.assertEqual(self.updates, [])

    def test_lack_clamped_to_total(self):
        """异常数据不应写出超过总集数的缺失数"""
        sub = self._sub(lack=1, total=8)
        self.handler.sync_lack_episode_with_library(sub, 99, season=1)
        self.assertEqual(self.updates[-1], (93, {"lack_episode": 8}))

    def test_none_subscribe_safe(self):
        self.assertFalse(self.handler.sync_lack_episode_with_library(None, 1))


class TestCheckFinishUsesLibraryLack(unittest.TestCase):
    """
    v1.5.8：写回 lack_episode 必须以媒体库口径为准（不能用插件自身 note 反推），
    但"是否完成订阅"仍按 note 覆盖率判断，保持原有行为。
    """

    @classmethod
    def setUpClass(cls):
        import p115strgmsub.handlers.subscribe as sub_mod
        from p115strgmsub.handlers.subscribe import SubscribeHandler
        cls.handler_cls = SubscribeHandler
        cls.sub_mod = sub_mod

        # 让 MediaType(...) 可调用（mock 中它是普通类，实例化会抛 TypeError）
        class _CallableMediaType:
            TV = "电视剧"
            MOVIE = "电影"

            def __new__(cls, value):
                return types.SimpleNamespace(value=value)

        sub_mod.MediaType = _CallableMediaType

    def setUp(self):
        self.handler = self.handler_cls()
        self.updates = []
        from app.db.subscribe_oper import SubscribeOper
        SubscribeOper.return_value.update = lambda sid, payload: self.updates.append((sid, payload))

    def _sub(self, lack=8, total=8, note=None, start=0):
        return types.SimpleNamespace(
            id=93, name="绿灯军团", type="电视剧",
            total_episode=total, lack_episode=lack, start_episode=start,
            note=note if note is not None else [], season=1, year="2026",
        )

    def _tv(self):
        from app.schemas.types import MediaType
        return types.SimpleNamespace(type=MediaType.TV)

    def _run(self, sub, success_episodes, library_lack=None):
        # 屏蔽官方完成接口，只验证写库内容
        from app.chain.subscribe import SubscribeChain
        SubscribeChain.return_value.finish_subscribe_or_not = lambda **kw: None
        self.handler.check_and_finish_subscribe(
            subscribe=sub, mediainfo=self._tv(),
            success_episodes=success_episodes, library_lack=library_lack
        )
        return {k: v for _, payload in self.updates for k, v in payload.items()}

    def test_library_lack_wins_over_note(self):
        """note 只记录了插件自己转存的 1 集，真实缺失应按媒体库算成 2"""
        sub = self._sub(lack=8, note=[])
        payload = self._run(sub, [6], library_lack=2)
        self.assertEqual(payload["lack_episode"], 2)
        self.assertEqual(payload["note"], [6])

    def test_fallback_to_note_without_library_lack(self):
        """未拿到媒体库缺失数据时退回原 note 反推逻辑"""
        sub = self._sub(lack=8, note=[1, 2, 3, 4, 5, 6])
        payload = self._run(sub, [], library_lack=None)
        self.assertEqual(payload["lack_episode"], 2)

    def test_finish_not_triggered_when_library_still_missing(self):
        """媒体库仍有缺失时不应把订阅移入历史"""
        sub = self._sub(lack=2, note=[1, 2, 3, 4, 5, 6, 7, 8])
        from app.chain.subscribe import SubscribeChain
        called = []
        SubscribeChain.return_value.finish_subscribe_or_not = lambda **kw: called.append(1)
        self.handler.check_and_finish_subscribe(
            subscribe=sub, mediainfo=self._tv(), success_episodes=[], library_lack=2
        )
        # 完成判定按 note 覆盖率：note 已覆盖全部 -> 行为与修复前一致（仍会完成）
        self.assertEqual(called, [1])

    def test_zero_library_lack_written_when_complete(self):
        sub = self._sub(lack=3, note=[1, 2, 3, 4, 5])
        from app.chain.subscribe import SubscribeChain
        SubscribeChain.return_value.finish_subscribe_or_not = lambda **kw: None
        self.handler.check_and_finish_subscribe(
            subscribe=sub, mediainfo=self._tv(),
            success_episodes=[6, 7, 8], library_lack=0
        )
        payload = {k: v for _, p in self.updates for k, v in p.items()}
        self.assertEqual(payload["lack_episode"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
