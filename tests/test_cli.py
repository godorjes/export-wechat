import subprocess
import sys
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'cli.py'), *args],
                              capture_output=True, encoding='utf8', errors='replace')

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


if __name__ == '__main__':
    unittest.main()
