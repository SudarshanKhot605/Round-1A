# PDF Heading Classification System

A robust, intelligent system for extracting document titles and hierarchical outlines from PDF files using advanced text formatting analysis and machine learning techniques.

## 🎯 Approach

Our solution employs a multi-stage pipeline that combines PDF text extraction with sophisticated heading classification:

### 1. PDF Text Extraction
- Uses **PyMuPDF (fitz)** for high-fidelity text extraction with complete formatting preservation
- Captures essential metadata: font sizes, styles (bold/italic), positioning coordinates, and spatial relationships
- Maintains document structure with accurate page numbers and text boundaries

### 2. Intelligent Header/Footer Detection
- Implements position-based and style-based detection algorithms
- Uses cross-page repetition analysis to identify recurring elements
- Filters out non-content elements to focus on meaningful text

### 3. Advanced Heading Classification
- **Score-based grouping**: Elements are grouped by formatting characteristics (font size, style, positioning)
- **Priority scoring system**: Combines font size, styling attributes, spatial positioning, and word count analysis
- **Bracket-based hierarchy assignment**: Uses 10-point score ranges with intelligent exclusion rules
- **Title identification**: Employs validation algorithms to distinguish document titles from headings

### 4. Hierarchy Correction & Validation
- Automatically corrects improper heading sequences (H2→H1→H3 becomes H1→H2→H3)
- Handles title misplacement and ensures logical document structure
- Applies quality filtering using English dictionary validation

## 📚 Libraries & Dependencies

- **PyMuPDF (fitz)**: High-performance PDF text extraction with formatting preservation
- **enchant**: English dictionary validation for text quality assessment
- **collections**: Counter and defaultdict for efficient data aggregation
- **dataclasses**: Type-safe data structures for text elements and heading groups
- **re**: Pattern matching for text validation and cleanup
- **json**: Data serialization and output formatting

## 🚀 Build & Run Instructions

### Prerequisites
```bash
pip install PyMuPDF pyenchant
```

### Docker Setup
Clone the repository and build the Docker image:
```bash
git clone https://github.com/SudarshanKhot605/Round-1A.git
cd Round-1A
docker build --platform linux/amd64 -t kraken:latest .
```

### Running the Solution
Execute the containerized solution:
```bash
cd kraken_io
docker run --rm -v $(pwd)/input:/app/input -v $(pwd)/output:/app/output --network none kraken:latest
```

### Direct Python Execution
For development and testing:
```python
from pdf_extractor import PDFLineExtractor
from heading_classifier import classify_headings

# Extract text with formatting
extractor = PDFLineExtractor("document.pdf")
text_data = extractor.extract_text_lines()

# Classify headings and extract outline
result = classify_headings(text_data)
print(f"Title: {result['title']}")
print(f"Outline: {len(result['outline'])} headings")
```

### Input/Output Format
- **Input**: PDF files placed in `/input` directory
- **Output**: JSON files with structured title and outline data in `/output` directory
- **Format**: `{"title": "Document Title", "outline": [{"level": "H1", "text": "Heading", "page": 1}]}`

The system automatically handles complex document layouts, multiple font families, and various document structures while maintaining high accuracy in heading detection and hierarchical organization.