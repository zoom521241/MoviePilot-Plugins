"""Small-video policy and deleted-file outcomes, using synthetic data only."""
import copy
import importlib
import unittest

import test_doc115subscribe_runtime_blackbox as blackbox
from test_doc115subscribe_backend import main, rec


org = importlib.import_module(main.__package__ + ".organization")
MIB = 1024 ** 2


class SmallMediaPolicyTests(unittest.TestCase):
    def video(self, size=3 * MIB, **fields):
        return {"name": "幕后短片.mp4", "source_path": "/下载/Show/幕后短片.mp4",
                "storage": "115网盘Plus", "required": True, "size": size, **fields}

    def test_known_small_ordinary_videos_are_optional_without_mutating_input(self):
        for suffix in ("mkv", "mp4", "avi", "mov", "wmv", "flv", "ts", "mpg", "mpeg", "webm"):
            with self.subTest(suffix=suffix):
                incoming = [self.video(name="附带视频." + suffix)]
                original = copy.deepcopy(incoming)
                result = org.classify_optional_media(incoming, 10)
                self.assertEqual(incoming, original)
                self.assertIsNot(result[0], incoming[0])
                self.assertFalse(result[0]["required"])
                self.assertEqual(result[0]["role"], "small_video")
                self.assertIn("10", result[0]["ignored_reason"])

    def test_integer_and_decimal_integer_string_sizes_are_known_including_zero(self):
        for size in (0, 3 * MIB, "0", str(3 * MIB), " 0003145728 "):
            with self.subTest(size=size):
                result = org.classify_optional_media([self.video(size)], 10)[0]
                self.assertFalse(result["required"])
                self.assertIsInstance(result["size"], int)

    def test_unknown_and_invalid_sizes_remain_required(self):
        for size in (None, -1, "-1", 0.0, 3.5, "3.5", "", " ", "unknown", True, False,
                     [], {}, "²", "³", "1" * 5000):
            with self.subTest(size=size):
                result = org.classify_optional_media([self.video(size)], 10)[0]
                self.assertTrue(result["required"])
                self.assertNotEqual(result.get("role"), "small_video")
        incoming = self.video()
        incoming.pop("size")
        self.assertTrue(org.classify_optional_media([incoming], 10)[0]["required"])

    def test_strict_mib_boundary_and_disabled_policy(self):
        for size in (10 * MIB, 10 * MIB + 1, 100 * MIB):
            with self.subTest(size=size):
                self.assertTrue(org.classify_optional_media([self.video(size)], 10)[0]["required"])
        self.assertFalse(org.classify_optional_media([self.video(10 * MIB - 1)], 10)[0]["required"])
        incoming = [self.video(0), self.video(3 * MIB)]
        self.assertEqual(org.classify_optional_media(incoming, 0), incoming)

    def test_bluray_containers_directories_and_nonvideos_are_not_ignored_by_size(self):
        for fields in ({"name": "Disc.iso"}, {"name": "00001.m2ts"},
                       {"name": "00001.m2ts", "role": "media"},
                       {"name": "Folder.mp4", "is_dir": True},
                       {"name": "字幕.srt"}, {"name": "Poster.jpg"}, {"name": "Archive.zip"}):
            with self.subTest(fields=fields):
                result = org.classify_optional_media([self.video(0, **fields)], 10)[0]
                self.assertTrue(result["required"])
                self.assertNotEqual(result.get("role"), "small_video")

    def test_all_small_files_cannot_prove_organization_success(self):
        incoming = org.classify_optional_media([self.video()], 10)
        manifest = org.prepare_manifest(incoming, complete=True)
        self.assertFalse(manifest["complete"])
        self.assertIn("empty_required_manifest", manifest["reason"])
        result = org.summarize(manifest["items"], [], complete=manifest["complete"], pagination_complete=True)
        self.assertNotEqual(result["organization_status"], "success")
        self.assertFalse(result["organization_confirmed"])

    def test_normal_episodes_and_deleted_small_video_have_twenty_required_units(self):
        incoming = [{"name": f"Show.S01E{i:02}.mkv", "source_path": f"/下载/Show/Show.S01E{i:02}.mkv",
                     "required": True, "storage": "115网盘Plus", "size": 100 * MIB}
                    for i in range(1, 21)] + [self.video()]
        manifest = org.prepare_manifest(org.classify_optional_media(incoming, 10), complete=True,
                                        expected_episodes=range(1, 21))
        self.assertTrue(manifest["complete"])
        required = [u for u in manifest["items"] if u["required"]]
        self.assertEqual(len(required), 20)
        evidence = [{"unit_keys": [u["unit_key"]], "status": True, "evidence_at": i}
                    for i, u in enumerate(required)]
        result = org.summarize(manifest["items"], evidence, complete=True)
        self.assertEqual((result["organization_status"], result["organized_count"], result["organized_total"]),
                         ("success", 20, 20))
        result = org.summarize(manifest["items"], evidence[:-1], complete=True)
        self.assertEqual((result["organization_status"], result["organized_count"], result["organized_total"]),
                         ("partial", 19, 20))


class CloudWithSmallVideo(blackbox.SyntheticCloud):
    def __init__(self, *, extra_size=3 * MIB, episode_size=100 * MIB, episodes=20):
        super().__init__(episodes=episodes)
        self.extra_size = extra_size
        self.episode_size = episode_size

    def share_manifest_slice(self, url, cursor=None):
        result = super().share_manifest_slice(url, cursor)
        for item in result["items"]:
            item["size"] = self.episode_size
        result["items"].append({"source_file_id": "extra", "relative_path": "Season/幕后短片.mp4",
                                "required": True, "size": self.extra_size})
        return result

    def manifest_slice(self, path, cursor=None, file_id=""):
        result = super().manifest_slice(path, cursor, file_id)
        for item in result["items"]:
            item["size"] = self.episode_size
        result["items"].append({"id": "199", "path": f"{path}/幕后短片.mp4", "name": "幕后短片.mp4",
                                "required": True, "size": self.extra_size})
        return result


class SmallMediaRuntimeTests(unittest.TestCase):
    setUp = blackbox.RuntimeBlackBox.setUp
    queue = blackbox.RuntimeBlackBox.queue
    tick = blackbox.RuntimeBlackBox.tick
    histories = blackbox.RuntimeBlackBox.histories
    organize = blackbox.RuntimeBlackBox.organize

    def synthetic_cloud(self, **fields):
        self.cloud = CloudWithSmallVideo(**fields)
        self.plugin._transfers = lambda: self.cloud

    def queue_source(self, source):
        fields = {"expected_episodes": list(range(1, 21))}
        if source == "magnet":
            fields["links"] = [("magnet", "magnet:?xt=urn:btih:" + "a" * 40)]
        batch = self.queue(**fields)
        self.tick(3 if source == "magnet" else 1)
        return self.plugin._records().get(batch["id"])

    def test_deleted_small_attachment_does_not_prevent_share_twenty_of_twenty(self):
        self.synthetic_cloud()
        batch = self.queue_source("share")
        self.assertEqual(batch["min_media_size_mb"], 10)
        result = self.organize(batch, self.histories(batch))
        self.assertEqual((result["organization_status"], result["organized_count"], result["organized_total"]),
                         ("success", 20, 20))
        self.assertEqual([x[0] for x in self.cloud.writes], ["receive"])
        view = self.plugin.api_records()["data"]["records"][0]
        self.assertEqual(len(view["files"]), 20)
        self.assertEqual(view["ignored_files"][0]["name"], "幕后短片.mp4")
        self.assertEqual(view["ignored_files"][0]["size"], 3 * MIB)

    def test_deleted_real_episode_still_reports_share_nineteen_of_twenty(self):
        self.synthetic_cloud()
        batch = self.queue_source("share")
        result = self.organize(batch, self.histories(batch, 19))
        self.assertEqual((result["organization_status"], result["organized_count"], result["organized_total"],
                          result["organized_missing"]), ("partial", 19, 20, 1))
        self.plugin.api_retry_task({"id": batch["id"]})
        self.tick(2)
        self.assertEqual([x[0] for x in self.cloud.writes], ["receive"])

    def test_deleted_small_attachment_does_not_prevent_magnet_twenty_of_twenty(self):
        self.synthetic_cloud()
        batch = self.queue_source("magnet")
        result = self.organize(batch, self.histories(batch))
        self.assertEqual((result["acquisition_status"], result["move_status"], result["organization_status"]),
                         ("saved", "success", "success"))
        self.assertEqual((result["organized_count"], result["organized_total"]), (20, 20))
        self.assertEqual([x[0] for x in self.cloud.writes], ["offline", "move"])

    def test_deleted_real_episode_still_reports_magnet_nineteen_of_twenty(self):
        self.synthetic_cloud()
        batch = self.queue_source("magnet")
        result = self.organize(batch, self.histories(batch, 19))
        self.assertEqual((result["acquisition_status"], result["move_status"], result["organization_status"]),
                         ("saved", "success", "partial"))
        self.assertEqual((result["organized_count"], result["organized_total"], result["organized_missing"]), (19, 20, 1))
        self.plugin.api_retry_task({"id": batch["id"]})
        self.tick(2)
        self.assertEqual([x[0] for x in self.cloud.writes], ["offline", "move"])

    def test_unknown_extra_size_remains_required_in_both_sources(self):
        for source in ("share", "magnet"):
            with self.subTest(source=source):
                self.synthetic_cloud(extra_size=None)
                batch = self.queue_source(source)
                result = self.organize(batch, self.histories(batch))
                self.assertEqual((result["organization_status"], result["organized_count"], result["organized_total"]),
                                 ("partial", 20, 21))
                self.assertEqual(result["organized_missing"], 1)
                self.assertEqual(self.plugin._record_view(result)["ignored_files"], [])

    def test_disabling_threshold_requires_small_attachment_in_both_sources(self):
        self.plugin._min_media_size_mb = 0
        for source in ("share", "magnet"):
            with self.subTest(source=source):
                self.synthetic_cloud()
                batch = self.queue_source(source)
                result = self.organize(batch, self.histories(batch))
                self.assertEqual(result["min_media_size_mb"], 0)
                self.assertEqual((result["organization_status"], result["organized_total"]), ("partial", 21))

    def test_all_tiny_batches_never_report_success_in_either_source(self):
        for source in ("share", "magnet"):
            with self.subTest(source=source):
                self.synthetic_cloud(episode_size=MIB)
                batch = self.queue_source(source)
                result = self.organize(batch, self.histories(batch))
                self.assertFalse(result["manifest_complete"])
                self.assertNotEqual(result["organization_status"], "success")
                self.assertEqual(len(self.plugin._record_view(result)["ignored_files"]), 21)

    def test_ignored_attachment_failure_does_not_override_main_episode_success(self):
        self.synthetic_cloud()
        batch = self.queue_source("share")
        entries = self.histories(batch)
        entries.append({**entries[0], "id": "extra-failure", "status": False,
                        "src": f"{batch['final_path']}/Season/幕后短片.mp4", "errmsg": "合成小视频已人为删除"})
        result = self.organize(batch, entries)
        self.assertEqual((result["organization_status"], result["organized_failed"], result["organized_total"]),
                         ("success", 0, 20))

    def test_config_reload_keeps_original_threshold_and_new_task_uses_new_setting(self):
        self.synthetic_cloud()
        old = self.queue()
        self.assertEqual(old["min_media_size_mb"], 10)
        self.plugin.init_plugin({"enabled": True, "p115_cookie": "SYNTHETIC", "tencent_cookie": "SYNTHETIC",
                                 "min_media_size_mb": 0})
        self.tick()
        old = self.plugin._records().get(old["id"])
        result = self.organize(old, self.histories(old))
        self.assertEqual((result["min_media_size_mb"], result["organization_status"], result["organized_total"]),
                         (10, "success", 20))
        ok, _ = self.plugin.do_transfer(rec("Show Season 1", media_type="tv", sheet="电视剧", tmdbid="900",
                                            links=[("115_share", "https://115.com/s/SYNTHETICNEW")]), "tv")
        self.assertTrue(ok)
        new = next(x for x in self.plugin._records().list() if x["id"] != old["id"])
        self.tick()
        new = self.plugin._records().get(new["id"])
        result = self.organize(new, self.histories(new))
        self.assertEqual((result["min_media_size_mb"], result["organization_status"], result["organized_total"]),
                         (0, "partial", 21))

    def test_invalid_config_threshold_is_rejected_before_changing_running_state(self):
        initial = self.plugin._generation
        for value in (-1, 1025, 1.2, "10", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.plugin.init_plugin({"enabled": True, "min_media_size_mb": value})
                self.assertEqual(self.plugin._generation, initial)
                self.assertEqual(self.plugin._min_media_size_mb, 10)
                self.assertTrue(self.plugin._enabled)


if __name__ == "__main__":
    unittest.main()
