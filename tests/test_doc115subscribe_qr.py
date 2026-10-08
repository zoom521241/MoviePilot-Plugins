"""Synthetic QR login regression checks; no browser or network is started."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / "plugins.v3" / "doc115subscribe" / "qrlogin_browser.py"
SPEC = importlib.util.spec_from_file_location("doc115_qr_test", SOURCE)
qr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qr)


class QrSessionTests(unittest.TestCase):
    def test_rejects_non_document_hosts(self):
        for url in ("http://docs.qq.com/sheet/test", "https://docs.qq.com.evil.test/sheet/test",
                    "https://127.0.0.1/sheet/test", "https://docs.qq.com@evil.test/sheet/test",
                    "https://docs.qq.com:8443/sheet/test", "https://docs.qq.com/sheet/",
                    "https://docs.qq.com:invalid/sheet/test", "https://docs.qq.com/sheet/../other"):
            with self.subTest(url=url), self.assertRaises(qr.QrLoginError):
                qr.BrowserQrLogin(url)

    def test_close_before_start_is_idempotent_and_does_not_spawn_worker(self):
        session = qr.BrowserQrLogin("https://docs.qq.com/sheet/test")
        with patch.object(qr, "_get_worker") as get_worker:
            session.close()
            session.close()
            self.assertEqual(session.check()["state"], "expired")
        get_worker.assert_not_called()

    def test_commands_are_scoped_to_original_worker_and_session(self):
        worker = Mock()
        worker.submit.side_effect = [(b"png", False), {"state": "wait"}, None]
        session = qr.BrowserQrLogin("https://docs.qq.com/sheet/test")
        with patch.object(qr, "_get_worker", return_value=worker) as get_worker:
            session.start()
            session.check()
            session.close()
            session.close()
        get_worker.assert_called_once()
        calls = worker.submit.call_args_list
        self.assertEqual(calls[0].args[1]["session_id"], session.session_id)
        self.assertEqual(calls[1].args, ("check", session.session_id))
        self.assertEqual(calls[2].args, ("end_session", session.session_id))

    def test_stale_session_cannot_check_or_close_replacement(self):
        worker = qr._Worker.__new__(qr._Worker)
        worker._session_id = "new"
        worker._ctx = Mock()
        worker._page = Mock()
        self.assertEqual(worker._check("old")["state"], "expired")
        worker._ctx.cookies.assert_not_called()
        worker._end_session("old")
        worker._ctx.close.assert_not_called()
        self.assertEqual(worker._session_id, "new")

    def test_cookie_domain_boundary_does_not_accept_spoofed_tencent_domain(self):
        worker = qr._Worker.__new__(qr._Worker)
        worker._session_id = "current"
        worker._last_shot = qr.time.time()
        worker._ctx = Mock()
        worker._ctx.cookies.return_value = [{"name": "uid", "value": "attacker", "domain": "evilqq.com"}]
        self.assertEqual(worker._check("current")["state"], "wait")
        worker._ctx.cookies.return_value += [{"name": "uid", "value": "good", "domain": ".docs.qq.com"}]
        result = worker._check("current")
        self.assertEqual(result["state"], "confirmed")
        self.assertEqual(result["cookie"], "uid=good")


if __name__ == "__main__":
    unittest.main()
