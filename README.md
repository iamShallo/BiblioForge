# BiblioForge

**University Exam Project: Big Data Management (University of Camerino)**
Developed by:
- Francesco Caldarelli (francesco.caldarelli@studenti.unicam.it)
- Claudio Cozzolino (claudio.cozzolino@studenti.unicam.it)

---

BiblioForge is an AI-assisted data ingestion pipeline designed to manage, clean, and enrich book catalogs. 

It was built to solve a specific problem: transforming messy, error-prone archives into clean, normalized, and editorially rich databases using public APIs and Google Gemini.

## Core Use Cases

The system supports two main workflows to cover all cataloging needs:

### 1. Batch Import (From "Dirty" Excel Files)
Do you have an Excel file with hundreds of poorly formatted records or missing data?
- Upload the file via the Dashboard.
- The pipeline automatically cleans and normalizes fields (titles, authors, publishers).
- It queries public APIs (Google Books, OpenLibrary) to validate and enrich missing data.
- It uses AI to generate summaries and editorial tags.
- Records are placed in a "Review Queue" for final Human-in-the-Loop approval.

### 2. Manual Ingestion (Out-of-Database Books)
Need to quickly add a single book that is missing from the batch file?
- Use the CLI to search and ingest the book.
- The system applies the exact same API and AI enrichment pipeline and places the enriched record into the review queue.

---

## Setup and Installation (Windows)

Open your terminal and run the following commands:

    git clone https://github.com/your-username/BiblioForge.git
    cd BiblioForge
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install streamlit httpx pydantic pandas openpyxl

---

## How to Run

1. Launch the Dashboard (For Excel imports and Review Queue):
    
    python main.py dashboard

2. Manual CLI Ingestion (Single Book):
    
    python main.py ingest "The Name of the Rose" "Umberto Eco"

---

## Project Structure

The code is modularly organized to separate responsibilities:

- /controllers : Orchestrates the workflow (from cleaning to approval).
- /services : The core engine (Text cleaning, API calls, Gemini integration).
- /repositories : Reads and writes JSON databases.
- /models : Strict data structures using Pydantic.
- /views : The Streamlit user interface.
- /data : Raw Excel files, processing queues, and approved databases.
