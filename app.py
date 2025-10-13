import os
from flask import Flask, request, send_file, jsonify
from docx import Document
from bs4 import BeautifulSoup
import tempfile
import traceback
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Frame, PageTemplate
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.platypus.doctemplate import BaseDocTemplate
import base64

app = Flask(__name__)

API_KEY = os.environ.get('API_KEY')

def require_api_key():
    # Temporär deaktiviert für Tests - entferne diese Zeile für Produktion
    if not API_KEY:
        return True
    
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return False
    token = auth.split(' ', 1)[1]
    return token == API_KEY

# Example: Standardize the DOCX structure
# You can expand this function to match your protocol's needs
def html_to_standardized_docx(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    doc = Document()

    # Set page margins - keep content margins but allow full-width header/footer
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
            cell_obj.text = cell.get_text()
            
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
            is_header = cell.name == 'th'
            is_first_col = col_idx == 0
            
            # Set cell background color
            if is_header:
                # Header cells - professional blue
                from docx.oxml.shared import OxmlElement, qn
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:val'), 'clear')
                shading_elm.set(qn('w:color'), 'auto')
                shading_elm.set(qn('w:fill'), '2E86AB')  # Professional blue
                cell_obj._tc.get_or_add_tcPr().append(shading_elm)
            elif is_first_col:
                # First column - light gray background
                shading_elm = OxmlElement('w:shd')
                shading_elm.set(qn('w:val'), 'clear')
                shading_elm.set(qn('w:color'), 'auto')
                shading_elm.set(qn('w:fill'), 'E9ECEF')  # Light gray
                cell_obj._tc.get_or_add_tcPr().append(shading_elm)
            
            # Enhanced text styling
            for paragraph in cell_obj.paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Arial'
                    run.font.size = Pt(12 if is_header else 11)
                    run.font.bold = is_header or is_first_col
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Arial')
                    
                    # Header text color
                    if is_header:
                        run.font.color.rgb = RGBColor(255, 255, 255)  # White text for headers
                
                # Paragraph alignment and spacing
                paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER if is_header else WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.space_before = Pt(6)
                paragraph.paragraph_format.space_after = Pt(6)
                paragraph.paragraph_format.left_indent = Inches(0.1)
                paragraph.paragraph_format.right_indent = Inches(0.1)
            
            # Set cell borders
            from docx.oxml import OxmlElement
            from docx.oxml.ns import nsdecls
            from docx.oxml import parse_xml
            
            # Define border style
            border_xml = '''
            <w:tcBorders xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:top w:val="single" w:sz="4" w:space="0" w:color="DEE2E6"/>
                <w:left w:val="single" w:sz="4" w:space="0" w:color="DEE2E6"/>
                <w:bottom w:val="single" w:sz="4" w:space="0" w:color="DEE2E6"/>
                <w:right w:val="single" w:sz="4" w:space="0" w:color="DEE2E6"/>
            </w:tcBorders>
            '''
            
            # Apply borders
            tc = cell_obj._tc
            tcPr = tc.get_or_add_tcPr()
            borders = parse_xml(border_xml)
            tcPr.append(borders)
            
            col_idx += colspan

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
    except:
        pass
    
    # Create document with content area between header and footer
    doc = SimpleDocTemplate(tmp.name, pagesize=A4, 
                          topMargin=header_height + 0.2*inch, 
                          bottomMargin=footer_height + 0.2*inch,
                          leftMargin=0.5*inch, 
                          rightMargin=0.5*inch)
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        spaceAfter=12,
        alignment=TA_LEFT
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        spaceAfter=8,
        alignment=TA_LEFT
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        spaceAfter=6,
        alignment=TA_LEFT
    )
    
    # Build content
    story = []
    
    # Process HTML elements
    for elem in body.children:
        if elem.name is None:
            continue  # Skip text nodes or whitespace
        
        if elem.name in ['h1', 'h2', 'h3']:
            level = {'h1': title_style, 'h2': heading_style, 'h3': heading_style}[elem.name]
            para = Paragraph(elem.get_text(), level)
            story.append(para)
        elif elem.name == 'p':
            para = Paragraph(elem.get_text(), normal_style)
            story.append(para)
        elif elem.name == 'table':
            table_data = _convert_html_table_to_reportlab(elem)
            if table_data:
                table = Table(table_data, repeatRows=1)  # Repeat header on new pages
                
                # Professional table styling
                table_style = [
                    # Header row styling
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E86AB')),  # Professional blue
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('LEFTPADDING', (0, 0), (-1, 0), 15),
                    ('RIGHTPADDING', (0, 0), (-1, 0), 15),
                    
                    # Data rows styling
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 11),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('VALIGN', (0, 1), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 1), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
                    ('LEFTPADDING', (0, 1), (-1, -1), 15),
                    ('RIGHTPADDING', (0, 1), (-1, -1), 15),
                    
                    # Alternating row colors
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
                    
                    # Borders
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DEE2E6')),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#2E86AB')),
                    
                    # First column styling (labels)
                    ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                    ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#E9ECEF')),
                ]
                
                table.setStyle(TableStyle(table_style))
                story.append(table)
                story.append(Spacer(1, 0.3*inch))
    
    # Build PDF with custom canvas
    doc.build(story, canvasmaker=NumberedCanvas)
    print('PDF created at', tmp.name)
    return tmp.name

def _convert_html_table_to_reportlab(table_elem):
    """Convert HTML table to ReportLab table format with enhanced parsing"""
    rows = table_elem.find_all('tr')
    if not rows:
        return None
    
    table_data = []
    for row in rows:
        cells = row.find_all(['td', 'th'])
        row_data = []
        for cell in cells:
            # Handle colspan by adding empty cells
            colspan = int(cell.get('colspan', 1))
            
            # Enhanced text extraction - handle lists and formatting
            cell_text = _extract_cell_text(cell)
            row_data.append(cell_text)
            
            # Add empty cells for colspan
            for _ in range(colspan - 1):
                row_data.append('')
        table_data.append(row_data)
    
    return table_data

def _extract_cell_text(cell):
    """Extract and format cell text, handling lists and special formatting"""
    # Handle lists
    lists = cell.find_all(['ul', 'ol'])
    if lists:
        list_texts = []
        for ul in lists:
            items = ul.find_all('li')
            if items:
                item_texts = [item.get_text().strip() for item in items]
                list_texts.append(' • '.join(item_texts))
        return ' | '.join(list_texts)
    
    # Handle line breaks
    br_tags = cell.find_all('br')
    if br_tags:
        # Replace <br> with line breaks
        text = str(cell)
        for br in br_tags:
            text = text.replace(str(br), '\n')
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text().strip()
    
    # Regular text extraction
    return cell.get_text().strip()

def _save_docx_to_tempfile(doc):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    doc.save(tmp.name)
    tmp.close()
    print('DOCX created at', tmp.name)
    return tmp.name

@app.before_request
def log_request_info():
    print(f"Received {request.method} request for {request.url}")
    print(f"Headers: {dict(request.headers)}")
    print(f"Body: {request.get_data(as_text=True)[:1000]}")  # Print up to 1000 chars

@app.route('/convert', methods=['POST'])
def convert():
    try:
        if not require_api_key():
            print('Unauthorized request')
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Try to parse JSON body first
        try:
            json_data = request.get_json()
            if json_data:
                html_content = json_data.get('html', '')
                format_type = json_data.get('format', 'docx').lower()
            else:
                # Fallback to raw data for backward compatibility
                if not request.data:
                    print('No HTML provided in request')
                    return jsonify({'error': 'No HTML provided'}), 400
                html_content = request.data.decode('utf-8')
                format_type = 'docx'
        except:
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
            download_name = 'protocol.pdf'
            mimetype = 'application/pdf'
        elif format_type in ['word', 'docx']:
            output_path = html_to_standardized_docx(html_content)
            download_name = 'protocol.docx'
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            print(f'Unsupported format: {format_type}')
            return jsonify({'error': f'Unsupported format: {format_type}. Use "pdf" or "word"/"docx"'}), 400
        
        response = send_file(output_path, as_attachment=True, download_name=download_name, mimetype=mimetype)
        
        @response.call_on_close
        def cleanup():
            os.remove(output_path)
        
        return response
    except Exception as e:
        print('Exception occurred:')
        print(traceback.format_exc())
        return jsonify({'error': 'Internal server error', 'details': str(e), 'trace': traceback.format_exc()}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')