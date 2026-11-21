#!/usr/bin/env python3
"""Поиск по аннотированному корпусу и проверка ссылок. Python 3.10+."""

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "knowledge" / "corpus.json"
STOP = set(
    "а без был бы быть вам вас ведь во вот вы где да для до его ее если"
    " есть еще же за зачем и из или им их к как кого когда который кто ли"
    " либо между мне мы на над не него нет но о об они от по под почему"
    " при про с сам свое свой себе со так там те тем то того том ту ты у"
    " уже хотя чем что чтобы это этой этот я в книге книги говорится"
    " сказано учение текст тексте означает".split()
)


def normalize(value):
    return value.casefold().replace("ё", "е")


def terms(value):
    # Короткие основы сближают падежные формы русского слова.
    words = re.findall(r"[a-zа-я]+|\d+", normalize(value))
    return [word[:5] for word in words if word not in STOP and len(word) > 1]


def load():
    with DATA.open(encoding="utf-8") as handle:
        return json.load(handle)


def citation(record, books):
    source = record["source"]
    book = books[source["book"]]
    fields = [book["title"]]
    if "chapter" in source:
        fields.append(f"гл. {source['chapter']}")
    if source.get("locator"):
        fields.append(source["locator"])
    first, last = source["pdf_pages"]
    pages = str(first) if first == last else f"{first}–{last}"
    fields.append(f"PDF с. {pages}")
    if "printed_pages" in source:
        first, last = source["printed_pages"]
        pages = str(first) if first == last else f"{first}–{last}"
        fields.append(f"печ. с. {pages}")
    return ", ".join(fields)


def matching_concepts(query, concepts):
    normalized = normalize(query).strip()
    query_tokens = set(terms(query))
    if not query_tokens:
        return []
    candidates = []
    for concept in concepts:
        scores = []
        for name in [concept["label"], *concept["aliases"]]:
            if normalize(name) == normalized:
                scores.append(10)
                continue
            name_tokens = set(terms(name))
            if name_tokens and name_tokens <= query_tokens:
                scores.append(1 + 2 * len(name_tokens))
        if scores:
            candidates.append((max(scores), concept))
    return sorted(candidates, key=lambda pair: (-pair[0], pair[1]["id"]))


def search(data, query, book=None, limit=6):
    records = [record for record in data["evidence"] if not book or record["source"]["book"] == book]
    query_terms = set(terms(query))
    if not records or not query_terms:
        return []
    concepts = matching_concepts(query, data["concepts"])[:4]
    concept_weight = Counter()
    for weight, concept in concepts:
        for record_id in concept["evidence"]:
            concept_weight[record_id] = max(concept_weight[record_id], 0.5 * weight)
    counts = []
    frequency = Counter()
    for record in records:
        title_count = Counter(terms(record["title"]))
        body_count = Counter(terms(record["summary"]))
        frequency.update(set(title_count) | set(body_count))
        counts.append((title_count, body_count))
    ranked = []
    for record, (title_count, body_count) in zip(records, counts):
        score = 0.0
        for term in query_terms:
            count = 2 * title_count[term] + body_count[term]
            if count:
                weight = math.log(1 + (len(records) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += weight * count / (count + 1)
        score += concept_weight[record["id"]]
        if score > 0:
            if record["kind"] == "navigation":
                score *= 0.72
            ranked.append((round(score, 4), record))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return [
        {**record, "citation": citation(record, data["books"]), "score": score}
        for score, record in ranked[:limit]
    ]


def verify(data):
    books = data["books"]
    errors = []
    evidence = {item["id"]: item for item in data["evidence"]}
    concepts = {item["id"]: item for item in data["concepts"]}
    evidence_ids = set(evidence)
    if len(evidence) != len(data["evidence"]) or len(concepts) != len(data["concepts"]):
        errors.append("В базе есть повторяющиеся идентификаторы.")
    if len(books) != 7 or sum(book["pages"] for book in books.values()) != 377:
        errors.append("Реестр не соответствует семи использованным PDF и 377 страницам.")
    for record in evidence.values():
        source = record["source"]
        book = books.get(source["book"])
        if book is None:
            errors.append(f"{record['id']}: неизвестная книга.")
            continue
        start, end = source["pdf_pages"]
        if not 1 <= start <= end <= book["pages"]:
            errors.append(f"{record['id']}: страницы вне книги.")
        if "chapter" in source and not 1 <= source["chapter"] <= book.get("chapters", 0):
            errors.append(f"{record['id']}: глава вне книги.")
        if "printed_pages" in source:
            offset = book.get("printed_offset")
            if offset is None or source["printed_pages"] != [start + offset, end + offset]:
                errors.append(f"{record['id']}: печатная пагинация не соответствует PDF.")
    for book_id, book in books.items():
        if book.get("chapters"):
            indexed = {
                entry["source"]["chapter"] for entry in evidence.values()
                if entry["kind"] == "navigation" and entry["source"]["book"] == book_id
            }
            if indexed != set(range(1, book["chapters"] + 1)):
                errors.append(f"{book_id}: указатель глав неполный.")
    for item in data["concepts"]:
        if item["category"] not in data["categories"]:
            errors.append(f"{item['id']}: неизвестная категория.")
    for item in [*data["concepts"], *data["relations"], *data["questions"]]:
        if not set(item["evidence"]) <= evidence_ids:
            errors.append(f"Неизвестная ссылка в записи {item.get('id', item.get('question'))}.")
        if not item["evidence"] and item.get("kind") != "вне корпуса":
            errors.append(f"Нет источника в записи {item.get('id')}.")
    for relation in data["relations"]:
        if relation["from"] not in concepts or relation["to"] not in concepts:
            errors.append(f"{relation['id']}: неизвестное понятие в связи.")
    return errors


def concept_view(data, query):
    exact = [item for item in data["concepts"] if normalize(item["id"]) == normalize(query)]
    matches = exact or [item for _, item in matching_concepts(query, data["concepts"])[:8]]
    by_id = {item["id"]: item for item in data["evidence"]}
    return [
        {
            **item,
            "citations": [citation(by_id[key], data["books"]) for key in item["evidence"]],
            "relations": [rel for rel in data["relations"] if item["id"] in (rel["from"], rel["to"])],
        }
        for item in matches
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("search", help="Найти фрагменты по вопросу или ключевым словам")
    find.add_argument("query")
    find.add_argument("--book", choices=["foundations", "appeals", "proclamation", "commandments", "prayer", "hope", "turn"])
    find.add_argument("--limit", type=int, choices=range(1, 26), metavar="1–25", default=6)
    concept = commands.add_parser("concept", help="Найти понятие и его связи")
    concept.add_argument("query")
    for command in (find, concept):
        command.add_argument("--json", action="store_true", help="Машиночитаемый ответ")
    commands.add_parser("verify", help="Проверить структуру, ссылки и границы страниц")
    args = parser.parse_args()
    data = load()
    if args.command == "verify":
        errors = verify(data)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print(f"Проверено: {len(data['books'])} источников, {len(data['evidence'])} записей, "
              f"{len(data['concepts'])} понятий, {len(data['relations'])} связей.")
        return 0
    if args.command == "concept":
        records = concept_view(data, args.query)
    else:
        records = search(data, args.query, args.book, args.limit)
    if args.json:
        print(json.dumps({"status": "candidates" if records else "no_match", "results": records},
                         ensure_ascii=False, indent=2))
    elif not records:
        print("В указателе не найдено достаточно совпадений для этого запроса.")
    else:
        for row in records:
            if args.command == "concept":
                print(f"[{row['id']}] {row['label']}\n{row['definition']}")
                print("\n".join(row["citations"]), end="\n\n")
            else:
                print(f"[{row['id']}] {row['title']}\n{row['citation']}\n{row['summary']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
