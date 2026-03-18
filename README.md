# BiblioForge
AI-driven pipeline for cleaning raw book titles, enriching them with trusted metadata, and generating concise editorial insights. Built as an exam project for **Big Data Management** by **Francesco Caldarelli** and **Claudio Cozzolino**.

## What it does
- Cleans noisy titles into search-friendly strings
- Enriches metadata via Google Books plus a Goodreads scrape fallback
- Calls Gemini to generate summaries, tags, and transparency notes (with local fallback when no key is set)
- Surfaces a Streamlit dashboard for human-in-the-loop review and approval
- Persists processed books to a simple JSON store for demo purposes

## Architecture
- `main.py`: CLI entrypoint (`dashboard` or `ingest`).
- `controllers/pipeline_controller.py`: orchestrates normalization, enrichment, AI insights, and persistence.
- `services/normalization_service.py`: cleans the raw title.
- `services/crawling_service.py`: fetches Google Books metadata and scrapes Goodreads ratings/snippets.
- `services/ai_service.py`: builds the Gemini prompt, parses responses, and falls back to heuristic insights.
- `repositories/book_repository.py`: JSON-backed storage located at `biblioforge/data/processed/books.json`.
- `views/dashboard.py`: Streamlit UI to ingest, review, approve, or re-run books.
- `data/clean_books.py`: one-off cleaner that turns the raw XLSX inventory into a structured XLSX/CSV (see `data/CLEAN_BOOKS_README.md`).

## Prerequisites
- Python 3.11+
- Recommended: virtual environment (`python -m venv .venv && source .venv/bin/activate`)

Install deps (adjust if you already have a requirements file):
```bash
pip install streamlit httpx pydantic pandas openpyxl
```

Optional environment variables:
- `GOOGLE_BOOKS_API_KEY` for richer metadata
- `GEMINI_API_KEY` for LLM insights (otherwise a deterministic fallback is used)

## Quick start
```bash
# 1) Activate your venv and install deps
source .venv/bin/activate
pip install streamlit httpx pydantic pandas openpyxl

# 2) Launch the dashboard
python main.py dashboard

# 3) Or ingest from CLI (adds a book and queues it for review)
python main.py ingest "The Name of the Rose - Umberto Eco" "Umberto Eco"
```

The dashboard runs on Streamlit (default http://localhost:8501). Pending books appear in the dropdown; you can edit summaries, adjust tags, approve, or mark for re-run.

## Data cleaning helper
The legacy catalog lives in `biblioforge/data/raw/Stampa_Libri_Interni_RAW.xlsx`. To produce a cleaned spreadsheet:
```bash
python biblioforge/data/clean_books.py
```
See `biblioforge/data/CLEAN_BOOKS_README.md` for the exact transformations (column renames, title/author split, price formatting, quantity normalization).

## Notes and limitations
- Storage is a JSON file aimed at demo usage; replace `BookRepository` with a real database for production.
- Network calls (Google Books, Goodreads) are best-effort and may be rate-limited; the pipeline falls back to safe defaults on errors.
- Gemini requests require a valid API key; without it, the app returns a deterministic fallback summary and tags.

## Credits
Created by **Francesco Caldarelli** and **Claudio Cozzolino** for the Big Data Management exam.
