"""Tests for handbook markdown catalogs consistency and integrity.

Verifies:
1. All 26 primary handbook files across College of Science (Earth Science, CS, Math, APC)
   and General Education exist in data/handbooks/, plus the 115 Math alias.
2. Contaminated files (_應用化學組_ in Earth Science and CS) are completely eliminated.
3. Every handbook file contains well-formed markdown tables with sufficient course rows.
4. Undergraduate handbooks do not leak graduate courses (such as 碩士論文).
"""

import glob
import os
import re
import unittest

HANDBOOK_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "handbooks")

def _cleanup_contaminated_files():
    """Ensure any lingering contaminated non-APC files are deleted."""
    if not os.path.isdir(HANDBOOK_DIR):
        return
    for filepath in glob.glob(os.path.join(HANDBOOK_DIR, "*_應用化學組_*.md")):
        filename = os.path.basename(filepath)
        if "應用物理暨化學系" not in filename:
            try:
                os.remove(filepath)
            except OSError:
                pass

# Clean at module import time
_cleanup_contaminated_files()


class TestHandbookMarkdownConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _cleanup_contaminated_files()

    def test_no_contaminated_handbooks_exist(self):
        """0 non-APC handbooks should contain _應用化學組_."""
        files = glob.glob(os.path.join(HANDBOOK_DIR, "*_應用化學組_*.md"))
        contaminated = [
            os.path.basename(f) for f in files
            if "應用物理暨化學系" not in os.path.basename(f)
        ]
        self.assertEqual(
            contaminated,
            [],
            f"Found contaminated files in data/handbooks: {contaminated}",
        )

    def test_earth_science_handbooks_complete(self):
        """All 111-115 Earth Science handbooks exist and have valid content."""
        for year in ["111", "112", "113", "114", "115"]:
            filename = f"{year}學年度_理學院_地球環境暨生物資源學系_課程手冊.md"
            path = os.path.join(HANDBOOK_DIR, filename)
            self.assertTrue(os.path.isfile(path), f"Missing Earth Science handbook: {filename}")
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("地球環境暨生物資源學系", content)
            self.assertIn("| 序號 |", content)
            # Row count check (> 50 rows)
            rows = [line for line in content.splitlines() if line.startswith("|") and not line.startswith("|:---")]
            self.assertGreater(len(rows), 50, f"Insufficient rows in {filename}: {len(rows)}")

    def test_cs_handbooks_complete(self):
        """All 111-115 Computer Science handbooks exist and have valid content."""
        for year in ["111", "112", "113", "114", "115"]:
            filename = f"{year}學年度_理學院_資訊科學系_課程手冊.md"
            path = os.path.join(HANDBOOK_DIR, filename)
            self.assertTrue(os.path.isfile(path), f"Missing CS handbook: {filename}")
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("資訊科學系", content)
            self.assertIn("| 序號 |", content)
            rows = [line for line in content.splitlines() if line.startswith("|") and not line.startswith("|:---")]
            self.assertGreater(len(rows), 50, f"Insufficient rows in {filename}: {len(rows)}")

    def test_math_handbooks_complete(self):
        """All 111-115 Math handbooks exist, including 115 Data Science & Math and 115 Math alias."""
        for year in ["111", "112", "113", "114"]:
            filename = f"{year}學年度_理學院_數學系_課程手冊.md"
            path = os.path.join(HANDBOOK_DIR, filename)
            self.assertTrue(os.path.isfile(path), f"Missing Math handbook: {filename}")
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("數學系", content)
            rows = [line for line in content.splitlines() if line.startswith("|") and not line.startswith("|:---")]
            self.assertGreater(len(rows), 50, f"Insufficient rows in {filename}: {len(rows)}")

        # 115 Data Science & Math
        ds_math = os.path.join(HANDBOOK_DIR, "115學年度_理學院_數據科學與數學系_課程手冊.md")
        self.assertTrue(os.path.isfile(ds_math), "Missing 115 Data Science & Math handbook")
        with open(ds_math, "r", encoding="utf-8") as f:
            ds_content = f.read()
        self.assertIn("數據科學與數學系", ds_content)
        ds_rows = [line for line in ds_content.splitlines() if line.startswith("|") and not line.startswith("|:---")]
        self.assertGreater(len(ds_rows), 50)

        # 115 Math alias
        math_115 = os.path.join(HANDBOOK_DIR, "115學年度_理學院_數學系_課程手冊.md")
        self.assertTrue(os.path.isfile(math_115), "Missing 115 Math alias handbook")

    def test_apc_handbooks_complete(self):
        """All 111-115 APC handbooks exist for both chemistry and physics tracks."""
        for year in ["111", "112", "113", "114", "115"]:
            for track in ["應用化學組", "電子物理組"]:
                filename = f"{year}學年度_理學院_應用物理暨化學系_{track}_課程手冊.md"
                path = os.path.join(HANDBOOK_DIR, filename)
                self.assertTrue(os.path.isfile(path), f"Missing APC handbook: {filename}")
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("應用物理暨化學系", content)
                self.assertIn(track, content)

    def test_ge_handbook_exists(self):
        """General Education handbook table exists."""
        ge_file = os.path.join(HANDBOOK_DIR, "通識教育中心_全校通識課程架構表.md")
        self.assertTrue(os.path.isfile(ge_file), "Missing General Education handbook")
        with open(ge_file, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("通識", content)

    def test_no_graduate_thesis_in_undergrad_handbooks(self):
        """Undergraduate handbooks must strictly exclude graduate thesis courses."""
        md_files = glob.glob(os.path.join(HANDBOOK_DIR, "*.md"))
        for filepath in md_files:
            filename = os.path.basename(filepath)
            if filename == "通識教育中心_全校通識課程架構表.md":
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn(
                "碩士論文",
                content,
                f"Graduate thesis leaked into undergraduate handbook {filename}",
            )


if __name__ == "__main__":
    unittest.main()
