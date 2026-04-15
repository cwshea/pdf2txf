#!/usr/bin/env python3
"""TXF file decoder and validator.

Parses a TXF file, validates its structure, and prints a human-readable
summary of the records. Reports any format errors that would cause
tax software to reject the file.

Usage:
  python3 txf_decoder.py output.txf
"""

import argparse
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TxfHeader:
    version: str = ""
    account_name: str = ""
    date: str = ""


@dataclass
class TxfRecord:
    record_type: str = ""       # "TD" (detail) or "TS" (summary)
    txf_code: int = 0           # N line
    copy: str = ""              # C line
    line: str = ""              # L line
    payer: str = ""             # P line
    dates: list[str] = field(default_factory=list)   # D lines
    amounts: list[float] = field(default_factory=list)  # $ lines
    line_number: int = 0        # line in file where record starts


TXF_CODE_NAMES = {
    1: ("W-2", "Wages"),
    2: ("W-2", "Federal tax withheld"),
    321: ("Schedule D", "Short-term capital gain/loss"),
    323: ("Schedule D", "Long-term capital gain/loss"),
    488: ("1099-DIV", "Ordinary dividends"),
    489: ("1099-DIV", "Qualified dividends"),
    491: ("1099-DIV", "Capital gain distributions"),
    547: ("1099-MISC", "Rents / Nonemployee compensation"),
    548: ("1099-MISC", "Royalties"),
    553: ("1099-MISC", "Other income"),
    711: ("1099-B", "Short-term, covered"),
    713: ("1099-B", "Short-term, noncovered"),
    715: ("1099-B", "Long-term, covered"),
    717: ("1099-B", "Long-term, noncovered"),
}

# Codes that represent capital gains transactions (have proceeds + cost basis)
CAPITAL_GAIN_CODES = {321, 323, 711, 713, 715, 717}

VALID_RECORD_TYPES = {"TD", "TS"}
VALID_LINE_TAGS = {"V", "A", "D", "N", "C", "L", "P", "$", "^", "T"}


def parse_txf(filepath: str) -> tuple[TxfHeader, list[TxfRecord], list[str]]:
    """Parse a TXF file and return header, records, and validation errors."""
    header = TxfHeader()
    records = []
    errors = []

    with open(filepath, "rb") as f:
        raw = f.read()
    has_crlf = b"\r\n" in raw
    lines = raw.decode("ascii", errors="replace").splitlines(True)

    if not lines:
        errors.append("ERROR: File is empty")
        return header, records, errors

    # Check for BOM
    if lines[0].startswith("\ufeff"):
        errors.append("WARNING: File contains BOM (byte order mark) — may cause issues")
        lines[0] = lines[0].lstrip("\ufeff")

    # Check line endings
    if has_crlf:
        line_ending = "CRLF (Windows)"
    elif b"\r" in raw:
        line_ending = "CR (old Mac)"
        errors.append("ERROR: File uses CR line endings — TurboTax expects CRLF")
    else:
        line_ending = "LF (Unix)"
        errors.append("WARNING: File uses LF line endings — TurboTax Desktop may require CRLF")

    # Strip line endings
    lines = [l.rstrip("\r\n") for l in lines]

    # Parse header (lines before first record separator ^)
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == "^":
            i += 1
            break
        if line.startswith("V"):
            header.version = line[1:]
            if header.version != "042":
                errors.append(f"WARNING line {i+1}: Version is '{header.version}', expected '042'")
        elif line.startswith("A"):
            header.account_name = line[1:]
        elif line.startswith("D"):
            header.date = line[1:].strip()
        else:
            errors.append(f"WARNING line {i+1}: Unexpected header line: '{line}'")
        i += 1
    else:
        errors.append("ERROR: No record separator (^) found after header")
        return header, records, errors

    if not header.version:
        errors.append("ERROR: Missing version line (V042) in header")

    # Parse records
    current_record = None
    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if line == "^":
            if current_record:
                _validate_record(current_record, errors)
                records.append(current_record)
                current_record = None
            else:
                errors.append(f"WARNING line {i+1}: Record separator (^) without a preceding record")
            i += 1
            continue

        # Start of a new record (TD or TS line)
        if line in VALID_RECORD_TYPES:
            if current_record:
                errors.append(f"ERROR line {i+1}: New record started before previous record "
                              f"was closed with ^ (started at line {current_record.line_number})")
                _validate_record(current_record, errors)
                records.append(current_record)
            current_record = TxfRecord(record_type=line, line_number=i + 1)
            i += 1
            continue

        # Check for common mistakes: TT, SS, T, S instead of TD, TS
        if line in ("TT", "SS", "T", "S", "TI", "SI"):
            if current_record:
                errors.append(f"ERROR line {i+1}: New record started before previous record "
                              f"was closed with ^")
                _validate_record(current_record, errors)
                records.append(current_record)
            errors.append(f"ERROR line {i+1}: Invalid record type '{line}'. "
                          f"Must be 'TD' (transaction detail) or 'TS' (transaction summary). "
                          f"TurboTax will silently skip records with invalid type codes.")
            current_record = TxfRecord(record_type=line, line_number=i + 1)
            i += 1
            continue

        if current_record is None:
            tag = line[0] if line else ""
            if tag in VALID_LINE_TAGS:
                errors.append(f"ERROR line {i+1}: Line '{line}' appears outside of a record "
                              f"(missing TD/TS record start)")
            else:
                errors.append(f"WARNING line {i+1}: Unrecognized line: '{line}'")
            i += 1
            continue

        # Parse record fields
        tag = line[0]
        value = line[1:].strip() if len(line) > 1 else ""

        if tag == "N":
            try:
                current_record.txf_code = int(value)
            except ValueError:
                errors.append(f"ERROR line {i+1}: Invalid TXF code: '{value}' (must be integer)")
        elif tag == "C":
            current_record.copy = value
        elif tag == "L":
            current_record.line = value
        elif tag == "P":
            current_record.payer = value
        elif tag == "D":
            current_record.dates.append(value)
        elif tag == "$":
            try:
                current_record.amounts.append(float(value))
            except ValueError:
                errors.append(f"ERROR line {i+1}: Invalid amount: '{value}'")
        else:
            errors.append(f"WARNING line {i+1}: Unrecognized tag '{tag}' in record "
                          f"starting at line {current_record.line_number}")

        i += 1

    # Handle unclosed final record
    if current_record:
        errors.append(f"ERROR: File ends without closing record separator (^) "
                      f"for record starting at line {current_record.line_number}")
        _validate_record(current_record, errors)
        records.append(current_record)

    return header, records, errors


def _validate_record(record: TxfRecord, errors: list[str]) -> None:
    """Validate a single TXF record and append errors."""
    ln = record.line_number

    if record.record_type not in VALID_RECORD_TYPES:
        # Already reported above
        pass

    if record.txf_code == 0:
        errors.append(f"ERROR line {ln}: Record missing TXF code (N line)")

    if record.txf_code in TXF_CODE_NAMES:
        form, desc = TXF_CODE_NAMES[record.txf_code]
    else:
        errors.append(f"WARNING line {ln}: Unknown TXF code {record.txf_code}")

    if not record.amounts:
        errors.append(f"ERROR line {ln}: Record has no dollar amounts ($ lines)")

    # 1099-B transaction records should have 2 dates and 2 amounts
    if record.txf_code in CAPITAL_GAIN_CODES:
        if record.record_type == "TD":
            if len(record.dates) < 2:
                errors.append(f"WARNING line {ln}: 1099-B transaction record should have "
                              f"2 dates (acquired, sold), found {len(record.dates)}")
            if len(record.amounts) < 2:
                errors.append(f"WARNING line {ln}: 1099-B transaction record should have "
                              f"2 amounts (proceeds, cost basis), found {len(record.amounts)}")

    # Validate dates
    for d in record.dates:
        if not _is_valid_date(d):
            errors.append(f"ERROR line {ln}: Invalid date format '{d}' (expected MM/DD/YYYY)")


def _is_valid_date(date_str: str) -> bool:
    """Check if a date string is valid MM/DD/YYYY."""
    import re
    return bool(re.match(r"\d{2}/\d{2}/\d{4}$", date_str))


def print_report(header: TxfHeader, records: list[TxfRecord], errors: list[str]) -> None:
    """Print a human-readable report of the TXF file."""
    print("=" * 70)
    print("TXF FILE VALIDATION REPORT")
    print("=" * 70)

    # Header
    print(f"\nHeader:")
    print(f"  Version:  {header.version or '(missing)'}")
    print(f"  Account:  {header.account_name or '(none)'}")
    print(f"  Date:     {header.date or '(none)'}")

    # Errors summary
    err_count = sum(1 for e in errors if e.startswith("ERROR"))
    warn_count = sum(1 for e in errors if e.startswith("WARNING"))

    print(f"\nValidation: {err_count} error(s), {warn_count} warning(s)")
    if errors:
        print("-" * 70)
        for e in errors:
            print(f"  {e}")

    # Records
    print(f"\nRecords: {len(records)} total")
    print("-" * 70)

    total_proceeds = 0.0
    total_basis = 0.0

    for i, rec in enumerate(records, 1):
        code_info = TXF_CODE_NAMES.get(rec.txf_code, ("Unknown", "Unknown"))
        type_ok = "OK" if rec.record_type in VALID_RECORD_TYPES else "BAD"

        print(f"\n  Record #{i} (line {rec.line_number}):")
        print(f"    Type:     {rec.record_type} [{type_ok}]")
        print(f"    Code:     N{rec.txf_code} — {code_info[0]}: {code_info[1]}")
        if rec.payer:
            print(f"    Payer:    {rec.payer}")
        if rec.dates:
            labels = ["Acquired", "Sold"] if len(rec.dates) >= 2 else ["Date"]
            for j, d in enumerate(rec.dates):
                label = labels[j] if j < len(labels) else f"Date {j+1}"
                print(f"    {label}:  {d}")
        if rec.amounts:
            if rec.txf_code in CAPITAL_GAIN_CODES and len(rec.amounts) >= 2:
                # TXF field order: $1 = cost basis, $2 = proceeds
                print(f"    Basis:    ${rec.amounts[0]:,.2f}")
                print(f"    Proceeds: ${rec.amounts[1]:,.2f}")
                gain = rec.amounts[1] - rec.amounts[0]
                print(f"    Gain/Loss: ${gain:,.2f}")
                total_basis += rec.amounts[0]
                total_proceeds += rec.amounts[1]
            else:
                for j, amt in enumerate(rec.amounts):
                    print(f"    Amount {j+1}: ${amt:,.2f}")

    # Totals
    if total_proceeds or total_basis:
        print(f"\n{'=' * 70}")
        print(f"TOTALS:")
        print(f"  Total proceeds:   ${total_proceeds:,.2f}")
        print(f"  Total cost basis: ${total_basis:,.2f}")
        print(f"  Net gain/loss:    ${total_proceeds - total_basis:,.2f}")

    # Final verdict
    print(f"\n{'=' * 70}")
    if err_count > 0:
        print("RESULT: INVALID — TurboTax will likely reject or silently skip records.")
        print("Fix the errors above and re-generate the TXF file.")
    else:
        print("RESULT: VALID — file should import into TurboTax / TaxAct.")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Decode and validate a TXF file")
    parser.add_argument("input", help="TXF file to decode")
    args = parser.parse_args()

    try:
        header, records, errors = parse_txf(args.input)
    except FileNotFoundError:
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    print_report(header, records, errors)
    sys.exit(1 if any(e.startswith("ERROR") for e in errors) else 0)


if __name__ == "__main__":
    main()
