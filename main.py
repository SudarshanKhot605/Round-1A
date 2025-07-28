import os
import sys
import json
import logging
from kraken import extract_outline

# Constants for directories
INPUT_DIR = '/app/input'
OUTPUT_DIR = '/app/output'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def ensure_directories():
    """
    Ensure that the input and output directories exist and are accessible.
    """
    if not os.path.isdir(INPUT_DIR) or not os.access(INPUT_DIR, os.R_OK):
        logging.error(f"Cannot read input directory: {INPUT_DIR}")
        sys.exit(1)

    if not os.path.isdir(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            logging.info(f"Created output directory: {OUTPUT_DIR}")
        except Exception as e:
            logging.error(f"Failed to create output directory: {OUTPUT_DIR} - {e}")
            sys.exit(1)
    elif not os.access(OUTPUT_DIR, os.W_OK):
        logging.error(f"Cannot write to output directory: {OUTPUT_DIR}")
        sys.exit(1)

def process_pdfs():
    """
    Process all PDF files in the input directory and extract their outlines.
    """
    files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith('.pdf')]
    if not files:
        logging.warning(f"No PDF files found in {INPUT_DIR}")
        return

    for pdf in files:
        path_in = os.path.join(INPUT_DIR, pdf)
        try:
            data = extract_outline(path_in)
        except Exception as e:
            logging.error(f"Error processing '{pdf}': {e}")
            continue

        # Prepare output filename
        base = os.path.splitext(pdf)[0]
        out_path = os.path.join(OUTPUT_DIR, f"{base}.json")

        try:
            with open(out_path, 'w', encoding='utf-8') as fout:
                json.dump(data, fout, ensure_ascii=False, indent=2)
            logging.info(f"Processed: {pdf} -> {base}.json")
        except Exception as e:
            logging.error(f"Failed writing output for '{pdf}': {e}")

def main():
    ensure_directories()
    process_pdfs()

if __name__ == '__main__':
    main()