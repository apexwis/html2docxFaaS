from flask import Flask, request, jsonify, send_file
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.shared import qn
from bs4 import BeautifulSoup
import tempfile
import os
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import tempfile
import re
from hyphen import Hyphenator

app = Flask(__name__)

# API Key for authentication
API_KEY = os.getenv('API_KEY', 'de6e0b65-8bd6-43db-844b-b49e0f76d412')

# Initialize German hyphenator for intelligent word breaking
try:
    de_hyphenator = Hyphenator('de_DE')
except:
    # Fallback if German dictionary is not available
    de_hyphenator = None

def add_hyphenation(text, language='de_DE', min_word_length=12):
    """
    Add intelligent hyphenation to text using PyHyphen.
    
    Args:
        text: Input text to hyphenate
        language: Language code (default: 'de_DE')
        min_word_length: Minimum word length to hyphenate (default: 12)
    
    Returns:
        Text with soft hyphens inserted at appropriate positions
    """
    try:
        if not text or not de_hyphenator:
            return text
        
        # Split text into words while preserving spaces and punctuation
        words = re.findall(r'\S+|\s+', text)
        result_words = []
        
        for word in words:
            if re.match(r'^\S+$', word) and len(word) >= min_word_length:
                # This is a word (not whitespace/punctuation) that's long enough
                
                # Skip hyphenation for certain patterns
                if (re.match(r'^[A-Za-z]+[A-Z][a-z]+', word) or  # Mixed case like "apexConsulting"
                    re.match(r'^[A-Z]{2,}', word) or  # All caps abbreviations
                    word.count('-') > 0 or  # Already hyphenated words - SKIP COMPLETELY
                    re.match(r'^\d+', word)):  # Numbers
                    result_words.append(word)
                    continue
                
                try:
                    # Get hyphenation points from PyHyphen
                    syllables = de_hyphenator.syllables(word)
                    if syllables and len(syllables) > 1:
                        # Only add soft hyphens between syllables, not after every syllable
                        # Join syllables with soft hyphens, but be more conservative
                        if len(syllables) <= 3:
                            # For 2-3 syllables, join all with soft hyphens
                            result_words.append('\u00AD'.join(syllables))
                        else:
                            # For 4+ syllables, be more conservative - only add soft hyphens every 2nd syllable
                            conservative_syllables = []
                            for i, syllable in enumerate(syllables):
                                conservative_syllables.append(syllable)
                                # Add soft hyphen after every 2nd syllable (except the last)
                                if i < len(syllables) - 1 and (i + 1) % 2 == 0:
                                    conservative_syllables.append('\u00AD')
                            result_words.append(''.join(conservative_syllables))
                    else:
                        result_words.append(word)
                except:
                    # Fallback: add soft hyphen every 8-10 characters for very long words
                    if len(word) > 15:
                        # Add soft hyphen every 8-10 characters
                        hyphenated = re.sub(r'(\w{8,10})', r'\1\u00AD', word)
                        result_words.append(hyphenated)
                    else:
                        result_words.append(word)
            else:
                result_words.append(word)
        
        return ''.join(result_words)
    except Exception as e:
        print(f"Error in add_hyphenation: {e}")
        return text  # Return original text if hyphenation fails

def require_api_key(f):
    def decorated_function(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
        
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401
        
        token = auth_header.split(' ')[1]
        if token != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def html_to_standardized_docx(html_content):
    """Convert HTML to standardized DOCX with Header.png and Footer.png"""
    soup = BeautifulSoup(html_content, 'html.parser')
    doc = Document()

    # Set page margins - zero for header/footer, normal for content
    section = doc.sections[0]
    section.top_margin = Inches(0)  # Header will be in header area
    section.bottom_margin = Inches(0)  # Footer will be in footer area
    section.left_margin = Inches(0.5)  # Content margin
    section.right_margin = Inches(0.5)  # Content margin
    
    # Add Header.png to header (full width, correct aspect ratio)
    try:
        from PIL import Image as PILImage
        
        # Get original image dimensions to maintain aspect ratio
        pil_img = PILImage.open('Header.png')
        img_width, img_height = pil_img.size
        aspect_ratio = img_height / img_width
        
        # Calculate height to maintain aspect ratio with full page width (8.5 inches)
        header_height = 8.5 * aspect_ratio
        
        header = section.header
        paragraph = header.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        run.add_picture('Header.png', width=Inches(8.5), height=Inches(header_height))
    except Exception as e:
        print(f"Header image error: {e}")
    
    # Add Footer.png to footer (full width, correct aspect ratio)
    try:
        from PIL import Image as PILImage
        
        # Get original image dimensions to maintain aspect ratio
        pil_img = PILImage.open('Footer.png')
        img_width, img_height = pil_img.size
        aspect_ratio = img_height / img_width
        
        # Calculate height to maintain aspect ratio with full page width (8.5 inches)
        footer_height = 8.5 * aspect_ratio
        
        footer = section.footer
        footer_para = footer.paragraphs[0]
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_run = footer_para.add_run()
        footer_run.add_picture('Footer.png', width=Inches(8.5), height=Inches(footer_height))
    except Exception as e:
        print(f"Footer image error: {e}")

    body = soup.body
    if not body:
        body = soup

    for elem in body.children:
        if elem.name is None:
            continue  # Skip text nodes or whitespace
        if elem.name in ['h1', 'h2', 'h3']:
            level = {'h1': 0, 'h2': 1, 'h3': 2}[elem.name]
            heading = doc.add_heading(elem.get_text(), level=level)
            # Set heading font to Arial
            for run in heading.runs:
                run.font.name = 'Arial'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
        elif elem.name == 'p':
            para = doc.add_paragraph(elem.get_text())
            # Set body text font to Arial 11
            for run in para.runs:
                run.font.name = 'Arial'
                run.font.size = Pt(11)
                run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
        elif elem.name == 'table':
            _add_enhanced_table_to_docx(doc, elem)
    return _save_docx_to_tempfile(doc)

def _add_enhanced_table_to_docx(doc, table_elem):
    """Add enhanced table with colspan/rowspan support and styling to DOCX"""
    rows = table_elem.find_all('tr')
    if not rows:
        return
    
    # Calculate max columns considering colspan
    max_cols = 0
    for row in rows:
        cols = 0
        for cell in row.find_all(['td', 'th']):
            colspan = int(cell.get('colspan', 1))
            cols += colspan
        max_cols = max(max_cols, cols)
    
    # Create table
    table_docx = doc.add_table(rows=len(rows), cols=max_cols)
    table_docx.style = 'Table Grid'
    
    # Set table to full width with variable column widths (like HTML example)
    table_docx.autofit = False
    table_docx.allow_autofit = False
    
    # Remove table alignment and margins to make it flush with text
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tbl = table_docx._element
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    
    # Left align table - no indent, let it respect document margins
    # Table will align with text at 0.5" from page edge
    
    # Set table to fixed width (7.0" = 10080 twips)
    tblW = OxmlElement('w:tblW')
    tblW.set(qn('w:w'), '10080')  # 7.0 inches = 10080 twips
    tblW.set(qn('w:type'), 'dxa')  # Fixed width, not percentage
    tblPr.append(tblW)
    
    # Set table cell margins for proper padding and auto-height
    tblCellMar = OxmlElement('w:tblCellMar')
    # Left and right margins for padding inside cells
    left_mar = OxmlElement('w:left')
    left_mar.set(qn('w:w'), '120')  # Slightly more padding
    left_mar.set(qn('w:type'), 'dxa')
    tblCellMar.append(left_mar)
    
    right_mar = OxmlElement('w:right')
    right_mar.set(qn('w:w'), '120')  # Slightly more padding
    right_mar.set(qn('w:type'), 'dxa')
    tblCellMar.append(right_mar)
    
    # Top and bottom padding for better text spacing
    top_mar = OxmlElement('w:top')
    top_mar.set(qn('w:w'), '60')  # More top padding
    top_mar.set(qn('w:type'), 'dxa')
    tblCellMar.append(top_mar)
    
    bottom_mar = OxmlElement('w:bottom')
    bottom_mar.set(qn('w:w'), '60')  # More bottom padding
    bottom_mar.set(qn('w:type'), 'dxa')
    tblCellMar.append(bottom_mar)
    
    tblPr.append(tblCellMar)
    
    # Calculate column widths - intelligent auto-sizing based on content
    # Table width = 7.0 inches
    content_width = 7.0
    
    # Auto-detect optimal column widths based on content
    if max_cols == 5:
        # 5 columns: "Lösung, Beschreibung, Umsetzbarkeit, Angebot, Priorität"
        # First column wider for bold text wrapping
        col_widths = [1.4, 2.3, 1.8, 1.0, 0.5]
    elif max_cols == 4:
        # 4 columns: First 3 narrow (labels), last wide (content)
        col_widths = [1.0, 1.0, 1.0, 4.0]
    elif max_cols == 3:
        # 3 columns: First 2 narrow, last wide
        col_widths = [1.0, 1.0, 5.0]
    elif max_cols == 2:
        # 2 columns: First narrow (label), second wide (content)
        col_widths = [1.5, 5.5]
    else:
        # Equal distribution for other cases
        col_widths = [content_width / max_cols] * max_cols
    
    # Set column widths
    for i, width in enumerate(col_widths):
        if i < max_cols:
            for row in table_docx.rows:
                row.cells[i].width = Inches(width)
    
    # Track used cells for rowspan
    used_cells = set()
    
    for i, row in enumerate(rows):
        cells = row.find_all(['td', 'th'])
        col_idx = 0
        
        for cell in cells:
            # Skip if this cell position is already used by rowspan
            while (i, col_idx) in used_cells:
                col_idx += 1
            
            cell_obj = table_docx.cell(i, col_idx)
            # Pass is_first_column flag for better text wrapping
            cell_obj.text = _extract_cell_text(cell, is_first_column=(col_idx == 0))
            
            # Handle colspan
            colspan = int(cell.get('colspan', 1))
            if colspan > 1:
                # Merge cells horizontally
                for merge_col in range(1, colspan):
                    if col_idx + merge_col < max_cols:
                        cell_obj.merge(table_docx.cell(i, col_idx + merge_col))
            
            # Handle rowspan
            rowspan = int(cell.get('rowspan', 1))
            if rowspan > 1:
                # Mark cells as used for rowspan
                for merge_row in range(1, rowspan):
                    if i + merge_row < len(rows):
                        used_cells.add((i + merge_row, col_idx))
                        # Merge cells vertically
                        cell_obj.merge(table_docx.cell(i + merge_row, col_idx))
            
            # Enhanced cell styling
            # ONLY first row is header (not first column)
            is_header_row = (i == 0)
            is_first_col = (col_idx == 0)
            
            # Set cell background color
            from docx.oxml.shared import OxmlElement, qn
            if is_header_row:
                # Header row - professional blue background
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:val'), 'clear')
                shading_elm.set(qn('w:color'), 'auto')
                shading_elm.set(qn('w:fill'), '2E86AB')  # Professional blue
                cell_obj._tc.get_or_add_tcPr().append(shading_elm)
            else:
                # Data cells - light blue background
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:val'), 'clear')
                shading_elm.set(qn('w:color'), 'auto')
                shading_elm.set(qn('w:fill'), 'F8FAFD')  # Light blue
                cell_obj._tc.get_or_add_tcPr().append(shading_elm)
            
            # Enhanced text styling with proper line breaks
            for paragraph in cell_obj.paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Arial'
                    run.font.size = Pt(9)  # Slightly larger for better readability
                    run.font.bold = is_header_row or is_first_col
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
                    
                    # Header text color (white on blue)
                    if is_header_row:
                        run.font.color.rgb = RGBColor(255, 255, 255)  # White text for header row
                
                # Paragraph alignment and spacing with proper line breaks
                paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER if is_header_row else WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.space_before = Pt(3)  # Better spacing
                paragraph.paragraph_format.space_after = Pt(3)   # Better spacing
                paragraph.paragraph_format.left_indent = Inches(0)  # NO indent - flush with table edge
                paragraph.paragraph_format.right_indent = Inches(0) # NO indent - flush with table edge
                
                # Enable text wrapping and line breaks - especially important for bold text
                paragraph.paragraph_format.widow_control = True
                paragraph.paragraph_format.keep_together = False
                paragraph.paragraph_format.keep_with_next = False
                
                # Additional properties for better text wrapping, especially for bold text
                paragraph.paragraph_format.line_spacing = 1.0  # Single line spacing
                paragraph.paragraph_format.space_before = Pt(2)  # Reduced spacing for better wrapping
                paragraph.paragraph_format.space_after = Pt(2)   # Reduced spacing for better wrapping
                
                # FORCE text wrapping for first column (bold text)
                if is_first_col:
                    paragraph.paragraph_format.widow_control = False  # Allow breaking
                    paragraph.paragraph_format.keep_together = False  # Allow breaking
                    paragraph.paragraph_format.keep_with_next = False  # Allow breaking
                    paragraph.paragraph_format.orphan_control = False  # Allow breaking
            
            # Set cell borders and auto-height
            from docx.oxml import OxmlElement
            from docx.oxml.ns import nsdecls
            from docx.oxml import parse_xml
            
            # Define border style - black borders like HTML
            border_xml = '''
            <w:tcBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>
                <w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>
                <w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>
                <w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>
            </w:tcBorders>
            '''
            
            # Apply borders and auto-height
            tc = cell_obj._tc
            tcPr = tc.get_or_add_tcPr()
            borders = parse_xml(border_xml)
            tcPr.append(borders)
            
            # Enable auto-height for cells and text wrapping
            tcPr.set(qn('w:vAlign'), 'top')  # Align content to top of cell
            tcPr.set(qn('w:noWrap'), '0')  # Enable text wrapping (0 = false, 1 = true)
            
            col_idx += colspan

def _extract_cell_text(cell, is_first_column=False):
    """Extract text from table cell, handling lists and line breaks properly"""
    # Get clean text content
    text = cell.get_text().strip()
    
    # Handle HTML entities and special characters
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    
    # Clean up multiple spaces
    import re
    text = re.sub(r'\s+', ' ', text)
    
    # Handle line breaks - convert to proper line breaks for Word
    text = text.replace('\n', '\n')
    
    # Apply intelligent hyphenation for Word documents
    # Use soft hyphens (Unicode \u00AD) for Word compatibility
    if not is_first_column:
        # Only apply hyphenation to non-first columns
        text = add_hyphenation(text, min_word_length=12)
    
    # FORCE line breaks for first column (bold text) to prevent overflow
    if is_first_column:
        # For first column, just add soft hyphens to existing hyphens - NO additional processing
        if '-' in text:
            # Only add soft hyphens after existing hyphens, nothing else
            text = text.replace('-', '-\u00AD')
    
    return text.strip()

def _save_docx_to_tempfile(doc):
    """Save DOCX document to temporary file and return path"""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    doc.save(tmp.name)
    tmp.close()
    return tmp.name

class NumberedCanvas(canvas.Canvas):
    """Custom canvas with header and footer"""
    
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
    
    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
    
    def save(self):
        """Add page info to each page (page x of y)"""
        num_pages = len(self._saved_page_states)
        for (page_num, state) in enumerate(self._saved_page_states):
            self.__dict__.update(state)
            self.draw_page_info(page_num + 1, num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)
    
    def draw_page_info(self, page_num, total_pages):
        """Draw header and footer on each page"""
        # Draw header (full width, no margins)
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open('Header.png')
            img_width, img_height = pil_img.size
            aspect_ratio = img_height / img_width
            
            # Calculate height to maintain aspect ratio with full page width
            header_height = A4[0] * aspect_ratio
            
            # Draw header at top (y = page height - header height)
            self.drawImage('Header.png', 0, A4[1] - header_height, 
                          width=A4[0], height=header_height)
        except Exception as e:
            print(f"Header image error: {e}")
        
        # Draw footer (full width, no margins)
        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open('Footer.png')
            img_width, img_height = pil_img.size
            aspect_ratio = img_height / img_width
            
            # Calculate height to maintain aspect ratio with full page width
            footer_height = A4[0] * aspect_ratio
            
            # Draw footer at bottom (y = 0)
            self.drawImage('Footer.png', 0, 0, 
                          width=A4[0], height=footer_height)
        except Exception as e:
            print(f"Footer image error: {e}")

def html_to_pdf(html_content):
    """Convert HTML to PDF with full-width header/footer using ReportLab Canvas"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Get body content
    body = soup.body
    if not body:
        body = soup
    
    # Create PDF document with proper content margins
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
    tmp.close()
    
    # Calculate header and footer heights
    header_height = 0
    footer_height = 0
    
    try:
        from PIL import Image as PILImage
        # Header height
        pil_img = PILImage.open('Header.png')
        img_width, img_height = pil_img.size
        aspect_ratio = img_height / img_width
        header_height = A4[0] * aspect_ratio
        
        # Footer height
        pil_img = PILImage.open('Footer.png')
        img_width, img_height = pil_img.size
        aspect_ratio = img_height / img_width
        footer_height = A4[0] * aspect_ratio
    except Exception as e:
        print(f"Image processing error: {e}")
        header_height = 0.5 * inch
        footer_height = 0.5 * inch
    
    # Create document with margins for header/footer
    doc = SimpleDocTemplate(tmp.name, 
                          pagesize=A4,
                          topMargin=header_height + 0.5*inch,
                          bottomMargin=footer_height + 0.5*inch,
                          leftMargin=0.5*inch,
                          rightMargin=0.5*inch)
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6,
        fontName='Helvetica'
    )
    
    # Build content
    story = []
    
    for elem in body.children:
        if elem.name is None:
            continue
        if elem.name in ['h1']:
            para = Paragraph(elem.get_text(), title_style)
            story.append(para)
        elif elem.name in ['h2', 'h3']:
            level = {'h2': 1, 'h3': 2}[elem.name]
            para = Paragraph(elem.get_text(), heading_style)
            story.append(para)
        elif elem.name == 'p':
            para = Paragraph(elem.get_text(), normal_style)
            story.append(para)
        elif elem.name == 'table':
            try:
                table_data = _convert_html_table_to_reportlab(elem)
                if table_data:
                    # Calculate column widths - intelligent auto-sizing based on content
                    # Count actual cells in the first row (handle both strings and Paragraph objects)
                    if table_data and len(table_data) > 0:
                        first_row = table_data[0]
                        num_cols = len(first_row)
                    else:
                        num_cols = 4
                    # Table width = 7.0 inches
                    content_width = 7.0 * inch
                    
                    # Auto-detect optimal column widths based on content
                    if num_cols == 5:
                        # 5 columns: "Lösung, Beschreibung, Umsetzbarkeit, Angebot, Priorität"
                        # First column wider for bold text wrapping
                        col_widths = [1.4*inch, 2.3*inch, 1.8*inch, 1.0*inch, 0.5*inch]
                    elif num_cols == 4:
                        # 4 columns: First 3 narrow (labels), last wide (content)
                        col_widths = [1.0*inch, 1.0*inch, 1.0*inch, 4.0*inch]
                    elif num_cols == 3:
                        # 3 columns: First 2 narrow, last wide
                        col_widths = [1.0*inch, 1.0*inch, 5.0*inch]
                    elif num_cols == 2:
                        # 2 columns: First narrow (label), second wide (content)
                        col_widths = [1.5*inch, 5.5*inch]
                    else:
                        # Equal distribution for other cases
                        col_widths = [content_width / num_cols] * num_cols
                    
                    # Left align the table
                    # Create table with automatic row height adjustment
                    table = Table(table_data, repeatRows=1, colWidths=col_widths, hAlign='LEFT')
                    
                    # Enable automatic row height calculation
                    # Don't set _argH to None as it causes errors - let ReportLab handle it automatically
                    
                    # Professional table styling with intelligent text wrapping
                    table_style = [
                        # Header row styling - ultra thin and elegant
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86AB')),  # Professional blue
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, 0), 9),   # Slightly larger for readability
                        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                        ('TOPPADDING', (0, 0), (-1, 0), 8),   # Increased padding for better spacing
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 8), # Increased padding for better spacing
                        ('LEFTPADDING', (0, 0), (-1, 0), 8),
                        ('RIGHTPADDING', (0, 0), (-1, 0), 8),
                        
                        # Data rows styling - better text wrapping and spacing
                        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 1), (-1, -1), 9),   # Larger text for better readability
                        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                        ('VALIGN', (0, 1), (-1, -1), 'TOP'),
                        ('TOPPADDING', (0, 1), (-1, -1), 8),  # Increased padding for wrapped text
                        ('BOTTOMPADDING', (0, 1), (-1, -1), 8), # Increased padding for wrapped text
                        ('LEFTPADDING', (0, 1), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 1), (-1, -1), 8),
                        
                        # Light blue background for all data cells (like HTML #f8fafd)
                        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F8FAFD')),
                        
                        # Black borders like HTML example
                        ('GRID', (0, 0), (-1, -1), 1, colors.black),
                        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2E86AB')),
                        
                    # First column styling - bold text with better wrapping
                    ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 1), (0, -1), 8),  # Slightly smaller font for better wrapping
                    ('TOPPADDING', (0, 1), (0, -1), 10),  # More padding for bold text
                    ('BOTTOMPADDING', (0, 1), (0, -1), 10),  # More padding for bold text
                    ]
                    
                    table.setStyle(TableStyle(table_style))
                    story.append(table)
                    story.append(Spacer(1, 0.3*inch))
            except Exception as e:
                print(f"Table processing error: {e}")
                # Continue with other elements if table processing fails
    
    # Build PDF with custom canvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print('PDF created at', tmp.name)
    return tmp.name

def _convert_html_table_to_reportlab(table_elem):
    """Convert HTML table to ReportLab table data format with intelligent text wrapping"""
    try:
        rows = table_elem.find_all('tr')
        if not rows:
            return []
        
        table_data = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            row_data = []
            for col_idx, cell in enumerate(cells):
                # Pass is_first_column flag for better text wrapping
                cell_text = _extract_cell_text(cell, is_first_column=(col_idx == 0))
                # Create Paragraph objects for better text wrapping
                if len(cell_text) > 30 or col_idx == 0:  # Always wrap first column (bold text)
                    # Use ReportLab Paragraph for intelligent wrapping
                    from reportlab.lib.styles import getSampleStyleSheet
                    styles = getSampleStyleSheet()
                    normal_style = styles['Normal']
                    normal_style.fontSize = 9
                    normal_style.fontName = 'Helvetica'
                    normal_style.leading = 11  # Line spacing
                    normal_style.alignment = 0  # Left align
                    normal_style.wordWrap = 'LTR'  # Enable word wrapping
                    normal_style.splitLongWords = 1  # Allow splitting long words
                    
                    # FORCE wrapping for first column (bold text)
                    if col_idx == 0:
                        normal_style.splitLongWords = 1  # Force word splitting
                        normal_style.wordWrap = 'LTR'  # Force left-to-right wrapping
                    
                    # Apply intelligent hyphenation using PyHyphen
                    hyphenated_text = add_hyphenation(cell_text, min_word_length=10)
                    
                    # Create paragraph with proper wrapping and hyphenation
                    para = Paragraph(hyphenated_text, normal_style)
                    row_data.append(para)
                else:
                    row_data.append(cell_text)
            table_data.append(row_data)
        
        return table_data
    except Exception as e:
        print(f"Error in _convert_html_table_to_reportlab: {e}")
        return []

@app.route('/', methods=['GET'])
def welcome_page():
    """Welcome page for the HTML to DOCX/PDF Converter API"""
    html_content = """
    <!DOCTYPE html>
    <html lang="de">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Apex PDF/Word FaaS - HTML to DOCX/PDF Converter</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            
            .container {
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                padding: 40px;
                max-width: 800px;
                width: 100%;
            }
            
            .header {
                text-align: center;
                margin-bottom: 40px;
            }
            
            .logo {
                font-size: 2.5em;
                font-weight: bold;
                background: linear-gradient(45deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 10px;
            }
            
            .subtitle {
                color: #666;
                font-size: 1.2em;
                margin-bottom: 20px;
            }
            
            .description {
                color: #555;
                line-height: 1.6;
                margin-bottom: 30px;
                text-align: center;
            }
            
            .api-section {
                background: #f8f9fa;
                border-radius: 15px;
                padding: 30px;
                margin-bottom: 30px;
            }
            
            .api-title {
                color: #333;
                font-size: 1.5em;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
            }
            
            .api-icon {
                background: #667eea;
                color: white;
                width: 40px;
                height: 40px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 15px;
                font-weight: bold;
            }
            
            .endpoint {
                background: #2d3748;
                color: #e2e8f0;
                padding: 15px;
                border-radius: 10px;
                font-family: 'Courier New', monospace;
                margin: 15px 0;
                border-left: 4px solid #667eea;
            }
            
            .method {
                color: #48bb78;
                font-weight: bold;
            }
            
            .security-badge {
                background: #fed7d7;
                color: #c53030;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 0.9em;
                font-weight: bold;
                display: inline-block;
                margin: 10px 0;
            }
            
            .features {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }
            
            .feature {
                background: white;
                padding: 20px;
                border-radius: 15px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.08);
                text-align: center;
            }
            
            .feature-icon {
                font-size: 2em;
                margin-bottom: 15px;
            }
            
            .feature-title {
                font-weight: bold;
                color: #333;
                margin-bottom: 10px;
            }
            
            .feature-desc {
                color: #666;
                font-size: 0.9em;
            }
            
            .footer {
                text-align: center;
                color: #888;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">Apex PDF/Word FaaS</div>
                <div class="subtitle">HTML to DOCX/PDF Converter</div>
                <div class="description">
                    Professioneller Service zur Konvertierung von HTML-Inhalten in DOCX- und PDF-Dokumente mit benutzerdefinierten Headern und Fußzeilen.
                </div>
            </div>
            
            <div class="api-section">
                <div class="api-title">
                    <div class="api-icon">API</div>
                    API Endpoint
                </div>
                
                <div class="endpoint">
                    <span class="method">POST</span> /convert
                </div>
                
                <div class="security-badge">🔒 API Key geschützt</div>
                
                <p><strong>Verwendung:</strong></p>
                <ul style="margin: 15px 0; padding-left: 20px; color: #555;">
                    <li>Senden Sie HTML-Inhalt als JSON oder Raw Data</li>
                    <li>Spezifizieren Sie das gewünschte Format (docx/pdf)</li>
                    <li>Authentifizierung über Bearer Token erforderlich</li>
                </ul>
                
                <p><strong>Beispiel Request:</strong></p>
                <div class="endpoint">
                    {<br>
                    &nbsp;&nbsp;"html": "&lt;h1&gt;Mein Dokument&lt;/h1&gt;&lt;p&gt;Inhalt...&lt;/p&gt;",<br>
                    &nbsp;&nbsp;"format": "docx"<br>
                    }
                </div>
            </div>
            
            <div class="features">
                <div class="feature">
                    <div class="feature-icon">📄</div>
                    <div class="feature-title">DOCX Export</div>
                    <div class="feature-desc">Professionelle Word-Dokumente mit Tabellen, Formatierung und Styling</div>
                </div>
                
                <div class="feature">
                    <div class="feature-icon">📋</div>
                    <div class="feature-title">PDF Export</div>
                    <div class="feature-desc">Hochwertige PDF-Dokumente mit benutzerdefinierten Headern und Fußzeilen</div>
                </div>
                
                <div class="feature">
                    <div class="feature-icon">🎨</div>
                    <div class="feature-title">Custom Styling</div>
                    <div class="feature-desc">Automatische Header/Footer-Integration und professionelle Tabellenformatierung</div>
                </div>
                
                <div class="feature">
                    <div class="feature-icon">🔐</div>
                    <div class="feature-title">Sicher</div>
                    <div class="feature-desc">API Key-basierte Authentifizierung für sichere Nutzung</div>
                </div>
            </div>
            
            <div class="footer">
                <p>Powered by <strong>ApexAI</strong> | Elevate Solutions GmbH</p>
                <p>Ihr Vorsprung durch KI.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.route('/convert', methods=['POST'])
@require_api_key
def convert():
    """Convert HTML to DOCX or PDF based on request format"""
    try:
        # Try to get JSON data first
        json_data = request.get_json()
        if json_data:
            html_content = json_data.get('html', '')
            format_type = json_data.get('format', 'docx').lower()
            
            if not html_content:
                print('No HTML provided in request')
                return jsonify({'error': 'No HTML provided'}), 400
        else:
            # Fallback to raw data for backward compatibility
            if not request.data:
                print('No HTML provided in request')
                return jsonify({'error': 'No HTML provided'}), 400
            html_content = request.data.decode('utf-8')
            format_type = 'docx'
        
        if not html_content:
            print('No HTML content found')
            return jsonify({'error': 'No HTML content found'}), 400
        
        # Convert based on format
        if format_type in ['pdf']:
            output_path = html_to_pdf(html_content)
            download_name = 'document.pdf'
            mimetype = 'application/pdf'
        else:  # Default to DOCX for 'docx', 'word', or any other format
            output_path = html_to_standardized_docx(html_content)
            download_name = 'document.docx'
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        return send_file(output_path, as_attachment=True, download_name=download_name, mimetype=mimetype)
        
    except Exception as e:
        print(f"Conversion error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
