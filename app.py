import os
from flask import Flask, request, send_file, jsonify
from docx import Document
from bs4 import BeautifulSoup
import tempfile

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

    # Example: Add a title if present
    title = soup.find('h1')
    if title:
        doc.add_heading(title.get_text(), level=0)

    # Example: Add all paragraphs
    for p in soup.find_all('p'):
        doc.add_paragraph(p.get_text())

    # You can add more structure here (tables, headings, etc.)

    # Save to a temporary file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
    doc.save(tmp.name)
    tmp.close()
    return tmp.name

@app.route('/convert', methods=['POST'])
def convert():
    if not require_api_key():
        return jsonify({'error': 'Unauthorized'}), 401
    if not request.data:
        return jsonify({'error': 'No HTML provided'}), 400
    html_content = request.data.decode('utf-8')
    docx_path = html_to_standardized_docx(html_content)
    response = send_file(docx_path, as_attachment=True, download_name='protocol.docx')
    # Clean up temp file after sending
    @response.call_on_close
    def cleanup():
        os.remove(docx_path)
    return response

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
