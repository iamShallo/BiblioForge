import json
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
        try:
            # Accept both UTF-8 and UTF-8 with BOM (common with PowerShell writes).
            raw = json.loads(self.storage_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            return []
        if not isinstance(raw, list):
            return []

        result: List[SoldBook] = []
        for item in raw:
            if isinstance(item, dict):
                result.append(self._dict_to_sold_book(item))
        return result

    def _persist(self) -> None:
        payload = [asdict(sold_book) for sold_book in self._cache]
        self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

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
