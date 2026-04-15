"""Write TaxRecords to CSV format compatible with EasyTXF and TurboTax."""

import csv
import io
from parsers import TaxRecord

# TXF code to Form 8949 box mapping
CODE_TO_BOX = {
    711: "A",  # Short-term, basis reported to IRS
    713: "B",  # Short-term, basis NOT reported to IRS
    715: "D",  # Long-term, basis reported to IRS
    717: "E",  # Long-term, basis NOT reported to IRS
}

# EasyTXF-compatible column headers
CSV_HEADERS = [
    "Description",
    "Date Acquired",
    "Date Sold",
    "Sales Proceeds",
    "Cost Basis",
    "Gain/Loss",
    "Wash Sale Loss",
    "8949 Box",
    "Federal Tax Withheld",
]


def write_csv(records: list[TaxRecord], output_path: str) -> None:
    """Write tax records to a CSV file."""
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for rec in records:
            if rec.txf_code == 0:
                continue
            _write_row(writer, rec)


def records_to_csv_string(records: list[TaxRecord]) -> str:
    """Return CSV content as a string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADERS)
    for rec in records:
        if rec.txf_code == 0:
            continue
        _write_row(writer, rec)
    return buf.getvalue()


def _write_row(writer: csv.writer, rec: TaxRecord) -> None:
    box = CODE_TO_BOX.get(rec.txf_code, "")
    proceeds = rec.amount
    basis = rec.cost_basis or 0.0
    gain_loss = proceeds - basis

    writer.writerow([
        rec.security_name or rec.payer_name,
        rec.date_acquired or "",
        rec.date_sold or "",
        f"{proceeds:.2f}",
        f"{basis:.2f}",
        f"{gain_loss:.2f}",
        "0.00",
        box,
        "0.00",
    ])
