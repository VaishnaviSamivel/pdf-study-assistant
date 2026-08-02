# 📚 PDF Study Assistant

An intelligent, full-stack AI-powered study assistant and interactive learning hub built with Python (Flask) and SQLite. Upload any PDF document—Science, Math, History, Computer Science, Law, and more—and instantly generate summary notes, interactive 3D flashcards, timed mock tests, and subject-aware multiple-choice practice quizzes.

---

## ✨ Features

- 📄 **PDF Text Extraction**: Reads and parses structured text from uploaded PDF documents using `pypdf`.
- 💡 **Extractive Summary Notes**: Analyzes document word frequencies to extract top key takeaways and summary points.
- 🎴 **Interactive 3D Study Flashcards**: 3D flip cards for active recall with intuitive navigation controls (`Flip Card`, `Next`, `Previous`).
- 🎯 **Smart 100% Dynamic MCQ Generator**: Context-aware exam-style questions for **ANY subject**. All 4 options ($A, B, C, D$) are extracted 100% directly from the uploaded PDF text with zero hardcoded static distractors.
- ⏱️ **Timed Mock Test Mode**: Practice under pressure with a live 2-minute countdown timer badge and automatic quiz submission upon timeout.
- 📊 **Score History & Progress Dashboard**: Tracks score percentages, attempt badges, document names, and timestamps for every quiz attempt.
- 📂 **Multi-Document Library**: Upload multiple PDF files, switch between active study workspaces, or remove documents seamlessly.
- 🗄️ **Persistent SQLite Storage**: Built-in SQLite database (`database.db`) maintaining separate study data, flashcards, and score history per document across server restarts.
- 🚀 **Production Ready**: Configured for WSGI servers (`Gunicorn`) and cloud deployment on platforms like Render.

---

## 🛠️ Technology Stack

- **Backend**: Python 3, Flask 3.1.3, SQLite3, PyPDF
- **Frontend**: HTML5, Vanilla CSS3 (Custom Glassmorphism & 3D Transforms), JavaScript (ES6)
- **Production Server**: Gunicorn 23.0.0
- **Version Control**: Git, GitHub

---

## 📂 Project Structure

```text
pdf-study-assistant/
├── app.py              # Flask server, routes, SQLite DB models & MCQ generator
├── database.db         # Persistent SQLite database (auto-created on startup)
├── requirements.txt    # Production dependencies
├── .gitignore          # Version control ignore rules
├── static/
│   └── style.css       # Design system, CSS variables, 3D flip transforms & badges
├── templates/
│   └── index.html      # Responsive Single-Page Application (SPA) layout
└── uploads/            # Local PDF file storage directory
```

---

## 🚀 Quick Start Guide

### Prerequisites
- Python 3.9 or higher installed on your system.

### 1. Clone the Repository
```bash
git clone https://github.com/VaishnaviSamivel/pdf-study-assistant.git
cd pdf-study-assistant
```

### 2. Create a Virtual Environment (Optional but Recommended)
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

### 4. Run the Local Web Server
```bash
python app.py
```

Open your browser and navigate to:
```text
http://127.0.0.1:5000
```

---

## 🌐 Cloud Deployment (Render.com)

This repository is pre-configured for free cloud deployment on **Render**:

1. Push your repository to GitHub.
2. Log in to [Render.com](https://render.com) and create a **New Web Service**.
3. Connect your `pdf-study-assistant` GitHub repository.
4. Set the build parameters:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
5. Click **Create Web Service**. Render will build and launch your live application URL!

---

## 📜 Database Schema

The SQLite database (`database.db`) uses two relational tables:

```text
+-----------------------+           +-----------------------+
|       documents       |           |     quiz_attempts     |
+-----------------------+           +-----------------------+
| id (PK)               |1       *  | id (PK)               |
| filename (UNIQUE)     |<----------| doc_id (FK)           |
| file_path             |           | score                 |
| upload_time           |           | total                 |
| extracted_text        |           | percentage            |
| summary_notes         |           | timestamp             |
| quiz_questions        |           | filename              |
| flashcards            |           +-----------------------+
| word_count            |
| submitted             |
| user_answers          |
| score                 |
+-----------------------+
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/VaishnaviSamivel/pdf-study-assistant/issues).

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
