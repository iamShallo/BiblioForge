"""Entrypoint for running BiblioForge demos and dashboard."""

import argparse
import subprocess
import sys
from pathlib import Path

from biblioforge.controllers.pipeline_controller import PipelineController


def run_dashboard() -> int:
    app_path = Path(__file__).parent / "biblioforge" / "views" / "dashboard.py"
    print("Launching Streamlit dashboard...")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path)])


def run_ingestion(title: str, author: str) -> None:
    controller = PipelineController()
    book = controller.ingest_raw_book(title, author)
    print(f"Ingested book '{book.normalized_title}' with status {book.status.value}.")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BiblioForge control plane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dash = subparsers.add_parser("dashboard", help="Launch Streamlit UI")
    dash.set_defaults(command="dashboard")

    ingest = subparsers.add_parser("ingest", help="Ingest a raw title and author")
    ingest.add_argument("title", help="Raw title field")
    ingest.add_argument("author", help="Author name")
    ingest.set_defaults(command="ingest")

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.command == "dashboard":
        return run_dashboard()
    if args.command == "ingest":
        run_ingestion(args.title, args.author)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
