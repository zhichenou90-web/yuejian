"""离线入库脚本：python scripts/ingest_book.py <txt路径>"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.ingest_service import ingest_novel_file


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scripts/ingest_book.py <小说.txt路径>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"文件不存在: {path}")
        sys.exit(1)
    result = ingest_novel_file(path)
    print(result)


if __name__ == "__main__":
    main()
