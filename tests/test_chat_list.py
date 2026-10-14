import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_export_all import FakeDB, create_contact_db, create_message_db, load_core


class ChatListTests(unittest.TestCase):
    def test_metadata_keeps_remark_and_nickname_without_reading_body(self):
        core = load_core()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_contact_db(root / 'contact.db', [
                ('wxid_a', '小张', '同事'), ('wxid_b', '小李', '同事'),
                ('room@chatroom', '项目群', ''), ('no_chat', '没聊过', ''),
            ])
            create_message_db(root / 'message.db', ['wxid_a', 'wxid_b', 'room@chatroom'], ['a' * 32])
            db = FakeDB(root)
            db.nicks = {'wxid_a': '同事', 'wxid_b': '同事'}
            db.add_db('contact/contact.db', root / 'contact.db')
            db.add_db('message/message_0.db', root / 'message.db', message=True)
            with patch.object(core, 'load_rows', side_effect=AssertionError('Must not read messages')):
                rows, unresolved = core._batch_chat_candidates(db)
            self.assertEqual(unresolved, 1)
            by_id = {r['username']: r for r in rows}
            self.assertEqual(set(by_id), {'wxid_a', 'wxid_b', 'room@chatroom'})
            self.assertEqual(by_id['wxid_a'].get('nick_name'), '小张')
            self.assertEqual(by_id['wxid_a'].get('remark'), '同事')

    def test_search_and_category_keep_selection_by_username(self):
        import chat_list_service as service
        model = service.ChatSelection()
        model.replace([
            {'username': 'a', 'name': '同名', 'nick_name': '小张', 'is_group': False},
            {'username': 'b', 'name': '同名', 'remark': '小李', 'is_group': False},
            {'username': 'r@chatroom', 'name': '项目群', 'is_group': True},
        ])
        model.toggle('a')
        self.assertEqual([c['username'] for c in model.filter('好友', '小李')], ['b'])
        model.select_visible(model.filter('群聊'))
        self.assertEqual(model.selected, {'a', 'r@chatroom'})
        self.assertEqual(len(model.filter('全部', '同名')), 2)
        self.assertEqual(model.filter('全部', '不存在'), [])
        model.replace(list(model.chats.values()) * 2)
        self.assertEqual(len(model.chats), 3)
        self.assertEqual(model.selected, {'a', 'r@chatroom'})
        model.replace([model.chats['a']])
        self.assertEqual(model.selected, {'a'})
        model.clear()
        self.assertEqual(model.selected, set())


if __name__ == '__main__':
    unittest.main()
