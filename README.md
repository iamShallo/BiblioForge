# BiblioForge

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B)
![Google Gemini](https://img.shields.io/badge/AI-Google_Gemini-8E75B2)
![Academic](https://img.shields.io/badge/Exam-Big_Data_Management-brightgreen)

**BiblioForge** is an AI-driven pipeline designed to clean raw book titles, enrich them with trusted web metadata, and generate concise, editorial insights. 

Built as an exam project for the **Big Data Management** course by **Francesco Caldarelli** and **Claudio Cozzolino**.

---

## Key Features

* ** Automated Data Cleaning:** Transforms noisy, unstructured catalog titles into clean, search-friendly strings.
* ** Smart Enrichment:** Fetches reliable metadata via the Google Books API, with a best-effort fallback to scrape Goodreads for ratings and snippets.
* ** AI-Powered Insights:** Integrates with Google Gemini to generate dynamic summaries, smart tags, and transparency notes (includes a deterministic local fallback if no API key is provided).
* ** Human-in-the-Loop (HITL):** Features a sleek **Streamlit** dashboard allowing human operators to review, edit, approve, or re-run AI-processed books before final database insertion.

---

## Project Architecture

The codebase is organized using a clean, modular structure separating concerns across views, controllers, and services:

```text
biblioforge/
├── main.py                       # CLI entry point (Run dashboard or ingest books)
├── controllers/
│   └── pipeline_controller.py    # Orchestrates normalization, enrichment, and AI insights
├── services/
│   ├── normalization_service.py  # Cleans raw strings/titles
│   ├── crawling_service.py       # Fetches Google Books metadata & Goodreads data
│   └── ai_service.py             # Builds Gemini prompts and parses JSON responses
├── repositories/
│   └── book_repository.py        # JSON-backed storage (data/processed/books.json)
├── views/
│   └── dashboard.py              # Streamlit UI for HITL review
└── data/
    ├── clean_books.py            # One-off script to structure raw XLSX inventory
    └── CLEAN_BOOKS_README.md     # Documentation for data transformations
```

---

## Getting Started

### 1. Prerequisites
Ensure you have **Python 3.11+** installed. It is highly recommended to use a virtual environment.

### 2. Installation
Clone the repository and set up your environment:

```bash
# Create and activate virtual environment
python -m venv .venv

# On MacOS/Linux:
source .venv/bin/activate  

# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install streamlit httpx pydantic pandas openpyxl
```

### 3. Environment Variables (Optional but Recommended)
For the full experience, set up your API keys in your terminal or via a `.env` file in the root directory:
* `GOOGLE_BOOKS_API_KEY`: Enables richer and more reliable metadata extraction.
* `GEMINI_API_KEY`: Enables LLM insights. Without this, the app gracefully falls back to deterministic, hardcoded summaries/tags for demonstration purposes.

---

## Usage

You can interact with BiblioForge via the CLI or the Web Dashboard.

### Launch the Dashboard (Recommended)
Fire up the Streamlit UI to review pending books, edit AI-generated summaries, adjust tags, and approve records:

```bash
python main.py dashboard
```
*The dashboard will run locally at `http://localhost:8501`.*

### Ingest Data via CLI
To manually add a book to the pipeline and queue it for dashboard review:

```bash
python main.py ingest "The Name of the Rose - Umberto Eco" "Umberto Eco"
```

---

## Data Cleaning Helper

The legacy catalog is located at `biblioforge/data/raw/Stampa_Libri_Interni_RAW.xlsx`. 
To produce a cleaned, structured spreadsheet ready for ingestion:

```bash
python biblioforge/data/clean_books.py
```
*Note: Check `biblioforge/data/CLEAN_BOOKS_README.md` for exact transformation rules (e.g., column renames, title/author split, price formatting, quantity normalization).*

---

## Notes & Limitations

* **Storage:** Currently, persistence is handled via a local JSON file (`books.json`) designed for demonstration and academic purposes. For a production environment, `BookRepository` should be refactored to connect to a relational database (e.g., PostgreSQL).
* **Network Reliability:** External calls (Google Books, Goodreads) are "best-effort" and subject to rate limits. The pipeline is designed with fallbacks to prevent crashes.
* **AI Capabilities:** Full summarization and dynamic tagging require a valid Gemini API key.

---

## 🎓 Credits
Developed by **Francesco Caldarelli** and **Claudio Cozzolino** for the **Big Data Management** exam.
