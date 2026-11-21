#!/usr/bin/env python3
"""Verify the seven bundled PDF originals against the recorded manifest."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "texts" / "ru"


def main():
    manifest = json.loads((FOLDER / "manifest.json").read_text(encoding="utf-8"))
    corpus = json.loads((ROOT / "knowledge" / "corpus.json").read_text(encoding="utf-8"))
    if set(manifest) != set(corpus["books"]) or len(manifest) != 7:
        print("The PDF manifest does not match the seven-book corpus.", file=sys.stderr)
        return 1
    for book_id, entry in manifest.items():
        book = corpus["books"][book_id]
        if entry["file"] != book["file"] or entry["pdf_pages"] != book["pages"]:
            print(f"Metadata mismatch: {book_id}", file=sys.stderr)
            return 1
        path = FOLDER / entry["file"]
        if not path.is_file() or not path.read_bytes().startswith(b"%PDF"):
            print(f"Missing or invalid PDF: {path}", file=sys.stderr)
            return 1
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"] or path.stat().st_size != entry["size_bytes"]:
            print(f"PDF mismatch: {path.name}", file=sys.stderr)
            return 1
    print("Verified: seven original PDFs match the repository manifest and index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
