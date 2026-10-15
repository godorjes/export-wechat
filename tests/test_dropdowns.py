import gc
import time
import tkinter as tk
import unittest


class DropdownTests(unittest.TestCase):
    def setUp(self):
        from ui.main_window import App
        self.app = App(auto_load=False)
        self.app.geometry('1160x780+10+10')
        self.app.update()

    def tearDown(self):
        self.app.destroy()
        self.app = None
        gc.collect()

    def choose_row(self, control, index):
        canvas = control.popup_canvas
        canvas.event_generate('<ButtonRelease-1>', x=30, y=control.row_height*index+control.row_height//2+6)
        self.app.update()

    def test_format_dropdown_keeps_multiple_choices_until_dismissed(self):
        app = self.app
        control = getattr(app, 'format_combo', None)
        self.assertIsNotNone(control, 'Formats must be inside one dropdown field')
        self.assertIsInstance(control, tk.Canvas)
        control.invoke()
        app.update()
        self.assertTrue(control.popup.winfo_viewable())
        self.choose_row(control, 1)
        self.choose_row(control, 2)
        self.assertTrue(control.popup.winfo_viewable(), 'Multi-select must remain open after choosing a row')
        self.assertEqual(app.get_export_options().formats, ('json', 'md', 'txt'))
        control.popup_canvas.event_generate('<Escape>')
        app.update()
        self.assertIsNone(control.popup)
        self.assertEqual(control.get(), 'TXT、Markdown、JSON')
        control.invoke()
        app.update()
        for index in (0, 1, 2):
            self.choose_row(control, index)
        self.assertEqual(app.export_btn.cget('state'), 'disabled')
        self.assertIn('至少选择', app.format_help.get())

    def test_single_dropdowns_apply_filter_and_export_content(self):
        app = self.app
        app.list_loaded({'chats': [{'username': 'friend', 'name': '好友', 'is_group': False},
                                 {'username': 'group@chatroom', 'name': '群聊', 'is_group': True}],
                         'account_dir': 'E:/synthetic', 'sensitive_cache_cleanup': True})
        for control in (app.chat_list.category_combo, app.content_combo):
            self.assertIsInstance(control, tk.Canvas, 'All dropdowns must share the new field and popup style')
            self.assertEqual(control.winfo_height(), 42)
        category = app.chat_list.category_combo
        category.invoke()
        app.update()
        self.choose_row(category, 2)
        self.assertIsNone(category.popup)
        self.assertEqual([c['username'] for c in app.chat_list.visible], ['group@chatroom'])
        content = app.content_combo
        content.invoke()
        app.update()
        self.choose_row(content, 2)
        self.assertIsNone(content.popup)
        self.assertTrue(app.get_export_options().export_images)
        self.assertTrue(app.get_export_options().export_files)

    def test_dropdown_keyboard_dismissal_and_disabled_state(self):
        control = self.app.content_combo
        self.assertIsInstance(control, tk.Canvas)
        control.focus_force()
        self.app.update()
        control.event_generate('<Down>')
        self.app.update()
        canvas = control.popup_canvas
        canvas.event_generate('<Down>')
        canvas.event_generate('<Return>')
        self.app.update()
        self.assertTrue(self.app.get_export_options().export_images)
        self.assertFalse(self.app.get_export_options().export_files)
        control.invoke()
        self.app.update()
        control.configure(state='disabled')
        self.assertIsNone(control.popup)
        control.invoke()
        self.assertIsNone(control.popup)
        control.configure(state='readonly')
        control.invoke()
        self.app.update()
        control.popup.event_generate('<ButtonRelease-1>', x=-10, y=-10)
        self.app.update()
        self.assertIsNone(control.popup)

    def test_app_has_no_task_details_window_or_entry(self):
        app = self.app
        self.assertFalse(any(isinstance(w, tk.Toplevel) for w in app.winfo_children()))
        def walk(widget):
            for child in widget.winfo_children():
                yield child
                yield from walk(child)
        labels = [str(w.cget('text')) for w in walk(app) if 'text' in w.keys()]
        self.assertFalse(any('任务详情' in text for text in labels))

    def test_popup_keyboard_returns_focus_and_tabs_between_fields(self):
        formats, content = self.app.format_combo, self.app.content_combo
        cases = [(formats, 'Return', formats), (formats, 'Escape', formats),
                 (formats, 'Tab', content), (content, 'Shift-Tab', formats),
                 (content, 'Return', content)]
        for control, key, expected in cases:
            with self.subTest(key=key, multi=control == formats):
                control.focus_force()
                self.app.update()
                control.invoke()
                self.app.update()
                control.popup_canvas.event_generate('<'+key+'>')
                self.app.update()
                self.assertIsNone(control.popup)
                self.assertEqual(self.app.focus_get(), expected)

    def test_worker_export_error_is_visible_without_details_window(self):
        def fail():
            raise RuntimeError('PRIVATE ERROR BODY')
        self.app.launch('export', fail, lambda _: None)
        deadline = time.monotonic()+3
        while self.app.busy and time.monotonic() < deadline:
            self.app.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy)
        self.assertIn('RuntimeError', self.app.state.get())
        self.assertNotIn('PRIVATE ERROR BODY', self.app.state.get())

    def test_popup_position_keeps_secondary_monitors_and_work_area_edges(self):
        import ui.dropdown as dropdown
        position = getattr(dropdown, 'popup_position', None)
        self.assertIsNotNone(position, 'Use the field monitor work area, including negative coordinates')
        cases = [
            ((-800, 180, 310, 42), (310, 132), (-1920, 0, 0, 1040), (-800, 227)),
            ((-200, 950, 310, 42), (310, 132), (-1920, 0, 0, 1040), (-310, 813)),
            ((3700, 980, 200, 42), (310, 172), (1920, 0, 3840, 1040), (3530, 803)),
            ((400, -300, 310, 42), (310, 132), (0, -1080, 1920, 0), (400, -253)),
        ]
        for anchor, menu, work_area, expected in cases:
            with self.subTest(anchor=anchor):
                self.assertEqual(position(anchor, menu, work_area), expected)


if __name__ == '__main__':
    unittest.main()
