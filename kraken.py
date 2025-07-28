from text_extraction import PDFLineExtractor
from structure_analysis import classify_headings


def extract_outline(pdf_path: str) -> dict:
    """
    Extracts title and hierarchical outline (H1–H4) from a PDF.
    
    Args:
        pdf_path (str): Path to the PDF file.
    Returns:
        dict: {
            "title": <str>,
            "outline": [{"level": "H1"/"H2"/"H3"/"H4", "text": <str>, "page": <int>}, ...]
        }
    """
    try:
        # Extract text lines with formatting metadata
        extractor = PDFLineExtractor(pdf_path)
        extractor.extract_text_lines()
        
        # Get formatted data for processing
        json_data = extractor.get_pdf_lines(include_metadata=True)
        
        # Classify headings and extract structure
        result = classify_headings(json_data)
        
        return {
            "title": result.get("title", ""),
            "outline": result.get("outline", [])
        }
        
    except Exception:
        return {"title": "", "outline": []}