import os
import re
import json
import secrets
import sqlite3
import tempfile
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, jsonify,
    send_from_directory, abort, make_response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required, current_user
)
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pypdf import PdfReader

# Load local environment variables from .env file
load_dotenv()

# ==========================================
# MODIFIED: Structured Security & Audit Logger
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("pdf_assistant_security")

def get_clean_env(key):
    """Retrieves an environment variable, stripping surrounding quotes or whitespace."""
    val = os.getenv(key)
    if not val:
        return None
    val = val.strip().strip('"').strip("'")
    if not val or val in ("your_key_here", "your_gemini_api_key_here"):
        return None
    return val

GROQ_API_KEY = get_clean_env("GROQ_API_KEY")
GEMINI_API_KEY = get_clean_env("GEMINI_API_KEY")

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

# ==========================================
# MODIFIED: Session Security & Hardening Configuration
# ==========================================
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = (os.environ.get("FLASK_ENV") == "production")

# Set maximum file upload size limit to 10MB
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit

# Upload folder configuration (defaults to /tmp on Render for cloud compatibility)
FALLBACK_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'pdf_chatbot_uploads')
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", FALLBACK_UPLOAD_DIR)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure master upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# SQLite Database Path configuration (defaults to /tmp on Render)
FALLBACK_DB_PATH = os.path.join(tempfile.gettempdir(), 'pdf_chatbot.db')
DB_PATH = os.environ.get("DATABASE_PATH", FALLBACK_DB_PATH)

# ==========================================
# MODIFIED: Flask-Login, CSRF & Rate Limiter Initialization
# ==========================================
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please sign in to access your private PDF documents.'
login_manager.login_message_category = 'info'

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

# ==========================================
# MODIFIED: Secure HTTP Headers Middleware
# ==========================================
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self' https: 'unsafe-inline' 'unsafe-eval'; img-src 'self' data: https:;"
    return response

# ==========================================
# MODIFIED: Unauthenticated API Response Handler (HTTP 401)
# ==========================================
@login_manager.unauthorized_handler
def unauthorized_handler():
    session.clear()
    if request.path.startswith('/api/'):
        logger.warning(f"Unauthorized API access attempt to {request.path} from IP {request.remote_addr}")
        return jsonify({"error": "Unauthorized", "message": "Authentication required to access this resource"}), 401
    flash("Please sign in to access this page.", "info")
    return redirect(url_for('login'))


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handles file uploads exceeding 10MB max content length."""
    flash("File too large. Please upload a PDF file under 10MB.", "error")
    return redirect(url_for("index"))

# ==========================================
# MODIFIED: Database Connection & Foreign Key Enforcement
# ==========================================
def get_db_connection():
    """Establishes SQLite connection with PRAGMA foreign_keys = ON."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# MODIFIED: Multi-User Schema & Automatic Migration
# ==========================================
def init_db():
    """Creates SQLite tables for users, documents (with user_id FK), and chat_history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            reset_token TEXT,
            reset_token_expiry TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    
    # 2. Documents Table linked to users with CASCADE DELETE & UNIQUE(user_id, filename)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            upload_time TEXT NOT NULL,
            extracted_text TEXT,
            word_count INTEGER,
            chunks_json TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    ''')
    # Check if existing documents table has foreign key constraint
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'")
    row = cursor.fetchone()
    if row and row['sql'] and 'FOREIGN KEY' not in row['sql']:
        logger.info("Migrating database schema for foreign key ON DELETE CASCADE support...")
        # Ensure at least one user exists for foreign key validity
        cursor.execute("SELECT COUNT(*) as count FROM users")
        if cursor.fetchone()['count'] == 0:
            default_pass = generate_password_hash("AdminPass123!")
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT INTO users (id, username, email, password_hash, created_at) VALUES (1, 'default_admin', 'admin@example.com', ?, ?)", (default_pass, now_str))

        cursor.execute("ALTER TABLE documents RENAME TO legacy_documents;")
        cursor.execute('''
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                extracted_text TEXT,
                word_count INTEGER,
                chunks_json TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            INSERT INTO documents (id, user_id, filename, file_path, upload_time, extracted_text, word_count, chunks_json)
            SELECT id, 1, filename, file_path, upload_time, extracted_text, word_count, chunks_json FROM legacy_documents;
        ''')
        cursor.execute("DROP TABLE legacy_documents;")

    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_user_filename ON documents(user_id, filename);')

    # 3. Chat History Table linked to documents with CASCADE DELETE
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

# ==========================================
# MODIFIED: User Data Model & Flask-Login User Loader
# ==========================================
class User(UserMixin):
    def __init__(self, id, username, email, password_hash, reset_token=None, reset_token_expiry=None, created_at=None):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.reset_token = reset_token
        self.reset_token_expiry = reset_token_expiry
        self.created_at = created_at

    @staticmethod
    def get_by_id(user_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(**dict(row))
        return None

    @staticmethod
    def get_by_identifier(identifier):
        """Fetch user by username or email (case-insensitive)."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)', (identifier, identifier))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(**dict(row))
        return None

    @staticmethod
    def get_by_email(email):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE LOWER(email) = LOWER(?)', (email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(**dict(row))
        return None

    @staticmethod
    def get_by_reset_token(token):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE reset_token = ?', (token,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return User(**dict(row))
        return None

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

# ==========================================
# MODIFIED: Path Traversal Defense & File Isolation Helpers
# ==========================================
ALLOWED_EXTENSIONS = {'pdf'}

def is_pdf(filename):
    """Checks if the filename has a valid .pdf extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user_upload_dir(user_id):
    """Returns absolute path to user-isolated directory uploads/<user_id>/."""
    user_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def validate_user_file_path(user_id, filename):
    """
    Path Traversal Security Guard:
    Resolves absolute path and verifies it strictly resides inside uploads/<user_id>/ folder.
    Returns absolute path if valid, or None if path traversal attempt is detected.
    """
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        logger.error(f"SECURITY VIOLATION: Path traversal attempt blocked for user_id={user_id}, filename='{filename}'")
        return None

    user_dir = os.path.abspath(get_user_upload_dir(user_id))
    raw_clean = secure_filename(filename)
    if not raw_clean:
        return None

    target_path = os.path.abspath(os.path.join(user_dir, raw_clean))
    if not target_path.startswith(user_dir):
        logger.error(f"SECURITY VIOLATION: Path traversal attack blocked for user_id={user_id}, filename='{filename}'")
        return None
    return target_path


def get_user_document_or_403(filename):
    """
    Strict Ownership Check:
    Fetches document owned by current_user.id. Aborts with HTTP 403 Forbidden if unauthorized.
    """
    if not current_user.is_authenticated:
        abort(401)
        
    user_id = int(current_user.id)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM documents WHERE filename = ? AND user_id = ?', (filename, user_id))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        logger.warning(f"UNAUTHORIZED ACCESS ATTEMPT: User {user_id} tried accessing document '{filename}'")
        abort(403)
        
    return dict(row)


# ==========================================
# PDF Text Extraction & RAG Engine
# ==========================================
def extract_pdf_pages_and_chunks(file_path, chunk_size=700, chunk_overlap=120):
    """Extracts text page by page using pypdf and builds overlapping text chunks."""
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
            
            start = 0
            text_len = len(cleaned_page_text)
            
            while start < text_len:
                end = start + chunk_size
                chunk_str = cleaned_page_text[start:end]
                
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
        logger.error(f"Error extracting PDF text: {e}")
        return f"Error reading PDF file: {str(e)}", [], 0

def retrieve_relevant_chunks(query, chunks, top_k=3):
    """RAG Retrieval Engine: returns top_k most relevant text chunks."""
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
        
        if len(query.strip()) > 5 and query.strip().lower() in chunk_text_lower:
            score += 15.0
            
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
    
    if not selected_chunks and chunks:
        selected_chunks = chunks[:top_k]
        
    return selected_chunks[:3]

def generate_groq_answer(question, context_chunks):
    """Generates an answer using Groq API based on PDF context."""
    groq_key = get_clean_env("GROQ_API_KEY")
    if not groq_key or not Groq:
        return None
        
    if not context_chunks:
        return "No relevant content found in document"
        
    try:
        context_str = "\n\n".join([f"[Page {c['page']}]: {c['text']}" for c in context_chunks[:3]])
        if len(context_str) > 4000:
            context_str = context_str[:4000] + "..."
            
        client = Groq(api_key=groq_key)
        system_prompt = (
            "You are a helpful assistant. Answer ONLY using the provided context. "
            "If the answer is not in the context, say 'Not found in document'. "
            "Do not make up information."
        )
        user_content = f"Context:\n{context_str}\n\nQuestion: {question}"
        
        candidate_models = ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama3-8b-8192"]
        for m_name in candidate_models:
            try:
                response = client.chat.completions.create(
                    model=m_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.3,
                    max_tokens=600
                )
                if response and response.choices and len(response.choices) > 0:
                    return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Groq API Error with model {m_name}: {e}")
            
    except Exception as err:
        logger.error(f"Groq API Exception: {err}")
        
    return None

def generate_gemini_answer(question, context_chunks):
    """Generates answer using Google Gemini API based on PDF context."""
    gemini_key = get_clean_env("GEMINI_API_KEY")
    if not gemini_key or not genai:
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
        logger.error(f"Gemini API Error: {err}")
        
    return None

def generate_fallback_extractive_answer(question, relevant_chunks):
    """Generates structured extractive answer from PDF chunks when LLM APIs are unavailable."""
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
            
        if get_clean_env("GROQ_API_KEY") or get_clean_env("GEMINI_API_KEY"):
            output_lines.append("*💡 Note: API key is configured on server, but API call failed. Displaying extractive fallback.*")
        else:
            output_lines.append("*💡 Note: Set `GROQ_API_KEY` in Render Environment Variables to enable Groq LLaMA 3 AI responses.*")
        
    return "\n".join(output_lines)

def generate_llm_answer(question, relevant_chunks, chat_history=[]):
    """Hybrid System: Groq -> Gemini -> Fallback Extractive QA."""
    top_chunks = relevant_chunks[:3]
    
    groq_answer = generate_groq_answer(question, top_chunks)
    if groq_answer:
        return groq_answer
        
    gemini_answer = generate_gemini_answer(question, top_chunks)
    if gemini_answer:
        return gemini_answer
        
    return generate_fallback_extractive_answer(question, top_chunks)

# ==========================================
# MODIFIED: Authentication Routes
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User Registration Route with Password Strength Validation."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Password Strength Validation (Minimum 8 characters)
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template('register.html')

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('register.html')

        if User.get_by_identifier(username):
            flash("Username is already taken. Please choose another.", "error")
            return render_template('register.html')

        if User.get_by_email(email):
            flash("An account with this email already exists.", "error")
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, created_at))
        conn.commit()
        conn.close()

        logger.info(f"New user registered successfully: username='{username}', email='{email}'")
        flash("Account created successfully! Please sign in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User Login Route."""
    # ==========================================
    # HIGHLIGHTED FIX: Check both Flask-Login and session['user_id']
    # ==========================================
    if current_user.is_authenticated and 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        identifier = request.form.get('username_or_email', '').strip()
        password = request.form.get('password', '')

        user = User.get_by_identifier(identifier)
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            # HIGHLIGHTED FIX: Store user_id in session
            session['user_id'] = user.id
            login_user(user, remember=False)  # Avoid persistent remember_token auto-relogin
            session.permanent = True
            logger.info(f"User signed in successfully: id={user.id}, username='{user.username}'")
            flash(f"Welcome back, {user.username}!", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))

        logger.warning(f"Failed login attempt for identifier='{identifier}' from IP {request.remote_addr}")
        flash("Invalid username/email or password.", "error")

    return render_template('login.html')

@app.route('/logout', methods=['POST', 'GET'])
def logout():
    """
    ==========================================
    HIGHLIGHTED FIX: User Logout Route
    Completely destroys Flask session & deletes session/remember cookies on response
    ==========================================
    """
    user_id = session.get('user_id') or (current_user.id if current_user.is_authenticated else 'unknown')
    logger.info(f"Logging out user: id={user_id}")

    logout_user()
    session.clear()
    
    logger.info(f"DEBUG - Session after clear: {dict(session)}")
    
    flash("You have been signed out successfully.", "info")
    
    response = make_response(redirect(url_for('login')))
    cookie_name = app.config.get('SESSION_COOKIE_NAME', 'session')
    response.delete_cookie(cookie_name)
    response.delete_cookie('remember_token')
    response.set_cookie(cookie_name, '', expires=0)
    response.set_cookie('remember_token', '', expires=0)
    return response


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password Reset Token Generation."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.get_by_email(email)
        
        if user:
            token = secrets.token_urlsafe(32)
            expiry = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
            
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET reset_token = ?, reset_token_expiry = ? WHERE id = ?', (token, expiry, user.id))
            conn.commit()
            conn.close()
            
            reset_url = url_for('reset_password', token=token, _external=True)
            logger.info(f"Password reset link generated for email='{email}': {reset_url}")
            flash(f"Password reset link generated! Use this URL: {reset_url}", "success")
        else:
            flash("If an account exists for that email, a password reset link has been generated.", "info")
            
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Password Reset Token Verification & Password Update."""
    user = User.get_by_reset_token(token)
    if not user:
        flash("Invalid or expired password reset token.", "error")
        return redirect(url_for('login'))
        
    if user.reset_token_expiry:
        expiry_dt = datetime.strptime(user.reset_token_expiry, '%Y-%m-%d %H:%M:%S')
        if datetime.now() > expiry_dt:
            flash("Reset token has expired. Please request a new one.", "error")
            return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template('reset_password.html', token=token, username=user.username)
            
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('reset_password.html', token=token, username=user.username)
            
        password_hash = generate_password_hash(password)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?', (password_hash, user.id))
        conn.commit()
        conn.close()
        
        logger.info(f"Password updated successfully via reset token for user_id={user.id}")
        flash("Password updated successfully! Please sign in with your new password.", "success")
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token, username=user.username)

# ==========================================
# MODIFIED: Protected Multi-User Application Routes
# ==========================================

@app.route('/')
@login_required
def index():
    """Main Chat UI route isolated for current_user.id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Query only documents belonging to logged-in user
    cursor.execute('SELECT id, filename, word_count, upload_time FROM documents WHERE user_id = ? ORDER BY id DESC', (current_user.id,))
    doc_rows = cursor.fetchall()
    documents = [dict(row) for row in doc_rows]
    
    active_filename = session.get('active_filename')
    # Reset active filename if it doesn't belong to current user
    if active_filename and not any(d['filename'] == active_filename for d in documents):
        active_filename = None
        
    if not active_filename and documents:
        active_filename = documents[0]['filename']
        session['active_filename'] = active_filename
        
    active_doc = None
    chat_messages = []
    
    if active_filename:
        cursor.execute('SELECT * FROM documents WHERE filename = ? AND user_id = ?', (active_filename, current_user.id))
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
    
    has_api = bool(get_clean_env("GROQ_API_KEY") or get_clean_env("GEMINI_API_KEY"))
    
    return render_template(
        'index.html',
        documents=documents,
        active_filename=active_filename,
        active_doc=active_doc,
        chat_messages=chat_messages,
        has_api_key=has_api
    )

@app.route('/upload', methods=['POST'])
@login_required
def upload_pdf():
    """Handles PDF file upload into user-isolated directory uploads/<user_id>/."""
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('index'))
        
    file = request.files['file']
    if file.filename == '':
        flash('Please select a PDF file to upload.', 'error')
        return redirect(url_for('index'))
        
    if file and is_pdf(file.filename):
        raw_filename = secure_filename(file.filename)
        if not raw_filename:
            flash('Invalid filename.', 'error')
            return redirect(url_for('index'))

        # Path Traversal Guard
        file_path = validate_user_file_path(current_user.id, raw_filename)
        if not file_path:
            flash('Invalid file path or name.', 'error')
            return redirect(url_for('index'))

        file.save(file_path)
        
        extracted_text, chunks, word_count = extract_pdf_pages_and_chunks(file_path)
        upload_time = datetime.now().strftime('%b %d, %Y at %I:%M %p')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM documents WHERE user_id = ? AND filename = ?', (current_user.id, raw_filename))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE documents
                SET file_path = ?, upload_time = ?, extracted_text = ?, word_count = ?, chunks_json = ?
                WHERE id = ?
            ''', (file_path, upload_time, extracted_text, word_count, json.dumps(chunks), existing['id']))
        else:
            cursor.execute('''
                INSERT INTO documents (user_id, filename, file_path, upload_time, extracted_text, word_count, chunks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (current_user.id, raw_filename, file_path, upload_time, extracted_text, word_count, json.dumps(chunks)))
        
        conn.commit()
        conn.close()

        
        session['active_filename'] = raw_filename
        logger.info(f"User {current_user.id} uploaded PDF '{raw_filename}' ({word_count} words).")
        flash(f"Uploaded '{raw_filename}'! Processed {word_count} words into {len(chunks)} searchable chunks.", 'success')
        return redirect(url_for('index'))
    else:
        flash('Invalid file type! Only .pdf files are allowed.', 'error')
        return redirect(url_for('index'))

@app.route('/download/<path:filename>')
@login_required
def download_doc(filename):
    """Secure File Access Endpoint with Path Traversal Defense & Ownership Check."""
    doc = get_user_document_or_403(filename)
    user_dir = os.path.abspath(get_user_upload_dir(current_user.id))
    
    file_path = validate_user_file_path(current_user.id, doc['filename'])
    if not file_path or not os.path.exists(file_path):
        flash("File not found on server.", "error")
        return redirect(url_for('index'))
        
    return send_from_directory(user_dir, doc['filename'], as_attachment=True)

@app.route('/select_doc/<path:filename>')
@login_required
def select_doc(filename):
    """Switches active document after strict ownership validation."""
    get_user_document_or_403(filename)
    session['active_filename'] = filename
    flash(f"Switched active document to '{filename}'.", 'info')
    return redirect(url_for('index'))

@app.route('/delete_doc/<path:filename>', methods=['POST'])
@login_required
def delete_doc(filename):
    """Deletes a user's document and associated chat history."""
    doc = get_user_document_or_403(filename)
    doc_id = doc['id']
    
    file_path = validate_user_file_path(current_user.id, filename)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logger.error(f"Error removing physical file '{file_path}': {e}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM chat_history WHERE doc_id = ?', (doc_id,))
    cursor.execute('DELETE FROM documents WHERE id = ? AND user_id = ?', (doc_id, current_user.id))
    conn.commit()
    
    if session.get('active_filename') == filename:
        cursor.execute('SELECT filename FROM documents WHERE user_id = ? ORDER BY id DESC LIMIT 1', (current_user.id,))
        rem = cursor.fetchone()
        session['active_filename'] = rem['filename'] if rem else None
        
    conn.close()
    logger.info(f"User {current_user.id} deleted document '{filename}'.")
    flash(f"Deleted document '{filename}'.", 'info')
    return redirect(url_for('index'))

@app.route('/api/chat', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def chat_api():
    """AJAX Chat Endpoint with Rate Limiting (10 req/min) & Data Isolation."""
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    
    if not user_message:
        return jsonify({"answer": "Please enter a valid question", "sources": []}), 400
        
    active_filename = session.get('active_filename')
    if not active_filename:
        return jsonify({"answer": "No active PDF selected. Please upload a PDF first.", "sources": []}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM documents WHERE filename = ? AND user_id = ?', (active_filename, current_user.id))
    doc_row = cursor.fetchone()
    
    if not doc_row:
        conn.close()
        return jsonify({"answer": "Active document not found in your account.", "sources": []}), 404
        
    doc_id = doc_row['id']
    chunks = json.loads(doc_row['chunks_json']) if doc_row['chunks_json'] else []
    
    # 1. Retrieve top 3 relevant chunks
    relevant_chunks = retrieve_relevant_chunks(user_message, chunks, top_k=3)[:3]
    
    # 2. Fetch conversation history for this document
    cursor.execute('SELECT role, content FROM chat_history WHERE doc_id = ? ORDER BY id DESC LIMIT 6', (doc_id,))
    history_rows = cursor.fetchall()
    history = [dict(r) for r in reversed(history_rows)]
    
    # 3. Generate answer via Hybrid system
    answer = generate_llm_answer(user_message, relevant_chunks, chat_history=history)
    timestamp = datetime.now().strftime('%I:%M %p')
    
    sources = [{"page": c["page"], "text": c["text"][:150] + "..." if len(c["text"]) > 150 else c["text"]} for c in relevant_chunks]
    
    # Save conversation history to SQLite
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

@app.route('/api/clear', methods=['POST'])
@login_required
def clear_chat():
    """Clears conversation history for current_user's active document."""
    active_filename = session.get('active_filename')
    if active_filename:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM documents WHERE filename = ? AND user_id = ?', (active_filename, current_user.id))
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
