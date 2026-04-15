#!/bin/bash
#
# pdf2txf.sh — Convert a Solium/Shareworks PDF to a validated TXF file
#
# Usage: ./pdf2txf.sh <input.pdf> [output.txf] [payer_name]
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Set up venv if needed ---
if [ ! -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
    source "$SCRIPT_DIR/venv/bin/activate"
    pip install -r "$SCRIPT_DIR/requirements.txt"
    echo ""
else
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# --- Arguments ---
PDF_FILE="${1:?Usage: $0 <input.pdf> [output.txf] [payer_name]}"
OUTPUT_FILE="${2:-${PDF_FILE%.pdf}.txf}"
PAYER="${3:-Morgan Stanley}"

# --- Validate input ---
if [ ! -f "$PDF_FILE" ]; then
    echo "Error: File not found: $PDF_FILE"
    exit 1
fi

CSV_FILE="${PDF_FILE%.pdf}.csv"

echo "=== pdf2txf ==="
echo "Input:  $PDF_FILE"
echo "Output: $OUTPUT_FILE"
echo "Payer:  $PAYER"
echo ""

# --- Step 1: Convert PDF to CSV ---
echo "Step 1: Converting PDF to CSV..."
python3 "$SCRIPT_DIR/pdf2txf.py" "$PDF_FILE" -o "$CSV_FILE" --payer "$PAYER"
echo ""

# --- Step 2: Convert CSV to TXF ---
echo "Step 2: Converting CSV to TXF..."
python3 "$SCRIPT_DIR/csv2txf.py" "$CSV_FILE" --only D
mv "${CSV_FILE%.csv}_D.txf" "$OUTPUT_FILE"
echo "  $OUTPUT_FILE"
echo ""

# --- Step 3: Validate TXF ---
echo "Step 3: Validating TXF..."
python3 "$SCRIPT_DIR/txf_decoder.py" "$OUTPUT_FILE"
