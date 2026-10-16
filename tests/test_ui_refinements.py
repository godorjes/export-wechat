import gc
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch


class UiRefinementsTests(unittest.TestCase):
    def setUp(self):
        from ui.main_window import App
        self.app = App(auto_load=False)
        self.app.update()

    def tearDown(self):
        self.app.destroy()
        self.app = None
        gc.collect()

    def wait_for_task(self):
        deadline = time.monotonic()+5
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy)

    def test_detect_button_reads_fixture_before_showing_available_account(self):
        import exporter_core as core
        from test_selected_export import fixture_db
        app = self.app
        def header_status():
            def walk(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from walk(child)
            return ' '.join(w.cget('text') for w in walk(app.account_btn.master)
                            if isinstance(w, tk.Label) and w != app.account_dot)
        self.assertIn('未识别', header_status())
        with tempfile.TemporaryDirectory() as tmp:
            db = fixture_db(Path(tmp)/'source')
            (Path(db.account_dir)/'db_storage').mkdir()
            gate = threading.Event()
            def discover(_progress):
                gate.wait(2)
                return [db.account_dir]
            with patch('ui.main_window.discover_sources', side_effect=discover), \
                 patch('ui.main_window.process_status', return_value='微信正在运行'), \
                 patch.object(core, 'WeChatDB', return_value=db):
                app.account_btn.invoke()
                app.update()
                try:
                    self.assertTrue(app.busy)
                    self.assertEqual(app.account_btn.cget('text'), '检测中…')
                    self.assertEqual(app.account_btn.cget('state'), 'disabled')
                    self.assertIn('检测中', header_status())
                    app.account_btn.invoke()
                    self.assertTrue(app.busy)
                    self.assertFalse(any(isinstance(w, tk.Toplevel) and w.winfo_ismapped()
                                         for w in app.winfo_children()))
                finally:
                    gate.set()
                    self.wait_for_task()
            self.assertTrue(app.source_ready)
            self.assertEqual(app.loaded_source, db.account_dir)
            self.assertEqual(app.account_dot.cget('foreground'), '#00bd84')
            self.assertEqual(app.account_btn.cget('text'), '重新检测')
            self.assertEqual(app.account_btn.cget('state'), 'normal')
            self.assertIn('已识别', header_status())
            self.assertIn('数据可读取', app.source_status.get())

    def test_local_directories_and_failed_detection_never_show_green(self):
        app = self.app
        with patch('ui.main_window.discover_sources', return_value=['E:/old-local-data']), \
             patch('ui.main_window.process_status', return_value='未检测到微信进程，请先登录微信'):
            app.account_btn.invoke()
            self.wait_for_task()
        self.assertFalse(app.source_ready)
        self.assertEqual(app.account_dot.cget('foreground'), '#db5252')
        self.assertIn('未检测到微信进程', app.source_status.get())
        for error, reason in [(PermissionError('PRIVATE BODY'), '权限'), (OSError('PRIVATE BODY'), '无法读取')]:
            app.list_loaded({'chats': [], 'account_dir': 'E:/synthetic-account', 'sensitive_cache_cleanup': True})
            with patch('ui.main_window.discover_sources', side_effect=error), \
                 patch('ui.main_window.messagebox.showerror', side_effect=AssertionError('Use inline feedback')):
                app.account_btn.invoke()
                self.wait_for_task()
            self.assertFalse(app.source_ready)
            self.assertEqual(app.account_dot.cget('foreground'), '#db5252')
            self.assertIn('检测失败', app.source_status.get())
            self.assertIn(reason, app.source_status.get())
            self.assertNotIn('PRIVATE BODY', app.source_status.get())
            self.assertEqual(app.account_btn.cget('state'), 'normal')

    def test_detection_skips_old_unreadable_account_and_pins_readable_account(self):
        import exporter_core as core
        from test_selected_export import fixture_db
        app = self.app
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root/'old-account'
            (old/'db_storage').mkdir(parents=True)
            db = fixture_db(root/'active-account')
            (Path(db.account_dir)/'db_storage').mkdir()
            app.list_loaded({'chats': [{'username': 'wxid_a', 'name': '同名'}],
                             'account_dir': str(old), 'sensitive_cache_cleanup': True})
            app.chat_list.model.toggle('wxid_a')
            attempts = []
            def connect(**kwargs):
                attempts.append(kwargs['account'])
                if kwargs['account'] == 'old-account':
                    raise RuntimeError('Old account is not readable')
                return db
            with patch('ui.main_window.discover_sources', return_value=[str(old), db.account_dir]), \
                 patch('ui.main_window.process_status', return_value='微信正在运行'), \
                 patch.object(core, 'WeChatDB', side_effect=connect):
                app.account_btn.invoke()
                self.wait_for_task()
            self.assertEqual(attempts, ['old-account', 'active-account'])
            self.assertTrue(app.source_ready)
            self.assertEqual(app.loaded_source, db.account_dir)
            self.assertEqual(app.get_export_options().db_dir, db.account_dir)
            self.assertEqual(app.chat_list.model.selected, set())

    def test_save_path_has_native_picker_manual_edit_and_no_duplicate_path_field(self):
        app = self.app
        original = app.out.get()
        self.assertTrue(app.path_entry.winfo_ismapped())
        with patch('ui.main_window.filedialog.askdirectory', return_value=''):
            app.browse_output_btn.invoke()
        self.assertEqual(app.out.get(), original)
        with tempfile.TemporaryDirectory() as tmp:
            with patch('ui.main_window.filedialog.askdirectory', return_value=tmp):
                app.browse_output_btn.invoke()
            self.assertEqual(app.path_entry.get(), tmp)
            self.assertEqual(Path(app.get_export_options().out_root), Path(tmp))
            app.path_entry.delete(0, 'end')
            app.path_entry.insert(0, str(Path(tmp)/'manual'))
            self.assertEqual(Path(app.get_export_options().out_root), Path(tmp)/'manual')
        self.assertFalse(hasattr(app, 'destination_combo'))
        self.assertFalse(hasattr(app, 'dest_help_label'))
        app.update()
        self.assertEqual(app.browse_output_btn.winfo_height(), 42)

    def test_invalid_output_is_rejected_before_reading_wechat(self):
        import exporter_core as core
        app = self.app
        app.loaded_source = 'E:/synthetic-account'
        app.chat_list.replace([{'username': 'a', 'name': '测试', 'is_group': False}])
        app.chat_list.model.toggle('a')
        app.source_ready = True
        app.update_buttons()
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'already-a-file'
            file.write_text('keep', encoding='utf8')
            app.out.set(str(file))
            with patch.object(core, 'WeChatDB', side_effect=AssertionError('No DB access for an invalid path')):
                app.export_btn.invoke()
                self.wait_for_task()
            self.assertIn('保存路径', app.state.get())
            self.assertIn('其他目录', app.state.get())
            self.assertIsNone(app.last_result)
            self.assertEqual(file.read_text(encoding='utf8'), 'keep')
        app.out.set('')
        with patch('ui.main_window.messagebox.showwarning', side_effect=AssertionError('Use inline path feedback')):
            app.export_btn.invoke()
        self.assertFalse(app.busy)
        self.assertIn('保存', app.state.get())

    def test_export_status_does_not_claim_a_percentage_or_zero_of_zero(self):
        from export_task_service import CancelToken
        app = self.app
        app.cancel_token = CancelToken()
        gate = threading.Event()
        app.launch('probe', lambda: gate.wait(2), lambda _: None)
        try:
            for event in [
                {'stage': '连接数据库', 'completed': 0, 'total': 0},
                {'stage': '解析消息', 'completed': 0, 'total': 2, 'current': 100, 'current_total': 500},
                {'stage': '会话完成', 'completed': 1, 'total': 2, 'messages': 500},
            ]:
                app.show_progress(event)
                app.update()
                self.assertEqual(app.progress_text.get(), '导出中…')
                self.assertEqual(app.state.get(), '导出中…')
                self.assertFalse(any(w.winfo_class() == 'TProgressbar' for w in app.task_frame.winfo_children()))
            app.cancel_btn.invoke()
            self.assertTrue(app.cancel_token.cancelled)
        finally:
            gate.set()
            self.wait_for_task()

    def test_flat_record_files_open_in_existing_json_and_text_preview(self):
        import exporter_core as core
        from export_task_service import ExportOptions, export_selected_chats
        from preview import open_export_preview
        from test_selected_export import fixture_db
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = fixture_db(root/'source')
            with patch.object(core, 'WeChatDB', return_value=db):
                result = export_selected_chats(['wxid_a'], ExportOptions(out_root=root/'out'))
            chat = result['chats'][0]
            with patch('preview.messagebox.showwarning', return_value=None):
                view = open_export_preview(self.app, chat['json'])
            self.assertIsNotNone(view)
            try:
                self.assertEqual(view.chat_name, '同名')
                self.assertEqual([m['content'] for m in view.messages], ['合成消息0', '合成消息1'])
                self.assertEqual(view.chat_dir, Path(result['output_dir']))
            finally:
                view.destroy()
            with patch('preview.messagebox.showwarning', return_value=None):
                text_view = open_export_preview(self.app, chat['txt'])
            self.assertIsNotNone(text_view)
            try:
                self.assertIn('合成消息0', text_view.text.get('1.0', 'end'))
            finally:
                text_view.close()

    def test_unrelated_json_is_rejected_without_leaving_an_empty_preview_window(self):
        from preview import open_export_preview
        before = len(self.app.winfo_children())
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp)/'unrelated.json'
            for contents in ('[]', '{"state":"completed"}', '{"messages":["not-a-message"]}'):
                record.write_text(contents, encoding='utf8')
                with patch('preview.messagebox.showerror', return_value=None):
                    view = open_export_preview(self.app, record)
                self.assertIsNone(view)
                self.assertEqual(len(self.app.winfo_children()), before)


if __name__ == '__main__':
    unittest.main()
