#!/usr/bin/env python3
"""Bridge multilingual questions to the Russian source index. Python 3.10+."""

import json
import re
import sys
from pathlib import Path

from corpus import load, search


def process(request):
    if not isinstance(request, dict):
        raise ValueError("Expected a JSON object.")
    question = request.get("query")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("query must be a nonempty string in the user's language.")
    language = request.get("answer_language", "same as query")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("answer_language must be a nonempty string.")
    queries = request.get("search_queries_ru")
    if queries is None and re.search(r"[А-Яа-яЁё]", question):
        queries = [question]
    if not isinstance(queries, list) or not 1 <= len(queries) <= 5 or any(
        not isinstance(q, str) or not re.search(r"[А-Яа-яЁё]", q) for q in queries
    ):
        raise ValueError("Provide 1–5 Russian search_queries_ru; translate the question before retrieval.")
    book = request.get("book")
    allowed = {"foundations", "appeals", "proclamation", "commandments", "prayer", "hope", "turn"}
    if book is not None and book not in allowed:
        raise ValueError("book must be one of the seven corpus book IDs.")
    limit = request.get("limit", 6)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 25:
        raise ValueError("limit must be an integer from 1 through 25.")
    data = load()
    found = {}
    for query in queries:
        # Every search runs against the unchanged Russian annotations.
        for hit in search(data, query, book=book, limit=limit):
            previous = found.get(hit["id"])
            if previous is None or hit["score"] > previous["score"]:
                found[hit["id"]] = hit
    ranked = sorted(found.values(), key=lambda hit: (-hit["score"], hit["id"]))[:limit]
    bundled_pdf_dir = Path(__file__).resolve().parents[1] / "texts" / "ru"
    pdf_dir = request.get("pdf_dir", str(bundled_pdf_dir) if bundled_pdf_dir.is_dir() else None)
    if pdf_dir is not None and (not isinstance(pdf_dir, str) or not pdf_dir.strip()):
        raise ValueError("pdf_dir must be a directory path when provided.")
    original_results = []
    if pdf_dir:
        from pdf_original_search import search_originals
        preferred = {}
        for rank, hit in enumerate(ranked):
            if hit["kind"] == "paraphrase":
                ref = hit["source"]
                for page in range(ref["pdf_pages"][0], ref["pdf_pages"][1] + 1):
                    key = (ref["book"], page)
                    preferred[key] = max(preferred.get(key, 0), 4 / (1 + rank))
        original_results = search_originals(data, queries, pdf_dir, limit=limit,
                                             book_filter=book, preferred_pages=preferred)
    return {
        "status": "candidates" if ranked or original_results else "no_match",
        "query": question,
        "answer_language": language,
        "search_queries_ru": queries,
        "search_corpus_language": "ru",
        "translation_performed_by_tool": False,
        "search_scope": "russian_original_pdf_and_index" if pdf_dir else "russian_editorial_index_only",
        "original_text_verified": False,
        "results": ranked,
        "original_results": original_results,
        "instruction": (
            "Read Russian index summaries and original PDF pages when available; verify exact quotations visually. "
            "Answer in answer_language, attribute claims to books, retain evidence IDs and source page numbers. "
            "State inferred connections as comparisons; say when the corpus has no supported answer."
        ),
    }


def main():
    try:
        request = json.load(sys.stdin)
        print(json.dumps(process(request), ensure_ascii=False, indent=2))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid_request", "error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
