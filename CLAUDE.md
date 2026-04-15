# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Converts PDF tax documents (primarily Solium/Shareworks Morgan Stanley stock plan 1099-B statements) into TXF files for import into TurboTax Desktop on Windows. Also supports generic 1099-B, 1099-INT, and 1099-DIV forms.

See README.md for usage and commands. No test suite, linter, or formatter is configured.

## Architecture

**Data flow:** PDF → `pdfplumber` text extraction → parser → `TaxRecord` → CSV (`pdf2txf.py`) → TXF (`csv2txf.py`)

Direct PDF→TXF conversion was tried originally and did not work. The working path goes through CSV as an intermediate.

**Parser chain** (`pdf2txf.py:parse_pdf`): Parsers are tried most-specific-first. The first parser that detects its format wins for 1099-B data. 1099-INT/DIV parsing runs independently and can add records alongside 1099-B records.

1. `SoliumParser` — Solium/Shareworks format with 6-decimal quantity fields
2. `Form1099BParser` — Generic 1099-B with trade line patterns
3. `Form1099IntDivParser` — Interest and dividend income (regex-based, runs alongside others)
4. `GenericAmountParser` — Fallback that captures labeled dollar amounts with `txf_code=0` (skipped in output, shown with `--show-all`)

**Core data type:** `TaxRecord` dataclass in `parsers.py` — all parsers produce these, `csv_writer.py` consumes them.

**TXF code mapping:** Parsers emit Form 8949 codes (711/713/715/717). `csv2txf.py` maps these to classic Schedule D codes (321/323) for TurboTax compatibility (format D). It also supports alternative format variations (A/B/C) for testing when one format doesn't import correctly.

**TXF output requirements:** Files must use CRLF line endings and ASCII encoding. The `$` line order is cost basis first, proceeds second. Records are delimited by `^`.
