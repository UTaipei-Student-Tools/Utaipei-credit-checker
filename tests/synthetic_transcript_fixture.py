"""Privacy-safe transcript PDF fixture for browser acceptance checks."""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz


def build_synthetic_transcript_pdf() -> bytes:
    """Return a synthetic transcript understood by the current PDF parser."""

    document = fitz.open()
    page = document.new_page(width=600, height=800)
    html = """<style>
body { font-size: 10pt; }
table { border-collapse: collapse; table-layout: fixed; width: 310px; }
td { padding: 0; height: 25px; vertical-align: top; }
.c0 { width:150px } .c1 { width:20px } .c2 { width:20px }
.c3 { width:30px } .c4 { width:30px } .c5 { width:25px } .c6 { width:35px }
.meta td { height:15px; width:310px; }
</style>
<table class="meta">
<tr><td>姓名：匿名測試同學</td></tr>
<tr><td>學號：Z999999999</td></tr>
<tr><td>入學年月：114年9月</td></tr>
<tr><td>系所：資訊科學系</td></tr>
</table>
<div style="height:14px">114學年</div>
<table>
<tr><td class="c0">普通物理學(一)</td><td class="c1">必</td><td class="c2">3</td><td class="c3">80</td><td class="c4"></td><td class="c5"></td><td class="c6"></td></tr>
<tr><td class="c0">普通化學(一)</td><td class="c1">必</td><td class="c2">3</td><td class="c3">未</td><td class="c4"></td><td class="c5"></td><td class="c6"></td></tr>
<tr><td class="c0">微積分</td><td class="c1">選</td><td class="c2">3</td><td class="c3">55</td><td class="c4">3</td><td class="c5">80</td><td class="c6"></td></tr>
<tr><td class="c0">資料結構</td><td class="c1">選</td><td class="c2">3</td><td class="c3">P</td><td class="c4"></td><td class="c5"></td><td class="c6"></td></tr>
</table>"""
    try:
        page.insert_htmlbox(fitz.Rect(20, 20, 590, 780), html)
        return document.tobytes()
    finally:
        document.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(build_synthetic_transcript_pdf())


if __name__ == "__main__":
    main()
