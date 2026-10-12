"""0.11.5 regressions (synthetic data only): single media-type attribution.

Covers the defect where `type == 'unknown'` (a truthy string) short-circuited the
`type or target_type` chain, so films fetched into the film directory were counted
in neither the film nor the TV bucket ("15 tasks, but only 2 + 8 shown").
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_doc115subscribe_backend import Plugin
from test_doc115subscribe_ledger import TaskLedger, ledger_module
from test_doc115subscribe_organization import org

FOLDER = "/115-影视/115-downloads/电影/合成电影:黎明[中字].Synthetic.Dawn.2016.2160p"
MAIN = FOLDER + "/Synthetic.Dawn.2016.2160p.mkv"


def movie_batch(**fields):
    return {"title": "合成电影：黎明[中字].Synthetic.Dawn.2016.2160p", "year": "2016", "type": "unknown",
            "target_type": "movie", "kind": "magnet", "source_storage": "115网盘Plus", "final_storage": "115网盘Plus",
            "final_path": "/115-影视/115-downloads/电影", **fields}


def movie_event(path, fid, success=True, stamp=2000, **fields):
    event = {"title": "合成电影：黎明", "year": "2016", "type": "电影", "tmdb_id": 9001, "status": success,
             "date": stamp, "time_is_observed": True, "src": path,
             "src_fileitem": {"path": path, "storage": "115网盘Plus", "fileid": fid}}
    event.update(fields)
    return event


class MediaBucketTests(unittest.TestCase):
    """统计条、列表筛选、账本派生列与身份匹配共用的唯一归属口径。"""

    def test_unknown_document_type_falls_back_to_the_chosen_directory(self):
        self.assertEqual(org.media_bucket({"type": "unknown", "target_type": "movie"}), "movie")
        self.assertEqual(org.media_bucket({"type": "unknown", "target_type": "tv"}), "tv")

    def test_unknown_without_any_fallback_is_unclassified(self):
        self.assertEqual(org.media_bucket({"type": "unknown", "target_type": None}), "")
        self.assertEqual(org.media_bucket({"type": "未知"}), "")
        self.assertEqual(org.media_bucket({}), "")
        self.assertEqual(org.media_bucket(None), "")

    def test_mp_authoritative_type_outranks_document_and_directory(self):
        self.assertEqual(org.media_bucket({"mp_media_type": "movie", "type": "unknown", "target_type": "tv"}), "movie")
        self.assertEqual(org.media_bucket({"mp_media_type": "tv", "type": "movie"}), "tv")

    def test_declared_type_outranks_the_chosen_directory(self):
        self.assertEqual(org.media_bucket({"type": "tv", "target_type": "movie"}), "tv")

    def test_chinese_labels_are_recognised(self):
        self.assertEqual(org.media_bucket({"type": "电影"}), "movie")
        self.assertEqual(org.media_bucket({"type": "电视剧"}), "tv")


class ObservedMediaTypeTests(unittest.TestCase):
    """MP 整理记录的权威类型提取：只认成功记录，矛盾时宁可不写。"""

    def test_successful_records_decide(self):
        self.assertEqual(org.observed_media_type([movie_event(MAIN, "1")]), "movie")

    def test_failed_records_never_decide(self):
        self.assertEqual(org.observed_media_type([movie_event(MAIN, "1", success=False, type="未知")]), "")

    def test_dest_path_is_used_when_the_type_is_a_placeholder(self):
        event = movie_event(MAIN, "1", type="未知", dest="/115-影视/115-links/电视剧/欧美剧/合成剧/Season 1/x.mkv")
        self.assertEqual(org.observed_media_type([event]), "tv")

    def test_dest_path_movie_is_not_confused_by_a_later_movie_word(self):
        event = movie_event(MAIN, "1", type="未知", dest="/115-影视/115-links/电影/华语电影/合成片/合成片.mkv")
        self.assertEqual(org.observed_media_type([event]), "movie")

    def test_conflicting_evidence_is_never_written_as_authoritative(self):
        events = [movie_event(MAIN, "1"), movie_event(MAIN, "2", type="电视剧")]
        self.assertEqual(org.observed_media_type(events), "")

    def test_no_evidence_means_no_opinion(self):
        self.assertEqual(org.observed_media_type([]), "")


class StatsAttributionTests(unittest.TestCase):
    """统计条：总数必须等于 电影 + 电视剧 + 类型待确认。"""

    @staticmethod
    def row(**fields):
        base = {"title": "x", "tracking_enabled": False, "acquisition_status": "saved",
                "organization_status": "success", "move_status": "success", "hidden": False}
        base.update(fields)
        return base

    def stats(self, rows):
        return Plugin._record_stats(rows)

    def test_backlog_of_unknown_movies_is_no_longer_dropped(self):
        rows = [self.row(type="movie") for _ in range(2)]
        rows += [self.row(type="tv") for _ in range(8)]
        rows += [self.row(type="unknown", target_type="movie") for _ in range(5)]
        stats = self.stats(rows)
        self.assertEqual((stats["movie"]["total"], stats["tv"]["total"], stats["unclassified"]), (7, 8, 0))
        self.assertEqual(stats["total"], 15)
        self.assertEqual(stats["total"],
                         stats["movie"]["total"] + stats["tv"]["total"] + stats["unclassified"])

    def test_genuinely_unknown_records_are_reported_not_silently_dropped(self):
        stats = self.stats([self.row(type="unknown"), self.row(type="movie")])
        self.assertEqual((stats["movie"]["total"], stats["tv"]["total"], stats["unclassified"], stats["total"]),
                         (1, 0, 1, 2))

    def test_hidden_records_stay_out_of_every_bucket(self):
        stats = self.stats([self.row(type="movie"), self.row(type="unknown", target_type="movie", hidden=True)])
        self.assertEqual((stats["movie"]["total"], stats["unclassified"], stats["total"]), (1, 0, 1))


class TypeAttributionFilterTests(unittest.TestCase):
    """任务列表按类型筛选：unknown 是有意暴露的一档，而不是静默漏掉。"""

    def api(self, rows, media):
        plugin = Plugin()
        plugin._records = lambda: type("S", (), {"list": lambda self, **kw: rows})()
        return plugin.api_records(filter="all", media=media)

    def test_unknown_filter_returns_exactly_the_unattributed_rows(self):
        rows = [{"id": "a", "type": "movie"}, {"id": "b", "type": "unknown", "target_type": "movie"},
                {"id": "c", "type": "unknown"}]
        result = self.api(rows, "unknown")
        self.assertEqual(result["code"], 0)
        self.assertEqual([r["id"] for r in result["data"]["records"]], ["c"])
        self.assertEqual([r["id"] for r in self.api(rows, "movie")["data"]["records"]], ["a", "b"])

    def test_unsupported_media_filter_is_still_rejected(self):
        self.assertEqual(self.api([], "series")["code"], 1)


class LedgerTypeAttributionTests(unittest.TestCase):
    """账本派生列与 MP 权威类型回填。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doc115-synthetic-v0115-")
        self.addCleanup(self.temp.cleanup)
        self.ledger = TaskLedger(Path(self.temp.name) / "t.sqlite3")
        with patch.object(ledger_module.time, "time", return_value=1000):
            self.batch_id = self.ledger.claim_resource("synthetic-dawn-v0115", movie_batch(), generation=1)["batch"]["id"]

    def column(self):
        with self.ledger._connection() as db:
            return db.execute("SELECT media_type FROM batches WHERE batch_id=?", (self.batch_id,)).fetchone()[0]

    def scan(self):
        items = [{"source_path": MAIN, "storage": "115网盘Plus", "file_id": "1", "size": 40 * 2**30,
                  "name": "Synthetic.Dawn.2016.2160p.mkv"}]
        return self.ledger.set_manifest(self.batch_id, org.classify_optional_media(items, 10), complete=True)

    def test_derived_column_uses_the_shared_attribution(self):
        self.assertEqual(self.column(), "movie", "unknown + target_type=movie 必须归到电影")

    def test_successful_evidence_writes_the_mp_authoritative_type(self):
        self.scan()
        batch = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "1")])
        self.assertEqual(batch["organization_status"], "success")
        self.assertEqual(batch.get("mp_media_type"), "movie")

    def test_mp_type_fills_the_gap_when_document_and_directory_are_both_silent(self):
        self.scan()
        self.ledger.update(self.batch_id, target_type="")
        self.assertEqual(self.column(), "", "只有 MP 能决定时，回填前的归属必须为空")
        batch = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "1")])
        self.assertEqual(batch.get("mp_media_type"), "movie")
        self.assertEqual(self.column(), "movie", "派生列必须跟着权威类型一起更新")

    def test_repeated_evidence_is_idempotent(self):
        self.scan()
        first = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "1")])
        second = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "1")])
        self.assertEqual(first.get("mp_media_type"), second.get("mp_media_type"))
        self.assertEqual(second["organization_status"], "success")

    def test_unmatched_evidence_never_writes_a_type(self):
        self.scan()
        batch = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "999")])
        self.assertNotIn("mp_media_type", batch)
        self.assertEqual(self.column(), "movie", "未被证实的记录不能改变归属")


if __name__ == "__main__":
    unittest.main()
