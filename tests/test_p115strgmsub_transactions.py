"""Real SQLAlchemy transactions with V3-style writes that do not auto-commit."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import JSON, Integer, String, create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column

ROOT = Path(os.environ.get("P115STRGMSUB_SOURCE_ROOT", str(
    Path(__file__).resolve().parents[1] / "plugins.v2/p115strgmsub")))


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscribe"
    id = mapped_column(Integer, primary_key=True)
    sites = mapped_column(JSON, nullable=True)


class Site(Base):
    __tablename__ = "site"
    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String)
    domain = mapped_column(String)


class Oper:
    def __init__(self, db):
        self.db = db

    def list(self):
        return list(self.db.scalars(select(Subscription).order_by(Subscription.id)))

    def get(self, sid):
        return self.db.get(Subscription, sid)

    def update(self, sid, payload):
        row = self.get(sid)
        if row:
            for name, value in payload.items():
                setattr(row, name, value)
        return row


def load_class(path, name, namespace, methods=None):
    node = next(n for n in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(n, ast.ClassDef) and n.name == name)
    node.decorator_list = []
    node.bases = []
    if methods:
        node.body = [n for n in node.body if isinstance(n, ast.FunctionDef)
                     and n.name in methods]
        for method in node.body:
            method.decorator_list = []
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[
        ast.alias(name="annotations")], level=0), node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return namespace[name]


class SubscriptionTransactionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            db.add_all([Subscription(id=93, sites=[-1]), Subscription(id=101, sites=None),
                        Subscription(id=102, sites=[2]),
                        Site(id=-1, name="115网盘", domain="115.com"),
                        Site(id=2, name="PT", domain="example.test")])
            db.commit()
        self.log = Mock()
        self.namespace = {"logger": self.log, "text": text, "SubscribeOper": Oper,
                          "SessionFactory": lambda: Session(self.engine)}
        self.handler_class = load_class(ROOT / "handlers/subscribe.py", "SubscribeHandler", self.namespace)
        self.plugin_class = load_class(ROOT / "__init__.py", "P115StrgmSub", self.namespace, {
            "_is_subscribe_excluded", "_apply_sites_to_all_subscribes",
            "_get_subscribe_id_from_event", "on_subscribe_added"})
        self.plugin = self.plugin_class()
        self.plugin._subscribe_filter_mode = "exclude"
        self.plugin._exclude_subscribes = []
        self.plugin._include_subscribes = []
        self.plugin._block_system_subscribe = True
        self.handler = self.handler_class(is_excluded_func=self.plugin._is_subscribe_excluded)
        self.plugin._subscribe_handler = self.handler
        self.plugin._init_subscribe_handler = lambda: None

    def tearDown(self):
        self.engine.dispose()

    def read_sites(self, sid):
        with Session(self.engine) as db:
            return db.get(Subscription, sid).sites

    def test_v3_explicit_session_does_not_save_without_commit(self):
        with Session(self.engine) as db:
            Oper(db).update(101, {"sites": [-1]})
        self.assertIsNone(self.read_sites(101))

    def test_empty_exclusion_list_blocks_all_after_session_closed(self):
        self.handler.set_blocked_sites_only_115()
        self.assertEqual([self.read_sites(i) for i in (93, 101, 102)], [[-1]] * 3)

    def test_excluded_subscription_preserves_pt_sites(self):
        self.plugin._exclude_subscribes = [102]
        self.handler.set_blocked_sites_only_115()
        self.assertEqual(self.read_sites(101), [-1])
        self.assertEqual(self.read_sites(102), [2])

    def test_include_mode_only_blocks_selected_subscription(self):
        self.plugin._subscribe_filter_mode = "include"
        self.plugin._include_subscribes = [101]
        self.handler.set_blocked_sites_only_115()
        self.assertEqual(self.read_sites(101), [-1])
        self.assertEqual(self.read_sites(102), [2])

    def test_new_subscription_event_commits(self):
        self.plugin.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 101}))
        self.assertEqual(self.read_sites(101), [-1])

    def test_new_excluded_subscription_event_keeps_existing_sites(self):
        self.plugin._exclude_subscribes = [101]
        self.plugin.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 101}))
        self.assertIsNone(self.read_sites(101))

    def test_new_subscription_legacy_fallback_commits(self):
        self.plugin._subscribe_handler = SimpleNamespace()
        self.plugin._ensure_115_site_id = lambda db: -1
        self.plugin.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 101}))
        self.assertEqual(self.read_sites(101), [-1])

    def test_batch_unblock_commits_and_preserves_exclusions(self):
        self.plugin._exclude_subscribes = [101]
        self.handler.set_unblocked_sites(["PT"])
        self.assertEqual(self.read_sites(93), [2])
        self.assertIsNone(self.read_sites(101))

    def test_single_unblock_commits(self):
        self.handler.set_sites_for_subscribe_by_names(101, ["PT"])
        self.assertEqual(self.read_sites(101), [2])

    def test_main_plugin_batch_path_commits(self):
        self.plugin._apply_sites_to_all_subscribes([-1], "test")
        self.assertEqual(self.read_sites(101), [-1])

    def test_failure_rolls_back_entire_batch(self):
        original = Oper.update
        def fail_last(oper, sid, payload):
            if sid == 102:
                raise RuntimeError("simulated write failure")
            return original(oper, sid, payload)
        with patch.object(Oper, "update", fail_last), self.assertRaises(RuntimeError):
            self.handler.set_blocked_sites_only_115()
        self.assertIsNone(self.read_sites(101))
        self.assertEqual(self.read_sites(102), [2])
        self.assertFalse(any("已更新" in str(call) for call in self.log.info.call_args_list))

    def test_commit_failure_does_not_claim_success(self):
        with patch.object(Session, "commit", side_effect=RuntimeError("commit failed")):
            with self.assertRaises(RuntimeError):
                self.handler.set_blocked_sites_only_115()
        self.assertIsNone(self.read_sites(101))
        self.assertFalse(any("已更新" in str(call) for call in self.log.info.call_args_list))


if __name__ == "__main__":
    unittest.main()
