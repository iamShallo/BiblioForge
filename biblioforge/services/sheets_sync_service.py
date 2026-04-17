"""Google Sheets synchronization service for central multi-device consistency."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from biblioforge.models.book import Book
from biblioforge.repositories.book_repository import BookRepository
from biblioforge.services.ai_service import generate_insights, normalize_catalog_entry
from biblioforge.services.crawling_service import enrich_book, search_candidates
from biblioforge.services.normalization_service import normalize_title


@dataclass
class SyncRunResult:
    status: str
    message: str
    pushed_tabs: int = 0
    pulled_books: int = 0
    skipped: bool = False
    details: Optional[Dict[str, Any]] = None
    elapsed_seconds: Optional[float] = None
    average_seconds: Optional[float] = None


class SheetsSyncService:
    """Two-way sync between local JSON repos and Google Sheets.

    Sync model:
    - Local repositories remain source of truth for edits during runtime.
    - A scheduled push (default 10m) overwrites remote tabs atomically to avoid duplicates.
    - Remote edits are merged into local state on demand; local state wins only for non-empty local fields.
    - Conflict strategy (default): local_wins.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    ROME_TZ = ZoneInfo("Europe/Rome")

    def __init__(
        self,
        queue_repository: BookRepository,
        approved_repository: BookRepository,
        state_path: Path,
    ) -> None:
        self.queue_repository = queue_repository
        self.approved_repository = approved_repository
        self.state_path = Path(state_path)
        self.project_root = Path(__file__).resolve().parents[2]
        self.package_root = Path(__file__).resolve().parent.parent
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path = self.state_path.parent / "sheets_sync_config.json"
        self.log_path = self.state_path.parent / "sheets_sync_log.json"
        self.sold_books_path = self.state_path.parent / "sold_books.json"

        persisted = self._load_persisted_config()

        env_sheet = os.getenv("BIBLIOFORGE_SHEETS_SPREADSHEET_ID")
        env_sa = os.getenv("BIBLIOFORGE_SHEETS_SERVICE_ACCOUNT_FILE")
        env_queue = os.getenv("BIBLIOFORGE_SHEETS_QUEUE_TAB")
        env_approved = os.getenv("BIBLIOFORGE_SHEETS_APPROVED_TAB")
        env_policy = os.getenv("BIBLIOFORGE_SHEETS_CONFLICT_POLICY")
        env_enabled = os.getenv("BIBLIOFORGE_SHEETS_SYNC_ENABLED")

        self.spreadsheet_id = (env_sheet if env_sheet is not None else persisted.get("spreadsheet_id", "")).strip()
        self.service_account_file = self._normalize_service_account_reference(
            env_sa if env_sa is not None else persisted.get("service_account_file", "")
        )
        self.queue_tab = ((env_queue if env_queue is not None else persisted.get("queue_tab", "Libri")).strip() or "Libri")
        self.approved_tab = ((env_approved if env_approved is not None else persisted.get("approved_tab", "Vendite")).strip() or "Vendite")
        self.conflict_policy = ((env_policy if env_policy is not None else persisted.get("conflict_policy", "local_wins")).strip().lower() or "local_wins")

        if env_enabled is None:
            self.enabled = bool(persisted.get("enabled", False))
        else:
            self.enabled = str(env_enabled).strip().lower() in {"1", "true", "yes", "y", "on"}

        # Fallback: if no service-account path is configured, use the conventional local path.
        if not self.service_account_file:
            default_sa = self._discover_service_account_file()
            if default_sa.exists():
                self.service_account_file = self._portable_service_account_reference(default_sa)

        self.sync_interval_seconds = self._read_interval_seconds()

    @staticmethod
    def _read_interval_seconds() -> int:
        raw = os.getenv("BIBLIOFORGE_SHEETS_SYNC_INTERVAL_SECONDS", "600").strip()
        try:
            value = int(raw)
        except ValueError:
            return 600
        return max(0, value)

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _rome_now_iso(cls) -> str:
        now_rome = datetime.now(cls.ROME_TZ)
        return f"{now_rome.isoformat()} {now_rome.tzname()}"

    @staticmethod
    def _truthy_env(name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

    def is_enabled(self) -> bool:
        return bool(self.enabled)

    def _load_persisted_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _resolve_service_account_path(self, service_account_file: str) -> Path:
        raw_path = str(service_account_file or "").strip()
        if not raw_path:
            return Path()
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path

        candidates = [
            Path.cwd() / path,
            self.state_path.parent / path,
            self.package_root / path,
            self.project_root / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        return self.project_root / path

    def _discover_service_account_file(self) -> Path:
        processed_dir = self.state_path.parent
        conventional_names = [
            "google_service_account.json",
            "service_account.json",
            "service-account.json",
            "credentials.json",
        ]

        for name in conventional_names:
            candidate = processed_dir / name
            if candidate.exists():
                return candidate

        reserved_names = {
            "sheets_sync_config.json",
            "sheets_sync_log.json",
            "sheets_sync_state.json",
            "books.json",
            "sold_books.json",
        }
        json_candidates = [
            candidate
            for candidate in processed_dir.glob("*.json")
            if candidate.name not in reserved_names
        ]
        if len(json_candidates) == 1:
            return json_candidates[0]

        return processed_dir / conventional_names[0]

    def _normalize_service_account_reference(self, service_account_file: Any) -> str:
        path = str(service_account_file or "").strip()
        if not path:
            return ""
        return self._portable_service_account_reference(self._resolve_service_account_path(path))

    def _portable_service_account_reference(self, path: Path) -> str:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            return str(candidate)

        for root in (self.state_path.parent, self.package_root, self.project_root):
            try:
                return str(candidate.relative_to(root))
            except ValueError:
                continue

        return str(candidate)

    def _save_persisted_config(self) -> None:
        payload = {
            "enabled": bool(self.enabled),
            "spreadsheet_id": self.spreadsheet_id,
            "service_account_file": self.service_account_file,
            "queue_tab": self.queue_tab,
            "approved_tab": self.approved_tab,
            "conflict_policy": self.conflict_policy,
        }
        self.config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _extract_sheet_id(sheet_link_or_id: str) -> str:
        raw = (sheet_link_or_id or "").strip()
        if not raw:
            return ""
        marker = "/spreadsheets/d/"
        if marker in raw:
            tail = raw.split(marker, 1)[1]
            return tail.split("/", 1)[0].strip()
        return raw

    def save_connection(
        self,
        sheet_link_or_id: str,
        service_account_file: Optional[str] = None,
        enabled: bool = True,
    ) -> Dict[str, Any]:
        sheet_id = self._extract_sheet_id(sheet_link_or_id)
        if not sheet_id:
            return {"ok": False, "message": "ID foglio non valido."}

        if service_account_file:
            self.service_account_file = self._normalize_service_account_reference(service_account_file)

        self.spreadsheet_id = sheet_id
        self.enabled = bool(enabled)
        self._save_persisted_config()
        return {"ok": True, "message": "Collegamento Google Sheets salvato."}

    def save_service_account_file(self, service_account_file: str) -> Dict[str, Any]:
        path = str(service_account_file or "").strip()
        if not path:
            return {"ok": False, "message": "Percorso credenziali non valido."}
        self.service_account_file = self._normalize_service_account_reference(path)
        self._save_persisted_config()
        return {"ok": True, "message": "Credenziali Google salvate."}

    def disable_connection(self) -> None:
        self.enabled = False
        self.spreadsheet_id = ""
        self._save_persisted_config()

    def list_drive_spreadsheets(self, limit: int = 50) -> List[Dict[str, str]]:
        cfg = self.describe_configuration()
        if cfg.get("missing") and "BIBLIOFORGE_SHEETS_SPREADSHEET_ID" in cfg.get("missing", []):
            # Listing from Drive only needs credentials, not selected spreadsheet id.
            if not self.service_account_file or not self._resolve_service_account_path(self.service_account_file).exists():
                return []

        credentials = self._get_google_credentials()
        google_api = importlib.import_module("googleapiclient.discovery")
        build = getattr(google_api, "build")
        drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)

        response = drive_service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            pageSize=max(1, min(int(limit), 200)),
            fields="files(id,name)",
            orderBy="modifiedTime desc",
        ).execute()

        files = response.get("files", []) or []
        items: List[Dict[str, str]] = []
        for file_item in files:
            file_id = str(file_item.get("id") or "").strip()
            name = str(file_item.get("name") or "").strip() or file_id
            if file_id:
                items.append({"id": file_id, "name": name})
        return items

    def get_missing_configuration(self) -> List[str]:
        missing: List[str] = []
        if not self.spreadsheet_id:
            missing.append("BIBLIOFORGE_SHEETS_SPREADSHEET_ID")
        if not self.service_account_file:
            missing.append("BIBLIOFORGE_SHEETS_SERVICE_ACCOUNT_FILE")
        elif not self._resolve_service_account_path(self.service_account_file).exists():
            missing.append(f"service account file not found: {self.service_account_file}")
        return missing

    def describe_configuration(self) -> Dict[str, Any]:
        missing = self.get_missing_configuration()
        return {
            "enabled": self.is_enabled(),
            "spreadsheet_id": self.spreadsheet_id,
            "service_account_file": self.service_account_file,
            "queue_tab": self.queue_tab,
            "approved_tab": self.approved_tab,
            "sync_interval_seconds": self.sync_interval_seconds,
            "conflict_policy": self.conflict_policy,
            "missing": missing,
            "ready": self.is_enabled() and not missing,
        }

    def _not_ready_result(self) -> SyncRunResult:
        cfg = self.describe_configuration()
        missing = cfg.get("missing", []) or []
        if not cfg.get("enabled", False):
            return SyncRunResult(
                status="disabled",
                message="Sincronizzazione Google Sheets non abilitata.",
                skipped=True,
            )
        if missing:
            return SyncRunResult(
                status="disabled",
                message="Sincronizzazione non pronta. Manca: " + ", ".join(str(item) for item in missing),
                skipped=True,
            )
        return SyncRunResult(
            status="disabled",
            message="Sincronizzazione non pronta.",
            skipped=True,
        )

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {
                "last_push_epoch": 0.0,
                "last_push_iso": None,
                "last_push_queue_rows": 0,
                "last_push_sales_rows": 0,
                "last_push_book_keys": [],
                "last_pull_duration_seconds": None,
                "avg_pull_duration_seconds": None,
                "pull_duration_history_seconds": [],
                "queue_checksum": "",
                "sales_checksum": "",
                "approved_checksum": "",
                "last_pull_iso": None,
                "last_error": None,
            }
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {
            "last_push_epoch": 0.0,
            "last_push_iso": None,
            "last_push_queue_rows": 0,
            "last_push_sales_rows": 0,
                "last_push_book_keys": [],
            "last_pull_duration_seconds": None,
            "avg_pull_duration_seconds": None,
            "pull_duration_history_seconds": [],
            "queue_checksum": "",
            "sales_checksum": "",
            "approved_checksum": "",
            "last_pull_iso": None,
            "last_error": "invalid_state_file",
        }

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _load_sync_log(self) -> List[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        try:
            data = json.loads(self.log_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [entry for entry in data if isinstance(entry, dict)]
        except Exception:
            pass
        return []

    def _save_sync_log(self, entries: List[Dict[str, Any]]) -> None:
        self.log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")

    def _append_sync_log_entry(
        self,
        *,
        queue_rows_before: int,
        queue_rows_after: int,
        sales_rows_before: int,
        sales_rows_after: int,
        queue_added: int,
        queue_deleted: int,
        sales_added: int,
        sales_deleted: int,
        pushed_tabs: int,
    ) -> None:
        log_entries = self._load_sync_log()
        log_entries.append(
            {
                "timestamp_epoch": time.time(),
                "timestamp_iso": self._rome_now_iso(),
                "queue_rows_before": queue_rows_before,
                "queue_rows_after": queue_rows_after,
                "queue_rows_added": queue_added,
                "queue_rows_deleted": queue_deleted,
                "sales_rows_before": sales_rows_before,
                "sales_rows_after": sales_rows_after,
                "sales_rows_added": sales_added,
                "sales_rows_deleted": sales_deleted,
                "pushed_tabs": pushed_tabs,
            }
        )
        self._save_sync_log(log_entries)

    def _mark_push_state(
        self,
        state: Dict[str, Any],
        queue_checksum: str,
        sales_checksum: str,
        queue_rows: int,
        sales_rows: int,
        queue_added: int,
        queue_deleted: int,
        sales_added: int,
        sales_deleted: int,
        queue_books: Optional[List[Book]] = None,
    ) -> None:
        state["last_push_epoch"] = time.time()
        state["last_push_iso"] = self._utc_now_iso()
        state["last_push_queue_rows"] = queue_rows
        state["last_push_sales_rows"] = sales_rows
        if queue_books is not None:
            state["last_push_book_keys"] = [self._book_sync_key(book) for book in queue_books]
        state["queue_checksum"] = queue_checksum
        state["sales_checksum"] = sales_checksum
        state["approved_checksum"] = sales_checksum
        state["last_error"] = None
        self._save_state(state)
        self._append_sync_log_entry(
            queue_rows_before=max(queue_rows - queue_added + queue_deleted, 0),
            queue_rows_after=queue_rows,
            sales_rows_before=max(sales_rows - sales_added + sales_deleted, 0),
            sales_rows_after=sales_rows,
            queue_added=queue_added,
            queue_deleted=queue_deleted,
            sales_added=sales_added,
            sales_deleted=sales_deleted,
            pushed_tabs=2,
        )

    @staticmethod
    def _serialize_book_payload(book: Book) -> str:
        return json.dumps(book.to_dict(), ensure_ascii=False, sort_keys=True)

    def _books_checksum(self, books: List[Book]) -> str:
        payload = [self._serialize_book_payload(book) for book in sorted(books, key=lambda b: b.id)]
        digest = hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()
        return digest

    @staticmethod
    def _payload_checksum(payload: List[Dict[str, Any]]) -> str:
        normalized = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in payload]
        digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()
        return digest

    @staticmethod
    def _book_fingerprint(book: Book) -> str:
        isbn = str(getattr(book, "isbn", None) or getattr(book, "catalog_ean", None) or "").strip().lower()
        title = str(getattr(book, "normalized_title", None) or getattr(book, "raw_title", None) or "").strip().lower()
        author = str(getattr(book, "author", None) or "").strip().lower()
        return "|".join([isbn, title, author])

    @staticmethod
    def _book_sync_key(book: Book) -> str:
        fp = SheetsSyncService._book_fingerprint(book)
        # Fallback key when a row has no reliable fingerprint fields.
        if fp.strip("|"):
            return fp
        return f"id:{book.id}"

    @staticmethod
    def _is_empty_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) == 0
        return False

    @staticmethod
    def _metadata_score(book: Book) -> int:
        score = 0
        if getattr(book, "info_link", None):
            score += 3
        if getattr(book, "canonical_volume_link", None):
            score += 3
        if getattr(book, "openlibrary_key", None):
            score += 2
        if getattr(book, "goodreads_link", None):
            score += 2
        if getattr(book, "cover_url", None):
            score += 2
        if (getattr(book, "isbn", None) or "").strip():
            score += 2
        if (getattr(book, "isbn_10", None) or "").strip():
            score += 1
        if (getattr(book, "fetched_summary", None) or "").strip():
            score += 2
        if getattr(book, "publisher", None):
            score += 1
        if getattr(book, "pages", None):
            score += 1
        if getattr(book, "publication_year", None):
            score += 1
        if getattr(book, "categories", None):
            score += 1
        return score

    @staticmethod
    def _looks_like_placeholder_cover(url: Optional[str]) -> bool:
        if not url:
            return False
        lowered = str(url).lower()
        if "via.placeholder.com" in lowered:
            return True
        if "covers.openlibrary.org" in lowered and "default=true" in lowered:
            return True
        return False

    @staticmethod
    def _has_synthetic_summary(book: Book) -> bool:
        source = (getattr(book, "summary_source", "") or "").strip().lower()
        summary = (getattr(book, "fetched_summary", None) or "").strip()
        return bool(summary) and source == "local_fallback"

    @staticmethod
    def _has_minimal_metadata(book: Book) -> bool:
        has_link = any(
            [
                bool(getattr(book, "info_link", None)),
                bool(getattr(book, "canonical_volume_link", None)),
                bool(getattr(book, "openlibrary_key", None)),
                bool(getattr(book, "goodreads_link", None)),
            ]
        )
        has_real_cover = bool(getattr(book, "cover_url", None)) and not SheetsSyncService._looks_like_placeholder_cover(
            getattr(book, "cover_url", None)
        )
        has_real_summary = bool((getattr(book, "fetched_summary", None) or "").strip()) and not SheetsSyncService._has_synthetic_summary(book)
        return has_link or has_real_cover or has_real_summary

    @staticmethod
    def _apply_candidate_metadata(book: Book, candidate: Optional[dict]) -> Book:
        if not candidate:
            return book

        candidate_link = (candidate.get("info_link") or "").strip() or None
        candidate_cover = (candidate.get("cover_url") or "").strip() or None
        candidate_published_date = (candidate.get("published_date") or "").strip() or None
        candidate_title = (candidate.get("title") or "").strip()
        candidate_authors = (candidate.get("authors") or "").strip()

        if candidate_title:
            canonical = normalize_title(candidate_title, candidate_authors or book.author)
            book.raw_title = canonical or candidate_title
            book.normalized_title = canonical or candidate_title
        if candidate_authors:
            book.author = candidate_authors

        if not getattr(book, "info_link", None) and candidate_link:
            book.info_link = candidate_link
        if (
            (not getattr(book, "cover_url", None) or SheetsSyncService._looks_like_placeholder_cover(getattr(book, "cover_url", None)))
            and candidate_cover
        ):
            book.cover_url = candidate_cover
        if not getattr(book, "openlibrary_key", None) and candidate_link:
            match = re.search(r"openlibrary\.org/works/([^/?#]+)", candidate_link)
            if match:
                book.openlibrary_key = match.group(1)
        if not getattr(book, "published_date", None) and candidate_published_date:
            book.published_date = candidate_published_date
        if not getattr(book, "publication_year", None) and candidate_published_date and candidate_published_date[:4].isdigit():
            book.publication_year = int(candidate_published_date[:4])

        if SheetsSyncService._has_synthetic_summary(book):
            book.fetched_summary = None
            book.summary_source = None

        return book

    @staticmethod
    def _merge_lists(first: Optional[List[Any]], second: Optional[List[Any]]) -> List[Any]:
        merged: List[Any] = []
        seen: set[str] = set()
        for item in list(first or []) + list(second or []):
            fingerprint = json.dumps(item, default=lambda value: getattr(value, "__dict__", str(value)), sort_keys=True, ensure_ascii=False)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            merged.append(item)
        return merged

    @staticmethod
    def _book_label(book: Book) -> str:
        title = (book.normalized_title or book.raw_title or "Titolo sconosciuto").strip()
        author = (book.author or "Autore sconosciuto").strip()
        identifier = (book.isbn or book.catalog_ean or "").strip()
        if identifier:
            return f"{title} - {author} (ISBN/EAN {identifier})"
        return f"{title} - {author}"

    @staticmethod
    def _sale_label(sale: Dict[str, Any]) -> str:
        title = str(sale.get("normalized_title") or sale.get("raw_title") or "Titolo sconosciuto").strip()
        author = str(sale.get("author") or "Autore sconosciuto").strip()
        identifier = str(sale.get("isbn") or sale.get("ean") or "").strip()
        if identifier:
            return f"{title} - {author} (ISBN/EAN {identifier})"
        return f"{title} - {author}"

    @staticmethod
    def _limit_preview(items: List[Any], limit: int = 40) -> List[Any]:
        if len(items) <= limit:
            return items
        return items[:limit]

    @staticmethod
    def _changed_fields(before: Any, after: Any, fields: List[str]) -> List[str]:
        changed: List[str] = []
        for field in fields:
            if getattr(before, field, None) != getattr(after, field, None):
                changed.append(field)
        return changed

    @staticmethod
    def _changed_sale_fields(before: Dict[str, Any], after: Dict[str, Any], fields: List[str]) -> List[str]:
        changed: List[str] = []
        for field in fields:
            if before.get(field) != after.get(field):
                changed.append(field)
        return changed

    def _merge_book_records(self, local_book: Optional[Book], remote_book: Book) -> Book:
        merged = copy.deepcopy(local_book or remote_book)
        for field_name in Book.__dataclass_fields__:
            if field_name in {"id", "status"}:
                continue

            local_value = getattr(local_book, field_name, None) if local_book is not None else None
            remote_value = getattr(remote_book, field_name, None)

            if field_name == "categories":
                value = self._merge_lists(local_value, remote_value)
            elif field_name in {"review_samples", "discarded_information_examples"}:
                value = remote_value if not self._is_empty_value(remote_value) else local_value
            elif field_name == "insights":
                value = remote_value if remote_value is not None else local_value
            elif self._is_empty_value(remote_value):
                value = local_value
            else:
                value = remote_value

            setattr(merged, field_name, value)

        if local_book is not None:
            merged.id = local_book.id
            merged.status = local_book.status
            merged.reject_attempts = max(int(getattr(local_book, "reject_attempts", 0) or 0), int(getattr(remote_book, "reject_attempts", 0) or 0))
        else:
            merged.id = remote_book.id

        return merged

    async def _enrich_merged_book(self, book: Book) -> Book:
        book_label = self._book_label(book)
        book_start = time.time()
        
        current = book
        original_status = current.status
        current_score = self._metadata_score(current)
        
        print(f"[ENRICH BOOK] Starting: {book_label} (metadata_score={current_score})")
        
        if current_score < 5 or not self._has_minimal_metadata(current):
            # First enrichment pass
            p1_start = time.time()
            first_pass = await enrich_book(current)
            p1_time = time.time() - p1_start
            first_score = self._metadata_score(first_pass)
            print(f"[ENRICH BOOK]   Pass 1 ({p1_time:.2f}s): score {current_score} -> {first_score}")
            current = first_pass if first_score >= current_score else current

            if not self._has_minimal_metadata(current):
                # Retry with normalization
                retry_seed = copy.deepcopy(current)
                p2_start = time.time()
                refreshed_catalog = normalize_catalog_entry(
                    raw_title=current.raw_title,
                    raw_author=current.author,
                    raw_publisher=getattr(current, "catalog_publisher", None),
                )
                retry_author = refreshed_catalog.get("author") or retry_seed.author
                retry_title_input = refreshed_catalog.get("title") or retry_seed.raw_title
                retry_title = normalize_title(retry_title_input, retry_author)
                if retry_title:
                    retry_seed.raw_title = retry_title
                    retry_seed.normalized_title = retry_title
                retry_seed.author = retry_author

                second_pass = await enrich_book(retry_seed)
                p2_time = time.time() - p2_start
                second_score = self._metadata_score(second_pass)
                print(f"[ENRICH BOOK]   Pass 2 ({p2_time:.2f}s): score -> {second_score}")
                current = second_pass if second_score >= self._metadata_score(current) else current

            if not self._has_minimal_metadata(current):
                # Last resort: search candidates
                p3_start = time.time()
                candidates = await search_candidates(
                    current.normalized_title or current.raw_title,
                    current.author,
                    getattr(current, "catalog_publisher", None),
                    getattr(current, "catalog_ean", None),
                    limit=1,
                )
                p3_time = time.time() - p3_start
                print(f"[ENRICH BOOK]   Candidate search ({p3_time:.2f}s): found {len(candidates) if candidates else 0}")
                if candidates:
                    current = self._apply_candidate_metadata(current, candidates[0])

            if not getattr(current, "insights", None):
                p4_start = time.time()
                try:
                    current = generate_insights(current)
                    p4_time = time.time() - p4_start
                    print(f"[ENRICH BOOK]   Insights ({p4_time:.2f}s): generated")
                except Exception as e:
                    print(f"[ENRICH BOOK]   Insights ERROR: {e}")

        current.status = original_status
        total_time = time.time() - book_start
        final_score = self._metadata_score(current)
        print(f"[ENRICH BOOK] Completed: {book_label} (score {current_score} -> {final_score}) in {total_time:.2f}s")
        
        return current

    async def _enrich_books_bulk(self, books: List[Book]) -> List[Book]:
        if not books:
            return []

        raw_limit = os.getenv("BIBLIOFORGE_PULL_ENRICH_CONCURRENCY", "8").strip()
        try:
            concurrency = max(1, int(raw_limit))
        except ValueError:
            concurrency = 8

        print(f"[ENRICH BULK] Starting enrichment of {len(books)} books with concurrency={concurrency}")
        semaphore = asyncio.Semaphore(concurrency)
        completed = [0]  # Use list for mutation in nested function
        start_time = time.time()

        async def _enrich_one(book: Book) -> Book:
            async with semaphore:
                try:
                    enriched = await self._enrich_merged_book(book)
                    completed[0] += 1
                    if completed[0] % max(1, len(books) // 10) == 0 or completed[0] == len(books):
                        elapsed = time.time() - start_time
                        print(f"[ENRICH PROGRESS] {completed[0]}/{len(books)} completed in {elapsed:.1f}s")
                    return enriched
                except Exception as e:
                    completed[0] += 1
                    print(f"[ENRICH ERROR] Failed to enrich book: {e}")
                    return book

        result = await asyncio.gather(*[_enrich_one(book) for book in books])
        total_time = time.time() - start_time
        print(f"[ENRICH COMPLETE] Enriched {len(books)} books in {total_time:.2f}s (avg {total_time/len(books):.2f}s per book)")
        return result

    def _merge_queue_with_remote(self, remote_queue: List[Book]) -> Dict[str, Any]:
        merge_start = time.time()
        print(f"[MERGE START] Remote queue size: {len(remote_queue)}")
        
        local_queue = self.queue_repository.list_books()
        print(f"[MERGE] Local queue size: {len(local_queue)}")
        
        local_by_key = {self._book_sync_key(book): book for book in local_queue}
        remote_by_key: Dict[str, Book] = {}

        for remote_book in remote_queue:
            key = self._book_sync_key(remote_book)
            existing_remote = remote_by_key.get(key)
            if existing_remote is None:
                remote_by_key[key] = remote_book
            else:
                remote_by_key[key] = self._merge_book_records(existing_remote, remote_book)

        merged_books: List[Book] = []
        books_to_enrich: List[Book] = []
        skipped_enrichment_count = 0
        updated = 0
        added = 0
        deleted = 0
        previously_pushed_keys = set(str(key) for key in (self._load_state().get("last_push_book_keys") or []))
        added_items: List[str] = []
        deleted_items: List[str] = []
        updated_items: List[Dict[str, Any]] = []

        for key, remote_book in remote_by_key.items():
            local_match = local_by_key.pop(key, None)
            if local_match is None:
                merged = copy.deepcopy(remote_book)
                added += 1
                added_items.append(self._book_label(merged))
                # New books can legitimately need enrichment.
                if self._metadata_score(merged) < 15:
                    books_to_enrich.append(merged)
                else:
                    merged_books.append(merged)
                    skipped_enrichment_count += 1
            else:
                merged = self._merge_book_records(local_match, remote_book)
                changed_fields = self._changed_fields(
                    local_match,
                    merged,
                    [
                        "normalized_title",
                        "author",
                        "catalog_quantity",
                        "catalog_price",
                        "catalog_ean",
                        "isbn",
                        "isbn_10",
                        "published_date",
                        "pages",
                    ],
                )
                if changed_fields:
                    updated += 1
                    updated_items.append(
                        {
                            "book": self._book_label(merged),
                            "changed_fields": changed_fields,
                        }
                    )

                    # Enrich only when bibliographic identity fields change and metadata is poor.
                    metadata_sensitive_fields = {
                        "normalized_title",
                        "author",
                        "catalog_ean",
                        "isbn",
                        "isbn_10",
                    }
                    if metadata_sensitive_fields.intersection(changed_fields) and self._metadata_score(merged) < 15:
                        books_to_enrich.append(merged)
                    else:
                        merged_books.append(merged)
                        skipped_enrichment_count += 1
                else:
                    # Fully unchanged record: keep as-is and skip expensive enrichment.
                    merged_books.append(merged)
                    skipped_enrichment_count += 1

        print(
            f"[MERGE] Before enrichment: added={added}, updated={updated}, "
            f"to_enrich={len(books_to_enrich)}, skip_enrich={skipped_enrichment_count}"
        )

        enrich_start = time.time()
        enriched_books = []
        if books_to_enrich:
            enriched_books = asyncio.run(self._enrich_books_bulk(books_to_enrich))
            enrich_elapsed = time.time() - enrich_start
            print(f"[ENRICHMENT] Enriched {len(enriched_books)} books in {enrich_elapsed:.2f}s")
            merged_books.extend(enriched_books)
        else:
            enrich_elapsed = 0.0

        skip_start = time.time()
        skip_elapsed = time.time() - skip_start
        print(f"[ENRICHMENT] Skipped {skipped_enrichment_count} books in {skip_elapsed:.3f}s")

        for key, local_book in list(local_by_key.items()):
            if key in previously_pushed_keys:
                self.queue_repository.delete_book(local_book.id)
                deleted += 1
                deleted_items.append(self._book_label(local_book))
                local_by_key.pop(key, None)
                continue
            merged_books.append(local_book)

        print(f"[MERGE] Local-only books kept: {len(local_by_key)}")
        
        upsert_start = time.time()
        self.queue_repository.upsert_many(merged_books)
        upsert_elapsed = time.time() - upsert_start
        print(f"[UPSERT] Saved {len(merged_books)} books in {upsert_elapsed:.2f}s")
        
        total_merge_time = time.time() - merge_start
        print(
            f"[MERGE COMPLETE] Total time: {total_merge_time:.2f}s "
            f"(enrichment={enrich_elapsed:.2f}s, upsert={upsert_elapsed:.2f}s, skipped={skipped_enrichment_count} books)"
        )
        
        return {
            "remote_rows": len(remote_queue),
            "upserted": len(merged_books),
            "added": added,
            "updated": updated,
            "deleted": deleted,
            "local_only": len(local_by_key),
            "added_items": self._limit_preview(added_items),
            "updated_items": self._limit_preview(updated_items),
            "deleted_items": self._limit_preview(deleted_items),
        }

    @staticmethod
    def _sale_sync_key(sale: Dict[str, Any]) -> str:
        base = "|".join(
            [
                str(sale.get("book_id") or "").strip().lower(),
                str(sale.get("normalized_title") or sale.get("raw_title") or "").strip().lower(),
                str(sale.get("author") or "").strip().lower(),
                str(sale.get("sale_date") or "").strip().lower(),
                str(sale.get("isbn") or "").strip().lower(),
                str(sale.get("ean") or "").strip().lower(),
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    def _merge_sale_records(self, local_sale: Optional[Dict[str, Any]], remote_sale: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(local_sale or {})
        for key, value in remote_sale.items():
            if key in {"book_id", "raw_title", "normalized_title", "author", "price", "quantity", "sale_date", "isbn", "ean"}:
                if not self._is_empty_value(value):
                    merged[key] = value
            elif key not in merged or self._is_empty_value(merged.get(key)):
                merged[key] = value
        return merged

    def _merge_sales_with_remote(self, remote_sales: List[Dict[str, Any]]) -> Dict[str, Any]:
        local_sales = self._load_sales()
        local_by_key = {self._sale_sync_key(sale): sale for sale in local_sales}
        remote_by_key: Dict[str, Dict[str, Any]] = {}

        for remote_sale in remote_sales:
            key = self._sale_sync_key(remote_sale)
            existing_remote = remote_by_key.get(key)
            if existing_remote is None:
                remote_by_key[key] = remote_sale
            else:
                remote_by_key[key] = self._merge_sale_records(existing_remote, remote_sale)

        merged_sales: List[Dict[str, Any]] = []
        added = 0
        updated = 0
        added_items: List[str] = []
        updated_items: List[Dict[str, Any]] = []

        for key, remote_sale in remote_by_key.items():
            local_match = local_by_key.pop(key, None)
            if local_match is None:
                merged_sales.append(remote_sale)
                added += 1
                added_items.append(self._sale_label(remote_sale))
            else:
                merged = self._merge_sale_records(local_match, remote_sale)
                changed_fields = self._changed_sale_fields(
                    local_match,
                    merged,
                    ["price", "quantity", "sale_date", "author", "isbn", "ean"],
                )
                if changed_fields:
                    updated += 1
                    updated_items.append(
                        {
                            "sale": self._sale_label(merged),
                            "changed_fields": changed_fields,
                        }
                    )
                merged_sales.append(merged)

        merged_sales.extend(local_by_key.values())
        self._save_sales(merged_sales)
        return {
            "remote_rows": len(remote_sales),
            "upserted": len(merged_sales),
            "added": added,
            "updated": updated,
            "local_only": len(local_by_key),
            "added_items": self._limit_preview(added_items),
            "updated_items": self._limit_preview(updated_items),
        }

    def _reconcile_queue_with_remote(self, remote_queue: List[Book]) -> Dict[str, int]:
        local_queue = self.queue_repository.list_books()
        local_by_key = {self._book_sync_key(book): book for book in local_queue}

        remote_keys: set[str] = set()
        to_upsert: List[Book] = []

        for remote_book in remote_queue:
            key = self._book_sync_key(remote_book)
            remote_keys.add(key)
            local_match = local_by_key.get(key)
            if local_match is not None:
                # Preserve local id when matching by logical fingerprint.
                remote_book.id = local_match.id
            to_upsert.append(remote_book)

        deleted = 0
        for local_book in local_queue:
            key = self._book_sync_key(local_book)
            if key not in remote_keys:
                if self.queue_repository.delete_book(local_book.id):
                    deleted += 1

        self.queue_repository.upsert_many(to_upsert)
        return {
            "remote_rows": len(remote_queue),
            "upserted": len(to_upsert),
            "deleted": deleted,
        }

    def _get_sheets_client(self):
        google_api = importlib.import_module("googleapiclient.discovery")
        build = getattr(google_api, "build")

        credentials = self._get_google_credentials()
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _get_google_credentials(self):
        google_oauth = importlib.import_module("google.oauth2.service_account")
        credentials_cls = getattr(google_oauth, "Credentials")
        return credentials_cls.from_service_account_file(str(self._resolve_service_account_path(self.service_account_file)), scopes=self.SCOPES)

    @staticmethod
    def _rows_from_books(books: List[Book]) -> List[List[Any]]:
        def _best_identifier(book: Book) -> str:
            for value in (
                getattr(book, "isbn", None),
                getattr(book, "isbn_10", None),
                getattr(book, "catalog_ean", None),
            ):
                text = str(value or "").strip()
                if text:
                    return text
            return ""

        headers = [
            "Titolo",
            "Autore",
            "Immagine principale",
            "Prezzo",
            "ISBN",
            "Data pubblicazione",
            "Numero pagine",
            "Categoria",
            "Quantita catalogo",
            "Valutazione media",
        ]
        rows: List[List[Any]] = [headers]
        for book in sorted(books, key=lambda b: b.id):
            categories = ", ".join(getattr(book, "categories", []) or [])
            rows.append(
                [
                    book.normalized_title or book.raw_title,
                    book.author or "",
                    getattr(book, "cover_url", None),
                    "" if book.catalog_price is None else float(book.catalog_price),
                    _best_identifier(book),
                    getattr(book, "published_date", None),
                    getattr(book, "pages", None),
                    categories,
                    "" if book.catalog_quantity is None else int(book.catalog_quantity),
                    getattr(book, "average_rating", None),
                ]
            )
        return rows

    @staticmethod
    def _best_sale_identifier(sale: Dict[str, Any]) -> str:
        for value in (
            sale.get("isbn"),
            sale.get("ean"),
        ):
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _load_sales(self) -> List[Dict[str, Any]]:
        if not self.sold_books_path.exists():
            return []
        try:
            raw = json.loads(self.sold_books_path.read_text(encoding="utf-8-sig"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []

        sales: List[Dict[str, Any]] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            sales.append(row)
        return sales

    def _save_sales(self, sales: List[Dict[str, Any]]) -> None:
        self.sold_books_path.write_text(json.dumps(sales, indent=2, ensure_ascii=False), encoding="utf-8")

    def _rows_from_sales(self, sales: List[Dict[str, Any]]) -> List[List[Any]]:
        headers = [
            "Titolo",
            "Autore",
            "Prezzo",
            "Quantita",
            "Data vendita",
            "ISBN",
            "EAN",
            "ID libro",
        ]
        rows: List[List[Any]] = [headers]
        for sale in sorted(sales, key=lambda s: str(s.get("sale_date") or ""), reverse=True):
            rows.append(
                [
                    sale.get("normalized_title") or sale.get("raw_title") or "",
                    sale.get("author") or "",
                    "" if sale.get("price") is None else float(sale.get("price") or 0.0),
                    int(sale.get("quantity") or 1),
                    sale.get("sale_date") or "",
                    self._best_sale_identifier(sale),
                    sale.get("ean") or "",
                    sale.get("book_id") or "",
                ]
            )
        return rows

    def _sales_from_sheet_values(self, values: List[List[Any]]) -> List[Dict[str, Any]]:
        if not values or len(values) < 2:
            return []

        header = [str(col).strip() for col in values[0]]
        rows = values[1:]
        sales: List[Dict[str, Any]] = []

        for row in rows:
            row_map = {header[i]: row[i] for i in range(min(len(header), len(row)))}

            def _value(*keys: str) -> Any:
                for key in keys:
                    if key in row_map:
                        return row_map.get(key)
                return None

            title = str(_value("Titolo", "Title") or "").strip()
            author = str(_value("Autore", "Author") or "").strip()
            price = self._parse_float(_value("Prezzo", "Price"))
            quantity = self._parse_int(_value("Quantita", "Quantità", "Quantity")) or 1
            sale_date = str(_value("Data vendita", "Sale Date") or "").strip()
            isbn = str(_value("ISBN") or "").strip()
            ean = str(_value("EAN") or "").strip()
            book_id = str(_value("ID libro", "Book ID") or "").strip()

            if not title and not isbn and not ean and not book_id:
                continue

            sales.append(
                {
                    "book_id": book_id,
                    "raw_title": title,
                    "normalized_title": title,
                    "author": author or None,
                    "price": price,
                    "quantity": int(quantity),
                    "sale_date": sale_date,
                    "isbn": isbn or None,
                    "ean": ean or None,
                }
            )

        return sales

    @staticmethod
    def _parse_int(value: Any) -> Optional[int]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_float(value: Any) -> Optional[float]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _stable_id_from_row(title: str, author: str, isbn: str) -> str:
        base = "|".join([title.strip().lower(), author.strip().lower(), isbn.strip().lower()])
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _books_from_sheet_values(values: List[List[Any]], default_status: str) -> List[Book]:
        if not values or len(values) < 2:
            return []

        header = [str(col).strip() for col in values[0]]
        rows = values[1:]
        books: List[Book] = []

        payload_idx = header.index("payload_json") if "payload_json" in header else -1
        id_idx = header.index("id") if "id" in header else -1

        for row in rows:
            try:
                if payload_idx >= 0 and payload_idx < len(row) and row[payload_idx]:
                    data = json.loads(str(row[payload_idx]))
                    if isinstance(data, dict):
                        books.append(BookRepository._dict_to_book(data))
                        continue

                if id_idx >= 0 and id_idx < len(row):
                    book_id = str(row[id_idx]).strip()
                    if not book_id:
                        continue
                    row_map = {header[i]: row[i] for i in range(min(len(header), len(row)))}
                    data = {
                        "id": book_id,
                        "raw_title": row_map.get("normalized_title") or "",
                        "normalized_title": row_map.get("normalized_title") or "",
                        "author": row_map.get("author") or None,
                        "catalog_ean": row_map.get("catalog_ean") or None,
                        "catalog_quantity": int(row_map.get("catalog_quantity") or 0) if str(row_map.get("catalog_quantity") or "").strip() else None,
                        "catalog_price": float(row_map.get("catalog_price") or 0.0) if str(row_map.get("catalog_price") or "").strip() else None,
                        "status": row_map.get("status") or default_status,
                    }
                    books.append(BookRepository._dict_to_book(data))
                    continue

                row_map = {header[i]: row[i] for i in range(min(len(header), len(row)))}
                def _value(*keys: str) -> Any:
                    for key in keys:
                        if key in row_map:
                            return row_map.get(key)
                    return None

                title = str(_value("Titolo", "Title") or "").strip()
                author = str(_value("Autore", "Author") or "").strip()
                isbn = str(_value("ISBN") or "").strip()

                if not title and not isbn:
                    continue

                categories_raw = str(_value("Categoria") or "").strip()
                categories = [c.strip() for c in categories_raw.split(",") if c.strip()] if categories_raw else []

                summary = str(_value("Riassunto contenuto", "Content Summary") or "").strip()
                insights = {"summary": summary, "tags": [], "rejected_information": []} if summary else None

                book_id = SheetsSyncService._stable_id_from_row(title, author, isbn)
                data = {
                    "id": book_id,
                    "raw_title": title,
                    "normalized_title": title,
                    "author": author or None,
                    "cover_url": _value("Immagine principale", "Primary Image") or None,
                    "catalog_price": SheetsSyncService._parse_float(_value("Prezzo")),
                    "isbn": isbn or None,
                    "catalog_ean": isbn or None,
                    "published_date": _value("Data pubblicazione", "Publication Date") or None,
                    "pages": SheetsSyncService._parse_int(_value("Numero pagine", "Number of pages")),
                    "categories": categories,
                    "catalog_quantity": SheetsSyncService._parse_int(_value("Quantita catalogo", "Catalog Quantity")),
                    "average_rating": SheetsSyncService._parse_float(_value("Valutazione media", "Average Rating")),
                    "insights": insights,
                    "status": default_status,
                }
                books.append(BookRepository._dict_to_book(data))
            except Exception:
                continue

        return books

    def _pull_tab(self, service, tab_name: str) -> List[Book]:
        self._ensure_tab_exists(service, tab_name)
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=f"{tab_name}!A:Z")
            .execute()
        )
        values = response.get("values", [])
        default_status = "approved" if tab_name == self.approved_tab else "to_approve"
        return self._books_from_sheet_values(values, default_status)

    def _pull_sales_tab(self, service, tab_name: str) -> List[Dict[str, Any]]:
        self._ensure_tab_exists(service, tab_name)
        response = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=f"{tab_name}!A:Z")
            .execute()
        )
        values = response.get("values", [])
        return self._sales_from_sheet_values(values)

    def _overwrite_tab(self, service, tab_name: str, books: List[Book]) -> None:
        self._ensure_tab_exists(service, tab_name)
        rows = self._rows_from_books(books)

        service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f"{tab_name}!A:Z",
            body={},
        ).execute()

        service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{tab_name}!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()

    def _overwrite_sales_tab(self, service, tab_name: str, sales: List[Dict[str, Any]]) -> None:
        self._ensure_tab_exists(service, tab_name)
        rows = self._rows_from_sales(sales)

        service.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f"{tab_name}!A:Z",
            body={},
        ).execute()

        service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{tab_name}!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()

    def _ensure_tab_exists(self, service, tab_name: str) -> None:
        metadata = service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id,
            fields="sheets.properties.title",
        ).execute()
        existing = {
            str(sheet.get("properties", {}).get("title", "")).strip()
            for sheet in metadata.get("sheets", [])
        }
        if tab_name in existing:
            return

        service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": tab_name,
                            }
                        }
                    }
                ]
            },
        ).execute()

    def pull_remote_into_local(
        self,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> SyncRunResult:
        cfg = self.describe_configuration()
        if not cfg["ready"]:
            return self._not_ready_result()

        started_at = time.time()
        phase_timings = {}

        def _report(progress: int, message: str) -> None:
            if progress_callback is not None:
                progress_callback(max(0, min(100, int(progress))), message)

        def _log_phase(phase_name: str, elapsed_phase: float) -> None:
            phase_timings[phase_name] = elapsed_phase
            print(f"[BIBLIOFORGE SYNC] {phase_name}: {elapsed_phase:.2f}s")

        try:
            # Phase 1: Google Sheets Client
            _report(5, "Connessione a Google Sheets...")
            p1_start = time.time()
            service = self._get_sheets_client()
            _log_phase("Client Setup", time.time() - p1_start)

            # Phase 2: Fetch Books
            _report(20, "Lettura libri dal cloud...")
            p2_start = time.time()
            remote_queue = self._pull_tab(service, self.queue_tab)
            p2_elapsed = time.time() - p2_start
            _log_phase(f"Pull Books ({len(remote_queue)} books)", p2_elapsed)

            # Phase 3: Fetch Sales
            _report(40, "Lettura vendite dal cloud...")
            p3_start = time.time()
            remote_sales = self._pull_sales_tab(service, self.approved_tab)
            p3_elapsed = time.time() - p3_start
            _log_phase(f"Pull Sales ({len(remote_sales)} sales)", p3_elapsed)

            # Phase 4: Merge Books
            _report(60, "Confronto modifiche libri...")
            p4_start = time.time()
            queue_reconcile = self._merge_queue_with_remote(remote_queue)
            p4_elapsed = time.time() - p4_start
            _log_phase(f"Merge Books (added={queue_reconcile['added']}, updated={queue_reconcile['updated']}, deleted={queue_reconcile['deleted']})", p4_elapsed)

            # Phase 5: Merge Sales
            _report(78, "Confronto modifiche vendite...")
            p5_start = time.time()
            sales_reconcile = self._merge_sales_with_remote(remote_sales)
            p5_elapsed = time.time() - p5_start
            _log_phase(f"Merge Sales (added={sales_reconcile['added']}, updated={sales_reconcile['updated']})", p5_elapsed)

            # Phase 6: Save State
            _report(92, "Salvataggio stato locale...")
            p6_start = time.time()
            refreshed_queue = self.queue_repository.list_books()
            refreshed_sales = self._load_sales()
            elapsed = time.time() - started_at

            state = self._load_state()
            state["last_pull_iso"] = self._utc_now_iso()
            history = state.get("pull_duration_history_seconds") or []
            if not isinstance(history, list):
                history = []
            history = [float(item) for item in history if isinstance(item, (int, float))]
            history.append(float(elapsed))
            history = history[-20:]
            avg_seconds = (sum(history) / len(history)) if history else float(elapsed)
            state["last_pull_duration_seconds"] = float(elapsed)
            state["avg_pull_duration_seconds"] = float(avg_seconds)
            state["pull_duration_history_seconds"] = history
            state["pull_phase_timings"] = phase_timings
            state["queue_checksum"] = self._books_checksum(refreshed_queue)
            state["sales_checksum"] = self._payload_checksum(refreshed_sales)
            state["approved_checksum"] = state["sales_checksum"]
            state["last_error"] = None
            self._save_state(state)
            _log_phase("Save State", time.time() - p6_start)
            _report(100, "Confronto completato.")

            print(f"[BIBLIOFORGE SYNC] ===== TOTAL TIME: {elapsed:.2f}s =====")
            print(f"[BIBLIOFORGE SYNC] Phase breakdown: {', '.join([f'{k}={v:.2f}s' for k, v in phase_timings.items()])}")

            details = {
                "books": queue_reconcile,
                "sales": sales_reconcile,
            }

            return SyncRunResult(
                status="ok",
                message=(
                    "Confronto completato: "
                    f"{queue_reconcile['updated']} libri aggiornati, "
                    f"{queue_reconcile['added']} libri nuovi importati, "
                    f"{queue_reconcile['deleted']} libri rimossi, "
                    f"{sales_reconcile['updated']} vendite aggiornate, "
                    f"{sales_reconcile['added']} vendite nuove importate. "
                    f"Tempo: {elapsed:.1f}s (media: {avg_seconds:.1f}s)."
                ),
                pulled_books=int(queue_reconcile["upserted"]),
                details=details,
                elapsed_seconds=float(elapsed),
                average_seconds=float(avg_seconds),
            )
        except Exception as exc:
            print(f"[BIBLIOFORGE SYNC] ERROR: {exc}")
            import traceback
            traceback.print_exc()
            state = self._load_state()
            state["last_error"] = f"pull_failed: {exc}"
            self._save_state(state)
            return SyncRunResult(status="error", message=f"Pull Google Sheets fallito: {exc}")

    def push_local_to_remote(self, force: bool = False) -> SyncRunResult:
        cfg = self.describe_configuration()
        if not cfg["ready"]:
            return self._not_ready_result()

        state = self._load_state()
        now_epoch = time.time()
        last_push_epoch = float(state.get("last_push_epoch", 0.0) or 0.0)
        elapsed = now_epoch - last_push_epoch

        queue_books = self.queue_repository.list_books()
        sales = self._load_sales()
        queue_checksum = self._books_checksum(queue_books)
        sales_checksum = self._payload_checksum(sales)
        queue_rows = len(queue_books)
        sales_rows = len(sales)
        previous_queue_rows = int(state.get("last_push_queue_rows", 0) or 0)
        previous_sales_rows = int(state.get("last_push_sales_rows", 0) or 0)
        queue_added = max(queue_rows - previous_queue_rows, 0)
        queue_deleted = max(previous_queue_rows - queue_rows, 0)
        sales_added = max(sales_rows - previous_sales_rows, 0)
        sales_deleted = max(previous_sales_rows - sales_rows, 0)

        changed = (
            queue_checksum != (state.get("queue_checksum") or "")
            or sales_checksum != (state.get("sales_checksum") or state.get("approved_checksum") or "")
        )

        if not force:
            if elapsed < self.sync_interval_seconds:
                return SyncRunResult(
                    status="skipped",
                    message=f"Prossima sync tra {int(self.sync_interval_seconds - elapsed)}s.",
                    skipped=True,
                )
            if not changed:
                state["last_push_epoch"] = now_epoch
                state["last_push_iso"] = self._utc_now_iso()
                state["last_error"] = None
                self._save_state(state)
                return SyncRunResult(
                    status="skipped",
                    message="Nessuna modifica locale da sincronizzare.",
                    skipped=True,
                )

        try:
            service = self._get_sheets_client()
            self._overwrite_tab(service, self.queue_tab, queue_books)
            self._overwrite_sales_tab(service, self.approved_tab, sales)

            self._mark_push_state(
                state,
                queue_checksum,
                sales_checksum,
                queue_rows,
                sales_rows,
                queue_added,
                queue_deleted,
                sales_added,
                sales_deleted,
                queue_books,
            )

            return SyncRunResult(
                status="ok",
                message="Sync Google Sheets completata.",
                pushed_tabs=2,
            )
        except Exception as exc:
            state["last_error"] = f"push_failed: {exc}"
            self._save_state(state)
            return SyncRunResult(status="error", message=f"Push Google Sheets fallito: {exc}")

    def get_state(self) -> Dict[str, Any]:
        state = self._load_state()
        state["config"] = self.describe_configuration()
        return state
