import os
import re
import json
import sqlite3
import tempfile
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.utils import secure_filename
from pypdf import PdfReader

# Load local environment variables from .env file
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Groq SDK Import
try:
    from groq import Groq
except ImportError:
    Groq = None

# Google Generative AI (Gemini) SDK
try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Initialize Flask Application
app = Flask(__name__)

# Secret key required for Flask session management
app.secret_key = os.environ.get("SECRET_KEY", "pdf-chatbot-study-assistant-secret-key")

# Upload folder configuration (defaults to /tmp on Render for cloud compatibility)
FALLBACK_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'pdf_chatbot_uploads')
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", FALLBACK_UPLOAD_DIR)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Set maximum file upload size limit to 5MB
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB limit

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# SQLite Database Path configuration (defaults to /tmp on Render)
FALLBACK_DB_PATH = os.path.join(tempfile.gettempdir(), 'pdf_chatbot.db')
DB_PATH = os.environ.get("DATABASE_PATH", FALLBACK_DB_PATH)

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handles file uploads exceeding 5MB max content length."""
    flash("File too large. Please upload a PDF under 5MB.", "error")
    return redirect(url_for("index"))

def get_db_connection():
    """Establishes and returns a connection to the SQLite database."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Creates SQLite database tables for documents and chat history if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            file_path TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            extracted_text TEXT,
            word_count INTEGER,
            chunks_json TEXT
        )
    ''')
    
    # 2. Chat history table linked to documents
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize DB schema on server startup
init_db()

def is_pdf(filename):
    """Checks if the filename has a .pdf extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def extract_pdf_pages_and_chunks(file_path, chunk_size=700, chunk_overlap=120):
    """
    Extracts text from PDF page by page using pypdf and builds overlapping text chunks
    with page number metadata for RAG retrieval.
    """
    try:
        reader = PdfReader(file_path)
        full_text_list = []
        chunks = []
        chunk_counter = 1
        
        for page_idx, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if not page_text or not page_text.strip():
                continue
            
            cleaned_page_text = re.sub(r'\s+', ' ', page_text).strip()
            full_text_list.append(f"--- Page {page_idx} ---\n{cleaned_page_text}")
            
            # Divide page text into overlapping windows
            start = 0
            text_len = len(cleaned_page_text)
            
            while start < text_len:
                end = start + chunk_size
                chunk_str = cleaned_page_text[start:end]
                
                # Trim to word boundary
                if end < text_len and ' ' in chunk_str[-20:]:
                    last_space = chunk_str.rfind(' ')
                    chunk_str = chunk_str[:last_space]
                    end = start + len(chunk_str)
                
                if len(chunk_str.strip()) > 30:
                    chunks.append({
                        "id": chunk_counter,
                        "page": page_idx,
                        "text": chunk_str.strip()
                    })
                    chunk_counter += 1
                
                start = end - chunk_overlap
                if start >= text_len or end >= text_len:
                    break
                    
        full_text = "\n\n".join(full_text_list)
        word_count = len(full_text.split())
        
        if not chunks and full_text:
            chunks.append({"id": 1, "page": 1, "text": full_text[:1000]})
            
        return full_text, chunks, word_count
    
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return f"Error reading PDF file: {str(e)}", [], 0

def retrieve_relevant_chunks(query, chunks, top_k=3):
    """
    RAG Retrieval Engine: Computes relevance scores for each chunk
    and returns top_k (max 3 chunks only) most relevant text chunks.
    """
    if not chunks or not query.strip():
        return []
    
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
        'by', 'from', 'is', 'was', 'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
        'it', 'its', 'this', 'that', 'these', 'those', 'as', 'which', 'who', 'whom', 'will',
        'would', 'can', 'could', 'should', 'than', 'then', 'so', 'if', 'not', 'no', 'all', 'any',
        'what', 'how', 'why', 'where', 'when', 'tell', 'me', 'about', 'explain', 'give'
    }
    
    query_clean = re.sub(r'[^\w\s]', ' ', query.lower())
    query_tokens = [w for w in query_clean.split() if w not in stop_words and len(w) > 2]
    
    if not query_tokens:
        query_tokens = [w for w in query_clean.split() if len(w) > 1]
        
    scored_chunks = []
    
    for chunk in chunks:
        chunk_text_lower = chunk['text'].lower()
        score = 0.0
        
        # Exact phrase match bonus
        if len(query.strip()) > 5 and query.strip().lower() in chunk_text_lower:
            score += 15.0
            
        # Token frequency scoring
        for token in query_tokens:
            count = len(re.findall(r'\b' + re.escape(token) + r'\b', chunk_text_lower))
            if count > 0:
                score += (count * 3.0) + 1.0
            elif token in chunk_text_lower:
                score += 0.5
                
        if score > 0:
            scored_chunks.append((score, chunk))
            
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    selected_chunks = [item[1] for item in scored_chunks[:top_k]]
    
    # Fallback if no exact keyword match: return first top_k chunks
    if not selected_chunks and chunks:
        selected_chunks = chunks[:top_k]
        
    return selected_chunks[:3]

def generate_groq_answer(question, context_chunks):
    """
    Generates a natural language answer using Groq API (llama3-8b-8192) based strictly on retrieved PDF context.
    Returns None if GROQ_API_KEY is missing or API call fails.
    """
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key or groq_key == "your_key_here" or not Groq:
        return None
        
    if not context_chunks:
        return "No relevant content found in document"
        
    try:
        # Combine top 3 retrieved chunks into a single context string
        context_str = "\n\n".join([f"[Page {c['page']}]: {c['text']}" for c in context_chunks[:3]])
        
        # Limit context length to 4000 characters max
        if len(context_str) > 4000:
            context_str = context_str[:4000] + "..."
            
        client = Groq(api_key=groq_key)
        
        system_prompt = (
            "You are a helpful assistant. Answer ONLY using the provided context. "
            "If the answer is not in the context, say 'Not found in document'. "
            "Do not make up information."
        )
        
        user_content = f"Context:\n{context_str}\n\nQuestion: {question}"
        
        # Groq model list: try llama-3.1-8b-instant or fallback to llama-3.3-70b-versatile
        model_name = "llama-3.1-8b-instant"
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
                max_tokens=600
            )
        except Exception:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,
                max_tokens=600
            )
        
        if response and response.choices and len(response.choices) > 0:
            return response.choices[0].message.content.strip()
            
    except Exception as err:
        print(f"Groq API Error: {err}")
        
    return None

def generate_gemini_answer(question, context_chunks):
    """
    Generates a natural language answer using Google Gemini API based strictly on the retrieved PDF context.
    If context does not contain the answer, returns 'Not found in document'.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key or gemini_key == "your_gemini_api_key_here" or not genai:
        return None
        
    try:
        genai.configure(api_key=gemini_key)
        
        context_str = "\n\n".join([f"[Page {c['page']}]: {c['text']}" for c in context_chunks])
        
        prompt = (
            "You are an AI PDF assistant. Answer the user question based ONLY on the provided PDF context below.\n\n"
            "Strict Rules:\n"
            "1. Answer ONLY using facts directly mentioned in the provided context.\n"
            "2. Do NOT assume, extrapolate, or use outside knowledge.\n"
            "3. If the answer cannot be found in the provided context, reply EXACTLY with: \"Not found in document\".\n\n"
            f"PDF Context:\n{context_str}\n\n"
            f"User Question: {question}\n\n"
            "Answer:"
        )
        
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        
        if response and response.text:
            return response.text.strip()
            
    except Exception as err:
        print(f"Gemini API Error: {err}")
        
    return None

def generate_fallback_extractive_answer(question, relevant_chunks):
    """
    Generates a structured extractive answer from retrieved PDF chunks when LLM API is unavailable or fails.
    """
    if not relevant_chunks:
        return "Not found in document"
    
    question_lower = question.lower()
    is_summary_req = any(w in question_lower for w in ['summary', 'summarize', 'overview', 'main point', 'about'])
    
    output_lines = []
    
    if is_summary_req:
        output_lines.append("### 📋 Document Summary Overview\n")
        output_lines.append("Based on the relevant sections of your PDF document:\n")
        for chunk in relevant_chunks:
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', chunk['text']) if len(s.strip()) > 15]
            if sentences:
                output_lines.append(f"- **Page {chunk['page']}**: {sentences[0]}")
    else:
        output_lines.append(f"### 🔍 Context Excerpts for: *\"{question}\"*\n")
        for idx, chunk in enumerate(relevant_chunks, start=1):
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', chunk['text']) if len(s.strip()) > 15]
            key_excerpt = " ".join(sentences[:3]) if sentences else chunk['text']
            output_lines.append(f"**Section {idx} (Page {chunk['page']})**:")
            output_lines.append(f"> \"{key_excerpt}\"\n")
            
        output_lines.append("*💡 Note: Set `GROQ_API_KEY` in your .env file to enable Groq LLaMA 3 AI responses.*")
        
    return "\n".join(output_lines)

def generate_llm_answer(question, relevant_chunks, chat_history=[]):
    """
    Hybrid System:
    1. If GROQ_API_KEY is available -> call Groq API (llama3-8b-8192) with top 3 chunks.
    2. Else -> try Gemini API if available.
    3. Else (or if API calls fail) -> fallback to existing extractive QA system.
    """
    top_chunks = relevant_chunks[:3]
    
    # 1. Try Groq API
    groq_answer = generate_groq_answer(question, top_chunks)
    if groq_answer:
        return groq_answer
        
    # 2. Try Gemini API
    gemini_answer = generate_gemini_answer(question, top_chunks)
    if gemini_answer:
        return gemini_answer
        
    # 3. Fallback to Extractive QA
    return generate_fallback_extractive_answer(question, top_chunks)

# Flask Web Routes

@app.route('/')
def index():
    """Main Chat UI route."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, filename, word_count, upload_time FROM documents ORDER BY id DESC')
    doc_rows = cursor.fetchall()
    documents = [dict(row) for row in doc_rows]
    
    active_filename = session.get('active_filename')
    if not active_filename and documents:
        active_filename = documents[0]['filename']
        session['active_filename'] = active_filename
        
    active_doc = None
    chat_messages = []
    
    if active_filename:
        cursor.execute('SELECT * FROM documents WHERE filename = ?', (active_filename,))
        doc_row = cursor.fetchone()
        if doc_row:
            active_doc = dict(doc_row)
            cursor.execute('SELECT * FROM chat_history WHERE doc_id = ? ORDER BY id ASC', (active_doc['id'],))
            msg_rows = cursor.fetchall()
            for msg in msg_rows:
                msg_dict = dict(msg)
                msg_dict['sources'] = json.loads(msg_dict['sources_json']) if msg_dict['sources_json'] else []
                chat_messages.append(msg_dict)
                
    conn.close()
    
    has_api = bool(
        (os.getenv("GROQ_API_KEY") and os.getenv("GROQ_API_KEY") != "your_key_here") or
        (os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "your_gemini_api_key_here")
    )
    
    return render_template(
        'index.html',
        documents=documents,
        active_filename=active_filename,
        active_doc=active_doc,
        chat_messages=chat_messages,
        has_api_key=has_api
    )

@app.route('/upload', methods=['POST'])
def upload_pdf():
    """Handles PDF file upload, text extraction, chunking, and SQLite storage."""
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('index'))
        
    file = request.files['file']
    if file.filename == '':
        flash('Please select a PDF file to upload.', 'error')
        return redirect(url_for('index'))
        
    if file and is_pdf(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        extracted_text, chunks, word_count = extract_pdf_pages_and_chunks(file_path)
        upload_time = datetime.now().strftime('%b %d, %Y at %I:%M %p')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO documents (filename, file_path, upload_time, extracted_text, word_count, chunks_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                file_path=excluded.file_path,
                upload_time=excluded.upload_time,
                extracted_text=excluded.extracted_text,
                word_count=excluded.word_count,
                chunks_json=excluded.chunks_json
        ''', (filename, file_path, upload_time, extracted_text, word_count, json.dumps(chunks)))
        
        conn.commit()
        conn.close()
        
        session['active_filename'] = filename
        flash(f"Uploaded '{filename}'! Processed {word_count} words into {len(chunks)} searchable chunks.", 'success')
        return redirect(url_for('index'))
    else:
        flash('Invalid file type! Please upload a valid .pdf file.', 'error')
        return redirect(url_for('index'))

@app.route('/api/chat', methods=['POST'])
def chat_api():
    """AJAX Chat endpoint: accepts question, retrieves top 3 chunks, calls hybrid LLM/extractive system."""
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({"answer": "Please enter a valid question", "sources": []}), 400
        
    active_filename = session.get('active_filename')
    if not active_filename:
        return jsonify({"answer": "No active PDF selected. Please upload a PDF first.", "sources": []}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM documents WHERE filename = ?', (active_filename,))
    doc_row = cursor.fetchone()
    
    if not doc_row:
        conn.close()
        return jsonify({"answer": "Active document not found in database.", "sources": []}), 404
        
    doc_id = doc_row['id']
    chunks = json.loads(doc_row['chunks_json']) if doc_row['chunks_json'] else []
    
    # 1. Retrieve top 3 relevant chunks
    relevant_chunks = retrieve_relevant_chunks(user_message, chunks, top_k=3)[:3]
    
    # 2. Fetch recent conversation history
    cursor.execute('SELECT role, content FROM chat_history WHERE doc_id = ? ORDER BY id DESC LIMIT 6', (doc_id,))
    history_rows = cursor.fetchall()
    history = [dict(r) for r in reversed(history_rows)]
    
    # 3. Generate answer via Hybrid system (Groq -> Gemini -> Fallback QA)
    answer = generate_llm_answer(user_message, relevant_chunks, chat_history=history)
    timestamp = datetime.now().strftime('%I:%M %p')
    
    # Prepare top 3 source citations
    sources = [{"page": c["page"], "text": c["text"][:150] + "..." if len(c["text"]) > 150 else c["text"]} for c in relevant_chunks]
    
    # Save message history to SQLite
    cursor.execute('''
        INSERT INTO chat_history (doc_id, role, content, sources_json, timestamp)
        VALUES (?, 'user', ?, '[]', ?)
    ''', (doc_id, user_message, timestamp))
    
    cursor.execute('''
        INSERT INTO chat_history (doc_id, role, content, sources_json, timestamp)
        VALUES (?, 'assistant', ?, ?, ?)
    ''', (doc_id, answer, json.dumps(sources), timestamp))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "answer": answer,
        "sources": sources,
        "timestamp": timestamp
    })

@app.route('/select_doc/<path:filename>')
def select_doc(filename):
    """Switches active PDF document."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT filename FROM documents WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        session['active_filename'] = filename
        flash(f"Switched active document to '{filename}'.", 'info')
    else:
        flash(f"Document '{filename}' not found.", 'error')
        
    return redirect(url_for('index'))

@app.route('/delete_doc/<path:filename>', methods=['POST'])
def delete_doc(filename):
    """Deletes a document and its chat history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM documents WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    
    if row:
        doc_id = row['id']
        cursor.execute('DELETE FROM chat_history WHERE doc_id = ?', (doc_id,))
        cursor.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        conn.commit()
        
        if session.get('active_filename') == filename:
            cursor.execute('SELECT filename FROM documents ORDER BY id DESC LIMIT 1')
            rem = cursor.fetchone()
            session['active_filename'] = rem['filename'] if rem else None
            
        flash(f"Deleted document '{filename}'.", 'info')
        
    conn.close()
    return redirect(url_for('index'))

@app.route('/api/clear', methods=['POST'])
def clear_chat():
    """Clears conversation history for the active PDF document."""
    active_filename = session.get('active_filename')
    if active_filename:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM documents WHERE filename = ?', (active_filename,))
        row = cursor.fetchone()
        if row:
            cursor.execute('DELETE FROM chat_history WHERE doc_id = ?', (row['id'],))
            conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Chat history cleared."})
        
    return jsonify({"status": "error", "message": "No active document."}), 400

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
