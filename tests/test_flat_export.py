from datetime import datetime
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import exporter_core as core
import export_task_service as service
from test_selected_export import fixture_db


class FlatExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = fixture_db(self.root/'source')

    def export(self, usernames, formats=('txt',)):
        with patch.object(core, 'WeChatDB', return_value=self.db), patch.object(service, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 15, 12, 30)
            return service.export_selected_chats(usernames, service.ExportOptions(out_root=self.root/'out', formats=formats))

    def test_chats_are_directly_in_dated_folder_without_summary_files(self):
        result = self.export(['wxid_a', 'room@chatroom'])
        folder = Path(result['output_dir'])
        self.assertEqual(folder.name, '2026-10-15WeChatExport')
        self.assertEqual({p.name for p in folder.iterdir()}, {'同名.txt', '讨论群.txt'})
        self.assertEqual(result['exported'], 2)
        for chat in result['chats']:
            self.assertEqual(Path(chat['txt']).parent, folder)
            self.assertEqual(Path(chat['output_dir']), folder)

    def test_same_names_and_repeated_exports_preserve_earlier_files(self):
        first = self.export(['wxid_a', 'wxid_b'], ('txt', 'json'))
        before = {Path(c['txt']): Path(c['txt']).read_bytes() for c in first['chats']}
        self.assertEqual({Path(c['txt']).name for c in first['chats']}, {'同名.txt', '同名 (2).txt'})
        again = self.export(['wxid_a'])
        self.assertEqual(first['output_dir'], again['output_dir'])
        self.assertEqual(Path(again['chats'][0]['txt']).name, '同名 (3).txt')
        for p, data in before.items():
            self.assertEqual(p.read_bytes(), data)

    def test_failed_publication_rolls_back_new_files_and_continues_other_chats(self):
        original = Path.rename
        def rename(source, target):
            if source.name == '同名.md':
                raise PermissionError('PRIVATE BODY')
            return original(source, target)
        with patch.object(Path, 'rename', rename):
            result = self.export(['wxid_a', 'room@chatroom'], ('txt', 'md', 'json'))
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['exported'], 1)
        self.assertEqual({p.name for p in Path(result['output_dir']).iterdir()},
                         {'讨论群.txt', '讨论群.md', '讨论群.json'})
        self.assertNotIn('PRIVATE BODY', json.dumps(result, ensure_ascii=False))

    def test_selecting_the_dated_folder_does_not_create_another_date_layer(self):
        folder = self.root/'2026-10-15WeChatExport'
        with patch.object(core, 'WeChatDB', return_value=self.db), patch.object(service, 'datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 15, 12, 30)
            result = service.export_selected_chats(['wxid_a'], service.ExportOptions(out_root=folder, formats=('txt',)))
        # Windows TEMP may use an 8.3 alias that resolve() expands.
        # Compare the actual directory, while the file listing still catches nesting.
        self.assertTrue(Path(result['output_dir']).samefile(folder))
        self.assertEqual({p.name for p in folder.iterdir()}, {'同名.txt'})

    def test_publish_never_replaces_an_existing_file(self):
        staged = self.root/'staged'
        final = self.root/'final'
        staged.mkdir()
        final.mkdir()
        (staged/'same.txt').write_text('new', encoding='utf8')
        (final/'same.txt').write_text('old', encoding='utf8')
        with self.assertRaises(FileExistsError):
            service._publish_flat(staged, final, {'txt': str(staged/'same.txt')}, service.CancelToken())
        self.assertEqual((final/'same.txt').read_text(encoding='utf8'), 'old')
        self.assertEqual((staged/'same.txt').read_text(encoding='utf8'), 'new')

    def test_rollback_failure_reports_exact_incomplete_files_without_hiding_success(self):
        original = Path.rename
        def rename(source, target):
            if source.name == '同名.md' or (source.name == '同名.json' and source.parent.name == '2026-10-15WeChatExport'):
                raise PermissionError('PRIVATE BODY')
            return original(source, target)
        with patch.object(Path, 'rename', rename):
            result = self.export(['wxid_a', 'room@chatroom'], ('txt', 'md', 'json'))
        self.assertEqual(result['failed'], 1)
        self.assertEqual(result['exported'], 1)
        self.assertTrue(result['partial_cleanup_error'])
        self.assertEqual(result['chats'][0]['partial_files'], [str(Path(result['output_dir'])/'同名.json')])
        self.assertTrue(Path(result['chats'][1]['txt']).is_file())
        self.assertNotIn('PRIVATE BODY', json.dumps(result, ensure_ascii=False))

    def test_two_processes_export_to_one_dated_folder_with_numbered_names(self):
        script = self.root/'parallel_export.py'
        script.write_text('''import json
from datetime import datetime
from pathlib import Path
import sys
import time
from unittest.mock import patch
repo, root, label = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path[:0] = [str(repo), str(repo/'tests')]
import exporter_core as core
import export_task_service as service
from test_selected_export import fixture_db
db = fixture_db(root/label)
def connect(**kwargs):
    (root/(label+'.ready')).write_text('ready')
    deadline = time.monotonic()+15
    while not (root/'release').exists():
        if time.monotonic()>deadline:
            raise RuntimeError('Test gate timed out')
        time.sleep(.01)
    return db
with patch.object(core, 'WeChatDB', side_effect=connect), patch.object(core, '_persistent_app_data_dir', return_value=root/'cache'), patch.object(service, 'datetime') as clock:
    clock.now.return_value = datetime(2026,10,15,12,30)
    result = service.export_selected_chats(['wxid_a'], service.ExportOptions(out_root=root/'out', formats=('txt',)))
(root/(label+'.json')).write_text(json.dumps(result, ensure_ascii=False), encoding='utf8')
''', encoding='utf8')
        processes = [subprocess.Popen([sys.executable, str(script), str(Path(__file__).resolve().parents[1]), str(self.root), label],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for label in ('one', 'two')]
        try:
            deadline = time.monotonic()+15
            while not all((self.root/(label+'.ready')).exists() for label in ('one', 'two')):
                if time.monotonic()>deadline or any(p.poll() is not None for p in processes):
                    self.fail('Parallel export did not reach both controlled DB constructors')
                time.sleep(.01)
            (self.root/'release').write_text('go')
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, stderr.decode('utf8', errors='replace'))
            results = [json.loads((self.root/(label+'.json')).read_text(encoding='utf8')) for label in ('one', 'two')]
            self.assertEqual([r['exported'] for r in results], [1, 1])
            self.assertEqual([r['failed'] for r in results], [0, 0])
            self.assertEqual({p.name for p in (self.root/'out/2026-10-15WeChatExport').iterdir()},
                             {'同名.txt', '同名 (2).txt'})
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate()


if __name__ == '__main__':
    unittest.main()
