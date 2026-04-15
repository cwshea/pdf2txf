"""Parsers for extracting tax data from PDF text."""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaxRecord:
    """A single tax record extracted from a PDF."""
    txf_code: int
    description: str
    amount: float
    date_acquired: Optional[str] = None   # MM/DD/YYYY
    date_sold: Optional[str] = None       # MM/DD/YYYY
    cost_basis: Optional[float] = None
    payer_name: str = ""
    security_name: str = ""
    form_type: str = ""


def parse_amount(text: str) -> Optional[float]:
    """Parse a dollar amount from text, handling parens for negatives."""
    text = text.strip().replace(",", "").replace("$", "")
    if not text or text == "-":
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    try:
        val = float(text)
        return -val if negative else val
    except ValueError:
        return None


def parse_date(text: str) -> Optional[str]:
    """Normalize a date string to MM/DD/YYYY."""
    text = text.strip()
    # MM/DD/YYYY or MM-DD-YYYY
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if m:
        month, day, year = m.groups()
        if len(year) == 2:
            year = "20" + year if int(year) < 50 else "19" + year
        return f"{int(month):02d}/{int(day):02d}/{year}"
    return None


class Form1099BParser:
    """Parse 1099-B brokerage statement data."""

    # Pattern: security name, date acquired, date sold, proceeds, cost basis, gain/loss
    TRADE_PATTERN = re.compile(
        r"(?P<security>.+?)\s+"
        r"(?P<date_acq>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+"
        r"(?P<date_sold>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+"
        r"(?P<proceeds>[\d,]+\.\d{2})\s+"
        r"(?P<basis>[\d,]+\.\d{2})\s+"
        r"(?P<gain_loss>[\-\(]?[\d,]+\.\d{2}\)?)",
        re.IGNORECASE,
    )

    # Simpler pattern: security, proceeds, cost, gain/loss
    SIMPLE_PATTERN = re.compile(
        r"(?P<security>.+?)\s+"
        r"\$?(?P<proceeds>[\d,]+\.\d{2})\s+"
        r"\$?(?P<basis>[\d,]+\.\d{2})\s+"
        r"\$?(?P<gain_loss>[\-\(]?[\d,]+\.\d{2}\)?)",
    )

    @staticmethod
    def detect(text: str) -> bool:
        indicators = ["1099-B", "1099-b", "Proceeds From Broker", "proceeds from broker",
                       "Short-Term", "Long-Term", "Capital Gains", "Capital gain"]
        return any(ind.lower() in text.lower() for ind in indicators)

    @classmethod
    def parse(cls, text: str) -> list[TaxRecord]:
        records = []
        is_long_term = False
        for line in text.split("\n"):
            line_lower = line.lower().strip()
            if "long-term" in line_lower or "long term" in line_lower:
                is_long_term = True
            elif "short-term" in line_lower or "short term" in line_lower:
                is_long_term = False

            # Try detailed pattern first
            m = cls.TRADE_PATTERN.search(line)
            if m:
                gain_loss = parse_amount(m.group("gain_loss"))
                if gain_loss is None:
                    continue
                txf_code = 715 if is_long_term else 711  # covered by default
                records.append(TaxRecord(
                    txf_code=txf_code,
                    description="Long-term capital gain" if is_long_term else "Short-term capital gain",
                    amount=parse_amount(m.group("proceeds")) or 0.0,
                    date_acquired=parse_date(m.group("date_acq")),
                    date_sold=parse_date(m.group("date_sold")),
                    cost_basis=parse_amount(m.group("basis")),
                    security_name=m.group("security").strip(),
                    form_type="1099-B",
                ))
                continue

            # Try simpler pattern
            m = cls.SIMPLE_PATTERN.search(line)
            if m:
                gain_loss = parse_amount(m.group("gain_loss"))
                if gain_loss is None:
                    continue
                txf_code = 715 if is_long_term else 711
                records.append(TaxRecord(
                    txf_code=txf_code,
                    description="Long-term capital gain" if is_long_term else "Short-term capital gain",
                    amount=parse_amount(m.group("proceeds")) or 0.0,
                    cost_basis=parse_amount(m.group("basis")),
                    security_name=m.group("security").strip(),
                    form_type="1099-B",
                ))
        return records


class Form1099IntDivParser:
    """Parse 1099-INT and 1099-DIV data."""

    PATTERNS = {
        # 1099-INT patterns
        r"(?:interest\s+income|taxable\s+interest)\s*[\$:]?\s*\$?([\d,]+\.\d{2})": (321, "Interest income", "1099-INT"),
        # 1099-DIV patterns
        r"(?:ordinary\s+dividends?|total\s+ordinary\s+dividends?)\s*[\$:]?\s*\$?([\d,]+\.\d{2})": (488, "Ordinary dividends", "1099-DIV"),
        r"(?:qualified\s+dividends?)\s*[\$:]?\s*\$?([\d,]+\.\d{2})": (489, "Qualified dividends", "1099-DIV"),
        r"(?:capital\s+gain\s+dist(?:ribution)?s?)\s*[\$:]?\s*\$?([\d,]+\.\d{2})": (491, "Capital gain distributions", "1099-DIV"),
    }

    @staticmethod
    def detect(text: str) -> bool:
        indicators = ["1099-INT", "1099-DIV", "Interest Income", "Ordinary Dividends",
                       "Qualified Dividends", "interest income", "ordinary dividends"]
        return any(ind.lower() in text.lower() for ind in indicators)

    @classmethod
    def parse(cls, text: str, payer_name: str = "") -> list[TaxRecord]:
        records = []
        for pattern, (code, desc, form) in cls.PATTERNS.items():
            for m in re.finditer(pattern, text, re.IGNORECASE):
                amount = parse_amount(m.group(1))
                if amount is not None and amount > 0:
                    records.append(TaxRecord(
                        txf_code=code,
                        description=desc,
                        amount=amount,
                        payer_name=payer_name,
                        form_type=form,
                    ))
        return records


class SoliumParser:
    """Parse Solium/Shareworks (Morgan Stanley) stock plan 1099-B statements."""

    # Pattern: SecurityName  Quantity  DateAcq  DateSold  $Proceeds  $CostBasis
    # e.g.: Verily 43.000000 11/25/23 12/29/25 $946.00 $4,490.92
    TRADE_PATTERN = re.compile(
        r"(?P<security>[A-Za-z][\w\s\-\.]*?)\s+"
        r"(?P<qty>\d+\.\d{6})\s+"
        r"(?P<date_acq>\d{1,2}/\d{1,2}/\d{2,4})\s+"
        r"(?P<date_sold>\d{1,2}/\d{1,2}/\d{2,4})\s+"
        r"\$(?P<proceeds>[\d,]+\.\d{2})\s+"
        r"\$(?P<basis>[\d,]+\.\d{2})"
    )

    @staticmethod
    def detect(text: str) -> bool:
        indicators = ["shareworks", "solium", "stock plan account",
                       "morgan stanley capital management"]
        text_lower = text.lower()
        return any(ind in text_lower for ind in indicators)

    @classmethod
    def parse(cls, text: str) -> list[TaxRecord]:
        records = []
        # Track covered vs noncovered and short vs long term from section headers
        is_long_term = False
        is_noncovered = False

        for line in text.split("\n"):
            line_lower = line.lower().strip()

            # Detect section headers
            if "long term" in line_lower or "long-term" in line_lower:
                is_long_term = True
            elif "short term" in line_lower or "short-term" in line_lower:
                is_long_term = False

            if "noncovered" in line_lower or "non-covered" in line_lower:
                is_noncovered = True
            elif "covered" in line_lower and "noncovered" not in line_lower and "non-covered" not in line_lower:
                is_noncovered = False

            # Skip total/summary lines
            if line_lower.startswith("total"):
                continue

            m = cls.TRADE_PATTERN.search(line)
            if m:
                proceeds = parse_amount(m.group("proceeds"))
                basis = parse_amount(m.group("basis"))
                if proceeds is None:
                    continue

                if is_long_term:
                    txf_code = 717 if is_noncovered else 715
                else:
                    txf_code = 713 if is_noncovered else 711

                term = "Long-term" if is_long_term else "Short-term"
                coverage = "noncovered" if is_noncovered else "covered"

                records.append(TaxRecord(
                    txf_code=txf_code,
                    description=f"{term} capital gain ({coverage})",
                    amount=proceeds,
                    date_acquired=parse_date(m.group("date_acq")),
                    date_sold=parse_date(m.group("date_sold")),
                    cost_basis=basis,
                    security_name=m.group("security").strip(),
                    form_type="1099-B",
                ))
        return records


class GenericAmountParser:
    """Fallback parser that extracts labeled dollar amounts."""

    AMOUNT_PATTERN = re.compile(
        r"(?P<label>[A-Za-z][A-Za-z\s]{2,40}?)\s*[\$:]?\s*\$?(?P<amount>[\d,]+\.\d{2})"
    )

    @classmethod
    def parse(cls, text: str) -> list[TaxRecord]:
        records = []
        seen = set()
        for m in cls.AMOUNT_PATTERN.finditer(text):
            label = m.group("label").strip()
            amount = parse_amount(m.group("amount"))
            if amount is not None and amount > 0 and label not in seen:
                seen.add(label)
                records.append(TaxRecord(
                    txf_code=0,  # Unknown - user needs to assign
                    description=label,
                    amount=amount,
                    form_type="Unknown",
                ))
        return records
