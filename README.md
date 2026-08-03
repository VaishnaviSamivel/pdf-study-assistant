# ⚡ AI-Powered PDF Chatbot using RAG (Flask + Groq LLaMA 3)

An interactive, full-stack AI application that transforms uploaded PDF documents into a conversational chatbot ("ChatGPT for PDFs"). Powered by **Flask**, **Groq LLaMA 3 (llama3-8b-8192)**, **RAG (Retrieval-Augmented Generation)**, **`python-dotenv`**, and **SQLite**.

---

## ✨ Key Features

- ⚡ **Groq LLaMA 3 API Integration**: Uses Groq's high-speed inference engine (`llama3-8b-8192`) via `groq` SDK to generate clear, concise answers.
- 📄 **Page-Level PDF Extraction & Chunking**: Extracts text page-by-page from PDFs using `pypdf` / `PyPDF2` into overlapping text chunks with page number metadata.
- 🔍 **RAG Retrieval Engine**: Uses keyword similarity and TF-IDF relevance scoring to retrieve the top 3 most relevant PDF chunks per query.
- 🛡️ **Strict Context Prompting**: Enforces strict context-only answers: *"Answer ONLY using the provided context. If the answer is not in the context, say 'Not found in document'."*
- 🔄 **Hybrid Fallback Architecture**: Automatically falls back to an internal extractive QA engine if `GROQ_API_KEY` is not configured or an API error occurs.
- 💬 **Interactive Chat UI**: Modern dark-theme chat interface with real-time AJAX messaging, "Thinking..." loader, markdown parsing, and expandable **PDF Source Citations** (top 3 chunks).
- 🗄️ **Persistent SQLite History**: Saves conversation history per document across sessions in SQLite (`database.db`).
- ☁️ **Render Cloud Ready**: Configured with `/tmp` storage for file uploads and database persistence.

---

## 🛠️ Tech Stack

- **Backend Framework**: Flask 3.1.3, Werkzeug 3.1.8
- **AI & RAG Engine**: Groq SDK (`groq`), Scikit-Learn, NumPy, PyPDF / PyPDF2
- **Environment & Utilities**: `python-dotenv`, Requests, Tempfile
- **Frontend**: HTML5, Vanilla CSS3 (Custom Glassmorphism), JavaScript (ES6, Marked.js)
- **Production Server**: Gunicorn 23.0.0

---

## 🔑 Environment Variables Setup

Create a `.env` file in the root directory (copied from `.env.example`):

```bash
cp .env.example .env
```

Add your Groq API key:

```env
# Groq API Key (Get your free key at: https://console.groq.com/)
GROQ_API_KEY=your_groq_api_key_here

# Application Configuration
PORT=5000
UPLOAD_FOLDER=/tmp/uploads
DATABASE_PATH=/tmp/database.db
```

> ⚠️ **Security Rule**: Never commit `.env` to GitHub! It is ignored by `.gitignore`.

---

## 📂 Project Structure

```text
pdf-study-assistant/
├── app.py              # Flask server, RAG retrieval, Groq API integration & routes
├── database.db         # Persistent SQLite database (auto-created on startup)
├── requirements.txt    # Production dependencies
├── .env                # Local secrets file (git-ignored)
├── .env.example        # Environment variable template for repository
├── .gitignore          # Git tracking exclusions (.env, *.db, uploads/, __pycache__)
├── static/
│   └── style.css       # Design system, CSS variables & chat bubbles
└── templates/
    └── index.html      # Responsive Chatbot SPA template
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.9 or higher installed.

### 1. Clone Repository & Navigate
```bash
git clone https://github.com/VaishnaviSamivel/pdf-study-assistant.git
cd pdf-study-assistant
```

### 2. Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Local `.env`
Copy `.env.example` to `.env` and add your Groq API key from [https://console.groq.com/](https://console.groq.com/).

### 5. Run the Local Web Server
```bash
python app.py
```
Open your browser and navigate to `http://127.0.0.1:5000`.

---

## 🌐 Render Cloud Deployment

This repository is optimized for deployment on **Render**:

1. Push your code to GitHub.
2. Go to [Render.com](https://render.com) -> **New Web Service**.
3. Connect your repository.
4. Set deployment configuration:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py` (or `gunicorn app:app`)
5. Add Environment Variables in Render settings:
   - `GROQ_API_KEY`: `your_actual_groq_api_key`
   - `UPLOAD_FOLDER`: `/tmp/uploads`
   - `DATABASE_PATH`: `/tmp/database.db`
6. Click **Deploy Web Service**.

---

## 📜 License

This project is open-source under the [MIT License](LICENSE).
