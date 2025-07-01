import os
from flask import Flask, request, send_file, jsonify
from docx import Document
from bs4 import BeautifulSoup
import tempfile
import traceback

app = Flask(__name__)

API_KEY = os.environ.get('API_KEY')

def require_api_key():
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
    # Log structure for debugging
    print('Parsing HTML...')
    # Add all h1/h2/h3 as headings
    for tag in soup.find_all(['h1', 'h2', 'h3']):
        level = {'h1': 0, 'h2': 1, 'h3': 2}[tag.name]
        doc.add_heading(tag.get_text(), level=level)
    # Add all paragraphs
    for p in soup.find_all('p'):
        doc.add_paragraph(p.get_text())
    # Add all tables (basic)
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        cols = rows[0].find_all(['td', 'th'])
        table_docx = doc.add_table(rows=len(rows), cols=len(cols))
        for i, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            for j, cell in enumerate(cells):
                table_docx.cell(i, j).text = cell.get_text()
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
        if not request.data:
            print('No HTML provided in request')
            return jsonify({'error': 'No HTML provided'}), 400
        html_content = request.data.decode('utf-8')
        docx_path = html_to_standardized_docx(html_content)
        response = send_file(docx_path, as_attachment=True, download_name='protocol.docx')
        @response.call_on_close
        def cleanup():
            os.remove(docx_path)
        return response
    except Exception as e:
        print('Exception occurred:')
        print(traceback.format_exc())
        return jsonify({'error': 'Internal server error', 'details': str(e), 'trace': traceback.format_exc()}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
