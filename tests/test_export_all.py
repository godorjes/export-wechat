import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_core():
    wechatauto = ModuleType("wechatauto")
    wechatauto.WeChatDB = Mock(side_effect=AssertionError("Real WeChatDB is forbidden"))
    wechatauto.MediaDownloader = Mock(side_effect=AssertionError("Real media is forbidden"))

    zstandard = ModuleType("zstandard")
    zstandard.ZstdDecompressor = Mock(side_effect=AssertionError("No zstd fixtures"))

    pillow = ModuleType("PIL")
    pillow.Image = Mock()
    pillow.ImageStat = Mock()

    with patch.dict(sys.modules, {
        "wechatauto": wechatauto,
        "zstandard": zstandard,
        "PIL": pillow,
    }):
        spec = importlib.util.spec_from_file_location(
            "_bulk_exporter_core",
            ROOT / "exporter_core.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def create_contact_db(path: Path, rows):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE contact (username TEXT, nick_name TEXT, remark TEXT)"
        )
        conn.executemany(
            "INSERT INTO contact(username, nick_name, remark) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def create_session_db(path: Path, rows):
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE SessionTable "
            "(username TEXT, last_timestamp INTEGER, is_hidden INTEGER)"
        )
        conn.executemany(
            "INSERT INTO SessionTable(username, last_timestamp, is_hidden) "
            "VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def create_message_db(path: Path, usernames=(), unresolved_hashes=()):
    conn = sqlite3.connect(path)
    try:
        for username in usernames:
            md5hex = hashlib.md5(username.encode("utf-8")).hexdigest()
            conn.execute(f'CREATE TABLE "Msg_{md5hex}" (local_id INTEGER)')
        for md5hex in unresolved_hashes:
            conn.execute(f'CREATE TABLE "Msg_{md5hex}" (local_id INTEGER)')
        conn.commit()
    finally:
        conn.close()


class FakeDB:
    def __init__(self, root: Path, self_username="wxid_self"):
        self.root = root
        self.self_username = self_username
        self._db_files = []
        self._paths = {}
        self._message_rels = []
        self.nicks = {}

    def add_db(self, rel, path, message=False):
        self._db_files.append((rel, str(path), None))
        self._paths[rel] = str(path)
        if message:
            self._message_rels.append(rel)

    def _open(self, rel):
        return sqlite3.connect(
            Path(self._paths[rel]).as_uri() + "?mode=ro",
            uri=True,
        )

    def _message_dbs(self):
        return list(self._message_rels)

    def _nickname_index(self):
        return dict(self.nicks)

    def get_self_info(self):
        return {"username": self.self_username}


class BulkEnumerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_core()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_stable_folder_depends_only_on_username(self):
        a1 = self.core._stable_batch_folder("wxid_same")
        a2 = self.core._stable_batch_folder("wxid_same")
        b = self.core._stable_batch_folder("wxid_other")
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)
        self.assertIn("wxid_same", a1)

    def test_enumerates_only_real_message_tables_and_filters_special_accounts(self):
        contact = self.root / "contact.db"
        session = self.root / "session.db"
        message = self.root / "message_0.db"

        create_contact_db(contact, [
            ("wxid_friend", "好友", ""),
            ("wxid_member_only", "群成员", ""),
            ("111@chatroom", "项目群", ""),
            ("filehelper", "文件传输助手", ""),
            ("wxid_self", "我", ""),
        ])
        create_session_db(session, [
            ("111@chatroom", 200, 0),
            ("wxid_friend", 100, 0),
            ("wxid_member_only", 300, 0),
        ])
        create_message_db(
            message,
            usernames=("wxid_friend", "111@chatroom", "filehelper"),
        )

        db = FakeDB(self.root)
        db.nicks = {
            "wxid_friend": "好友",
            "wxid_member_only": "群成员",
            "111@chatroom": "项目群",
            "filehelper": "文件传输助手",
            "wxid_self": "我",
        }
        db.add_db("contact/contact.db", contact)
        db.add_db("session/session.db", session)
        db.add_db("message/message_0.db", message, message=True)

        chats, unresolved = self.core._batch_chat_candidates(db)
        self.assertEqual(unresolved, 0)
        self.assertEqual(
            [item["username"] for item in chats],
            ["111@chatroom", "wxid_friend"],
        )
        self.assertEqual(chats[0]["name"], "项目群")
        self.assertTrue(chats[0]["is_group"])
        self.assertNotIn("wxid_member_only", {c["username"] for c in chats})
        self.assertNotIn("filehelper", {c["username"] for c in chats})

    def test_unresolved_message_table_is_reported_not_guessed(self):
        message = self.root / "message_0.db"
        unresolved = "a" * 32
        create_message_db(message, unresolved_hashes=(unresolved,))
        db = FakeDB(self.root)
        db.add_db("message/message_0.db", message, message=True)
        logs = []

        chats, unresolved_count = self.core._batch_chat_candidates(
            db,
            progress=logs.append,
        )
        self.assertEqual(chats, [])
        self.assertEqual(unresolved_count, 1)
        self.assertTrue(
            any(
                "可靠反查 username" in line and "已跳过" in line
                for line in logs
            )
        )


class BulkExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_core()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.out = self.root / "out"

    def _chat(self, username, name, last_time):
        return {
            "username": username,
            "name": name,
            "is_group": username.endswith("@chatroom"),
            "last_time": last_time,
        }

    def _success_result(self, contact, folder, count=2):
        target = self.out / folder
        return {
            "chat_name": contact["name"],
            "is_group": contact["is_group"],
            "message_count": count,
            "sender_resolution_counts": {"resolved": count},
            "media_stats": {"images_requested": 0, "images_exported": 0},
            "output_dir": str(target),
            "txt": str(target / "chat_full_for_llm.txt"),
            "md": str(target / "chat_full_for_llm.md"),
            "json": str(target / "chat_full_parsed.json"),
        }

    def test_batch_reuses_one_db_isolates_errors_and_writes_index(self):
        contacts = [
            self._chat("wxid_a", "同名", 300),
            self._chat("wxid_b", "同名", 200),
            self._chat("111@chatroom", "群", 100),
        ]
        seen = []

        def fake_impl(**kwargs):
            seen.append(kwargs)
            username = kwargs["contact"]["username"]
            if username == "wxid_b":
                raise self.core.EmptyConversationError("没有读取到该会话的消息。")
            if username == "111@chatroom":
                raise RuntimeError("synthetic failure")
            return self._success_result(
                kwargs["contact"],
                kwargs["folder_name"],
                count=3,
            )

        fake_db = object()
        with (
            patch.object(self.core, "WeChatDB", return_value=fake_db) as constructor,
            patch.object(
                self.core,
                "_batch_chat_candidates",
                return_value=(contacts, 0),
            ),
            patch.object(self.core, "_export_chat_impl", side_effect=fake_impl),
        ):
            result = self.core._export_all_chats_impl(out_root=self.out)

        constructor.assert_called_once()
        self.assertEqual(len(seen), 3)
        self.assertIs(seen[0]["db"], seen[1]["db"])
        self.assertIs(seen[0]["index_cache"], seen[2]["index_cache"])
        self.assertEqual(result["exported"], 1)
        self.assertEqual(result["skipped_empty"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["total_messages"], 3)

        folders = {item["username"]: item["folder"] for item in result["chats"]}
        self.assertNotEqual(folders["wxid_a"], folders["wxid_b"])
        self.assertEqual(
            folders["wxid_a"],
            self.core._stable_batch_folder("wxid_a"),
        )

        data = json.loads(
            Path(result["index_json"]).read_text(encoding="utf-8-sig")
        )
        self.assertEqual(
            {item["username"]: item["status"] for item in data["chats"]},
            {
                "wxid_a": "exported",
                "wxid_b": "skipped_empty",
                "111@chatroom": "failed",
            },
        )

    def test_generic_value_error_is_failure_not_empty(self):
        contacts = [self._chat("wxid_a", "A", 1)]
        with (
            patch.object(self.core, "WeChatDB", return_value=object()),
            patch.object(
                self.core,
                "_batch_chat_candidates",
                return_value=(contacts, 0),
            ),
            patch.object(
                self.core,
                "_export_chat_impl",
                side_effect=ValueError("bad path"),
            ),
        ):
            result = self.core._export_all_chats_impl(out_root=self.out)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["skipped_empty"], 0)
        self.assertIn("ValueError", result["chats"][0]["error"])

    def test_limit_keeps_recent_order(self):
        contacts = [
            self._chat("wxid_new", "新", 300),
            self._chat("wxid_old", "旧", 100),
            self._chat("wxid_none", "无时间", None),
        ]
        seen = []

        def fake_impl(**kwargs):
            seen.append(kwargs["contact"]["username"])
            return self._success_result(
                kwargs["contact"],
                kwargs["folder_name"],
                count=1,
            )

        with (
            patch.object(self.core, "WeChatDB", return_value=object()),
            patch.object(
                self.core,
                "_batch_chat_candidates",
                return_value=(contacts, 0),
            ),
            patch.object(self.core, "_export_chat_impl", side_effect=fake_impl),
        ):
            result = self.core._export_all_chats_impl(
                out_root=self.out,
                limit=2,
            )

        self.assertEqual(seen, ["wxid_new", "wxid_old"])
        self.assertTrue(result["limited"])
        self.assertEqual(result["discovered_total"], 3)
        self.assertEqual(result["selected_total"], 2)

    def test_outer_batch_cleanup_runs_on_keyboard_interrupt(self):
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            seen = {}

            def fail_impl(**kwargs):
                seen["workdir"] = Path(kwargs["workdir"])
                (seen["workdir"] / "keys.json").write_text(
                    "secret",
                    encoding="utf-8",
                )
                raise KeyboardInterrupt()

            with (
                patch.object(
                    self.core.tempfile,
                    "gettempdir",
                    return_value=str(temp_root),
                ),
                patch.object(
                    self.core,
                    "_export_all_chats_impl",
                    side_effect=fail_impl,
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    self.core.export_all_chats(self.out)

            self.assertFalse(seen["workdir"].exists())

    def test_limit_validation(self):
        with self.assertRaisesRegex(ValueError, "正整数"):
            self.core.export_all_chats(self.out, limit=0)


class UpstreamLoggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_core()

    def test_sandbox_disables_and_restores_upstream_file_logger_flag(self):
        class FakeParam:
            ENABLE_FILE_LOGGER = True

        param = ModuleType("wechatauto.param")
        param.WxParam = FakeParam

        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "run"
            workdir.mkdir()
            with patch.dict(sys.modules, {"wechatauto.param": param}):
                with self.core._upstream_sensitive_sandbox(workdir):
                    self.assertFalse(FakeParam.ENABLE_FILE_LOGGER)
                self.assertTrue(FakeParam.ENABLE_FILE_LOGGER)



class PidEncodingCompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = load_core()

    def test_pid_lookup_uses_explicit_gbk_and_parses_pids(self):
        completed = Mock()
        completed.stdout = (
            '"Weixin.exe","4321","Console","1","123,456 K"\n'
            '"Weixin.exe","8765","Console","1","234,567 K"\n'
        )
        with patch.object(
            self.core.subprocess,
            "run",
            return_value=completed,
        ) as proc:
            pids = self.core._find_weixin_pids_compat(object())

        self.assertEqual(pids, [4321, 8765])
        kwargs = proc.call_args.kwargs
        self.assertTrue(kwargs["text"])
        self.assertEqual(kwargs["encoding"].lower(), "gbk")
        self.assertEqual(kwargs["errors"], "replace")

    def test_pid_lookup_tolerates_none_stdout(self):
        completed = Mock()
        completed.stdout = None
        with patch.object(
            self.core.subprocess,
            "run",
            return_value=completed,
        ):
            self.assertEqual(
                self.core._find_weixin_pids_compat(object()),
                [],
            )

    def test_sandbox_patches_and_restores_pid_lookup(self):
        class FakeDB:
            def _find_weixin_pids(self):
                return [999]

        original = FakeDB.__dict__["_find_weixin_pids"]
        with tempfile.TemporaryDirectory() as td:
            workdir = Path(td) / "run"
            workdir.mkdir()
            with patch.object(self.core, "WeChatDB", FakeDB):
                with self.core._upstream_sensitive_sandbox(workdir):
                    self.assertIs(
                        FakeDB.__dict__["_find_weixin_pids"],
                        self.core._find_weixin_pids_compat,
                    )
                self.assertIs(
                    FakeDB.__dict__["_find_weixin_pids"],
                    original,
                )


if __name__ == "__main__":
    unittest.main()
