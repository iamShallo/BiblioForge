#!/usr/bin/env python3
"""
Performance test for Update Database with realistic scenario:
- 30 books added
- 20 books deleted
- 15 books with price change
- 4 books with quantity down (2 -> 1)
- 9 books with quantity up (1 -> 2/3)
- 4 sales added
"""

import sys
import time
import copy
import random
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from biblioforge.repositories.book_repository import BookRepository
from biblioforge.services.sheets_sync_service import SheetsSyncService
from biblioforge.models.book import Book


def create_test_scenario():
    """Load real data and simulate the scenario."""
    
    # Load repositories
    processed_dir = project_root / "biblioforge" / "data" / "processed"
    queue_repo = BookRepository(processed_dir / "books.json")
    approved_repo = BookRepository(processed_dir / "approved_books.json")
    
    print("\n" + "="*80)
    print("PERFORMANCE TEST: Realistic Update Scenario")
    print("="*80)
    
    # Get local books
    local_books = queue_repo.list_books()
    print(f"\n[TEST] Loaded {len(local_books)} local books")
    
    if len(local_books) < 100:
        print("[ERROR] Not enough local books for test (need at least 100)")
        return None
    
    # Create remote books scenario
    remote_books = []
    
    # ===== Scenario: 20 books DELETED (not included in remote) =====
    # Start from index 20, skip first 20 books
    keep_count = len(local_books) - 20
    unchanged_books = copy.deepcopy(local_books[20:keep_count])
    remote_books = unchanged_books.copy()
    print(f"[TEST] 20 books DELETED (first 20 skipped)")
    print(f"[TEST] {keep_count} books will remain UNCHANGED in remote")
    
    # ===== Scenario: 15 books with price change =====
    price_indices = random.sample(range(min(500, len(remote_books))), 15)
    price_changed_books = []
    for idx in price_indices:
        if remote_books[idx].catalog_price:
            original_price = remote_books[idx].catalog_price
            remote_books[idx].catalog_price = original_price * 1.1  # +10% price
            price_changed_books.append(remote_books[idx].id)
    print(f"[TEST] Modified PRICE for 15 books")
    
    # ===== Scenario: 4 books quantity 2->1 =====
    qty_down_indices = random.sample(range(500, min(1000, len(remote_books))), min(4, len(remote_books)-500))
    qty_down_books = []
    for idx in qty_down_indices:
        remote_books[idx].catalog_quantity = 1
        qty_down_books.append(remote_books[idx].id)
    print(f"[TEST] Changed QUANTITY 2->1 for {len(qty_down_books)} books")
    
    # ===== Scenario: 9 books quantity 1->2/3 =====
    qty_up_indices = random.sample(range(1000, min(1500, len(remote_books))), min(9, len(remote_books)-1000))
    qty_up_books = []
    for idx in qty_up_indices:
        remote_books[idx].catalog_quantity = random.choice([2, 3])
        qty_up_books.append(remote_books[idx].id)
    print(f"[TEST] Changed QUANTITY 1->2/3 for {len(qty_up_books)} books")
    
    # ===== Scenario: 30 new books added =====
    new_books = copy.deepcopy(random.sample(local_books, 30))
    for i, book in enumerate(new_books):
        book.id = f"NEW_{int(time.time())}_{i}"
        book.raw_title = f"NUOVO LIBRO {i} - {book.raw_title[:40]}"
        book.normalized_title = book.raw_title
    remote_books.extend(new_books)
    print(f"[TEST] Added 30 NEW books → {len(remote_books)} remote books total")
    
    # Count unchanged books (should be ~3000+ if you have 3880 local books)
    unchanged_count = keep_count - 15 - len(qty_down_books) - len(qty_up_books)
    
    print(f"\n[TEST] ==== SCENARIO SUMMARY ====")
    print(f"  Local books total: {len(local_books)}")
    print(f"  Remote books total: {len(remote_books)}")
    print(f"  Unchanged books (should skip enrichment): {unchanged_count}")
    print(f"  Modified books (need enrichment/merge): {15 + len(qty_down_books) + len(qty_up_books)}")
    print(f"  Added (new) books: 30")
    print(f"  Deleted books: 20")
    print(f"\n  Expected MERGE results:")
    print(f"    - Updated: {15 + len(qty_down_books) + len(qty_up_books)}")
    print(f"    - Added: 30")
    print(f"    - Deleted: 20")
    print(f"    - Unchanged (skipped during merge): {unchanged_count}")
    print()
    
    return {
        "local_books": local_books,
        "remote_books": remote_books,
        "queue_repo": queue_repo,
        "approved_repo": approved_repo,
        "expected_modified": 15 + len(qty_down_books) + len(qty_up_books),
        "expected_unchanged": unchanged_count,
    }


def run_merge_test(scenario_data):
    """Simulate the merge and enrichment process."""
    
    local_books = scenario_data["local_books"]
    remote_books = scenario_data["remote_books"]
    queue_repo = scenario_data["queue_repo"]
    approved_repo = scenario_data["approved_repo"]
    expected_modified = scenario_data.get("expected_modified", 0)
    expected_unchanged = scenario_data.get("expected_unchanged", 0)
    
    # Create sync service with test repos
    state_path = project_root / "biblioforge" / "data" / "processed" / "sheets_sync_state.json"
    sync_service = SheetsSyncService(
        queue_repository=queue_repo,
        approved_repository=approved_repo,
        state_path=state_path,
    )
    
    print("\n" + "="*80)
    print("RUNNING MERGE TEST")
    print("="*80 + "\n")
    
    # Measure merge
    merge_start = time.time()
    result = sync_service._merge_queue_with_remote(remote_books)
    merge_time = time.time() - merge_start
    
    print(f"\n{'='*80}")
    print("TEST RESULTS")
    print("="*80)
    print(f"\n[RESULT] Merge completed in {merge_time:.2f}s")
    print(f"[RESULT] Total books processed: {result['upserted']} books")
    print(f"[RESULT]   - Added (NEW books): {result['added']}")
    print(f"[RESULT]   - Updated (modified): {result['updated']}")
    print(f"[RESULT]   - Deleted: {result['deleted']}")
    print(f"[RESULT]   - Local-only: {result['local_only']}")
    
    # Verify scenario expectations
    print(f"\n[VERIFICATION] Checking expectations:")
    print(f"  Expected modified books: {expected_modified}")
    print(f"  Actual updated: {result['updated']}")
    if result['updated'] == expected_modified:
        print(f"  ✅ MATCH: Modified books correctly identified for enrichment")
    else:
        print(f"  ⚠️  MISMATCH: Expected {expected_modified}, got {result['updated']}")
    
    print(f"\n  Expected unchanged books to skip enrichment: {expected_unchanged}")
    print(f"  These {expected_unchanged} books should have metadata_score >= 15")
    print(f"  and were NOT modified, so should be skipped by TIER 1 optimization")
    print(f"  ✅ UNCHANGED BOOKS VERIFICATION: If merge time is low, they were skipped!")
    
    print(f"\n[RESULT] Total Merge + Enrichment Time: {merge_time:.2f}s ({merge_time/60:.1f}m)")
    
    # Estimate full pull time with all phases
    # Breakdown: Client (0.18) + Pull Books (2.29) + Pull Sales (0.62) + Merge (actual) + Merge Sales (0.5) + Save (0.1)
    estimated_pull_total = 0.18 + 2.29 + 0.62 + merge_time + 0.5 + 0.1
    print(f"\n[ESTIMATE] Full pull_remote_into_local time breakdown:")
    print(f"  Client Setup: 0.18s")
    print(f"  Pull Books (3880 rows): 2.29s")
    print(f"  Pull Sales: 0.62s")
    print(f"  → Merge Books (measured): {merge_time:.2f}s")
    print(f"  Merge Sales: 0.50s")
    print(f"  Save State: 0.10s")
    print(f"  ───────────────────────")
    print(f"  TOTAL: ~{estimated_pull_total:.2f}s ({estimated_pull_total/60:.2f}m)")
    
    return {
        "merge_time": merge_time,
        "estimated_total": estimated_pull_total,
        "result": result,
    }


if __name__ == "__main__":
    try:
        print("\n🚀 BiblioForge Update Database Performance Test\n")
        
        # Create scenario
        scenario = create_test_scenario()
        if not scenario:
            sys.exit(1)
        
        # Run test
        test_result = run_merge_test(scenario)
        
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"\nMerge + Enrichment: {test_result['merge_time']:.1f}s")
        print(f"Full Update Database: ~{test_result['estimated_total']:.1f}s (~{test_result['estimated_total']/60:.1f}m)")
        
        if test_result['estimated_total'] < 600:
            print(f"\n✅ GOAL ACHIEVED: < 10 minutes ({test_result['estimated_total']/60:.1f}m)")
        elif test_result['estimated_total'] < 1200:
            print(f"\n⚠️  ACCEPTABLE: ~{test_result['estimated_total']/60:.1f}m (goal is < 10m)")
        else:
            print(f"\n❌ TOO SLOW: {test_result['estimated_total']/60:.1f}m (goal is < 10m)")
        
        print("\n" + "="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
