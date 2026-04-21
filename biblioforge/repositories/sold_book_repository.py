import json
import os
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List

from biblioforge.models.book import SoldBook


class SoldBookRepository:
    """JSON-backed repository for sold book records."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: List[SoldBook] = self._load()

    def _load(self) -> List[SoldBook]:
        if not self.storage_path.exists():
            return []
        
        # Retry logic for file locks during concurrent access
        max_retries = 3
        retry_delay = 0.05  # seconds
        
        for attempt in range(max_retries):
            try:
                # Accept both UTF-8 and UTF-8 with BOM (common with PowerShell writes).
                raw = json.loads(self.storage_path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                return []
            except (OSError, IOError):
                # File lock or other I/O error - retry with backoff
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # exponential backoff
                    continue
                return []
            
            if not isinstance(raw, list):
                return []

            result: List[SoldBook] = []
            for item in raw:
                if isinstance(item, dict):
                    result.append(self._dict_to_sold_book(item))
            return result
        
        return []

    def _persist(self) -> None:
        payload = [asdict(sold_book) for sold_book in self._cache]
        
        # Retry logic for file locks during concurrent access
        max_retries = 3
        retry_delay = 0.05  # seconds
        
        for attempt in range(max_retries):
            try:
                serialized = json.dumps(payload, indent=2, ensure_ascii=False)
                temp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
                temp_path.write_text(serialized, encoding="utf-8")
                os.replace(temp_path, self.storage_path)
                return
            except (OSError, IOError):
                # File lock or other I/O error - retry with backoff
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # exponential backoff
                    continue
                # After all retries, let the error propagate
                raise

    def _refresh_from_disk(self) -> None:
        self._cache = self._load()

    def list_all(self) -> List[SoldBook]:
        self._refresh_from_disk()
        return list(self._cache)

    def add_sale(self, sold_book: SoldBook) -> SoldBook:
        self._refresh_from_disk()
        if not sold_book.sale_date:
            sold_book.sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._cache.append(sold_book)
        self._persist()
        return sold_book

    @staticmethod
    def _dict_to_sold_book(data: dict) -> SoldBook:
        return SoldBook(
            book_id=data.get("book_id", ""),
            raw_title=data.get("raw_title", ""),
            normalized_title=data.get("normalized_title", ""),
            author=data.get("author"),
            price=data.get("price"),
            quantity=int(data.get("quantity", 1) or 1),
            sale_date=data.get("sale_date"),
            isbn=data.get("isbn"),
            ean=data.get("ean"),
        )
