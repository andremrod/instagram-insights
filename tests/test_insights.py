"""python3 -m unittest discover -s ~/.claude/skills/instagram-insights/tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S = ROOT / "scripts"
FIX = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(S))
from common import parse_date, parse_duration, parse_number, spearman  # noqa: E402


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], check=True, capture_output=True, text=True).stdout


def fake_posts(n=12):
    posts = []
    for i in range(n):
        views = [150, 140, 1600, 130, 8, 145, 900, 135, 160, 125, 10, 150][i % 12]
        posts.append({"id": f"p{i}", "caption": ("Imagine " if i % 2 else "Em 1940, ") + f"post fictício {i}. #Historia #SegundaGuerraMundial",
                      "published_at": f"2026-11-{1 + i:02d}T{10 + (i % 3)}:00" if i % 4 else f"2026-11-{1 + i:02d}T10:03",
                      "type": "reel", "views": views, "reach": int(views * .85), "likes": views // 25, "comments": 0,
                      "shares": 1 if views > 500 else 0, "saves": views // 200, "follows": views // 300,
                      "watch_time_s": views * 25, "avg_watch_s": 30 if views > 500 else 24, "duration_s": 85 + i})
    return posts


class Parsing(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(parse_number("1.127"), 1127)
        self.assertEqual(parse_number("7,3 mil"), 7300)
        self.assertEqual(parse_number("1,500"), 1500)
        self.assertEqual(parse_number("0,5"), 0.5)
        self.assertIsNone(parse_number("‑‑"))

    def test_durations(self):
        self.assertEqual(parse_duration("1 h 16 min"), 4560)
        self.assertEqual(parse_duration("56 min 58 s"), 3418)
        self.assertEqual(parse_duration("8 h"), 28800)
        self.assertEqual(parse_duration("0:26"), 26)

    def test_dates(self):
        ref = datetime(2026, 11, 10)
        self.assertEqual(parse_date("Segunda, 9 de novembro 10:49", ref), datetime(2026, 11, 9, 10, 49))
        self.assertEqual(parse_date("Sábado, 31 de dezembro 10:00", ref).year, 2025)  # sem ano e no futuro → ano anterior
        self.assertEqual(parse_date("11/09/2026 10:49", ref, dayfirst=False), datetime(2026, 11, 9, 10, 49))

    def test_spearman(self):
        self.assertEqual(spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0)
        self.assertIsNone(spearman([1, 2], [1, 2]))


class Pipeline(unittest.TestCase):
    def test_page_text(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "posts.json"
            run(S / "collect_parse.py", "--in", FIX / "page_text.txt", "--collected-at", "2026-11-10T12:00", "--out", out)
            posts = json.loads(out.read_text())["posts"]
            self.assertEqual(len(posts), 2)
            p = max(posts, key=lambda p: p["views"])
            self.assertEqual(p["views"], 1172)
            self.assertEqual(p["follows"], 4)
            self.assertEqual(p["avg_watch_s"], 31)
            self.assertEqual(p["watch_time_s"], 6 * 3600 + 60)
            self.assertTrue(p["caption"].startswith("Imagine um exemplo"))
            self.assertIsNone(min(posts, key=lambda p: p["views"])["follows"])

    def test_csv(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "posts.json"
            run(S / "collect_parse.py", "--in", FIX / "export.csv", "--monthfirst", "--out", out)
            posts = json.loads(out.read_text())["posts"]
            self.assertEqual([p["views"] for p in posts], [120, 1500])
            self.assertEqual(posts[1]["duration_s"], 60)
            self.assertEqual(posts[1]["id"], "AAA111")
            self.assertEqual(posts[1]["published_at"], "2026-11-09T10:49")

    def test_tags_analyze_render(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "posts.json").write_text(json.dumps({"account": "exemplo", "posts": fake_posts()}))
            run(S / "tag_posts.py", "--posts", d / "posts.json", "--out", d / "tags.json")
            tags = json.loads((d / "tags.json").read_text())["tags"]
            self.assertEqual({t["hook_type"] for t in tags}, {"Imagine (você na cena)", "Contexto/data"})
            self.assertTrue(all(t["theme"] == "Segunda Guerra Mundial" for t in tags))
            run(S / "analyze.py", "--posts", d / "posts.json", "--tags", d / "tags.json", "--out", d / "analysis.json")
            an = json.loads((d / "analysis.json").read_text())
            s = an["summary"]
            self.assertEqual(s["posts"], 12)
            self.assertEqual(s["hits"], 2)
            self.assertEqual(s["flops"], 2)
            self.assertIn("theme", an["dimensions"])
            self.assertTrue(any(f["id"] == "retention" for f in an["findings"]))
            # flops ficam fora da comparação por tema
            self.assertEqual(an["dimensions"]["theme"][0]["n"], 10)
            run(S / "render_report.py", "--analysis", d / "analysis.json", "--out", d / "report.html")
            html = (d / "report.html").read_text()
            self.assertTrue(html.startswith("<title>"))
            self.assertIn("<svg", html)
            self.assertNotIn("<body", html)

    def test_previous_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            posts = fake_posts()
            (d / "p1.json").write_text(json.dumps({"posts": posts[:10]}))
            (d / "p2.json").write_text(json.dumps({"posts": posts}))
            run(S / "tag_posts.py", "--posts", d / "p2.json", "--out", d / "tags.json")
            run(S / "analyze.py", "--posts", d / "p1.json", "--tags", d / "tags.json", "--out", d / "a1.json")
            run(S / "analyze.py", "--posts", d / "p2.json", "--tags", d / "tags.json", "--previous", d / "a1.json", "--out", d / "a2.json")
            prev = json.loads((d / "a2.json").read_text())["previous"]
            self.assertEqual(len(prev["new_posts"]), 2)


if __name__ == "__main__":
    unittest.main()
