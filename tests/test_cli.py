import subprocess
import os
import sys
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'cli.py'), *args],
                              capture_output=True, encoding='utf8', errors='replace',
                              env={**os.environ, **(env or {})})

    def test_list_and_selected_usage_is_documented(self):
        result = self.run_cli('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--username', result.stdout)
        self.assertIn('--list-chats', result.stdout)
        self.assertIn('--format', result.stdout)

    def test_selected_and_all_are_mutually_exclusive_before_db_access(self):
        result = self.run_cli('--username', 'a', '--all')
        self.assertEqual(result.returncode, 2)
        self.assertIn('不能同时', result.stderr)

    def test_chinese_cli_errors_are_utf8_even_with_ascii_redirected_streams(self):
        result = self.run_cli('--username', 'a', '--all', env={'PYTHONIOENCODING': 'ascii:backslashreplace'})
        self.assertEqual(result.returncode, 2)
        self.assertIn('不能同时', result.stderr)
        self.assertNotIn('\\u4e0d', result.stderr)


if __name__ == '__main__':
    unittest.main()
