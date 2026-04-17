"""Google Sheets synchronization service for central multi-device consistency."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from biblioforge.models.book import Book
from biblioforge.repositories.book_repository import BookRepository


@dataclass
class SyncRunResult:
    status: str
    message: str
    pushed_tabs: int = 0
    pulled_books: int = 0
    skipped: bool = False


class SheetsSyncService:
    """Two-way sync between local JSON repos and Google Sheets.

    Sync model:
    - Local repositories remain source of truth for edits during runtime.
    - A scheduled push (default 10m) overwrites remote tabs atomically to avoid duplicates.
    - Remote edits are not pulled automatically; local state wins.
    - Conflict strategy (default): local_wins.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    ROME_TZ = ZoneInfo("Europe/Rome")

    def _resolve_service_account_path(self) -> Path:
        raw = str(self.service_account_file or "").strip()
        if not raw:
            return Path("")

        configured = Path(raw).expanduser()
        if configured.is_absolute():
            if configured.exists():
                return configured
            # Portability fallback: reuse the same credentials filename in the local data folder.
            fallback = self.state_path.parent / configured.name
            if fallback.exists():
                return fallback
            return configured

        relative_candidate = (self.state_path.parent / configured).resolve()
        if relative_candidate.exists():
            return relative_candidate

        cwd_candidate = (Path.cwd() / configured).resolve()
        if cwd_candidate.exists():
            return cwd_candidate

        return relative_candidate

    def _normalize_service_account_for_storage(self, service_account_file: str) -> str:
        raw = str(service_account_file or "").strip()
        if not raw:
            return ""

        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            return Path(raw).as_posix()

        try:
            return candidate.resolve().relative_to(self.state_path.parent.resolve()).as_posix()
        except Exception:
            return str(candidate)

    def __init__(
        self,
        queue_repository: BookRepository,
        approved_repository: BookRepository,
        state_path: Path,
    ) -> None:
        self.queue_repository = queue_repository
        self.approved_repository = approved_repository
        self.state_path = Path(state_path)
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
        self.service_account_file = (env_sa if env_sa is not None else persisted.get("service_account_file", "")).strip()
        self.queue_tab = ((env_queue if env_queue is not None else persisted.get("queue_tab", "Libri")).strip() or "Libri")
        self.approved_tab = ((env_approved if env_approved is not None else persisted.get("approved_tab", "Vendite")).strip() or "Vendite")
        self.conflict_policy = ((env_policy if env_policy is not None else persisted.get("conflict_policy", "local_wins")).strip().lower() or "local_wins")

        if env_enabled is None:
            self.enabled = bool(persisted.get("enabled", False))
        else:
            self.enabled = str(env_enabled).strip().lower() in {"1", "true", "yes", "y", "on"}

        # Fallback: if no service-account path is configured, use the conventional local path.
        if not self.service_account_file:
            default_sa = self.state_path.parent / "google_service_account.json"
            if default_sa.exists():
                self.service_account_file = str(default_sa)

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

<<<<<<< HEAD
=======
    def _resolve_service_account_path(self, service_account_file: str) -> Path:
        raw_path = str(service_account_file or "").strip()
        if not raw_path:
            return Path()
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            # Try to return as-is first if it exists
            if path.exists():
                return path
            # If absolute path doesn't exist, still return it (will fail later with clear error)
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

        # Prefer state_path.parent as fallback for relative paths stored in config
        return self.state_path.parent / path

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

>>>>>>> b968eecf6efc10fdbcf7fb8e5b5dcc4e3cbfcdb7
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
            self.service_account_file = self._normalize_service_account_for_storage(service_account_file)

        self.spreadsheet_id = sheet_id
        self.enabled = bool(enabled)
        self._save_persisted_config()
        return {"ok": True, "message": "Collegamento Google Sheets salvato."}

    def save_service_account_file(self, service_account_file: str) -> Dict[str, Any]:
        path = self._normalize_service_account_for_storage(service_account_file)
        if not path:
            return {"ok": False, "message": "Percorso credenziali non valido."}
        self.service_account_file = path
        self._save_persisted_config()
        return {"ok": True, "message": "Credenziali Google salvate."}

    def disable_connection(self) -> None:
        self.enabled = False
        self._save_persisted_config()

    def list_drive_spreadsheets(self, limit: int = 50) -> List[Dict[str, str]]:
        cfg = self.describe_configuration()
        if cfg.get("missing") and "BIBLIOFORGE_SHEETS_SPREADSHEET_ID" in cfg.get("missing", []):
            # Listing from Drive only needs credentials, not selected spreadsheet id.
            if not self.service_account_file or not self._resolve_service_account_path().exists():
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
        elif not self._resolve_service_account_path().exists():
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
    ) -> None:
        state["last_push_epoch"] = time.time()
        state["last_push_iso"] = self._utc_now_iso()
        state["last_push_queue_rows"] = queue_rows
        state["last_push_sales_rows"] = sales_rows
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
        try:
            google_api = importlib.import_module("googleapiclient.discovery")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Dipendenza mancante: modulo 'googleapiclient'. "
                "Installa i pacchetti nel venv attivo con: pip install -r requirements.txt"
            ) from exc
        build = getattr(google_api, "build")

        credentials = self._get_google_credentials()
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def _get_google_credentials(self):
        try:
            google_oauth = importlib.import_module("google.oauth2.service_account")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Dipendenza mancante: modulo 'google.oauth2'. "
                "Installa i pacchetti nel venv attivo con: pip install -r requirements.txt"
            ) from exc
        credentials_cls = getattr(google_oauth, "Credentials")
        resolved_service_account = self._resolve_service_account_path()
        return credentials_cls.from_service_account_file(str(resolved_service_account), scopes=self.SCOPES)

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
        seen_keys: set[str] = set()
        for book in sorted(books, key=lambda b: b.id):
            # Mirror only one row per logical book to avoid duplicate titles in Sheets.
            fingerprint = SheetsSyncService._book_fingerprint(book)
            key = fingerprint if fingerprint.strip("|") else f"id:{book.id}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

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

    def pull_remote_into_local(self) -> SyncRunResult:
        cfg = self.describe_configuration()
        if not cfg["ready"]:
            return self._not_ready_result()

        try:
            service = self._get_sheets_client()
            remote_queue = self._pull_tab(service, self.queue_tab)

            reconcile = self._reconcile_queue_with_remote(remote_queue)

            state = self._load_state()
            state["last_pull_iso"] = self._utc_now_iso()
            state["last_error"] = None
            self._save_state(state)

            return SyncRunResult(
                status="ok",
                message=(
                    "Pull completato: "
                    f"{reconcile['remote_rows']} righe allineate, "
                    f"{reconcile['deleted']} libri rimossi localmente."
                ),
                pulled_books=int(reconcile["upserted"]),
            )
        except Exception as exc:
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
