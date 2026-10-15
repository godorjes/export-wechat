"""User-visible account, selection, and export-setting interactions."""
import gc
import json
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch


class AccountFoldedTests(unittest.TestCase):
    def setUp(self):
        from ui.main_window import App
        self.app = App(auto_load=False)
        self.app.geometry('1160x780+10+10')
        self.app.update()

    def tearDown(self):
        self.app.destroy()
        self.app = None
        gc.collect()

    def wait_for_task(self):
        deadline = time.monotonic() + 5
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy)

    def toggle_format(self, fmt):
        control = self.app.format_combo
        if control.popup is None:
            control.invoke()
            self.app.update()
        index = ('txt', 'md', 'json').index(fmt)
        control.popup_canvas.event_generate('<ButtonRelease-1>', x=30, y=6+index*40+20)
        self.app.update()

    def test_settings_are_visible_before_export_and_after_selecting_chat(self):
        app = self.app
        self.assertTrue(app.settings_canvas.winfo_ismapped())
        app.list_loaded({'chats': [{'username': 'a', 'name': '合成聊天', 'is_group': False}],
                         'account_dir': 'E:/synthetic', 'sensitive_cache_cleanup': True})
        app.update()
        app.chat_list.canvas.event_generate('<Button-1>', x=28, y=35)
        for geometry in ('1160x780', '980x640', '1160x780'):
            app.geometry(geometry+'+10+10')
            app.update()
            self.assertEqual(app.chat_list.model.selected, {'a'})
            self.assertTrue(app.settings_canvas.winfo_ismapped(), 'Settings canvas disappeared with the scrollbar')
            field = app.content_combo
            self.assertTrue(field.winfo_viewable())
            self.assertGreater(field.winfo_width(), 100)
            self.assertGreaterEqual(field.winfo_rooty(), app.settings_canvas.winfo_rooty())
            self.assertLessEqual(field.winfo_rooty()+field.winfo_height(),
                                 app.settings_canvas.winfo_rooty()+app.settings_canvas.winfo_height())
            self.assertFalse(app.busy)

    def test_tab_keeps_save_path_action_inside_settings_viewport(self):
        app = self.app
        app.geometry('980x640')
        app.chat_list.replace([{'username': 'a', 'name': '合成聊天', 'is_group': False}])
        app.source_ready = True
        app.update_buttons()
        app.update()
        self.assertTrue(app.format_combo.winfo_viewable())
        app.format_combo.focus_force()
        app.update()
        for _ in range(30):
            focused = app.focus_get()
            if focused == app.browse_output_btn.button:
                break
            self.assertIsNotNone(focused)
            focused.event_generate('<Tab>')
            app.update()
        self.assertEqual(app.focus_get(), app.browse_output_btn.button)
        self.assertGreaterEqual(app.browse_output_btn.winfo_rooty(), app.settings_canvas.winfo_rooty())
        self.assertLessEqual(app.browse_output_btn.winfo_rooty()+app.browse_output_btn.winfo_height(),
                             app.settings_canvas.winfo_rooty()+app.settings_canvas.winfo_height())

    def test_format_dropdown_drives_real_multi_format_export(self):
        import exporter_core as core
        from test_selected_export import fixture_db
        app = self.app
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = fixture_db(root / 'source')
            (root / 'source/db_storage').mkdir()
            chats, unresolved = core._batch_chat_candidates(db)
            app.list_loaded({'chats': chats, 'unresolved_message_tables': unresolved,
                             'account_dir': db.account_dir, 'sensitive_cache_cleanup': True})
            self.assertTrue(app.format_combo.winfo_viewable())
            self.toggle_format('txt')
            self.toggle_format('md')
            self.toggle_format('json')
            app.format_combo.close_popup()
            app.content_combo.set('文字、图片和普通文件')
            app.content_combo.event_generate('<<ComboboxSelected>>')
            app.out.set(str(root / 'custom output'))
            options = app.get_export_options()
            self.assertEqual(options.formats, ('json', 'md'))
            self.assertTrue(options.export_images)
            self.assertTrue(options.export_files)
            self.assertEqual(app.path_entry.get(), str(root / 'custom output'))
            app.chat_list.model.toggle('wxid_a')
            app.update_buttons()
            with patch.object(core, 'WeChatDB', return_value=db):
                app.export_btn.invoke()
                self.wait_for_task()
            result = app.last_result
            self.assertEqual(result['exported'], 1)
            self.assertEqual(result['formats'], ['json', 'md'])
            self.assertIsNone(result['chats'][0]['txt'])
            self.assertTrue(Path(result['chats'][0]['md']).is_file())
            data = json.loads(Path(result['chats'][0]['json']).read_text(encoding='utf-8-sig'))
            self.assertEqual(len(data['messages']), 2)
            app.update()
            actions = [w.cget('text') for w in app.result_buttons.winfo_children()
                       if w.winfo_viewable()]
            self.assertEqual(actions, ['打开文件夹'])
            self.toggle_format('md')
            self.toggle_format('json')
            self.assertEqual(app.export_btn.cget('state'), 'disabled')
            self.assertIn('至少选择', app.format_help.get())
            self.toggle_format('txt')
            self.assertEqual(app.get_export_options().formats, ('txt',))
            self.assertEqual(app.export_btn.cget('state'), 'normal')

    def test_busy_task_locks_sources_settings_and_row_selection(self):
        app = self.app
        app.chat_list.replace([{'username': 'a', 'name': '测试', 'is_group': False}])
        gate = threading.Event()
        self.assertTrue(app.launch('probe', lambda: gate.wait(2), lambda _: None))
        try:
            self.assertEqual(str(app.account_btn.cget('state')), 'disabled')
            self.assertEqual(app.format_combo.cget('state'), 'disabled')
            app.format_combo.invoke()
            self.assertIsNone(app.format_combo.popup)
            self.assertFalse(app.format_vars['json'].get())
            self.assertEqual(str(app.content_combo.cget('state')), 'disabled')
            self.assertEqual(str(app.chat_list.select_all_btn.cget('state')), 'disabled')
            app.chat_list.canvas.event_generate('<Button-1>', x=28, y=35)
            self.assertEqual(app.chat_list.model.selected, set())
        finally:
            gate.set()
            self.wait_for_task()
        self.assertEqual(app.format_combo.cget('state'), 'readonly')
        self.assertEqual(str(app.account_btn.cget('state')), 'normal')

    def test_canvas_list_toggles_visible_selection_and_handles_large_lists(self):
        widget = self.app.chat_list
        widget.replace([{'username': str(i), 'name': '同名' if i < 2 else f'聊天{i}',
                         'is_group': i % 2 == 0} for i in range(5000)])
        self.app.update()
        widget.canvas.event_generate('<Button-1>', x=28, y=35)
        self.assertEqual(widget.model.selected, {'0'})
        widget.category.set('好友')
        widget.select_all_btn.invoke()
        self.assertEqual(len(widget.model.selected), 2501)
        widget.select_all_btn.invoke()
        self.assertEqual(widget.model.selected, {'0'})
        widget.query.set('没有结果')
        self.assertEqual(widget.visible, [])
        widget.query.set('')
        widget.category.set('全部')
        widget.canvas.yview_moveto(1)
        self.app.update()
        self.assertLess(len(widget.canvas.find_all()), 250)
        self.assertEqual(widget.model.selected, {'0'})
        widget.canvas.focus_force()
        widget.canvas.event_generate('<End>')
        widget.canvas.event_generate('<space>')
        self.app.update()
        self.assertEqual(widget.model.selected, {'0', '4999'})

    def test_minimum_size_keeps_primary_action_and_save_path_reachable(self):
        app = self.app
        app.geometry('980x640')
        app.update()
        for geometry in ('1160x780', '980x640', '1160x780'):
            app.geometry(geometry)
            app.update()
            button = app.export_btn
            self.assertTrue(button.winfo_ismapped())
            self.assertGreaterEqual(button.winfo_rootx(), app.winfo_rootx())
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), app.winfo_rootx() + app.winfo_width())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), app.winfo_rooty() + app.winfo_height())
        app.settings_canvas.yview_moveto(1)
        app.update()
        self.assertTrue(app.browse_output_btn.winfo_ismapped())
        self.assertGreaterEqual(app.browse_output_btn.winfo_rooty(), app.settings_canvas.winfo_rooty())
        self.assertLessEqual(app.browse_output_btn.winfo_rooty() + app.browse_output_btn.winfo_height(), app.settings_canvas.winfo_rooty() + app.settings_canvas.winfo_height())


if __name__ == '__main__':
    unittest.main()
