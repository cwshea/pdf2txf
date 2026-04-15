#!/usr/bin/env python3
"""PDF to CSV tax data extractor.

Extracts tax-related data from PDF financial documents and outputs CSV.
Use csv2txf.py to convert the CSV to TXF for import into tax software.

Supported forms:
  - 1099-B  (Brokerage proceeds, capital gains/losses)
  - 1099-INT (Interest income)
  - 1099-DIV (Dividend income)
  - Generic labeled dollar amounts (exported with code 0 for manual review)

Usage:
  python pdf2txf.py input.pdf [-o output.csv] [--verbose] [--payer NAME]
"""

import argparse
import sys

import pdfplumber

from parsers import (
    Form1099BParser,
    Form1099IntDivParser,
    GenericAmountParser,
    SoliumParser,
    TaxRecord,
)
from csv_writer import write_csv, records_to_csv_string


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF file."""
    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)

            # Also try extracting from tables
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row:
                        row_text = "\t".join(cell or "" for cell in row)
                        pages_text.append(row_text)

    return "\n".join(pages_text)


def parse_pdf(pdf_path: str, payer_name: str = "", verbose: bool = False) -> list[TaxRecord]:
    """Parse a PDF and return extracted tax records."""
    text = extract_text_from_pdf(pdf_path)

    if verbose:
        print("=" * 60)
        print("EXTRACTED TEXT:")
        print("=" * 60)
        print(text[:3000])
        if len(text) > 3000:
            print(f"... ({len(text) - 3000} more characters)")
        print("=" * 60)

    records: list[TaxRecord] = []

    # Try specific parsers first (most specific to least specific)
    if SoliumParser.detect(text):
        if verbose:
            print("Detected Solium/Shareworks (Morgan Stanley) stock plan format")
        records.extend(SoliumParser.parse(text))

    if not records and Form1099BParser.detect(text):
        if verbose:
            print("Detected 1099-B content")
        records.extend(Form1099BParser.parse(text))

    if Form1099IntDivParser.detect(text):
        if verbose:
            print("Detected 1099-INT/DIV content")
        records.extend(Form1099IntDivParser.parse(text, payer_name))

    # If no specific records found, try generic extraction
    if not records:
        if verbose:
            print("No specific forms detected, using generic parser")
        records.extend(GenericAmountParser.parse(text))

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF financial documents to TXF (Tax Exchange Format)"
    )
    parser.add_argument("input", help="Input PDF file path")
    parser.add_argument("-o", "--output", help="Output TXF file path (default: stdout)")
    parser.add_argument("--payer", default="", help="Payer/institution name")
    parser.add_argument("--format", "-f", choices=["csv"], default="csv",
                        help="Output format (default: csv)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show extracted text and parsing details")
    parser.add_argument("--show-all", action="store_true",
                        help="Also show unmatched generic records (TXF code 0)")

    args = parser.parse_args()

    try:
        records = parse_pdf(args.input, payer_name=args.payer, verbose=args.verbose)
    except FileNotFoundError:
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading PDF: {e}", file=sys.stderr)
        sys.exit(1)

    valid_records = [r for r in records if r.txf_code != 0]
    skipped_records = [r for r in records if r.txf_code == 0]

    if args.verbose or args.show_all:
        print(f"\nFound {len(valid_records)} valid TXF records")
        if skipped_records:
            print(f"Skipped {len(skipped_records)} unmatched records:")
            for r in skipped_records:
                print(f"  - {r.description}: ${r.amount:.2f}")
        print()

    if not valid_records:
        print("Warning: No recognized tax records found in the PDF.", file=sys.stderr)
        print("The PDF may use a format not yet supported by this converter.", file=sys.stderr)
        print("Use --verbose to see extracted text for debugging.", file=sys.stderr)
        if skipped_records:
            print(f"\n{len(skipped_records)} dollar amounts were found but couldn't be "
                  "mapped to TXF codes. Use --show-all to see them.", file=sys.stderr)
        sys.exit(0)

    if args.output:
        write_csv(valid_records, args.output)
        print(f"Wrote {len(valid_records)} records to {args.output}")
    else:
        print(records_to_csv_string(valid_records), end="")


if __name__ == "__main__":
    main()
