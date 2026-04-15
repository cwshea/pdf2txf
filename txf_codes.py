"""TXF type codes for common tax form line items."""

# TXF record type codes mapped to form/line descriptions
# Reference: https://turbotax.intuit.com/txf/

TXF_CODES = {
    # 1099-INT: Interest Income
    "1099-INT": {
        "interest": 321,       # Interest income
    },
    # 1099-DIV: Dividends
    "1099-DIV": {
        "ordinary_dividends": 488,      # Ordinary dividends
        "qualified_dividends": 489,      # Qualified dividends
        "capital_gain_dist": 491,        # Capital gain distributions
    },
    # 1099-B: Proceeds from Broker and Barter Exchange
    "1099-B": {
        "st_covered": 711,     # Short-term covered
        "st_noncovered": 713,  # Short-term noncovered
        "lt_covered": 715,     # Long-term covered
        "lt_noncovered": 717,  # Long-term noncovered
    },
    # 1099-MISC / 1099-NEC
    "1099-MISC": {
        "rents": 547,
        "royalties": 548,
        "other_income": 553,
    },
    "1099-NEC": {
        "nonemployee_compensation": 547,
    },
    # W-2: Wages
    "W-2": {
        "wages": 1,
        "federal_tax_withheld": 2,
    },
}
