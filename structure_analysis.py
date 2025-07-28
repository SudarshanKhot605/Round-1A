import json
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, Counter
from dataclasses import dataclass, field
import re
import enchant
import string

# Create English dictionary
d = enchant.Dict("en_US")

def classify_string(text: str) -> bool:
    """
    Returns True if text is valid heading text based on:
    - Starts with digit (e.g. '1. Preamble')
    - All-caps acronym of length>=2 (e.g. 'RFP')  
    - Valid English word or contains valid English words
    - Must be at least 3 characters long
    - Must contain letters (not only numbers/special chars)
    - If not starting with number, first word must be capitalized
    """
    text = text.strip()
    if not text or len(text) < 3:
        return False

    # Check for consecutive special characters that shouldn't be in headings
    consecutive_patterns = ['--', '..', '==', '**', '^^', '<<', '>>', '//', '\\\\', '~~']
    if any(pattern in text for pattern in consecutive_patterns):
        return False
    
    # Reject if text contains only numbers and special characters (no letters)
    if not any(c.isalpha() for c in text):
        return False
    
    # Check capitalization rule for non-numeric starts
    if not text[0].isdigit():
        words = text.split()
        if words:
            first_word = words[0].strip(string.punctuation)
            if first_word and first_word[0].islower():
                return False
    
    # Numeric start - always allowed if it passes above rules
    if text[0].isdigit():
        return True

    # Trim surrounding punctuation for next checks
    cleaned = text.strip(string.punctuation)

    # Acronym: all uppercase letters, length>=2
    if cleaned.isupper() and len(cleaned) >= 2:
        return True

    # Check if entire text is a valid English word
    if d.check(cleaned):
        return True

    # Check if text contains at least one valid English word
    words = cleaned.split()
    for word in words:
        word_clean = word.strip(string.punctuation)
        if len(word_clean) >= 2 and d.check(word_clean):
            return True
    
    # Allow common title/heading patterns
    if len(cleaned) >= 3:
        alpha_count = sum(1 for c in cleaned if c.isalpha())
        if alpha_count >= len(cleaned) * 0.5:  # At least 50% letters
            return True

    return False

class HeaderFooterDetector:
    """Detects and removes headers/footers using position and style analysis"""
    
    def __init__(self, page_height=792, page_width=612):
        self.page_height = page_height
        self.page_width = page_width
        self.header_threshold = 0.12  # Top 12%
        self.footer_threshold = 0.88  # Bottom 12%
        self.min_repetition = 2
        
    def detect_headers_footers(self, all_pages_data):
        """Main detection method combining position, style, and repetition analysis"""
        results = {}
        
        for page_num, elements in all_pages_data.items():
            # Position-based detection
            pos_headers, pos_footers, pos_content = self._detect_by_position(elements)
            
            # Style-based detection
            style_headers, style_footers, style_content = self._detect_by_style(elements)
            
            # Combine results using intersection for higher confidence
            final_headers = self._combine_detections(pos_headers, style_headers)
            final_footers = self._combine_detections(pos_footers, style_footers)
            
            # Remove headers/footers from main content
            header_indices = {elem.get('original_index') for elem in final_headers}
            footer_indices = {elem.get('original_index') for elem in final_footers}
            
            main_content = [
                elem for elem in elements 
                if elem.get('original_index') not in header_indices 
                and elem.get('original_index') not in footer_indices
            ]
            
            results[page_num] = {
                'headers': final_headers,
                'footers': final_footers,
                'content': main_content
            }
        
        # Cross-page repetition analysis for refinement
        self._refine_by_repetition(results)
        
        return results
    
    def _detect_by_position(self, elements):
        """Detect headers/footers based on position on page"""
        headers = []
        footers = []
        content = []
        
        header_y_limit = self.page_height * self.header_threshold
        footer_y_limit = self.page_height * self.footer_threshold
        
        for element in elements:
            y_pos = element.get('y', self.page_height / 2)
            
            if y_pos <= header_y_limit:
                headers.append(element)
            elif y_pos >= footer_y_limit:
                footers.append(element)
            else:
                content.append(element)
        
        return headers, footers, content
    
    def _detect_by_style(self, elements):
        """Detect headers/footers based on font style characteristics"""
        if not elements:
            return [], [], []
        
        # Calculate main font size
        font_sizes = [elem.get('font_size', 12) for elem in elements]
        main_font_size = max(set(font_sizes), key=font_sizes.count)
        
        headers = []
        footers = []
        content = []
        
        for element in elements:
            font_size = element.get('font_size', 12)
            text = element.get('text', '').strip()
            y_pos = element.get('y', self.page_height / 2)
            
            # Style indicators for headers/footers
            is_small_font = font_size < main_font_size * 0.85
            is_page_number = self._is_page_number(text)
            is_short = len(text) < 60
            is_italic = element.get('is_italic', False)
            
            # Calculate header/footer likelihood score
            hf_score = 0
            if is_small_font: hf_score += 2
            if is_page_number: hf_score += 3
            if is_short: hf_score += 1
            if is_italic: hf_score += 1
            
            # Position-based classification with style weighting
            if y_pos <= self.page_height * 0.15:  # Top area
                if hf_score >= 2:
                    headers.append(element)
                else:
                    content.append(element)
            elif y_pos >= self.page_height * 0.85:  # Bottom area
                if hf_score >= 2:
                    footers.append(element)
                else:
                    content.append(element)
            else:
                content.append(element)
        
        return headers, footers, content
    
    def _is_page_number(self, text):
        """Check if text looks like a page number"""
        patterns = [
            r'^\d+$',  # Just a number
            r'^page\s+\d+$',  # "page 1"
            r'^p\.\s*\d+$',  # "p. 1"
            r'^\d+\s*/\s*\d+$',  # "1 / 10"
            r'^-\s*\d+\s*-$',  # "- 1 -"
        ]
        
        text_lower = text.lower().strip()
        return any(re.match(pattern, text_lower) for pattern in patterns)
    
    def _combine_detections(self, detection1, detection2):
        """Combine two detection results using intersection"""
        indices1 = {elem.get('original_index') for elem in detection1}
        indices2 = {elem.get('original_index') for elem in detection2}
        
        common_indices = indices1.intersection(indices2)
        
        return [elem for elem in detection1 if elem.get('original_index') in common_indices]
    
    def _refine_by_repetition(self, results):
        """Refine detection using cross-page repetition analysis"""
        header_patterns = defaultdict(list)
        footer_patterns = defaultdict(list)
        
        for page_num, page_data in results.items():
            for header in page_data['headers']:
                pattern = self._create_pattern(header)
                header_patterns[pattern].append((page_num, header))
            
            for footer in page_data['footers']:
                pattern = self._create_pattern(footer)
                footer_patterns[pattern].append((page_num, footer))
        
        # Find truly repeated patterns
        repeated_headers = {
            pattern: pages for pattern, pages in header_patterns.items()
            if len(pages) >= self.min_repetition
        }
        
        repeated_footers = {
            pattern: pages for pattern, pages in footer_patterns.items()
            if len(pages) >= self.min_repetition
        }
        
        # Mark repeated elements as confirmed headers/footers
        for page_num, page_data in results.items():
            for pattern, pages in repeated_headers.items():
                for p_num, element in pages:
                    if p_num == page_num:
                        element['is_repeated_header'] = True
            
            for pattern, pages in repeated_footers.items():
                for p_num, element in pages:
                    if p_num == page_num:
                        element['is_repeated_footer'] = True
    
    def _create_pattern(self, element):
        """Create a pattern for repetition detection"""
        text = element.get('text', '').strip()
        y_norm = round(element.get('y', 0) / self.page_height, 2)
        x_norm = round(element.get('x', 0) / self.page_width, 2)
        
        # For page numbers, use position only
        if self._is_page_number(text):
            return ('PAGE_NUMBER', y_norm, x_norm)
        
        # For other text, use text + position
        return (text, y_norm, x_norm)

@dataclass
class TextElement:
    """Represents a processed text element with validated attributes"""
    text: str = ""
    page: int = 1
    font_size: float = 12.0
    font: str = "Arial"
    is_bold: bool = False
    is_italic: bool = False
    is_underlined: bool = False
    is_center: bool = False
    space_above: float = 0.0
    space_below: float = 0.0
    original_index: int = 0
    x: float = 0.0
    y: float = 0.0
    
    def __post_init__(self):
        """Validate and clean the text element data"""
        try:
            # Clean and validate text
            self.text = str(self.text).strip() if self.text is not None else ""
            
            # Validate numeric fields
            self.page = max(1, int(self.page)) if self.page is not None else 1
            self.font_size = float(self.font_size) if self.font_size is not None else 12.0
            self.space_above = float(self.space_above) if self.space_above is not None else 0.0
            self.space_below = float(self.space_below) if self.space_below is not None else 0.0
            self.x = float(self.x) if self.x is not None else 0.0
            self.y = float(self.y) if self.y is not None else 0.0

            # Handle legacy coordinate fields
            if hasattr(self, 'x0') and self.x == 0.0:
                self.x = float(getattr(self, 'x0', 0.0))
            if hasattr(self, 'y0') and self.y == 0.0:
                self.y = float(getattr(self, 'y0', 0.0))
            
            # Validate string and boolean fields
            self.font = str(self.font) if self.font is not None else "Arial"
            self.is_bold = bool(self.is_bold) if self.is_bold is not None else False
            self.is_italic = bool(self.is_italic) if self.is_italic is not None else False
            self.is_underlined = bool(self.is_underlined) if self.is_underlined is not None else False
            self.is_center = bool(self.is_center) if self.is_center is not None else False
            
        except (ValueError, TypeError):
            self._set_defaults()
    
    def _set_defaults(self):
        """Set default values for invalid data"""
        self.text = ""
        self.page = 1
        self.font_size = 12.0
        self.font = "Arial"
        self.is_bold = False
        self.is_italic = False
        self.is_underlined = False
        self.is_center = False
        self.space_above = 0.0
        self.space_below = 0.0
        self.x = 0.0
        self.y = 0.0
    
    def to_dict(self):
        """Convert TextElement to dictionary for header/footer detection"""
        return {
            'text': self.text,
            'page': self.page,
            'font_size': self.font_size,
            'font': self.font,
            'is_bold': self.is_bold,
            'is_italic': self.is_italic,
            'is_underlined': self.is_underlined,
            'is_center': self.is_center,
            'space_above': self.space_above,
            'space_below': self.space_below,
            'original_index': self.original_index,
            'x': self.x,
            'y': self.y
        }

@dataclass
class HeadingGroup:
    """Represents a group of headings with similar formatting"""
    font_size: float
    is_bold: bool
    is_italic: bool
    is_center: bool
    font: str
    elements: List[TextElement] = field(default_factory=list)
    level: Optional[str] = None
    is_underlined: bool = False
    
    def get_signature(self) -> Tuple:
        """Get unique signature for grouping"""
        return (self.font_size, self.is_bold, self.is_italic, self.is_center, self.font)
    
    def add_element(self, element: TextElement):
        """Add element to the group"""
        self.elements.append(element)
    
    def get_priority_score(self) -> float:
        """Calculate priority score with font size, style, and word count bonuses"""
        # Base score from font size
        score = self.font_size * 100
        
        # Style bonuses for better differentiation
        if self.is_bold:
            score += 11
        if self.is_center:
            score += 5
        if self.is_italic:
            score += 11
        if hasattr(self, 'is_underlined') and self.is_underlined:
            score += 11
        
        # Spacing-based bonus
        if hasattr(self, 'space_above') and self.space_above > 10:
            score += 5
        if hasattr(self, 'space_below') and self.space_below > 10:
            score += 3
        
        # Word count bonus - fewer words get higher bonus
        word_count_bonus = self._calculate_word_count_bonus()
        score += word_count_bonus
        
        return score

    def _calculate_word_count_bonus(self) -> float:
        """Calculate bonus score based on word count - fewer words = higher bonus"""
        if not self.elements:
            return 0.0
        
        total_bonus = 0.0
        element_count = 0
        
        for element in self.elements:
            words = element.text.strip().split()
            word_count = len([word for word in words if word.strip()])
            
            # Calculate bonus for this element (no bonus if more than 8 words)
            if word_count <= 8:
                if word_count == 1:
                    element_bonus = 20.0
                elif word_count <= 2:
                    element_bonus = 15.0
                elif word_count <= 3:
                    element_bonus = 12.0
                elif word_count <= 4:
                    element_bonus = 10.0
                elif word_count <= 5:
                    element_bonus = 8.0
                elif word_count <= 6:
                    element_bonus = 5.0
                elif word_count <= 7:
                    element_bonus = 3.0
                else:  # word_count == 8
                    element_bonus = 1.0
            else:
                element_bonus = 0.0
            
            total_bonus += element_bonus
            element_count += 1
        
        return total_bonus / element_count if element_count > 0 else 0.0

class HeadingClassifier:
    """Main class for classifying headings with header/footer detection"""
    
    def __init__(self):
        self.elements: List[TextElement] = []
        self.groups: List[HeadingGroup] = []
        self.title: Optional[str] = None
        self.title_elements: List[TextElement] = []
        self.outline: List[Dict[str, Any]] = []
        self.font_size_threshold = 30
        self.header_footer_detector = HeaderFooterDetector()
        self.excluded_indices: set = set()
        self.max_text_length_for_lowest = 50
        
    def _validate_input(self, data: Any) -> bool:
        """Validate input data structure"""
        if not isinstance(data, list) or len(data) == 0:
            return False
        
        dict_count = sum(1 for item in data if isinstance(item, dict))
        return dict_count > 0
    
    def _parse_text_elements(self, data: List[Dict[str, Any]]):
        """Parse and validate text elements"""
        self.elements = []
        
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            
            element = TextElement(
                text=item.get('text', ''),
                page=item.get('page', 1),
                font_size=item.get('font_size', 12.0),
                font=item.get('font', 'Arial'),
                is_bold=item.get('is_bold', False),
                is_italic=item.get('is_italic', False),
                is_underlined=item.get('is_underlined', False),
                is_center=item.get('is_center', False),
                space_above=item.get('space_above', 0.0),
                space_below=item.get('space_below', 0.0),
                x=item.get('x', item.get('x0', 0.0)),
                y=item.get('y', item.get('y0', 0.0)),
                original_index=i
            )
            
            if element.text:
                self.elements.append(element)
    
    def _detect_and_remove_headers_footers(self):
        """Detect and remove headers/footers from elements"""
        try:
            # Group elements by page
            pages_data = defaultdict(list)
            for element in self.elements:
                pages_data[element.page].append(element.to_dict())
            
            # Run header/footer detection
            hf_results = self.header_footer_detector.detect_headers_footers(pages_data)
            
            # Collect indices of headers and footers to exclude
            header_footer_indices = set()
            
            for page_num, page_data in hf_results.items():
                for header in page_data['headers']:
                    header_footer_indices.add(header['original_index'])
                
                for footer in page_data['footers']:
                    header_footer_indices.add(footer['original_index'])
            
            self.excluded_indices = header_footer_indices
            
            # Filter out header/footer elements
            self.elements = [
                element for element in self.elements 
                if element.original_index not in header_footer_indices
            ]
            
        except Exception:
            pass  # Continue without header/footer filtering

    def _filter_by_font_size(self):
        """Smart font size filtering - keep elements that could be headings"""
        if not self.elements:
            return
        
        font_size_counts = Counter(element.font_size for element in self.elements)
        total_elements = len(self.elements)
        
        # If we have very few font sizes, keep all
        if len(font_size_counts) <= 3:
            return
        
        # Smart filtering based on percentage
        excluded_sizes = set()
        kept_sizes = set()
        
        for font_size, count in font_size_counts.items():
            percentage = (count / total_elements) * 100
            
            # Exclude if it's more than 50% of all elements (likely body text)
            if percentage > 50:
                excluded_sizes.add(font_size)
            else:
                kept_sizes.add(font_size)
        
        # Apply classify_string filter early to reduce elements
        self.elements = [
            element for element in self.elements 
            if classify_string(element.text)
        ]
        
        # Safety check: Always keep at least the largest font sizes
        if not kept_sizes:
            largest_sizes = sorted(font_size_counts.keys(), reverse=True)[:3]
            kept_sizes = set(largest_sizes)
            excluded_sizes = set(font_size_counts.keys()) - kept_sizes
        
        # Filter elements
        self.elements = [
            element for element in self.elements 
            if element.font_size not in excluded_sizes
        ]
        
        # Final safety check
        if len(self.elements) == 0:
            self.font_size_threshold = float('inf')

    def _create_groups(self):
        """Group elements by formatting attributes with spatial proximity"""
        try:
            group_map = defaultdict(list)
            
            for element in self.elements:
                # Create base signature without is_center
                base_signature = (
                    round(element.font_size, 1),
                    element.is_bold,
                    element.is_italic,
                    element.font.lower().replace('-', '').replace(' ', '')
                )
                
                # Look for existing groups with same base formatting on same page
                merged_to_existing = False
                
                for signature, existing_elements in group_map.items():
                    if (len(signature) >= 4 and signature[:4] == base_signature and 
                        existing_elements and existing_elements[0].page == element.page):
                        
                        # Check if spatially close to any element in this group
                        for existing_elem in existing_elements:
                            y_diff = abs(element.y - existing_elem.y)
                            dynamic_threshold = max(3, element.font_size * 0.2)
                            if y_diff <= dynamic_threshold:
                                group_map[signature].append(element)
                                merged_to_existing = True
                                break
                        
                        if merged_to_existing:
                            break
                
                # If not merged, create new group
                if not merged_to_existing:
                    full_signature = base_signature + (element.is_center,)
                    group_map[full_signature].append(element)
            
            # Create HeadingGroup objects
            self.groups = []
            for signature, elements in group_map.items():
                if len(signature) >= 4:
                    font_size = signature[0]
                    is_bold = signature[1]
                    is_italic = signature[2]
                    font = signature[3] if isinstance(signature[3], str) else "Arial"
                    is_center = signature[4] if len(signature) > 4 else False
                    is_group_underlined = any(getattr(elem, 'is_underlined', False) for elem in elements)
                    
                    group = HeadingGroup(
                        font_size=font_size,
                        is_bold=is_bold,
                        is_italic=is_italic,
                        is_center=is_center,
                        font=font,
                        is_underlined=is_group_underlined, 
                        elements=elements
                    )
                    self.groups.append(group)
            
        except Exception:
            # Fallback to simple grouping
            self.groups = [HeadingGroup(
                font_size=12.0,
                is_bold=False,
                is_italic=False,
                is_center=False,
                font="Arial",
                elements=self.elements
            )]

    def _combine_consecutive_similar_elements(self):
        """Combine consecutive elements with identical formatting that should be one heading"""
        try:
            if not self.groups:
                return
            
            for group in self.groups:
                if len(group.elements) <= 1:
                    continue
                
                # Sort elements by page and original index
                group.elements.sort(key=lambda e: (e.page, e.original_index))
                
                # Group consecutive elements that are spatially close
                combined_elements = []
                current_group = [group.elements[0]]
                
                for i in range(1, len(group.elements)):
                    prev_elem = group.elements[i-1]
                    curr_elem = group.elements[i]
                    
                    # Check if elements are consecutive and spatially close
                    is_consecutive = (curr_elem.original_index - prev_elem.original_index <= 1)
                    is_same_page = (curr_elem.page == prev_elem.page)
                    spatial_threshold = max(2, curr_elem.font_size * 0.15)
                    is_spatially_close = (abs(curr_elem.y - prev_elem.y) <= spatial_threshold)
                    
                    if is_consecutive and is_same_page and is_spatially_close:
                        current_group.append(curr_elem)
                    else:
                        # Finalize current group and start new one
                        if len(current_group) > 1:
                            combined_elem = self._combine_elements_into_one(current_group)
                            combined_elements.append(combined_elem)
                        else:
                            combined_elements.extend(current_group)
                        
                        current_group = [curr_elem]
                
                # Handle the last group
                if len(current_group) > 1:
                    combined_elem = self._combine_elements_into_one(current_group)
                    combined_elements.append(combined_elem)
                else:
                    combined_elements.extend(current_group)
                
                # Update the group's elements
                if len(combined_elements) < len(group.elements):
                    group.elements = combined_elements
        
        except Exception:
            pass

    def _combine_elements_into_one(self, elements: List['TextElement']) -> 'TextElement':
        """Combine multiple elements into a single element"""
        if not elements:
            return None
        
        if len(elements) == 1:
            return elements[0]
        
        # Sort by original index
        elements.sort(key=lambda e: e.original_index)
        
        # Use the first element as base
        base_elem = elements[0]
        
        # Combine text using spatial reconstruction
        combined_text = self._reconstruct_title_text(elements)
        
        # Create new combined element
        combined_element = TextElement(
            text=combined_text,
            page=base_elem.page,
            font_size=base_elem.font_size,
            font=base_elem.font,
            is_bold=base_elem.is_bold,
            is_italic=base_elem.is_italic,
            is_underlined=base_elem.is_underlined,
            is_center=base_elem.is_center,
            space_above=base_elem.space_above,
            space_below=elements[-1].space_below,
            x=base_elem.x,
            y=base_elem.y,
            original_index=base_elem.original_index
        )
        
        return combined_element

    def _is_valid_title_text(self, text: str) -> bool:
        """Check if text is valid for a title using industry-standard criteria"""
        try:
            if not text or not text.strip():
                return False
            
            text = text.strip()
            
            # Length criteria
            if len(text) < 3 or len(text) > 200:
                return False
            
            # Character composition analysis
            total_chars = len(text)
            alpha_chars = sum(1 for c in text if c.isalpha())
            digit_chars = sum(1 for c in text if c.isdigit())
            
            # Must have reasonable proportion of alphabetic characters
            if alpha_chars < total_chars * 0.4:  # At least 40% letters
                return False
            
            # Too many digits suggests it's not a title
            if digit_chars > total_chars * 0.5:  # More than 50% digits
                return False
            
            # Pattern-based exclusions
            patterns_to_exclude = [
                r'^[0-9\s\-\.\/]+$',  # Only numbers, spaces, dashes, dots, slashes
                r'^[A-Z]{3,}\s*[0-9]+$',  # Pattern like "ABC 123" or "FORM123"
                r'^\d+[\.\-\s]*\d*$',  # Pure numeric patterns
                r'^[^\w\s]{3,}$',  # Only special characters
                r'.*\b(rev|version|ver|v)\s*[\d\.]+\b.*',  # Version numbers
                r'.*\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b.*',  # Dates
                r'.*\b[A-Z]{2,}\-\d+\b.*',  # Code patterns like "ABC-123"
                r'^(table|figure|chart|graph|image|photo)\s+\d+.*',  # Figure/table references
                r'.*-{2,}.*',  # Text containing consecutive dashes
            ]
            
            text_lower = text.lower()
            for pattern in patterns_to_exclude:
                if re.match(pattern, text_lower, re.IGNORECASE):
                    return False
            
            # Word-based analysis
            words = re.findall(r'\b[a-zA-Z]+\b', text)
            
            if not words:  # No valid words found
                return False
            
            # Check for minimum meaningful words
            if len(words) == 1 and len(words[0]) < 4:  # Single short word
                return False
            
            # Basic word pattern validation
            common_english_words = {
                'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
                'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
                'this', 'that', 'these', 'those', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
                'about', 'above', 'after', 'again', 'against', 'all', 'any', 'as', 'because', 'before',
                'below', 'between', 'both', 'but', 'during', 'each', 'few', 'from', 'further',
                'if', 'into', 'more', 'most', 'no', 'not', 'only', 'other', 'over', 'same', 'some',
                'such', 'than', 'through', 'under', 'until', 'up', 'very', 'while', 'within', 'without'
            }
            
            # Count recognizable words
            recognizable_words = 0
            for word in words:
                word_lower = word.lower()
                if (word_lower in common_english_words or 
                    len(word) >= 3 or
                    self._has_reasonable_letter_pattern(word)):
                    recognizable_words += 1
            
            # At least 60% of words should be recognizable
            if len(words) > 1 and recognizable_words / len(words) < 0.6:
                return False
            
            if self._looks_like_code_or_technical_id(text):
                return False
            
            return True
            
        except Exception:
            return True  # Be permissive on error

    def _has_reasonable_letter_pattern(self, word: str) -> bool:
        """Check if word has reasonable vowel-consonant patterns"""
        if len(word) < 2:
            return True
        
        vowels = set('aeiouAEIOU')
        has_vowel = any(c in vowels for c in word)
        has_consonant = any(c.isalpha() and c not in vowels for c in word)
        
        # Should have both vowels and consonants for longer words
        if len(word) >= 4:
            return has_vowel and has_consonant
        
        return True

    def _looks_like_code_or_technical_id(self, text: str) -> bool:
        """Check if text looks like code, IDs, or technical references"""
        patterns = [
            r'.*[a-zA-Z]+\d+[a-zA-Z]+\d+.*',  # Mixed letters and numbers pattern
            r'.*\b[A-Z]{2,}_[A-Z0-9_]+\b.*',  # Underscore separated caps
            r'.*\b[a-z]+[A-Z][a-z]*[A-Z].*',  # camelCase patterns
            r'.*\b\w*[0-9]{3,}\w*\b.*',  # Words with 3+ consecutive digits
            r'.*\b[A-F0-9]{8,}\b.*',  # Hex-like patterns
        ]
        
        for pattern in patterns:
            if re.match(pattern, text):
                return True
        
        return False

    def _reconstruct_title_text(self, elements: List['TextElement']) -> str:
        """Reconstruct complete title text from fragmented elements"""
        if not elements:
            return ""
        
        elements = self._remove_overlapping_elements(elements)
        
        # Try to reconstruct by overlapping text analysis
        reconstructed = self._reconstruct_by_overlap_analysis(elements)
        if reconstructed:
            return reconstructed
        
        # Try positional reconstruction
        reconstructed = self._reconstruct_by_position(elements)
        if reconstructed:
            return reconstructed
        
        # Simple concatenation with deduplication
        return self._simple_concatenation_with_dedup(elements)

    def _remove_overlapping_elements(self, elements: List['TextElement']) -> List['TextElement']:
        """Remove overlapping/duplicate elements based on spatial coordinates and text content"""
        if len(elements) <= 1:
            return elements
        
        sorted_elements = sorted(elements, key=lambda e: e.original_index)
        filtered_elements = []
        
        for current_elem in sorted_elements:
            should_keep = True
            current_text = current_elem.text.strip()
            
            for existing_elem in filtered_elements:
                existing_text = existing_elem.text.strip()
                
                # Check for spatial overlap
                x_overlap = abs(current_elem.x - existing_elem.x) < 3
                y_overlap = abs(current_elem.y - existing_elem.y) < 2
                
                # Check for text containment
                text_contained = (current_text in existing_text or 
                                existing_text in current_text)
                
                # If elements overlap spatially and have similar/contained text, skip the shorter one
                if x_overlap and y_overlap and text_contained:
                    if len(current_text) <= len(existing_text):
                        should_keep = False
                        break
                    else:
                        # Current text is longer, remove the existing shorter one
                        filtered_elements.remove(existing_elem)
            
            if should_keep:
                filtered_elements.append(current_elem)
        
        return filtered_elements

    def _reconstruct_by_overlap_analysis(self, elements: List['TextElement']) -> str:
        """Reconstruct text by analyzing overlapping fragments"""
        if len(elements) <= 1:
            return elements[0].text.strip() if elements else ""
        
        # Sort elements by their original index
        sorted_elements = sorted(elements, key=lambda e: e.original_index)
        
        # Try to find the longest coherent sequence
        text_fragments = [elem.text.strip() for elem in sorted_elements if elem.text.strip()]
        
        if not text_fragments:
            return ""
        
        # Look for patterns in the fragments
        reconstructed = self._merge_overlapping_fragments(text_fragments)
        
        return reconstructed

    def _merge_overlapping_fragments(self, fragments: List[str]) -> str:
        """Merge overlapping text fragments into coherent text"""
        if not fragments:
            return ""
        
        if len(fragments) == 1:
            return fragments[0]
        
        # Remove exact duplicates first
        unique_fragments = []
        for frag in fragments:
            if frag not in unique_fragments:
                unique_fragments.append(frag)
        
        if len(unique_fragments) == 1:
            return unique_fragments[0]
        
        # Sort fragments by length (longest first) to prioritize complete text
        unique_fragments.sort(key=len, reverse=True)
        
        # Start with the longest fragment
        result = unique_fragments[0]
        
        for i in range(1, len(unique_fragments)):
            current_fragment = unique_fragments[i]
            
            # Skip if current fragment is completely contained in result
            if current_fragment.lower() in result.lower():
                continue
            
            # Try to find overlap with the result
            merged = self._merge_two_fragments(result, current_fragment)
            if merged != result and len(merged) > len(result):  # Only accept if merge makes text longer
                result = merged
            elif not any(word.lower() in result.lower() for word in current_fragment.split() if len(word) > 2):
                # If no significant word overlap, append as continuation
                result = result + " " + current_fragment
        
        return result.strip()

    def _merge_two_fragments(self, text1: str, text2: str) -> str:
        """Try to merge two potentially overlapping fragments"""
        # Check for suffix-prefix overlap
        max_overlap = min(len(text1), len(text2)) // 2
        
        for overlap_len in range(max_overlap, 0, -1):
            if text1[-overlap_len:].lower() == text2[:overlap_len].lower():
                # Found overlap
                merged = text1 + text2[overlap_len:]
                return merged
        
        # Check for prefix-suffix overlap (reverse)
        for overlap_len in range(max_overlap, 0, -1):
            if text2[-overlap_len:].lower() == text1[:overlap_len].lower():
                # Found overlap
                merged = text2 + text1[overlap_len:]
                return merged
        
        # Check if one is contained in the other
        if text1.lower() in text2.lower():
            return text2
        elif text2.lower() in text1.lower():
            return text1
        
        return text1  # No merge possible

    def _reconstruct_by_position(self, elements: List['TextElement']) -> str:
        """Reconstruct text based on spatial positioning (if x,y coordinates available)"""
        if not all(hasattr(elem, 'x') and hasattr(elem, 'y') for elem in elements):
            return ""
        
        # Group elements by approximate y-position (same line)
        lines = defaultdict(list)
        
        for elem in elements:
            # Round y-position to group elements on the same line
            line_key = round(elem.y / 10) * 10  # Group within 5 units
            lines[line_key].append(elem)
        
        # Sort lines by y-position (top to bottom)
        sorted_lines = sorted(lines.items(), key=lambda x: x[0])
        
        # For each line, sort elements by x-position (left to right)
        line_texts = []
        for y_pos, line_elements in sorted_lines:
            line_elements.sort(key=lambda e: e.x)
            line_text = " ".join(elem.text.strip() for elem in line_elements if elem.text.strip())
            if line_text:
                line_texts.append(line_text)
        
        # Combine lines
        return " ".join(line_texts)

    def _simple_concatenation_with_dedup(self, elements: List['TextElement']) -> str:
        """Simple concatenation with basic deduplication"""
        if not elements:
            return ""
        
        # Get unique text pieces in document order
        seen_texts = set()
        unique_texts = []
        
        for elem in sorted(elements, key=lambda e: e.original_index):
            text = elem.text.strip()
            if text and text not in seen_texts:
                unique_texts.append(text)
                seen_texts.add(text)
        
        return " ".join(unique_texts)

    def _determine_hierarchy(self):
        """Initial hierarchy determination - will be reassigned after title identification"""
        try:
            if not self.groups:
                return
            
            # Sort groups by priority score (descending - highest priority first)
            sorted_groups = sorted(self.groups, key=lambda g: g.get_priority_score(), reverse=True)
            
            # Assign TEMPORARY levels (these will be reassigned after title identification)
            level_names = ['TEMP1', 'TEMP2', 'TEMP3', 'TEMP4', 'TEMP5']
            
            for i, group in enumerate(sorted_groups):
                if i < len(level_names):
                    group.level = level_names[i]
                else:
                    group.level = f'TEMP{i+1}'
            
            # Update the groups list with sorted order
            self.groups = sorted_groups
            
        except Exception:
            for i, group in enumerate(self.groups):
                group.level = f'TEMP{i+1}'

    def _identify_title(self):
        """Identify title based on HIGHEST scoring group that passes validation"""
        try:
            if not self.groups:
                self.title = ""
                self.title_elements = []
                return
            
            # Sort groups by score in descending order (highest first)
            sorted_groups = sorted(self.groups, key=lambda g: g.get_priority_score(), reverse=True)
            
            # Check each group starting from highest score
            title_found = False
            for i, group in enumerate(sorted_groups):
                score = group.get_priority_score()
                
                # Get all elements from this group
                group_elements = group.elements
                if not group_elements:
                    continue
                    
                # Check if this group appears on a single page
                pages_in_group = set(elem.page for elem in group_elements)
                
                # Reconstruct text from this group
                reconstructed_title = self._reconstruct_title_text(group_elements)
                
                # Title validation criteria
                if not reconstructed_title:
                    continue
                    
                if not self._is_valid_title_text(reconstructed_title):
                    continue
                
                # Prefer titles that appear early in document (first few pages)
                earliest_page = min(pages_in_group)
                if earliest_page > 3:  # First 3 pages only
                    continue
                
                # Prefer shorter titles (reasonable length)
                if len(reconstructed_title) > 150:
                    continue
                
                # SUCCESS - This is our title
                self.title = reconstructed_title
                self.title_elements = group_elements
                group.level = 'TITLE'
                
                title_found = True
                break
            
            if not title_found:
                self.title = ""
                self.title_elements = []
                        
        except Exception:
            self.title = ""
            self.title_elements = []

    def _remove_duplicate_headings(self):
        """Remove only the specific text elements that appear more than 5 times"""
        try:
            if not self.groups:
                return
            
            # Count all heading texts across all groups
            text_count = defaultdict(list)  # text -> list of (group, element) pairs
            
            for group in self.groups:
                if group.level not in ['TITLE', 'EXCLUDED']:  # Only check actual headings
                    for element in group.elements:
                        # Normalize text for comparison
                        normalized_text = ' '.join(element.text.strip().lower().split())
                        
                        if normalized_text and len(normalized_text) > 2:  # Skip very short texts
                            text_count[normalized_text].append((group, element))
            
            # Identify texts that appear more than 5 times
            texts_to_remove = set()
            for normalized_text, group_element_pairs in text_count.items():
                if len(group_element_pairs) > 5:
                    texts_to_remove.add(normalized_text)
            
            if not texts_to_remove:
                return
            
            # Remove specific elements (not entire groups)
            empty_groups = []
            
            for group in self.groups:
                if group.level not in ['TITLE', 'EXCLUDED']:
                    # Filter out elements with repeating text
                    new_elements = []
                    for element in group.elements:
                        normalized_text = ' '.join(element.text.strip().lower().split())
                        
                        if normalized_text not in texts_to_remove:
                            new_elements.append(element)
                    
                    # Update group with filtered elements
                    group.elements = new_elements
                    
                    # Track groups that became empty
                    if len(group.elements) == 0:
                        empty_groups.append(group)
            
            # Remove groups that became completely empty
            if empty_groups:
                self.groups = [group for group in self.groups if group not in empty_groups]
            
        except Exception:
            pass

    def _reassign_hierarchy_after_title(self):
        """Smart hierarchy assignment with 10-point score brackets and exclusion rules"""
        try:
            # Separate title groups from non-title groups
            title_groups = [g for g in self.groups if g.level == 'TITLE']
            non_title_groups = [g for g in self.groups if g.level != 'TITLE']
            
            if not non_title_groups:
                return
            
            # Get all scores and create brackets
            all_scores = []
            score_to_groups = defaultdict(list)
            for group in non_title_groups:
                score = group.get_priority_score()
                all_scores.append(score)
                score_to_groups[score].append(group)
            
            # Sort scores in descending order
            all_scores = sorted(set(all_scores), reverse=True)
            
            # Create score brackets with 15-point ranges
            brackets = self._create_score_brackets(all_scores)
            
            # Apply absolute exclusion rule (exclude brackets with >40 entries)
            brackets = self._apply_absolute_exclusion_rule(brackets, score_to_groups, max_entries_threshold=40)
            
            # Apply hierarchy rules based on number of brackets (after exclusion)
            num_brackets = len(brackets)
            original_bracket_count = len(self._create_score_brackets(all_scores))

            if num_brackets == 0:
                # No brackets left after exclusion
                for group in non_title_groups:
                    group.level = 'EXCLUDED'
                    
            elif num_brackets == 1:
                # Special handling for single bracket
                if original_bracket_count == 1:
                    for group in non_title_groups:
                        group.level = 'EXCLUDED'
                else:
                    self._assign_bracket_to_level(brackets[0], score_to_groups, 'H1')
                    
            elif num_brackets == 2:
                # Two brackets: H1 and conditional H2
                self._assign_bracket_to_level(brackets[0], score_to_groups, 'H1')
                
                # Check if second bracket should be included
                should_include = self._should_include_bracket(brackets[1], score_to_groups)
                if should_include:
                    self._assign_bracket_to_level(brackets[1], score_to_groups, 'H2')
                else:
                    self._assign_bracket_to_level(brackets[1], score_to_groups, 'EXCLUDED')
                    
            elif num_brackets == 3:
                # Three brackets: H1, H2, and conditional H3
                self._assign_bracket_to_level(brackets[0], score_to_groups, 'H1')
                self._assign_bracket_to_level(brackets[1], score_to_groups, 'H2')
                
                # Check if third bracket should be included
                should_include = self._should_include_bracket(brackets[2], score_to_groups)
                if should_include:
                    self._assign_bracket_to_level(brackets[2], score_to_groups, 'H3')
                else:
                    self._assign_bracket_to_level(brackets[2], score_to_groups, 'EXCLUDED')
                    
            else:  # num_brackets >= 4
                # Four or more brackets: Use top 3, exclude rest
                # Assign top 3 brackets
                self._assign_bracket_to_level(brackets[0], score_to_groups, 'H1')
                self._assign_bracket_to_level(brackets[1], score_to_groups, 'H2')
                
                # Check if third bracket should be included
                should_include = self._should_include_bracket(brackets[2], score_to_groups)
                if should_include:
                    self._assign_bracket_to_level(brackets[2], score_to_groups, 'H3')
                else:
                    self._assign_bracket_to_level(brackets[2], score_to_groups, 'EXCLUDED')
                
                # Exclude all remaining brackets
                for i in range(3, num_brackets):
                    self._assign_bracket_to_level(brackets[i], score_to_groups, 'EXCLUDED')
            
            # Update groups list - only include non-excluded groups
            valid_groups = title_groups + [g for g in non_title_groups if g.level != 'EXCLUDED']
            self.groups = valid_groups
            
        except Exception:
            pass

    def _create_score_brackets(self, sorted_scores):
        """Create score brackets with 15-point ranges"""
        if not sorted_scores:
            return []
        
        brackets = []
        i = 0
        
        while i < len(sorted_scores):
            # Start a new bracket with the current highest available score
            bracket_start = sorted_scores[i]
            bracket_end = bracket_start - 15
            
            # Find all scores that fall within this bracket
            bracket_scores = []
            while i < len(sorted_scores) and sorted_scores[i] >= bracket_end:
                bracket_scores.append(sorted_scores[i])
                i += 1
            
            brackets.append({
                'range': (bracket_start, bracket_end),
                'scores': bracket_scores
            })
        
        return brackets

    def _apply_absolute_exclusion_rule(self, brackets, score_to_groups, max_entries_threshold=40):
        """Apply absolute exclusion rule: exclude any bracket with more than max_entries_threshold entries"""
        try:
            if not brackets:
                return brackets
            
            # Calculate entries per bracket
            bracket_entry_counts = []

            for bracket in brackets:
                bracket_entries = 0
                for score in bracket['scores']:
                    for group in score_to_groups[score]:
                        bracket_entries += len(group.elements)
                bracket_entry_counts.append(bracket_entries)
            
            # Filter brackets based on absolute threshold
            filtered_brackets = []
            
            for i, bracket in enumerate(brackets):
                bracket_entries = bracket_entry_counts[i]
                
                if bracket_entries > max_entries_threshold:
                    # Mark groups in this bracket as excluded
                    for score in bracket['scores']:
                        for group in score_to_groups[score]:
                            group.level = 'EXCLUDED'
                else:
                    filtered_brackets.append(bracket)
            
            return filtered_brackets
            
        except Exception:
            return brackets

    def _assign_bracket_to_level(self, bracket, score_to_groups, level):
        """Assign all groups in a bracket to a specific level"""
        for score in bracket['scores']:
            for group in score_to_groups[score]:
                group.level = level

    def _should_include_bracket(self, bracket, score_to_groups):
        """Check if a bracket should be included based on text length"""
        # Get all groups in this bracket
        bracket_groups = []
        for score in bracket['scores']:
            bracket_groups.extend(score_to_groups[score])
        
        # Apply the same text length logic
        return self._should_include_lowest_score(bracket_groups, self.max_text_length_for_lowest)

    def _should_include_lowest_score(self, lowest_score_groups, max_text_length=50):
        """Check if lowest score groups should be included based on text length"""
        try:
            # Check all elements in lowest score groups
            for group in lowest_score_groups:
                for element in group.elements:
                    text_length = len(element.text.strip())
                    
                    # If ANY element has text length <= threshold, include the whole score group
                    if text_length <= max_text_length:
                        return True
            
            # If no short text found, exclude
            return False
            
        except Exception:
            return False  # Default to excluding on error

    def _create_outline(self):
        """Create the outline from grouped elements with hierarchy order correction"""
        try:
            self.outline = []
            
            # Create a set of original indices for title elements for fast lookup
            title_indices = set(element.original_index for element in self.title_elements)
            
            # Define allowed heading levels
            allowed_levels = {'H1', 'H2', 'H3', 'H4', 'H5', 'H6'}
            
            # Collect all elements with their levels
            all_elements = []
            
            for group in self.groups:
                # Only include groups with allowed levels
                if group.level in allowed_levels:
                    for element in group.elements:
                        all_elements.append((element, group.level))
            
            # Sort by page and original index to maintain document order
            all_elements.sort(key=lambda x: (x[0].page, x[0].original_index))
            
            # Create outline entries
            for element, level in all_elements:
                # Skip if this element was used in title construction
                if element.original_index in title_indices:
                    continue
                
                # Skip empty elements
                element_text = element.text.strip()
                if not element_text:
                    continue

                self.outline.append({
                    "level": level,
                    "text": element_text,
                    "page": element.page,
                })
            
            # Apply comprehensive title and hierarchy order correction
            self._correct_title_and_hierarchy_order()
            
        except Exception:
            self.outline = []

    def _correct_title_and_hierarchy_order(self):
        """Comprehensive correction of title and hierarchy order"""
        try:
            if not self.outline:
                return
            
            # Check title position relative to ALL headings
            title_needs_correction = False
            
            if self.title and self.title_elements:
                # Get the position of title elements in the original document
                title_positions = [elem.original_index for elem in self.title_elements]
                min_title_position = min(title_positions) if title_positions else float('inf')
                
                # Check all outline entries (headings) positions
                heading_before_title = []
                
                for entry in self.outline:
                    # Find the original elements that correspond to this outline entry
                    for group in self.groups:
                        if group.level == entry['level']:
                            for element in group.elements:
                                if (element.text.strip() == entry['text'].strip() and 
                                    element.page == entry['page']):
                                    
                                    if element.original_index < min_title_position:
                                        heading_before_title.append({
                                            'text': entry['text'],
                                            'level': entry['level'],
                                            'position': element.original_index,
                                            'page': element.page
                                        })
                
                # If ANY heading appears before title in document order, correction is needed
                if heading_before_title:
                    title_needs_correction = True
            
            # Apply title correction if needed
            if title_needs_correction:
                # Clear the title
                original_title = self.title
                self.title = ""
                
                # Add the former title as the first heading (H1)
                if self.title_elements:
                    # Create a new outline entry for the former title
                    title_element = self.title_elements[0]  # Use first title element
                    new_title_entry = {
                        "level": "H1",  # Former title becomes H1
                        "text": original_title,
                        "page": title_element.page,                        
                    }
                    
                    # Insert at the beginning of outline
                    self.outline.insert(0, new_title_entry)
            
            # Get unique levels in document order (after title correction)
            unique_levels = []
            seen_levels = set()
            
            for entry in self.outline:
                level = entry['level']
                if level not in seen_levels and level != 'TITLE':  # Skip TITLE level
                    unique_levels.append(level)
                    seen_levels.add(level)
            
            # Check if hierarchy correction is needed
            proper_order = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']
            needs_hierarchy_correction = False
            
            for i in range(len(unique_levels)):
                if i < len(proper_order):
                    expected_level = proper_order[i]
                    if unique_levels[i] != expected_level:
                        needs_hierarchy_correction = True
                        break
            
            # Apply hierarchy correction if needed
            if needs_hierarchy_correction or title_needs_correction:
                # Create level mapping
                level_mapping = {}
                available_levels = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']
                
                for i, current_level in enumerate(unique_levels):
                    if i < len(available_levels):
                        new_level = available_levels[i]
                        level_mapping[current_level] = new_level
                    else:
                        level_mapping[current_level] = f"H{i+1}"
                
                # Apply the mapping to all outline entries
                for entry in self.outline:
                    if entry['level'] in level_mapping:
                        original_level = entry['level']
                        new_level = level_mapping[original_level]
                        
                        if new_level != original_level:
                            entry['level'] = new_level
            
        except Exception:
            pass

    def process_input(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Main processing function with comprehensive error handling"""
        try:
            # Step 1: Input validation and sanitization
            if not self._validate_input(data):
                return self._create_error_output("Invalid input data")
            
            # Step 2: Parse and validate text elements
            self._parse_text_elements(data)
            
            if not self.elements:
                return self._create_error_output("No valid text elements found")
            
            # Step 3: Header/Footer detection and removal
            self._detect_and_remove_headers_footers()
            
            if not self.elements:
                return self._create_error_output("No content elements found after header/footer removal")
            
            # Step 4: Font size filtering
            self._filter_by_font_size()
            
            if not self.elements:
                return self._create_error_output("No heading-level text found after filtering")
            
            # Step 5: Group elements by formatting
            self._create_groups()

            # Step 6: Combine consecutive similar elements
            self._combine_consecutive_similar_elements()
            
            # Step 7: Determine TEMPORARY hierarchy (will be reassigned)
            self._determine_hierarchy()
            
            # Step 8: Identify title (this will mark one group as 'TITLE')
            self._identify_title()

            # Step 9: Remove duplicate headings BEFORE hierarchy reassignment
            self._remove_duplicate_headings()

            # Step 10: Reassign hierarchy starting from H1 after title identification
            self._reassign_hierarchy_after_title()

            # Step 11: Create outline
            self._create_outline()
            
            # Step 12: Generate output
            return self._generate_output()
            
        except Exception as e:
            return self._create_error_output(f"Processing failed: {str(e)}")

    def _generate_output(self) -> Dict[str, Any]:
        """Generate the final output dictionary"""
        try:
            # Final duplicate check on outline
            self._verify_no_duplicates_in_outline()
            
            output = {
                "title": self.title if self.title else "",
                "outline": self.outline
            }
            
            return output
            
        except Exception as e:
            return self._create_error_output(f"Failed to generate output: {str(e)}")

    def _verify_no_duplicates_in_outline(self):
        """Final verification - check for any remaining duplicates"""
        try:
            seen_texts = defaultdict(int)
            
            for entry in self.outline:
                normalized_text = entry["text"].strip().lower()
                seen_texts[normalized_text] += 1
            
            # Optional: could implement removal logic here if needed
            # Currently just verifies without removing
            
        except Exception as e:
            pass  # Fail silently to avoid disrupting output generation

    def _create_error_output(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error output format"""
        return {
            "title": "",
            "outline": [],
            "error": error_message
        }

    def classify_headings(input_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Main function to classify headings from input data with header/footer detection
        
        Args:
            input_data: List of dictionaries containing text elements with keys:
                    - text, page, font_size, font, is_bold, is_italic, etc.
            
        Returns:
            Dictionary with format:
            {
                "title": str,           # Document title (empty if none found)
                "outline": [            # List of heading entries
                    {
                        "level": str,   # H1, H2, H3, etc.
                        "text": str,    # Heading text
                        "page": int     # Page number
                    }
                ]
            }
        """
        try:
            classifier = HeadingClassifier()
            result = classifier.process_input(input_data)
            return result
            
        except Exception as e:
            return {
                "title": "",
                "outline": [],
                "error": f"Fatal error: {str(e)}"
            }

    def save_output(result: Dict[str, Any], filename: str = "output-learn-acrobat-2-exp.json"):
        """
        Save the classification result to a JSON file
        
        Args:
            result: The classification result dictionary
            filename: Output filename (default: "output-learn-acrobat-2-exp.json")
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            
        except Exception as e:
            pass  # Fail silently