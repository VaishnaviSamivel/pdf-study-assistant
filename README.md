# ⚡ GroqPDF - Ultra-Fast RAG PDF Chatbot ("ChatGPT for PDFs")

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![Groq](https://img.shields.io/badge/Groq-LLaMA--3.1--8b-f55036?style=for-the-badge&logo=groq&logoColor=white)](https://console.groq.com/)
[![License](https://img.shields.io/badge/License-MIT-green.style=for-the-badge)](LICENSE)

An intelligent, full-stack AI web application that transforms uploaded PDF documents into an interactive conversational assistant. Powered by **Flask**, **Groq LLaMA 3.1 (`llama-3.1-8b-instant`)**, **RAG (Retrieval-Augmented Generation)**, and **SQLite**.

---

## 🌟 Recommended Project Names

If you are updating your GitHub repository title, portfolio, or resume, here are catchy name suggestions:

1. ⚡ **GroqPDF** (*Ultra-Fast RAG PDF Chatbot*) – *(Recommended)*
2. 📄 **DocuChat AI** (*Interactive PDF Knowledge Assistant*)
3. 🚀 **PulsePDF AI** (*Lightning RAG Assistant powered by LLaMA 3*)
4. 🧠 **StudyGenie AI** (*ChatGPT for PDF Study Materials*)

---

## ✨ Features

- ⚡ **Ultra-Fast LLaMA 3 Inference**: Powered by Groq's LPUs (`llama-3.1-8b-instant`) for instant response generation.
- 📄 **Page-Level PDF Extraction & Chunking**: Parses PDFs using `pypdf` / `PyPDF2` into overlapping, searchable text chunks with page metadata.
- 🔍 **RAG Retrieval Engine**: Uses keyword relevance and TF-IDF scoring to retrieve the top 3 most relevant PDF chunks per query.
- 🎯 **Strict Context Answering**: Instructs the LLM to answer strictly from retrieved PDF context. Returns `"Not found in document"` if information is absent.
- 🛡️ **Hybrid Fallback QA System**: Automatically falls back to an internal extractive QA engine if the API key is unconfigured or rate-limited.
- 💬 **Modern Glassmorphism UI**: Features real-time AJAX messaging, a `"Thinking..."` spinner loader, markdown rendering, empty question prevention, and 5MB upload size validation.
- 📌 **Expandable PDF Source Citations**: Every assistant response includes page badges and exact text excerpts used to formulate the answer.
- 🗄️ **Persistent SQLite History**: Maintains conversation history for every PDF document across sessions in SQLite (`database.db`).
- ☁️ **Render Cloud Deployment Ready**: Pre-configured with environment variables and `/tmp` directory fallbacks for seamless cloud hosting.

---

## 🛠️ Tech Stack

- **Backend Framework**: Python 3.9+, Flask 3.1.3, Werkzeug 3.1.8
- **AI & RAG Engine**: Groq SDK (`groq`), Scikit-Learn, NumPy, PyPDF / PyPDF2
- **Environment & Storage**: `python-dotenv`, SQLite3, Tempfile
- **Frontend**: HTML5, Vanilla CSS3 (Custom Dark Glassmorphism Theme), JavaScript (ES6, Marked.js)
- **Production WSGI Server**: Gunicorn 23.0.0

---

## 📂 Project Structure

```text
pdf-study-assistant/
├── app.py              # Main Flask server, RAG retrieval engine, Groq SDK & routes
├── database.db         # Persistent SQLite database (auto-created on startup)
├── requirements.txt    # Production dependencies
├── .env                # Local secrets file (git-ignored)
├── .env.example        # Environment variable template for repository
├── .gitignore          # Version control ignore rules (.env, *.db, uploads/, __pycache__)
├── static/
│   └── style.css       # Custom design system, CSS variables, dark theme & chat bubbles
└── templates/
    └── index.html      # Responsive Chatbot Single-Page Application (SPA) layout
```

---

## 🔑 Environment Variables Setup

Follow these steps to set up API keys for local development:

1. **Copy `.env.example` to create `.env`**:
   ```bash
   cp .env.example .env
   ```

2. **Add your Groq API Key in `.env`**:
   ```env
   GROQ_API_KEY=gsk_your_actual_groq_api_key_here
   PORT=5000
   UPLOAD_FOLDER=/tmp/uploads
   DATABASE_PATH=/tmp/database.db
   ```
   *(Get your free API key at [Groq Console](https://console.groq.com/)).*

3. **Security Note**:
   - Never commit your `.env` file to GitHub! It is listed in `.gitignore` to protect your API keys.

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
Copy `.env.example` to `.env` and insert your `GROQ_API_KEY`.

### 5. Run the Local Web Server
```bash
python app.py
```
Open your browser and navigate to:
```text
http://127.0.0.1:5000
```

---

## 🌐 Render Cloud Deployment

This repository is optimized for free production deployment on **Render**:

1. Push your repository to GitHub.
2. Log in to [Render.com](https://render.com) and create a **New Web Service**.
3. Connect your repository (`pdf-study-assistant`).
4. Configure build parameters:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. Add Environment Variables in Render:
   - `GROQ_API_KEY`: `your_actual_groq_api_key`
   - `UPLOAD_FOLDER`: `/tmp/uploads`
   - `DATABASE_PATH`: `/tmp/database.db`
6. Click **Deploy Web Service**.

---

## 📜 Database Schema

The SQLite database (`database.db`) uses two relational tables:

```text
+-----------------------+           +-----------------------+
|       documents       |           |     chat_history      |
+-----------------------+           +-----------------------+
| id (PK)               |1       *  | id (PK)               |
| filename (UNIQUE)     |<----------| doc_id (FK)           |
| file_path             |           | role ('user'/'bot')   |
| upload_time           |           | content               |
| extracted_text        |           | sources_json          |
| word_count            |           | timestamp             |
| chunks_json           |           +-----------------------+
+-----------------------+
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to open an issue or pull request.

---

## 📄 License

This project is open-source under the [MIT License](LICENSE).
