from flask import Flask, request, jsonify, render_template
import mysql.connector
import os
import re
from werkzeug.utils import secure_filename
from docx import Document
import pdfplumber
import spacy
from dateutil import parser

app = Flask(__name__)

# Load the SpaCy model
nlp = spacy.load("en_core_web_sm")

# Configure MySQL database connection
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="your_password",  # Replace with your database password
    database="ResumeDatabase"  # Replace with your database name
)
cursor = db.cursor()

# Upload folder and allowed file types
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_information_with_nlp(content: str):
    """
    General resume information extraction function
    """
    result = {
        "first_name": "Unknown",
        "last_name": "Unknown",
        "email": "Unknown",
        "university": "Unknown",
        "major": "Unknown",
        "expected_graduation": "Unknown",
        "hiring_status": "pending",
    }

    sections = split_into_sections(content)

    # Extract name
    result.update(extract_name(content))

    # Extract email
    email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", content)
    result["email"] = email_match.group() if email_match else "Unknown"

    # Extract educational background
    education_section = sections.get("education", "")
    education_info = extract_education(education_section)
    result.update(education_info)

    return result

def split_into_sections(content: str):
    """
    Divide your resume into sections based on headings
    """
    section_headers = ["education", "work experience", "skills", "projects"]
    sections = {}
    current_section = "other"
    buffer = []

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(header in line.lower() for header in section_headers):
            if buffer:
                sections[current_section] = "\n".join(buffer)
            current_section = line.lower()
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        sections[current_section] = "\n".join(buffer)

    return sections

def extract_name(content: str):
    """
    Extract Name
    """
    doc = nlp(content)
    name = None
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            name = ent.text.strip()
            break

    if name:
        names = name.split()
        first_name = names[0].capitalize()
        last_name = " ".join(names[1:]).capitalize() if len(names) > 1 else "Unknown"
    else:
        first_name = last_name = "Unknown"

    return {"first_name": first_name, "last_name": last_name}

def extract_education(education_section: str):
    """
    Extracting educational information
    """
    result = {"university": "Unknown", "major": "Unknown", "expected_graduation": "Unknown"}
    school_match = re.search(r"[A-Za-z\s]+University|Institute|College", education_section)
    if school_match:
        result["university"] = school_match.group().strip()

    grad_match = re.search(r"(\d{4})", education_section)
    if grad_match:
        result["expected_graduation"] = f"{grad_match.group()}-12-31"

    return result

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        text = f"Error extracting text from PDF: {str(e)}"
    return text

def extract_text_from_docx(file_path):
    text = ""
    try:
        doc = Document(file_path)
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
    except Exception as e:
        text = f"Error extracting text from DOCX: {str(e)}"
    return text

@app.route('/')
def upload_page():
    return render_template('upload1.html')

@app.route('/upload_resume', methods=['POST'])
def upload_resume():
    try:
        if 'resume' not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files['resume']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            if filename.endswith('.pdf'):
                text_content = extract_text_from_pdf(file_path)
            elif filename.endswith('.docx'):
                text_content = extract_text_from_docx(file_path)
            else:
                return jsonify({"error": "Unsupported file format"}), 400

            info = extract_information_with_nlp(text_content)
            return jsonify({"message": "Resume processed successfully!", "data": info}), 200
        else:
            return jsonify({"error": "Invalid file type"}), 400
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/save_to_db', methods=['POST'])
def save_to_db():
    try:
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        university = request.form.get('university')
        major = request.form.get('major')
        expected_graduation = request.form.get('expected_graduation')

        cursor.execute("""
            INSERT INTO Students (email, first_name, last_name, university, major, expected_graduation, hiring_status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW(), NOW())
            ON DUPLICATE KEY UPDATE
            first_name = VALUES(first_name),
            last_name = VALUES(last_name),
            university = VALUES(university),
            major = VALUES(major),
            expected_graduation = VALUES(expected_graduation),
            updated_at = NOW()
        """, (email, first_name, last_name, university, major, expected_graduation))
        db.commit()

        return jsonify({"message": "Data saved successfully!"}), 200
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5006)