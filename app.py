import os
import re
import json
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from pypdf import PdfReader

# Initialize the Flask application
app = Flask(__name__)

# Secret key required for Flask session management and flash messages (uses env var if provided)
app.secret_key = os.environ.get("SECRET_KEY", "learning-pdf-app-secret-key")

# Define the folder where uploaded files will be stored locally
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Set maximum file upload size limit (16 MB)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Ensure the upload folder exists on server startup
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Path to the local SQLite database file
DB_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'database.db')

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enables dictionary-style column access
    return conn

def init_db():
    """Creates SQLite database tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Documents table: stores file info, extracted text, summary, quiz & flashcards
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            file_path TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            extracted_text TEXT,
            summary_notes TEXT,
            quiz_questions TEXT,
            flashcards TEXT,
            word_count INTEGER,
            submitted INTEGER DEFAULT 0,
            user_answers TEXT DEFAULT '{}',
            score INTEGER DEFAULT 0
        )
    ''')
    
    # 2. Quiz attempts table: stores score history linked to a document via doc_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percentage INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on app startup
init_db()

# Helper function to check if the uploaded file has a PDF extension
def is_pdf(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

# Helper function to extract text content from a PDF file
def extract_text_from_pdf(file_path):
    """
    Reads a PDF file using pypdf and extracts text from each page.
    """
    try:
        reader = PdfReader(file_path)
        extracted_pages = []
        
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                extracted_pages.append(f"--- Page {page_num} ---\n{page_text.strip()}")
        
        if not extracted_pages:
            return "No readable text found in this PDF document (it may contain scanned images or empty pages)."
            
        return "\n\n".join(extracted_pages)
    
    except Exception as e:
        return f"Error reading PDF file: {str(e)}"

# Simple, beginner-friendly text summarizer function (Pure Python)
def generate_summary_notes(text):
    """
    Generates concise summary notes from text using word-frequency sentence scoring.
    """
    if not text or "No readable text found" in text or "Error reading" in text:
        return ["No summary notes available for this document."]
    
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in raw_sentences if len(s.strip().split()) > 4 and not s.startswith('--- Page')]
    
    if not sentences:
        return ["The document text is too short to generate summary notes."]
    
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 
        'by', 'from', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'it', 'its', 'this', 'that', 'these', 'those', 'as', 'which', 'who', 'whom', 'will',
        'would', 'can', 'could', 'should', 'than', 'then', 'so', 'if', 'not', 'no', 'all', 'any'
    }
    
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    word_freq = {}
    for word in words:
        if word not in stop_words:
            word_freq[word] = word_freq.get(word, 0) + 1
            
    if not word_freq:
        return sentences[:3]
    
    scored_sentences = []
    for idx, sentence in enumerate(sentences):
        sentence_words = re.findall(r'\b[a-zA-Z]{3,}\b', sentence.lower())
        score = sum(word_freq.get(w, 0) for w in sentence_words)
        normalized_score = score / (len(sentence_words) + 1)
        scored_sentences.append((normalized_score, idx, sentence))
        
    num_notes = min(max(3, len(sentences) // 3), 5)
    top_sentences = sorted(scored_sentences, key=lambda item: item[0], reverse=True)[:num_notes]
    top_sentences.sort(key=lambda item: item[1])
    
    return [item[2] for item in top_sentences]

# Simple, beginner-friendly Multiple-Choice Question (MCQ) Generator (Pure Python)
import random

def extract_all_pdf_concepts(text):
    """
    Extracts all key terms, subjects, and concepts directly from ANY PDF text.
    No hardcoded lists or static fallbacks used.
    """
    if not text:
        return []

    concepts = []
    seen = set()

    # 1. Extract subjects/terms matching subject-verb patterns in sentences
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    for s in raw_sentences:
        m = re.search(r'\b([A-Z][a-zA-Z0-9\s]{1,30})\b\s+(is|are|enables|provides|uses|requires|allows|helps|creates|includes|refers to|means|breaks down|break down|converts|produces|contains|stores|absorbs|forms|consists of)\b', s, flags=re.IGNORECASE)
        if m:
            term = m.group(1).strip()
            term = re.sub(r'^(a|an|the)\s+', '', term, flags=re.IGNORECASE).strip()
            term = re.sub(r'\b(\w+)\s+\1\b', r'\1', term, flags=re.IGNORECASE).capitalize()
            if len(term.split()) <= 3 and len(term) >= 3 and term.lower() not in seen:
                seen.add(term.lower())
                concepts.append(term)

    # 2. Extract capitalized terms & prominent nouns from text
    words = re.findall(r'\b[A-Z][a-zA-Z0-9-]{2,}\b', text)
    stop_words = {
        'this', 'that', 'these', 'those', 'with', 'from', 'have', 'has', 'had', 'which', 'where', 
        'when', 'what', 'they', 'their', 'them', 'some', 'other', 'into', 'only', 'also', 'than', 
        'then', 'about', 'each', 'such', 'page', 'type', 'main', 'text', 'first', 'second', 'well', 
        'like', 'back', 'down', 'over', 'more', 'most', 'very', 'living', 'things', 'make', 'using', 
        'used', 'were', 'been', 'being', 'does', 'did', 'done', 'will', 'would', 'could', 'should'
    }

    for w in words:
        w_clean = re.sub(r'^(a|an|the)\s+', '', w, flags=re.IGNORECASE).strip().capitalize()
        if w_clean.lower() not in stop_words and len(w_clean) >= 3 and w_clean.lower() not in seen:
            seen.add(w_clean.lower())
            concepts.append(w_clean)

    # 3. If concepts are sparse, extract key 2-3 word phrases from sentences
    if len(concepts) < 4:
        for s in raw_sentences:
            s_clean = s.strip()
            if len(s_clean.split()) >= 4:
                phrase = ' '.join(s_clean.split()[:3]).rstrip(',.!?').capitalize()
                if phrase.lower() not in seen and len(phrase) >= 3:
                    seen.add(phrase.lower())
                    concepts.append(phrase)

    return concepts

def generate_mcqs(text, difficulty="medium"):
    """
    100% Dynamic MCQ Generator for ANY subject PDF.
    - Zero hardcoded fallback lists or static distractors.
    - All 4 options come 100% from the uploaded PDF text.
    - Context-aware for Science, Math, English, History, Law, CS, etc.
    """
    if not text or "No readable text found" in text or "Error reading" in text:
        text = ""

    # Extract all concepts/terms directly from the PDF text
    pdf_concepts = extract_all_pdf_concepts(text)

    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = []
    for s in raw_sentences:
        s_clean = s.strip()
        if len(s_clean.split()) >= 5 and not s_clean.startswith('--- Page'):
            s_clean = re.sub(r'\b(\w+)\s+\1\b', r'\1', s_clean, flags=re.IGNORECASE)
            sentences.append(s_clean)

    mcq_list = []
    option_letters = ['A', 'B', 'C', 'D']
    used_answers = set()

    for sentence in sentences:
        if len(mcq_list) >= 5:
            break

        match = re.search(r'\b([A-Z][a-zA-Z0-9\s]{1,30})\b\s+(is|are|enables|provides|uses|requires|allows|helps|creates|includes|refers to|means|breaks down|break down|converts|produces|contains|stores|absorbs|forms|consists of)\b\s+(.+)', sentence, flags=re.IGNORECASE)

        if match:
            target_term = match.group(1).strip()
            target_term = re.sub(r'^(a|an|the)\s+', '', target_term, flags=re.IGNORECASE).strip()
            target_term = re.sub(r'\b(\w+)\s+\1\b', r'\1', target_term, flags=re.IGNORECASE).capitalize()
            verb = match.group(2).strip().lower()
            rest = match.group(3).strip().rstrip('.!?')

            if target_term.lower() in used_answers or len(target_term) < 3:
                continue

            used_answers.add(target_term.lower())
            correct_answer = target_term

            if verb in ['is', 'are']:
                question_text = f"Which term describes {rest}?"
            elif verb in ['refers to', 'means']:
                question_text = f"Which term refers to {rest}?"
            elif verb in ['break down', 'breaks down']:
                question_text = f"Which organisms or factors break down {rest}?"
            elif verb in ['converts', 'convert']:
                question_text = f"What process is responsible for converting {rest}?"
            elif verb in ['absorbs', 'absorb']:
                question_text = f"Which component or substance absorbs {rest}?"
            else:
                question_text = f"Which key concept {verb} {rest}?"
        else:
            words = sentence.split()
            if len(words) < 5:
                continue
            cand_term = words[0].capitalize().rstrip(',.!?')
            cand_term = re.sub(r'^(a|an|the)\s+', '', cand_term, flags=re.IGNORECASE).strip().capitalize()
            if cand_term.lower() in used_answers or len(cand_term) < 3:
                continue

            used_answers.add(cand_term.lower())
            correct_answer = cand_term
            rest_sentence = ' '.join(words[1:]).rstrip('.!?')
            question_text = f"Which term is associated with {rest_sentence}?"

        # Build 3 distractors ONLY from pdf_concepts (extracted 100% from THIS PDF!)
        distractors = []
        for concept in pdf_concepts:
            if concept.lower() != correct_answer.lower() and concept.lower() not in [d.lower() for d in distractors]:
                distractors.append(concept)
                if len(distractors) == 3:
                    break

        # If PDF is very short and has <3 other concepts, extract short phrase predicates from other sentences
        if len(distractors) < 3:
            for s in sentences:
                if s != sentence:
                    words = s.split()
                    if len(words) >= 3:
                        phrase = ' '.join(words[:2]).capitalize()
                        if phrase.lower() != correct_answer.lower() and phrase.lower() not in [d.lower() for d in distractors]:
                            distractors.append(phrase)
                            if len(distractors) == 3:
                                break

        # Shuffle correct answer + 3 PDF distractors
        raw_options = [correct_answer] + distractors[:3]
        random.shuffle(raw_options)

        correct_index = raw_options.index(correct_answer)
        correct_letter = option_letters[correct_index]

        formatted_options = [f"{option_letters[i]}) {raw_options[i]}" for i in range(4)]

        mcq_list.append({
            'question_number': len(mcq_list) + 1,
            'question': question_text,
            'options': formatted_options,
            'correct_letter': correct_letter,
            'correct_text': correct_answer
        })

    return mcq_list[:5]





# Simple, beginner-friendly Flashcard Generator (Pure Python)
def generate_flashcards(text):
    """
    Generates 5 study flashcards from extracted PDF text.
    """
    flashcards = []
    
    if text and "No readable text found" not in text and "Error reading" not in text:
        raw_sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in raw_sentences if len(s.strip().split()) > 4 and not s.startswith('--- Page')]
        
        for sentence in sentences:
            if len(flashcards) >= 5:
                break
            
            words = sentence.split()
            if len(words) < 5:
                continue
                
            subject_match = re.search(r'\b([A-Z][a-zA-Z0-9\s]{1,25})\b\s+(is|are|allows|enables|helps|provides|requires|uses)\b', sentence)
            
            if subject_match:
                subject = subject_match.group(1).strip()
                verb = subject_match.group(2).strip()
                rest = sentence.split(subject_match.group(0))[-1].strip()
                
                front_text = f"What is the definition or role of '{subject}'?"
                back_text = f"According to the text: {subject} {verb} {rest.rstrip('.!?')}."
            else:
                front_text = f"Explain Key Concept: '{sentence[:50]}...'" if len(sentence) > 50 else f"Explain Key Concept: '{sentence}'"
                back_text = sentence.rstrip('.!?') + '.'
                
            flashcards.append({
                'id': len(flashcards) + 1,
                'front': front_text,
                'back': back_text
            })
            
    fallbacks = [
        ("What is the main purpose of this PDF study tool?", "To extract text, summarize key points, generate quiz questions, and provide study flashcards."),
        ("How are PDF documents processed locally?", "The Python Flask server saves the PDF file to an 'uploads' folder and reads text using pypdf."),
        ("What makes a sentence important for summary notes?", "Sentences containing frequent document keywords receive higher importance scores."),
        ("How do study flashcards help learners?", "Flashcards enable active recall by testing memory on the front side before revealing the answer on the back."),
        ("What format is used for the practice quiz?", "Multiple-choice questions (MCQs) with 4 options and immediate score evaluation.")
    ]
    
    fb_idx = 0
    while len(flashcards) < 5 and fb_idx < len(fallbacks):
        front, back = fallbacks[fb_idx]
        flashcards.append({
            'id': len(flashcards) + 1,
            'front': front,
            'back': back
        })
        fb_idx += 1
        
    return flashcards[:5]

def format_doc_row(row):
    """Formats a database document row into a template-friendly dictionary."""
    if not row:
        return None
    return {
        'id': row['id'],
        'filename': row['filename'],
        'file_path': row['file_path'],
        'upload_time': row['upload_time'],
        'extracted_text': row['extracted_text'],
        'summary_notes': json.loads(row['summary_notes']) if row['summary_notes'] else [],
        'quiz_questions': json.loads(row['quiz_questions']) if row['quiz_questions'] else [],
        'flashcards': json.loads(row['flashcards']) if row['flashcards'] else [],
        'word_count': row['word_count'],
        'submitted': bool(row['submitted']),
        'user_answers': json.loads(row['user_answers']) if row['user_answers'] else {},
        'score': row['score']
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    init_db()  # Ensure SQLite database tables exist
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part found in the request.', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('Please select a PDF file to upload.', 'error')
            return redirect(request.url)
        
        if file and is_pdf(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            # Save PDF file locally
            file.save(file_path)
            
            # Process PDF: Extract text, summary, quiz, and flashcards
            extracted_text = extract_text_from_pdf(file_path)
            summary_notes = generate_summary_notes(extracted_text)
            quiz_questions = generate_mcqs(extracted_text)
            flashcards = generate_flashcards(extracted_text)
            word_count = len(extracted_text.split())
            upload_time = datetime.now().strftime('%b %d, %Y at %I:%M %p')
            
            # Save / Update entry in SQLite database
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO documents 
                (filename, file_path, upload_time, extracted_text, summary_notes, quiz_questions, flashcards, word_count, submitted, user_answers, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '{}', 0)
                ON CONFLICT(filename) DO UPDATE SET
                    file_path=excluded.file_path,
                    upload_time=excluded.upload_time,
                    extracted_text=excluded.extracted_text,
                    summary_notes=excluded.summary_notes,
                    quiz_questions=excluded.quiz_questions,
                    flashcards=excluded.flashcards,
                    word_count=excluded.word_count,
                    submitted=0,
                    user_answers='{}',
                    score=0
            ''', (
                filename, file_path, upload_time, extracted_text,
                json.dumps(summary_notes), json.dumps(quiz_questions),
                json.dumps(flashcards), word_count
            ))
            
            conn.commit()
            conn.close()
            
            session['active_filename'] = filename
            flash(f"Uploaded '{filename}'! Saved permanently in SQLite database.", 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid file type! Only PDF files (.pdf) are allowed.', 'error')
            return redirect(request.url)

    # GET Request: Fetch all documents & active document data from SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT filename, word_count, upload_time FROM documents ORDER BY id DESC')
    doc_rows = cursor.fetchall()
    documents = {row['filename']: dict(row) for row in doc_rows}
    
    active_filename = session.get('active_filename')
    if not active_filename and documents:
        active_filename = list(documents.keys())[0]
        session['active_filename'] = active_filename
        
    active_doc = None
    score_history = []
    
    if active_filename:
        cursor.execute('SELECT * FROM documents WHERE filename = ?', (active_filename,))
        doc_row = cursor.fetchone()
        if doc_row:
            active_doc = format_doc_row(doc_row)
            cursor.execute('SELECT * FROM quiz_attempts WHERE doc_id = ? ORDER BY id ASC', (active_doc['id'],))
            attempt_rows = cursor.fetchall()
            score_history = [dict(r) for r in attempt_rows]
            
    conn.close()
    
    if not active_doc:
        active_doc = {}

    return render_template('index.html', 
                           documents=documents,
                           active_filename=active_filename,
                           extracted_text=active_doc.get('extracted_text'), 
                           summary_notes=active_doc.get('summary_notes'), 
                           quiz_questions=active_doc.get('quiz_questions'),
                           flashcards=active_doc.get('flashcards'),
                           filename=active_doc.get('filename'),
                           word_count=active_doc.get('word_count', 0),
                           submitted=active_doc.get('submitted', False),
                           score=active_doc.get('score', 0),
                           user_answers=active_doc.get('user_answers', {}),
                           score_history=score_history)

@app.route('/select_doc/<path:filename>')
def select_doc(filename):
    """Switches the active study document to the selected PDF filename."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT filename FROM documents WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        session['active_filename'] = filename
        flash(f"Switched study document to '{filename}'.", 'info')
    else:
        flash(f"Document '{filename}' not found in database.", 'error')
        
    return redirect(url_for('index'))

@app.route('/delete_doc/<path:filename>', methods=['POST'])
def delete_doc(filename):
    """Deletes a document and its linked score history from SQLite database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM documents WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    
    if row:
        doc_id = row['id']
        cursor.execute('DELETE FROM quiz_attempts WHERE doc_id = ?', (doc_id,))
        cursor.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
        
        if session.get('active_filename') == filename:
            cursor.execute('SELECT filename FROM documents ORDER BY id DESC LIMIT 1')
            rem = cursor.fetchone()
            session['active_filename'] = rem['filename'] if rem else None
            
        flash(f"Deleted document '{filename}' from SQLite database.", 'info')
        
    conn.close()
    return redirect(url_for('index'))

@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    """Handles quiz submission and stores attempt permanently in SQLite database."""
    active_filename = session.get('active_filename')
    
    if not active_filename:
        flash('No active study document selected. Please upload a PDF first.', 'error')
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM documents WHERE filename = ?', (active_filename,))
    doc_row = cursor.fetchone()
    
    if not doc_row:
        conn.close()
        flash('Active document not found in database.', 'error')
        return redirect(url_for('index'))
        
    doc_id = doc_row['id']
    quiz_questions = json.loads(doc_row['quiz_questions']) if doc_row['quiz_questions'] else []
    
    score = 0
    user_answers = {}
    
    for mcq in quiz_questions:
        q_num = str(mcq['question_number'])
        selected_option = request.form.get(f'q_{q_num}')
        user_answers[q_num] = selected_option
        
        if selected_option == mcq['correct_letter']:
            score += 1
            
    total_q = len(quiz_questions)
    percentage = int((score / total_q) * 100) if total_q > 0 else 0
    timestamp = datetime.now().strftime('%b %d, %Y at %I:%M %p')
    
    # Update active document submission status in SQLite database
    cursor.execute('''
        UPDATE documents 
        SET submitted = 1, score = ?, user_answers = ? 
        WHERE id = ?
    ''', (score, json.dumps(user_answers), doc_id))
    
    # Insert new record into quiz_attempts table linked by doc_id
    cursor.execute('''
        INSERT INTO quiz_attempts (doc_id, score, total, percentage, timestamp, filename)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (doc_id, score, total_q, percentage, timestamp, active_filename))
    
    conn.commit()
    conn.close()
    
    flash(f"Quiz Submitted! You scored {score}/{total_q} ({percentage}%) on '{active_filename}'. Saved to database!", 'success')
    return redirect(url_for('index'))

@app.route('/reset_quiz', methods=['POST'])
def reset_quiz():
    """Resets the active document's quiz state in SQLite database."""
    active_filename = session.get('active_filename')
    
    if active_filename:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE documents 
            SET submitted = 0, score = 0, user_answers = '{}' 
            WHERE filename = ?
        ''', (active_filename,))
        conn.commit()
        conn.close()
        flash(f"Quiz reset for '{active_filename}'!", 'info')
        
    return redirect(url_for('index'))

@app.route('/clear_history', methods=['POST'])
def clear_history():
    """Clears score history for the active study document in SQLite database."""
    active_filename = session.get('active_filename')
    
    if active_filename:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM documents WHERE filename = ?', (active_filename,))
        row = cursor.fetchone()
        if row:
            cursor.execute('DELETE FROM quiz_attempts WHERE doc_id = ?', (row['id'],))
            conn.commit()
        conn.close()
        flash(f"Score history cleared for '{active_filename}'!", 'info')
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Get port from environment variable (default: 5000 for local development)
    port = int(os.environ.get("PORT", 5000))
    is_debug = os.environ.get("FLASK_ENV") == "development"
    print(f"Starting web server on port {port}... Database path: {DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=is_debug)
