"""下载《李大霄投资战略》整理稿 v1.1，按页切成 references/book/pages.md。

整理稿由 @不说 发布在 bushuo-ruilin.github.io，原书版权归原作者和出版社。
本仓库不分发原文：这个脚本在你自己的机器上下载、切分，结果在 .gitignore 里。

用法：
    python fetch_book.py                 # 从发布页下载
    python fetch_book.py --pdf 本地.pdf  # 已有 PDF 时直接切分
依赖：pip install pymupdf
"""

import argparse
import os
import re
import sys
import urllib.request

URL = "https://bushuo-ruilin.github.io/personal-page/my_tools/%E6%9D%8E%E5%A4%A7%E9%9C%84%E6%8A%95%E8%B5%84%E6%88%98%E7%95%A5.pdf"
HERE = os.path.dirname(os.path.abspath(__file__))
BOOK = os.path.join(HERE, "..", "references", "book")
FOOTER = re.compile(r"\d{1,3}|[ivxlc]{1,6}")


def load_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError:
            sys.exit("缺 PyMuPDF：先运行 pip install pymupdf")


def download(dest):
    req = urllib.request.Request(URL, headers={"User-Agent": "li-daxiao-skill/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())


def split(pdf, out):
    doc = load_pymupdf().open(pdf)
    parts = [
        "# 《李大霄投资战略》整理稿 v1.1 原文（按页）\n\n",
        "由 scripts/fetch_book.py 在本机生成，不随仓库分发。每页标题写两个页码："
        "`PDF 第 N 页`（阅读器里看到的）和 `书页 M`（页脚印的，目录用这个）。\n",
    ]
    labeled = 0
    for i, page in enumerate(doc, 1):
        lines = [ln.rstrip() for ln in page.get_text("text").strip().splitlines()]
        foot = ""
        for ln in reversed(lines[-4:]):
            if FOOTER.fullmatch(ln.strip()):
                foot = ln.strip()
                lines.remove(ln)
                break
        labeled += bool(foot)
        head = f"\n## PDF 第 {i} 页" + (f" · 书页 {foot}" if foot else "") + "\n\n"
        parts.append(head + "\n".join(lines).strip() + "\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return len(doc), labeled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="已有的整理稿 PDF 路径；不给就下载")
    a = ap.parse_args()
    os.makedirs(BOOK, exist_ok=True)
    pdf = a.pdf
    if not pdf:
        pdf = os.path.join(BOOK, "ldx.pdf")
        print("下载整理稿 PDF ...")
        download(pdf)
    n, labeled = split(pdf, os.path.join(BOOK, "pages.md"))
    print(f"OK  {n} 页，其中 {labeled} 页带页脚页码 -> references/book/pages.md")


if __name__ == "__main__":
    main()
