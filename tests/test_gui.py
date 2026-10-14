import json
import gc
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._destroy_root)

    def tearDown(self):
        # Tcl objects from earlier test roots must be finalized on the GUI thread,
        # before a later background worker can trigger Python's cyclic GC.
        self.doCleanups()
        self.root = None
        gc.collect()

    def _destroy_root(self):
        try:
            self.root.update_idletasks()
            self.root.destroy()
        except tk.TclError:
            pass

    def test_checkbox_selection_survives_filter_and_refresh(self):
        from ui.chat_list import ChatList
        widget = ChatList(self.root)
        widget.replace([
            {'username': 'a', 'name': '同名', 'nick_name': '小张', 'is_group': False},
            {'username': 'b', 'name': '同名', 'is_group': False},
            {'username': 'g@chatroom', 'name': '工作群', 'is_group': True},
        ])
        widget.model.toggle('a')
        widget.category.set('群聊')
        widget.select_visible()
        widget.query.set('无结果')
        self.assertEqual(widget.tree.get_children(), ())
        self.assertEqual(widget.model.selected, {'a', 'g@chatroom'})
        widget.replace(list(widget.model.chats.values()))
        widget.query.set('')
        widget.category.set('全部')
        self.assertEqual(len(widget.tree.get_children()), 3)
        self.assertEqual(widget.model.selected, {'a', 'g@chatroom'})

    def test_large_json_preview_never_renders_more_than_one_page(self):
        from preview import ChatPreview
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'chat_full_parsed.json'
            p.write_text(json.dumps({'chat_name': '合成会话', 'messages': [
                {'time': '2026-10-14 12:00:00', 'sender': '我', 'is_self': True, 'content': f'第{i}条'}
                for i in range(350)
            ]}), encoding='utf8')
            view = ChatPreview(self.root, p)
            self.addCleanup(lambda: view.destroy() if view.winfo_exists() else None)
            for _ in range(3):
                self.assertLessEqual(len(view.separator_widgets), view.PAGE_SIZE)
                view._load_older()
            self.assertEqual(view.start_index, 0)
            self.assertLessEqual(len(view.separator_widgets), view.PAGE_SIZE)

    def test_text_preview_is_streamed_and_supports_previous_page(self):
        from preview import TextPageReader
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'chat_full_for_llm.txt'
            p.write_text('\n'.join(f'合成行{i}' for i in range(700)), encoding='utf-8-sig')
            reader = TextPageReader(p, page_size=100)
            self.addCleanup(reader.close)
            first = reader.next_page()
            second = reader.next_page()
            self.assertEqual(len(first), 100)
            self.assertEqual(second[0].strip(), '合成行100')
            self.assertEqual(reader.previous_page(), first)
            reader.close()

    def test_worker_never_calls_tk_and_repeated_launch_is_blocked(self):
        from ui.main_window import App
        self._destroy_root()
        app = App(auto_load=False)
        app.withdraw()
        self.addCleanup(lambda: app.destroy() if app.winfo_exists() else None)
        gate = threading.Event()
        main_thread = threading.get_ident()
        callback_threads = []
        def work():
            gate.wait(2)
            return {'ok': True}
        self.assertTrue(app.launch('probe', work, lambda result: callback_threads.append(threading.get_ident())))
        self.assertFalse(app.launch('probe', work, lambda result: None))
        gate.set()
        deadline = time.monotonic() + 3
        while app.busy and time.monotonic() < deadline:
            app.update()
            time.sleep(.01)
        self.assertFalse(app.busy)
        self.assertEqual(callback_threads, [main_thread])

    def test_selection_to_export_result_with_sqlite_fixture(self):
        from ui.main_window import App
        import exporter_core as core
        from test_selected_export import fixture_db
        self._destroy_root()
        app = App(auto_load=False)
        app.withdraw()
        self.addCleanup(lambda: app.destroy() if app.winfo_exists() else None)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = fixture_db(root / 'source')
            (root / 'source/db_storage').mkdir()
            chats, unresolved = core._batch_chat_candidates(db)
            app.list_loaded({'chats': chats, 'unresolved_message_tables': unresolved,
                             'account_dir': db.account_dir, 'sensitive_cache_cleanup': True})
            app.out.set(str(root / 'exports'))
            app.chat_list.model.toggle('wxid_a')
            app.update_buttons()
            with patch.object(core, 'WeChatDB', return_value=db):
                app.start_selected()
                deadline = time.monotonic() + 4
                while app.busy and time.monotonic() < deadline:
                    app.update()
                    time.sleep(.01)
            self.assertIsNotNone(app.last_result)
            self.assertEqual(app.last_result['exported'], 1)
            self.assertTrue(Path(app.last_result['chats'][0]['json']).is_file())
            self.assertEqual(app.loaded_source, db.account_dir)

    def test_minimum_window_keeps_action_buttons_inside_without_overlap(self):
        from ui.main_window import App
        self._destroy_root()
        app = App(auto_load=False)
        self.addCleanup(lambda: app.destroy() if app.winfo_exists() else None)
        app.geometry('980x640')
        app.update()
        controls = [app.export_btn, app.all_btn, app.cancel_btn]
        bounds = [(w.winfo_rootx(), w.winfo_rootx() + w.winfo_width()) for w in controls]
        self.assertLessEqual(bounds[0][1], bounds[1][0])
        self.assertLessEqual(bounds[1][1], bounds[2][0])
        self.assertLessEqual(bounds[2][1], app.winfo_rootx() + app.winfo_width())


if __name__ == '__main__':
    unittest.main()
