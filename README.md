# BiblioForge

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B)
![Google Gemini](https://img.shields.io/badge/AI-Google_Gemini-8E75B2)
![Academic](https://img.shields.io/badge/Exam-Big_Data_Management-brightgreen)

**BiblioForge** is an AI-driven pipeline designed to clean raw book titles, enrich them with trusted web metadata, and generate concise, editorial insights. 

Built as an exam project for the **Big Data Management** course by **Francesco Caldarelli** and **Claudio Cozzolino**.

---

## Key Features

* **Automated Data Cleaning:** Transforms noisy, unstructured catalog titles into clean, search-friendly strings.
* **Smart Enrichment:** Fetches reliable metadata via the Google Books API, with a best-effort fallback to scrape Goodreads for ratings and snippets.
* **AI-Powered Insights:** Integrates with Google Gemini to generate dynamic summaries, smart tags, and transparency notes (includes a deterministic local fallback if no API key is provided).
* **Human-in-the-Loop (HITL):** Features a sleek **Streamlit** dashboard allowing human operators to review, edit, approve, or re-run AI-processed books before final database insertion.

---

## Getting Started

### Prerequisites
Ensure you have **Python 3.11+** installed. It is highly recommended to use a virtual environment.

### Installation
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

### Environment Variables (Optional but Recommended)
For the full experience, set up your API keys in your terminal or via a `.env` file in the root directory:
* `GOOGLE_BOOKS_API_KEY`: Enables richer and more reliable metadata extraction.
* `GEMINI_API_KEY`: Enables LLM insights. Without this, the app gracefully falls back to deterministic, hardcoded summaries/tags for demonstration purposes.

---

## Credits
Developed by **Francesco Caldarelli** and **Claudio Cozzolino** for the **Big Data Management** exam.
