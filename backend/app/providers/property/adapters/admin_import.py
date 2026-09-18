"""AdminImportProvider — reads a platform-admin-authored listing file.

This is a legitimate inventory path: the operator imports data they are
licensed or authorized to use (e.g. an internal CRM export, a partner CSV, or
an authorized feed re-export). It never scrapes third-party websites.

File formats supported:
  * JSONL  (.jsonl / .ndjson) — one canonical record per line
  * JSON   (.json)           — JSON array of records
  * CSV    (.csv)            — header row; column names use canonical fields

An optional per-record ``status`` field is honored by ``refresh``:
  active  -> listing remains live
  sold / rented / inactive -> provider-confirmed terminal state
  missing -> treated as "provider no longer returns it" (NOT terminal)
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.providers.property.adapters.base import BasePropertyAdapter
from app.providers.property.errors import (
    ProviderListingNotFoundError,
    ProviderNotConfiguredError,
)

logger = logging.getLogger(__name__)


class AdminImportProvider(BasePropertyAdapter):
    name = "admin_import"
    source_type = "admin"

    def __init__(self, *, file_path: Optional[str] = None) -> None:
        super().__init__()
        self.file_path = file_path or settings.PROPERTY_PROVIDER_FILE
        if not self.file_path:
            raise ProviderNotConfiguredError(
                "admin_import is selected but PROPERTY_PROVIDER_FILE is not set"
            )
        self._records: Optional[List[Dict[str, Any]]] = None
        self._index: Dict[str, int] = {}

    # ── Loading helpers ────────────────────────────────────────────────

    def _load(self) -> List[Dict[str, Any]]:
        if self._records is not None:
            return self._records
        path = Path(self.file_path)
        if not path.exists():
            logger.warning("admin_import file missing path=%s", self.file_path)
            self._records = []
            return self._records

        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                records = self._load_csv(path)
            elif suffix in (".jsonl", ".ndjson", ".json"):
                records = self._load_json(path)
            else:
                logger.error("admin_import unsupported file type suffix=%s", suffix)
                records = []
        except Exception as exc:  # never let one bad file block the worker
            logger.error("admin_import failed to load path=%s error=%s", path, exc)
            records = []

        cleaned = [r for r in records if isinstance(r, dict) and r.get("source_listing_id")]
        self._records = cleaned
        self._index = {str(r["source_listing_id"]): i for i, r in enumerate(cleaned)}
        logger.info("admin_import loaded records=%s path=%s", len(cleaned), path)
        return self._records

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8-sig") as handle:
            text = handle.read()
        if path.suffix.lower() == ".json":
            data = json.loads(text)
            return data if isinstance(data, list) else [data]
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def _load_csv(self, path: Path) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]
# ── Provider operations (normalized records) ───────────────────────

    async def fetch_properties(self, cursor: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        await self._throttle()
        records = self._load()
        start = int(cursor) if cursor else 0
        batch = records[start:start + settings.INGESTION_BATCH_SIZE]
        next_cursor = str(start + len(batch)) if start + len(batch) < len(records) else None
        return [r for r in batch], next_cursor

    async def get_property(self, source_listing_id: str) -> Dict[str, Any]:
        await self._throttle()
        self._load()
        index = self._index.get(str(source_listing_id))
        if index is None:
            raise ProviderListingNotFoundError(f"listing {source_listing_id} not present in import file")
        return dict(self._records[index])

    async def refresh(self, source_listing_id: str) -> Dict[str, Any]:
        """Return the current record. Terminal status in the file is honored;
        absence of the record is NOT treated as a terminal state."""
        await self._throttle()
        self._load()
        index = self._index.get(str(source_listing_id))
        if index is None:
            # Provider is reachable but no longer returns the listing. The
            # refresh worker marks it stale — never sold/inactive directly.
            raise ProviderListingNotFoundError(
                f"listing {source_listing_id} no longer returned by provider"
            )
        return dict(self._records[index])

    async def search(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        await self._throttle()
        records = self._load()
        results = []
        for record in records:
            if self._match(record, intent):
                results.append(dict(record))
        return results

    @staticmethod
    def _match(record: Dict[str, Any], intent: Dict[str, Any]) -> bool:
        for key in ("city", "locality", "property_type"):
            expected = intent.get(key)
            if expected and str(record.get(key, "")).lower() != str(expected).lower():
                return False
        listing_type = intent.get("listing_type") or intent.get("transaction_type")
        if listing_type:
            rec_type = record.get("listing_type") or record.get("transaction_type")
            if rec_type and str(rec_type).lower() != str(listing_type).lower():
                return False
        min_price = intent.get("min_price")
        if min_price is not None and float(record.get("price", 0) or 0) < min_price:
            return False
        max_price = intent.get("max_price")
        if max_price is not None and float(record.get("price", 0) or 0) > max_price:
            return False
        bedrooms = intent.get("bedrooms")
        if bedrooms is not None and record.get("bedrooms") not in (None, "", bedrooms):
            if int(record.get("bedrooms", 0) or 0) != int(bedrooms):
                return False
        return True