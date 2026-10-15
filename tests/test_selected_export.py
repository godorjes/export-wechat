import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

import exporter_core as core
from test_export_all import FakeDB, create_contact_db


def fixture_db(root):
    root.mkdir(parents=True, exist_ok=True)
    create_contact_db(root / 'contact.db', [
        ('wxid_a', '张甲', '同名'), ('wxid_b', '张乙', '同名'),
        ('room@chatroom', '讨论群', ''), ('empty', '空会话', ''),
    ])
    db = FakeDB(root)
    db.account_dir = str(root)
    db.nicks = {'wxid_a': '同名', 'wxid_b': '同名', 'room@chatroom': '讨论群', 'wxid_self': '自己'}
    db.add_db('contact/contact.db', root / 'contact.db')
    for shard, self_id, friend_id in ((0, 1, 2), (1, 2, 1)):
        p = root / f'message_{shard}.db'
        with closing(sqlite3.connect(p)) as conn:
            conn.execute('CREATE TABLE Name2Id (user_name TEXT)')
            identities = ['wxid_self', 'wxid_a'] if shard == 0 else ['wxid_a', 'wxid_self']
            conn.executemany('INSERT INTO Name2Id VALUES (?)', [(x,) for x in identities])
            for username in ('wxid_a', 'wxid_b', 'room@chatroom', 'empty'):
                table = 'Msg_' + hashlib.md5(username.encode()).hexdigest()
                conn.execute(f'CREATE TABLE {table} (local_id INTEGER, local_type INTEGER, real_sender_id INTEGER, create_time INTEGER, message_content TEXT, sort_seq INTEGER)')
                if username != 'empty':
                    conn.execute(f'INSERT INTO {table} VALUES (?,?,?,?,?,?)',
                                 (shard+1, 1, self_id if shard == 0 else friend_id,
                                  1700000000+shard, '合成消息' + str(shard), shard+1))
            conn.commit()
        db.add_db(f'message/message_{shard}.db', p, message=True)
        # closing() owns the handle; commit explicitly before releasing it.
    return db


class SelectedExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = fixture_db(self.root / '中文 source')
        self.before = {Path(p): Path(p).read_bytes() for _, p, _ in self.db._db_files}

    def run_export(self, usernames, formats=('txt', 'md', 'json'), token=None, progress=None, out_root=None):
        import export_task_service as service
        options = service.ExportOptions(out_root=out_root or self.root / '输出 path', formats=formats)
        with patch.object(core, 'WeChatDB', return_value=self.db) as constructor:
            result = service.export_selected_chats(usernames, options, progress, token)
        self.assertEqual(constructor.call_count, 1)
        self.assertTrue(result['sensitive_cache_cleanup'])
        for p, content in self.before.items():
            self.assertEqual(p.read_bytes(), content)
        return result

    def test_selected_ids_same_name_and_shard_sender_remain_correct(self):
        result = self.run_export(['wxid_a', 'wxid_b', 'wxid_a'])
        self.assertEqual(result['exported'], 2)
        self.assertEqual(result['total_messages'], 4)
        a, b = result['chats']
        self.assertEqual(a['output_dir'], b['output_dir'])
        self.assertNotEqual(a['json'], b['json'])
        data = json.loads(Path(a['json']).read_text(encoding='utf-8-sig'))
        self.assertEqual([m['is_self'] for m in data['messages']], [True, False])
        self.assertEqual([m['sender_username'] for m in data['messages']], ['wxid_self', 'wxid_a'])
        self.assertEqual([m['content'] for m in data['messages']], ['合成消息0', '合成消息1'])

    def test_only_requested_chat_format_is_written(self):
        for fmt, file in [('txt', '同名.txt'), ('md', '同名.md'), ('json', '同名.json')]:
            with self.subTest(fmt=fmt):
                result = self.run_export(['wxid_a'], (fmt,), out_root=self.root / fmt)
                folder = Path(result['chats'][0]['output_dir'])
                self.assertEqual({p.name for p in folder.iterdir()}, {file})
                self.assertIsNone(result['chats'][0].get('json') if fmt != 'json' else result['chats'][0].get('txt'))

    def test_missing_and_empty_chat_do_not_stop_later_success(self):
        result = self.run_export(['missing', 'empty', 'wxid_a'])
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['skipped_empty'], 1)
        self.assertEqual(result['exported'], 1)
        self.assertEqual([r['status'] for r in result['chats']], ['failed', 'skipped_empty', 'exported'])

    def test_all_mode_stays_available(self):
        result = self.run_export(None)
        self.assertEqual(result['selected_total'], 4)
        self.assertEqual(result['exported'], 3)
        self.assertEqual(result['skipped_empty'], 1)

    def test_mid_chat_cancel_discards_partial_and_releases_sandbox(self):
        import export_task_service as service
        token = service.CancelToken()
        old_temp = tempfile.tempdir
        old_keys = os.environ.get(core.UPSTREAM_KEYS_ENV)
        def progress(event):
            if event['stage'] == '写出文件':
                token.cancel()
        result = self.run_export(['wxid_a', 'wxid_b'], token=token, progress=progress)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['exported'], 0)
        self.assertEqual(result['cancelled'], 2)
        self.assertEqual(list(Path(result['output_dir']).iterdir()), [])
        self.assertEqual(tempfile.tempdir, old_temp)
        self.assertEqual(os.environ.get(core.UPSTREAM_KEYS_ENV), old_keys)

    def test_cancel_between_chats_preserves_success(self):
        import export_task_service as service
        token = service.CancelToken()
        def progress(event):
            if event.get('completed') == 1:
                token.cancel()
        result = self.run_export(['wxid_a', 'wxid_b'], token=token, progress=progress)
        self.assertEqual(result['exported'], 1)
        self.assertEqual(result['cancelled'], 1)
        self.assertTrue(Path(result['chats'][0]['txt']).is_file())

    def test_write_failure_does_not_commit_partial_chat_or_leak_content(self):
        with patch.object(core, '_write_txt', side_effect=OSError('SECRET CHAT CONTENT')):
            result = self.run_export(['wxid_a', 'wxid_b'], ('txt',))
        self.assertEqual(result['failed'], 2)
        self.assertNotIn('SECRET CHAT CONTENT', json.dumps(result, ensure_ascii=False))
        self.assertEqual(list(Path(result['output_dir']).iterdir()), [])

    def test_repeated_task_does_not_overwrite_previous_export(self):
        first = self.run_export(['wxid_a'])
        second = self.run_export(['wxid_a'], ('txt',))
        self.assertEqual(first['output_dir'], second['output_dir'])
        self.assertNotEqual(first['chats'][0]['txt'], second['chats'][0]['txt'])
        self.assertTrue(Path(first['chats'][0]['json']).is_file())

    def test_options_reject_no_format_and_invalid_ids_before_connecting(self):
        import export_task_service as service
        with self.assertRaises(ValueError):
            service.ExportOptions(formats=())
        with patch.object(core, 'WeChatDB', side_effect=AssertionError('must not connect')):
            with self.assertRaises(ValueError):
                service.export_selected_chats([], service.ExportOptions(out_root=self.root))

    def test_writer_can_cancel_inside_message_loop(self):
        import export_task_service as service
        token = service.CancelToken()
        calls = 0
        def check():
            nonlocal calls
            calls += 1
            if calls >= 2:
                raise service.ExportCancelled()
        token.check = check
        messages = [{'time': '2026-10-14 12:00:00', 'sender': '我', 'content': '合成文本', 'type': '文本'}] * 10
        with self.assertRaises(service.ExportCancelled):
            core._write_txt(messages, self.root / 'partial.txt', False, '测试', cancel_token=token)

    def test_constructor_error_reports_sensitive_cleanup(self):
        import export_task_service as service
        with patch.object(core, 'WeChatDB', side_effect=RuntimeError('SECRET KEY')):
            result = service.export_selected_chats(['wxid_a'], service.ExportOptions(out_root=self.root))
        self.assertEqual(result['state'], 'failed')
        self.assertTrue(result.get('sensitive_cache_cleanup'))
        self.assertNotIn('SECRET KEY', result['error'])

    def test_selected_export_copies_real_file_and_plain_image_thumbnail(self):
        from PIL import Image
        import export_task_service as service
        table = 'Msg_' + hashlib.md5(b'wxid_a').hexdigest()
        with closing(sqlite3.connect(self.db.root / 'message_0.db')) as conn:
            conn.executemany(f'INSERT INTO {table} VALUES (?,?,?,?,?,?)', [
                (3, 49, 1, 1700000000, '<msg><appmsg><type>6</type><title>测试附件.txt</title></appmsg></msg>', 3),
                (4, 3, 1, 1700000000, '', 4),
            ])
            conn.commit()
        file = self.db.root / 'msg/file/测试附件.txt'
        file.parent.mkdir(parents=True)
        file.write_bytes(b'synthetic attachment')
        thumb = self.db.root / 'cache/2023-11/Message' / hashlib.md5(b'wxid_a').hexdigest() / 'Thumb/4_1700000000_thumb.jpg'
        thumb.parent.mkdir(parents=True)
        Image.new('RGB', (20, 20), 'blue').save(thumb)
        class MediaBoundary:
            def _file_name(self, _row):
                return None
        self.before = {Path(p): Path(p).read_bytes() for _, p, _ in self.db._db_files}
        with patch.object(core, 'WeChatDB', return_value=self.db), \
             patch.object(core, 'MediaDownloader', return_value=MediaBoundary()), \
             patch.object(core, '_ensure_cfg_dword', return_value=(None, None)):
            result = service.export_selected_chats(['wxid_a'], service.ExportOptions(
                out_root=self.root / 'media-out', export_images=True, export_files=True))
        self.assertEqual(result['exported'], 1)
        chat = result['chats'][0]
        self.assertEqual(chat['media_stats']['files_exported'], 1)
        self.assertEqual(chat['media_stats']['images_exported'], 1)
        data = json.loads(Path(chat['json']).read_text(encoding='utf-8-sig'))
        attachments = {m['media']['kind']: m['media']['path'] for m in data['messages'] if m['media']}
        self.assertEqual((Path(chat['output_dir']) / attachments['file']).read_bytes(), file.read_bytes())
        self.assertEqual((Path(chat['output_dir']) / attachments['image']).read_bytes(), thumb.read_bytes())
        self.assertTrue(all(p.startswith('同名_media/') for p in attachments.values()))
        markdown = Path(chat['md']).read_text(encoding='utf8')
        links = re.findall(r'(?:src="|\]\()([^"\)]+)', markdown)
        self.assertEqual(len(links), 2)
        for link in links:
            self.assertTrue((Path(chat['output_dir']) / unquote(link)).is_file())
        text = Path(chat['txt']).read_text(encoding='utf-8-sig')
        for relative in attachments.values():
            self.assertIn(relative, text)

    def test_real_pinned_self_info_method_does_not_leave_sqlite_handles_open(self):
        opened = []
        original_open = self.db._open
        def tracked_open(rel):
            conn = original_open(rel)
            opened.append(conn)
            self.addCleanup(conn.close)
            return conn
        self.db._open = tracked_open
        self.db.wxid = 'wxid_self'
        # Save the actual pinned method before replacing only its constructor.
        from wechatauto import WeChatDB
        self.db.get_self_info = lambda: WeChatDB.get_self_info(self.db)
        self.run_export(['wxid_a'])
        for conn in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute('SELECT 1')

    def test_cancel_during_constructor_skips_all_metadata_work(self):
        import export_task_service as service
        token = service.CancelToken()
        def connect(**kwargs):
            token.cancel()
            return self.db
        with patch.object(core, 'WeChatDB', side_effect=connect), \
             patch.object(core, '_batch_chat_candidates', side_effect=AssertionError('No enumeration after cancel')):
            result = service.export_selected_chats(['wxid_a'], service.ExportOptions(out_root=self.root), cancel_token=token)
        self.assertEqual(result['state'], 'cancelled')
        self.assertTrue(result['sensitive_cache_cleanup'])
        self.assertEqual(result['cancelled'], 1)


if __name__ == '__main__':
    unittest.main()
