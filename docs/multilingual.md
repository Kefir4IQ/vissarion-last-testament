# Universal language adapter

This adapter lets an English-language or other-language agent answer from the **Russian** edition that underlies the [seven-book corpus](sources.md). The agent translates the question into Russian retrieval queries; the Python program searches Russian index entries **and, when the original files are supplied, the Russian PDFs themselves**, returning page hits and short snippets. The agent then writes the answer in the user's language. Paste [AGENTS.universal.md](../AGENTS.universal.md) as a self-contained system/developer instruction, or use [AGENTS.multilingual.md](../AGENTS.multilingual.md) as an extension of [AGENTS.md](../AGENTS.md).

## Pipeline

| Stage | Input | Output | Responsible component |
| --- | --- | --- | --- |
| Understand | Question in any language | Question meaning and ambiguous terms | Multilingual agent |
| Bridge | Meaning and key terms | 1–5 Russian queries | Multilingual agent or configured translation model |
| Retrieve | Russian queries and bundled PDFs in `texts/ru` | Russian source cards, original PDF page hits, E IDs | `tools/multilingual_adapter.py` |
| Verify | Candidate cards | Relevant Russian paragraphs in the specified PDF, when exact wording matters | Agent with access to original PDF |
| Answer | Verified supported meanings | Reply in the user's requested language, preserving source coordinates | Multilingual agent |

The Python tool has no built-in translator or external service dependency. It will **reject a non-Russian query that has not been bridged**; this prevents an English keyword search from silently returning accidental matches. It does not by itself translate or verify quotations. A universal language workflow requires a multilingual model or a separately configured translation component at the first and last stages.

## Tool contract

Call from the repository root with a UTF-8 JSON object on standard input. `query` is the original question; `search_queries_ru` is an array of 1–5 Russian formulations; `answer_language` is a free-text language name or code. The program automatically opens the seven original files from `texts/ru`. Optional `pdf_dir` points to another directory containing all seven files named in [sources.md](sources.md); `book` and `limit` are optional. The program uses PyMuPDF for source PDF reading (`python3 -m pip install pymupdf` if needed). Russian questions can omit `search_queries_ru`, in which case the original question is used. Results have `status: candidates | no_match`, the Russian formulations actually used, indexed `results` and page-level `original_results`. `search_scope` shows whether the originals were searched. `translation_performed_by_tool` and `original_text_verified` remain `false` because PDF text extraction alone cannot verify exact quotations.

```sh
python3 tools/multilingual_adapter.py <<'JSON'
{"query":"What is the soul and why does it need a body?","answer_language":"en","search_queries_ru":["Что такое душа и зачем ей плоть?","Душа плоть подвижный разум","Воплощение души и деяния плоти"],"limit":6}
JSON
```

For a question in Spanish, use the same contract and answer in Spanish:

```json
{"query":"¿Qué significa el nacimiento desde arriba?","answer_language":"es","search_queries_ru":["Что означает рождение Свыше?","Рождение души созидательная потребность"],"limit":5}
```

The output includes Russian card titles and summaries, canonical Russian book names, matching original PDF pages and stable page numbers. The original PDF files are stored in `texts/ru`; extracted page text is read at runtime and is not stored a second time. Two originals contain extracted characters in a Latin-1 form; the tool decodes these back into Russian before searching. Its scores rank **candidates**, not truth. The agent must select the passages that actually support the question. If the translation introduced two senses, search for both and say which the Russian passage uses. When the result is `no_match`, rephrase in Russian within the original scope or report the limit; do not answer from a remembered but unlocated passage.

## Terms that need special care

| Non-Russian search idea | Search in the original | Note |
| --- | --- | --- |
| soul | `душа`, `рождение души`, `Божия искра` | Check whether the passage discusses the soul or the whole human being. |
| spirit | `Дух Жизни`, `Святой Дух`, `дух зла` | These are distinct uses; retain the Russian name in the answer. |
| God, Father | `Единый`, `Отец Небесный`, `Бог-Сын` | Do not collapse the book's different referents into one term. |
| destiny, calling | `вынужденная судьба`, `предначертание`, `самородок` | Read [the corresponding source passages](books/foundations.md) before equating them. |
| commandments, prayer | `Заповеди`, `Молитва`, `пункт 12 утро`, `пункт 12 вечер` | Specify the morning or evening variant of prayer point 12. |

The JSON index consists of editorial summaries and chapter locators. Original full PDFs are identified in [sources.md](sources.md); giving the agent access to the matching Russian PDF enables exact quotation. Machine translation of a quotation should be marked as a translation, while the Russian original and its location stay available for checking.
