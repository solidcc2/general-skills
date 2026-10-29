from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "scripts/deliver_file.py"
SPEC = importlib.util.spec_from_file_location("deliver_file", MODULE_PATH)
assert SPEC and SPEC.loader
deliver_file = importlib.util.module_from_spec(SPEC)
sys.modules["deliver_file"] = deliver_file
SPEC.loader.exec_module(deliver_file)


class DeliverFileTest(unittest.TestCase):
    def config(self) -> dict:
        return {
            "profile": "test-profile",
            "root_folder_token": "fld_root",
            "ledger": {
                "base_token": "base_token",
                "table_id": "tbl_table",
                "fields": {"file": "文件", "recipient": "收件人", "category": "分类", "note": "备注"},
            },
        }

    def test_dry_run_has_fixed_order_and_never_calls_lark(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.zip"
            artifact.write_bytes(b"test")
            args = argparse.Namespace(
                file=str(artifact), recipient="张三", category="builds", name=None,
                note="", message=None, dry_run=True, yes=False,
            )
            with mock.patch.object(deliver_file, "cli") as mocked_cli:
                result = deliver_file.deliver(args, self.config())
            mocked_cli.assert_not_called()
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["steps"][-1], "log")

    def test_permission_mismatch_stops_delivery(self) -> None:
        result = {"permission_public": {"security_entity": "only_full_access"}}
        members = {"items": [{"member_type": "openid", "member_id": "ou_1", "perm": "edit"}]}
        with mock.patch.object(deliver_file, "cli", side_effect=[{}, members, result]):
            with self.assertRaises(deliver_file.DeliveryError) as context:
                deliver_file.authorize(self.config(), "file_token", "ou_1")
        self.assertEqual(context.exception.stage, "permission-verify")

    def test_log_contains_only_success_fields(self) -> None:
        response = {"ok": True, "data": {"record_id_list": ["rec_1"]}}
        with mock.patch.object(deliver_file, "cli", return_value=response) as mocked_cli:
            record_ids = deliver_file.write_log(
                self.config(), "https://example/file/1", "ou_1", "builds", "done"
            )
        self.assertEqual(record_ids, ["rec_1"])
        argv = mocked_cli.call_args.args[1]
        payload = json.loads(argv[argv.index("--json") + 1])
        self.assertEqual(payload["fields"], ["文件", "收件人", "分类", "备注"])

    def test_delivery_orders_send_before_log(self) -> None:
        events = []
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.zip"
            artifact.write_bytes(b"test")
            args = argparse.Namespace(
                file=str(artifact), recipient="张三", category="builds", name=None,
                note="done", message=None, dry_run=False, yes=True,
            )
            with (
                mock.patch.object(deliver_file, "auth", side_effect=lambda config: events.append("auth")),
                mock.patch.object(deliver_file, "recipient", side_effect=lambda config, query: (events.append("recipient") or {"id": "ou_1", "name": "张三"})),
                mock.patch.object(deliver_file, "folder", side_effect=lambda config, parent, name: (events.append("folder") or f"fld_{name}")),
                mock.patch.object(deliver_file, "upload", side_effect=lambda *unused: (events.append("upload") or ("file_1", "https://example/file/1"))),
                mock.patch.object(deliver_file, "authorize", side_effect=lambda *unused: events.append("authorize")),
                mock.patch.object(deliver_file, "send", side_effect=lambda *unused: (events.append("send") or "msg_1")),
                mock.patch.object(deliver_file, "write_log", side_effect=lambda *unused, **kwargs: (events.append("log") or ["rec_1"])),
            ):
                result = deliver_file.deliver(args, self.config())
        self.assertEqual(events, ["auth", "recipient", "folder", "folder", "upload", "authorize", "send", "log"])
        self.assertEqual(result["record_ids"], ["rec_1"])

    def test_log_failure_after_send_returns_recovery_without_resend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "artifact.zip"
            artifact.write_bytes(b"test")
            args = argparse.Namespace(
                file=str(artifact), recipient="张三", category="builds", name=None,
                note="done", message=None, dry_run=False, yes=True,
            )
            with (
                mock.patch.object(deliver_file, "auth"),
                mock.patch.object(deliver_file, "recipient", return_value={"id": "ou_1", "name": "张三"}),
                mock.patch.object(deliver_file, "folder", side_effect=["fld_category", "fld_month"]),
                mock.patch.object(deliver_file, "upload", return_value=("file_1", "https://example/file/1")),
                mock.patch.object(deliver_file, "authorize"),
                mock.patch.object(deliver_file, "send", return_value="msg_1") as mocked_send,
                mock.patch.object(deliver_file, "write_log", side_effect=deliver_file.DeliveryError("ledger", "down")),
            ):
                with self.assertRaises(deliver_file.DeliveryError) as context:
                    deliver_file.deliver(args, self.config())
        self.assertEqual(context.exception.stage, "ledger-after-send")
        self.assertEqual(context.exception.recovery["message_id"], "msg_1")
        mocked_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
