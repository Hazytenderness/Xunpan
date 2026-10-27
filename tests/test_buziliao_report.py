import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BuziliaoReportTests(unittest.TestCase):
    def test_daily_has_two_new_lines(self):
        out = subprocess.run([sys.executable, str(ROOT / 'tools/补资料/日报.py'), 'daily'],
                             capture_output=True, text=True, encoding='utf-8', stdin=subprocess.DEVNULL, timeout=60).stdout
        self.assertRegex(out, r'(?m)^能发的家：待发 \d+ 家；卡住：没有可问的家 \d+、被占或没旺旺名 \d+、已在问 \d+$')
        m = re.search(r'(?m)^同款确认累计：问到 (\d+) 家，完全匹配 (\d+)、不匹配 (\d+)$', out)
        self.assertIsNotNone(m)
        tot = ok = no = 0
        for line in (ROOT / 'batches/补资料/quotes.jsonl').read_text(encoding='utf-8').splitlines():
            v = (json.loads(line).get('匹配确认') or {}).get('值') if line.strip() else None
            if v:
                tot += 1
                ok += v == '完全匹配'
                no += v == '不匹配'
        self.assertEqual(tuple(map(int, m.groups())), (tot, ok, no))

    def test_batch_json_not_rewritten_when_summary_same(self):
        src = (ROOT / 'tools/补资料/建队列.py').read_text(encoding='utf-8')
        self.assertIn("old.get('本次') != summary", src)


if __name__ == '__main__':
    unittest.main()
