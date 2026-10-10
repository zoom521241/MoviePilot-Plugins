"""0.11.0 link extraction regressions with synthetic links only."""
import importlib
import sys
import types
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugins.v3" / "doc115subscribe"
PACKAGE = "_doc115_parser_testpkg"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(PLUGIN)]
    sys.modules[PACKAGE] = package
links = importlib.import_module(PACKAGE + ".link_router")

MD4 = "0123456789ABCDEF0123456789ABCDEF"
ED2K = f"ed2k://|file|Synthetic Movie 2025 4K.mkv|1048576|{MD4}|/"


class ShareHostTests(unittest.TestCase):
    def test_anxia_and_share_subdomains_are_115(self):
        for url in ("https://anxia.com/s/SYNTH", "https://share.115.com/s/SYNTH",
                    "https://x.anxia.com/s/SYNTH", "https://115cdn.com/s/SYNTH?password=ab12"):
            with self.subTest(url=url):
                self.assertEqual(links.classify_link(url), "115_share")
        for url in ("https://anxia.com.evil.invalid/s/SYNTH", "https://evilanxia.com/s/SYNTH"):
            self.assertNotEqual(links.classify_link(url), "115_share")

    def test_normalize_share_target_is_unified(self):
        for url in ("https://115cdn.com/s/SYNTH?password=ab12", "https://anxia.com/s/SYNTH/?pwd=ab12",
                    "https://www.115.com/s/SYNTH#password=ab12", "https://share.115.com/s/SYNTH?password=ab12&x=1"):
            with self.subTest(url=url):
                self.assertEqual(links.normalize_115_share(url), "https://115.com/s/SYNTH?password=ab12")
        self.assertEqual(links.normalize_115_share("https://115cdn.com/s/SYNTH"), "https://115.com/s/SYNTH")


class UrlBoundaryTests(unittest.TestCase):
    def test_chinese_text_and_fullwidth_punctuation_are_not_swallowed(self):
        for text in ("https://115.com/s/SYNTH链接", "https://115.com/s/SYNTH，下一个", "（https://115.com/s/SYNTH）",
                     "https://115.com/s/SYNTH。", "地址:https://115.com/s/SYNTH 备注"):
            with self.subTest(text=text):
                self.assertEqual(links.extract_links(text), [("115_share", "https://115.com/s/SYNTH")])

    def test_magnet_stops_at_chinese(self):
        magnet = "magnet:?xt=urn:btih:" + "a" * 40
        self.assertEqual(links.extract_links(magnet + "（4K中字）"), [("magnet", magnet)])

    def test_password_in_same_cell(self):
        for text in ("https://115.com/s/SYNTH 提取码：ab12", "https://115.com/s/SYNTH 访问码 ab12",
                     "https://115.com/s/SYNTH 密码:ab12", "https://115.com/s/SYNTH pwd=ab12",
                     "code: ab12 https://115.com/s/SYNTH"):
            with self.subTest(text=text):
                self.assertEqual(links.extract_links(text)[0][1], "https://115.com/s/SYNTH?password=ab12")
        # 链接自带提取码优先
        self.assertEqual(links.extract_links("https://115.com/s/SYNTH?password=zz99 提取码 ab12")[0][1],
                         "https://115.com/s/SYNTH?password=zz99")


class Ed2kTests(unittest.TestCase):
    def test_name_with_spaces_is_kept(self):
        self.assertEqual(links.extract_links(ED2K), [("ed2k", ED2K)])

    def test_https_wrapped_ed2k_is_unwrapped(self):
        self.assertEqual(links.extract_links("https://" + ED2K), [("ed2k", ED2K)])

    def test_trailing_chinese_punctuation_is_excluded(self):
        self.assertEqual(links.extract_links(ED2K + "，备用"), [("ed2k", ED2K)])
        self.assertEqual(links.extract_links(ED2K[:-1] + "。"), [("ed2k", ED2K[:-1])])

    def test_hash_attribute_suffix(self):
        url = f"ed2k://|file|A B.mkv|123|{MD4}|h=ABCDEFGHIJKLMNOP|/"
        self.assertEqual(links.extract_links(url + "中文"), [("ed2k", url)])

    def test_dedup(self):
        found = links.extract_links(ED2K + " https://" + ED2K)
        self.assertEqual(links.dedup_links(found), [("ed2k", ED2K)])
        shares = [("115_share", "https://115.com/s/SYNTH"), ("115_share", "https://115.com/s/SYNTH?password=ab12")]
        self.assertEqual(links.dedup_links(shares), [("115_share", "https://115.com/s/SYNTH?password=ab12")])
        magnets = [("magnet", "magnet:?xt=urn:btih:" + "A" * 40), ("magnet", "magnet:?xt=urn:btih:" + "a" * 40 + "&dn=x")]
        self.assertEqual(len(links.dedup_links(magnets)), 1)


if __name__ == "__main__":
    unittest.main()
