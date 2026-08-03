# ⚡ GroqPDF - Secure Multi-User RAG PDF Assistant ("ChatGPT for PDFs")

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Flask-Login](https://img.shields.io/badge/Flask--Login-0.6.3-4B8BBE?style=for-the-badge&logo=python&logoColor=white)](https://flask-login.readthedocs.io/)
[![Groq](https://img.shields.io/badge/Groq-LLaMA--3.1--8b-f55036?style=for-the-badge&logo=groq&logoColor=white)](https://console.groq.com/)
[![License](https://img.shields.io/badge/License-MIT-green.style=for-the-badge)](LICENSE)

An intelligent, secure multi-user SaaS web application that transforms uploaded PDF documents into interactive, context-aware AI study assistants. Powered by **Flask**, **Flask-Login**, **Groq LLaMA 3 (`llama-3.1-8b-instant`)**, **RAG (Retrieval-Augmented Generation)**, **Flask-WTF**, **Flask-Limiter**, and **SQLite**.

---

## ✨ Key Features & Multi-User Architecture

- 🔐 **Multi-User Authentication System**: Complete user registration (`/register`), login (`/login`), and logout (`/logout`) powered by `Flask-Login` and `werkzeug.security` password hashing.
- 🔑 **Password Reset Token System**: Includes "Forgot Password" token generation and validation (`/forgot-password`, `/reset-password/<token>`).
- 🛡️ **User-Level Data Isolation**: Each user can only view, upload, query, or delete their own private PDF documents. All database queries and file access layers are strictly scoped by `user_id = current_user.id`.
- 🗂️ **Isolated File Storage & Path Traversal Guard**: PDF uploads are saved in user-isolated directories (`uploads/<user_id>/`). Every file path is validated via `os.path.abspath` to prevent directory traversal attacks (`../../etc/passwd`).
- 🛑 **Strict Ownership Validation**: Direct URL or API access to another user's documents returns `HTTP 403 Forbidden`. Unauthenticated API calls return `HTTP 401 JSON`.
- ⚡ **Ultra-Fast LLaMA 3 Inference**: Powered by Groq's LPUs (`llama-3.1-8b-instant`) for instant context-aware question answering.
- 🔍 **RAG Retrieval Engine**: Extracts text page-by-page using `pypdf`, chunking into overlapping windows and retrieving top 3 relevant sections per query.
- 🎯 **Strict Context & Fallback Answering**: Directs the LLM to answer strictly from retrieved context. Includes a fallback extractive QA engine if API keys are unconfigured.
- ⏳ **Rate Limiting & Security Hardening**: Integrates `Flask-Limiter` (10 requests/min per IP/user on `/api/chat`), `Flask-WTF` CSRF protection, session cookie hardening (`HttpOnly`, `SameSite=Lax`), and secure HTTP headers (`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy`).
- 💬 **Modern Glassmorphic Dark UI**: Custom responsive theme with login/register cards, user profile badges, AJAX messaging, markdown rendering, and PDF download buttons.

---

## 🛠️ Tech Stack

- **Backend Framework**: Python 3.9+, Flask 3.1.3, Werkzeug 3.1.8
- **Session & Authentication**: Flask-Login 0.6.3, Flask-WTF 1.2.2, Flask-Limiter 3.10.1
- **AI & RAG Engine**: Groq SDK (`groq`), Google Generative AI (`google.generativeai`), Scikit-Learn, NumPy, PyPDF
- **Environment & Storage**: `python-dotenv`, SQLite3 (with `PRAGMA foreign_keys = ON;`), Tempfile
- **Frontend**: HTML5, Vanilla CSS3 (Custom Dark Glassmorphism Theme), JavaScript (ES6, Marked.js)
- **Production WSGI Server**: Gunicorn 23.0.0

---

## 📂 Project Structure

```text
pdf-study-assistant/
├── app.py                  # Main Flask server, authentication, RAG retrieval engine & security defenses
├── requirements.txt        # Production dependencies (Flask-Login, Flask-WTF, Flask-Limiter, Groq, etc.)
├── .env                    # Local environment variables & secret keys (git-ignored)
├── .env.example            # Environment variable template
├── .gitignore              # Version control ignore rules (.env, *.db, uploads/, __pycache__)
├── static/
│   └── style.css           # Design system, glassmorphism card components, auth forms & chat styling
└── templates/
    ├── index.html          # Main PDF Assistant Chatbot Application UI
    ├── login.html          # User Login Page
    ├── register.html       # User Registration Page (Password strength validation)
    ├── forgot_password.html # Password Reset Link Generator
    └── reset_password.html # Password Reset Token Verification Page
```

---

## 🔑 Environment Variables Setup

Follow these steps to set up API keys and configuration for local development:

1. **Copy `.env.example` to create `.env`**:
   ```bash
   cp .env.example .env
   ```

2. **Configure your environment variables in `.env`**:
   ```env
   SECRET_KEY=your_random_secret_key_here
   GROQ_API_KEY=gsk_your_actual_groq_api_key_here
   PORT=5000
   UPLOAD_FOLDER=/tmp/uploads
   DATABASE_PATH=/tmp/database.db
   ```
   *(Get your free Groq API key at [Groq Console](https://console.groq.com/)).*

---

## 🚀 Quick Start Guide

### 1. Clone the Repository
```bash
git clone https://github.com/VaishnaviSamivel/pdf-study-assistant.git
cd pdf-study-assistant
```

### 2. Set Up Virtual Environment
```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Create `.env` File
Copy `.env.example` to `.env` and fill in your keys.

### 5. Run the Application
```bash
python app.py
```
Open your browser and navigate to:
```text
http://127.0.0.1:5000
```

---

## 🌐 Render Cloud Deployment

This application is ready for production deployment on **Render**:

1. Push your repository to GitHub.
2. Log in to [Render.com](https://render.com) and create a **New Web Service**.
3. Connect your repository (`pdf-study-assistant`).
4. Configure build parameters:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. Add Environment Variables in Render:
   - `SECRET_KEY`: `your_random_secret_key`
   - `GROQ_API_KEY`: `your_actual_groq_api_key`
   - `UPLOAD_FOLDER`: `/tmp/uploads`
   - `DATABASE_PATH`: `/tmp/database.db`
6. Click **Deploy Web Service**.

---

## 📜 Database Schema

The SQLite database uses referential integrity with cascading deletes (`PRAGMA foreign_keys = ON;`):

```text
+-----------------------+           +-----------------------+           +-----------------------+
|         users         |           |       documents       |           |     chat_history      |
+-----------------------+           +-----------------------+           +-----------------------+
| id (PK)               |1       *  | id (PK)               |1       *  | id (PK)               |
| username (UNIQUE)     |<----------| user_id (FK CASCADE)  |<----------| doc_id (FK CASCADE)   |
| email (UNIQUE)        |           | filename              |           | role ('user'/'bot')   |
| password_hash         |           | file_path             |           | content               |
| reset_token           |           | upload_time           |           | sources_json          |
| reset_token_expiry    |           | extracted_text        |           | timestamp             |
| created_at            |           | word_count            |           +-----------------------+
+-----------------------+           | chunks_json           |
                                    +-----------------------+
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to open an issue or pull request.

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
