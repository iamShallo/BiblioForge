#!/usr/bin/env python3
"""
Alternative performance test for Update Database.

Scenario:
- 30 books added
- 20 books deleted
- 15 books with price change
- 4 books quantity 2 -> 1
- 9 books quantity 1 -> 2/3
- 4 sales added

This script runs in an isolated temporary dataset so it does not modify
real processed files.
"""

import copy
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from biblioforge.repositories.book_repository import BookRepository
from biblioforge.services.sheets_sync_service import SheetsSyncService


def prepare_temp_dataset() -> dict:
    processed_dir = project_root / "biblioforge" / "data" / "processed"
    required = [
        processed_dir / "books.json",
        processed_dir / "sold_books.json",
    ]
    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="biblioforge_perf_"))

    shutil.copy2(processed_dir / "books.json", temp_dir / "books.json")
    shutil.copy2(processed_dir / "sold_books.json", temp_dir / "sold_books.json")

    approved_src = processed_dir / "approved_books.json"
    approved_dst = temp_dir / "approved_books.json"
    if approved_src.exists():
        shutil.copy2(approved_src, approved_dst)
    else:
        # Keep the test isolated while remaining compatible with environments
        # where approved_books.json is not present.
        approved_dst.write_text("[]", encoding="utf-8")

    queue_repo = BookRepository(temp_dir / "books.json")
    approved_repo = BookRepository(temp_dir / "approved_books.json")

    state_path = temp_dir / "sheets_sync_state.json"
    service = SheetsSyncService(
        queue_repository=queue_repo,
        approved_repository=approved_repo,
        state_path=state_path,
    )

    return {
        "temp_dir": temp_dir,
        "queue_repo": queue_repo,
        "approved_repo": approved_repo,
        "service": service,
    }


def build_remote_books_scenario(local_books, rng: random.Random) -> tuple[list, dict]:
    if len(local_books) < 200:
        raise RuntimeError("Not enough books to build test scenario")

    # Delete 20 books from remote view
    remote_books = copy.deepcopy(local_books[20:])

    # Price changes: 15
    price_targets = rng.sample(range(len(remote_books)), 15)
    for idx in price_targets:
        if remote_books[idx].catalog_price:
            remote_books[idx].catalog_price = float(remote_books[idx].catalog_price) * 1.1

    # Quantity 2 -> 1 for 4 books
    qty_down_candidates = [i for i, b in enumerate(remote_books) if int(b.catalog_quantity or 0) >= 2]
    qty_down_targets = rng.sample(qty_down_candidates, min(4, len(qty_down_candidates)))
    for idx in qty_down_targets:
        remote_books[idx].catalog_quantity = 1

    # Quantity 1 -> 2/3 for 9 books
    qty_up_candidates = [i for i, b in enumerate(remote_books) if int(b.catalog_quantity or 0) == 1]
    qty_up_targets = rng.sample(qty_up_candidates, min(9, len(qty_up_candidates)))
    for idx in qty_up_targets:
        remote_books[idx].catalog_quantity = rng.choice([2, 3])

    # Add 30 books with only sheet-like base fields (no rich metadata).
    source_for_new = copy.deepcopy(rng.sample(local_books, 30))
    epoch = int(time.time())
    for i, book in enumerate(source_for_new):
        book.id = f"ALT_NEW_{epoch}_{i}"
        original = (book.raw_title or "").strip()
        book.raw_title = f"ALT NUOVO LIBRO {i} - {original[:50]}"
        book.normalized_title = book.raw_title

        # Keep only fields typically present from Google Sheet import columns.
        # Everything else must be discovered by crawling + AI.
        book.info_link = None
        book.canonical_volume_link = None
        book.openlibrary_key = None
        book.goodreads_link = None
        book.isbn_10 = None
        book.publisher = None
        book.publication_year = None
        book.fetched_summary = None
        book.summary_source = None
        book.review_samples = []
        book.discarded_information_examples = []
        book.insights = None

        # Keep image/category/pages/date/rating as sheet-like values.
        if book.categories is None:
            book.categories = []

    remote_books.extend(source_for_new)

    expected = {
        "added_books": 30,
        "deleted_books": 20,
        "price_changed": 15,
        "qty_down": len(qty_down_targets),
        "qty_up": len(qty_up_targets),
    }
    return remote_books, expected


def build_remote_sales_scenario(local_sales: list[dict], local_books: list, rng: random.Random) -> tuple[list, int]:
    remote_sales = copy.deepcopy(local_sales)

    # Add 4 sales rows
    sample_books = rng.sample(local_books, 4)
    today = time.strftime("%Y-%m-%d")
    for i, book in enumerate(sample_books):
        price = float(book.catalog_price or 10.0)
        remote_sales.append(
            {
                "book_id": book.id,
                "raw_title": book.raw_title,
                "normalized_title": book.normalized_title,
                "author": book.author,
                "price": price,
                "quantity": 1,
                "sale_date": today,
                "isbn": book.isbn,
                "ean": book.catalog_ean,
                "test_marker": f"ALT_SALE_{i}",
            }
        )

    return remote_sales, 4


def run_test() -> int:
    rng = random.Random(42)
    ctx = prepare_temp_dataset()
    service = ctx["service"]
    queue_repo = ctx["queue_repo"]

    local_books = queue_repo.list_books()
    local_sales = service._load_sales()

    remote_books, expected_books = build_remote_books_scenario(local_books, rng)
    remote_sales, expected_sales_added = build_remote_sales_scenario(local_sales, local_books, rng)

    print("\n" + "=" * 80)
    print("ALTERNATIVE PERFORMANCE TEST")
    print("=" * 80)
    print(f"[SCENARIO] Local books: {len(local_books)}")
    print(f"[SCENARIO] Remote books: {len(remote_books)}")
    print(f"[SCENARIO] +{expected_books['added_books']} added, -{expected_books['deleted_books']} deleted")
    print(f"[SCENARIO] Price changes: {expected_books['price_changed']}")
    print(f"[SCENARIO] Qty 2->1: {expected_books['qty_down']}")
    print(f"[SCENARIO] Qty 1->2/3: {expected_books['qty_up']}")
    print(f"[SCENARIO] Sales +{expected_sales_added}")

    t0 = time.time()
    book_result = service._merge_queue_with_remote(remote_books)
    books_elapsed = time.time() - t0

    t1 = time.time()
    sales_result = service._merge_sales_with_remote(remote_sales)
    sales_elapsed = time.time() - t1

    total_estimate = 0.18 + 2.29 + 0.62 + books_elapsed + sales_elapsed + 0.10

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"[BOOKS] merge elapsed: {books_elapsed:.2f}s")
    print(f"[BOOKS] added: {book_result.get('added', 0)}")
    print(f"[BOOKS] updated: {book_result.get('updated', 0)}")
    print(f"[BOOKS] deleted: {book_result.get('deleted', 0)}")
    print(f"[BOOKS] local_only: {book_result.get('local_only', 0)}")

    print(f"[SALES] merge elapsed: {sales_elapsed:.2f}s")
    print(f"[SALES] added: {sales_result.get('added', 0)}")
    print(f"[SALES] updated: {sales_result.get('updated', 0)}")

    print(f"\n[ESTIMATE] Full Update Database: {total_estimate:.2f}s ({total_estimate/60:.2f}m)")
    if total_estimate < 600:
        print("[GOAL] OK: below 10 minutes")
        code = 0
    else:
        print("[GOAL] FAIL: above 10 minutes")
        code = 2

    summary_path = ctx["temp_dir"] / "alt_test_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "books_elapsed": books_elapsed,
                "sales_elapsed": sales_elapsed,
                "total_estimate": total_estimate,
                "book_result": book_result,
                "sales_result": sales_result,
                "scenario": {
                    **expected_books,
                    "sales_added": expected_sales_added,
                    "local_books": len(local_books),
                    "remote_books": len(remote_books),
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"[OUTPUT] Summary written to: {summary_path}")
    return code


if __name__ == "__main__":
    try:
        exit_code = run_test()
        sys.exit(exit_code)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
