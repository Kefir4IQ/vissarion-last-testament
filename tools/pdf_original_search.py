"""Page-level search over the user's Russian source PDFs; no source text is stored."""

import math
import re
from collections import Counter
from pathlib import Path


def normalize(text):
    return text.casefold().replace("ё", "е")


def repair_mojibake(text):
    # Two supplied PDFs contain Cyrillic bytes interpreted as Latin-1 glyphs.
    def replace(match):
        try:
            return match.group().encode("latin-1").decode("cp1251")
        except UnicodeError:
            return match.group()
    return re.sub(r"[\u0080-\u00ff]+", replace, text)


def extract_pages(data, pdf_dir):
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("Original PDF search needs PyMuPDF (python -m pip install pymupdf).") from exc
    directory = Path(pdf_dir)
    if not directory.is_dir():
        raise ValueError("pdf_dir must point to a directory with the seven original Russian PDFs.")
    pages = []
    for book_id, book in data["books"].items():
        path = directory / book["file"]
        if not path.is_file():
            raise ValueError(f"Missing original PDF: {book['file']}")
        try:
            with fitz.open(path) as document:
                if len(document) != book["pages"]:
                    raise ValueError(f"Unexpected page count in {book['file']}")
                for number, page in enumerate(document, 1):
                    raw = repair_mojibake(page.get_text())
                    raw = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", raw)
                    raw = re.sub(r"\s+", " ", raw).strip()
                    pages.append((book_id, number, raw))
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Could not read {book['file']}: {exc}") from exc
    return pages


def search_originals(data, queries, pdf_dir, limit=6, book_filter=None, preferred_pages=None):
    pages = extract_pages(data, pdf_dir)
    if book_filter:
        pages = [p for p in pages if p[0] == book_filter]
    # Use the same short Russian stems as the existing source index.
    from corpus import terms
    query_terms = set().union(*(terms(q) for q in queries))
    query_terms = {term for term in query_terms if re.search(r"[а-я]", term)}
    if not query_terms:
        return []
    frequency = Counter()
    counts = []
    for _, _, content in pages:
        count = Counter(terms(content))
        counts.append(count)
        frequency.update(set(count) & query_terms)
    result = []
    for (book_id, number, content), count in zip(pages, counts):
        matched = query_terms & count.keys()
        if not matched:
            continue
        score = sum(math.log(1 + (len(pages) - frequency[t] + .5) / (frequency[t] + .5))
                    * min(count[t], 5) / (min(count[t], 5) + 1) for t in matched)
        score *= len(matched) / len(query_terms)
        score += (preferred_pages or {}).get((book_id, number), 0)
        lower = normalize(content)
        positions = [m.start() for t in matched for m in [re.search(r"(?<![а-я])" + re.escape(t), lower)] if m]
        at = min(positions, default=0)
        snippet = content[max(0, at - 30):at + 110].strip()
        book = data["books"][book_id]
        citation = f"{book['title']}, PDF с. {number}"
        if book.get("printed_offset") is not None and number >= book.get("printed_from_pdf_page", 1):
            citation += f", печ. с. {number + book['printed_offset']}"
        result.append({"book": book_id, "pdf_page": number, "citation_ru": citation,
                       "matched_stems": sorted(matched), "snippet_ru": snippet, "score": round(score, 4)})
    return sorted(result, key=lambda row: (-row["score"], row["book"], row["pdf_page"]))[:limit]
