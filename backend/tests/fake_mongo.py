"""In-memory MongoDB emulation for fast, DB-free unit tests.

Implements exactly the subset of PyMongo operations the discovery layer uses:
insert_one, find_one, find (with limit/sort), update_one (with ``$set`` and
upsert), update_many, delete_one, delete_many, count_documents and
create_index (no-op). Only the query operators actually used are supported
(``$gt``, ``$lt``, ``$in``, ``$ne``, ``$exists``).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def __iter__(self):
        return iter(self._docs)

    def limit(self, n: Optional[int]):
        self._docs = self._docs[:n] if n else self._docs
        return self

    def skip(self, n: int):
        self._docs = self._docs[n:] if n else self._docs
        return self

    @staticmethod
    def _sort_key(value: Any):
        # Missing/None values sort last in both directions, matching how a
        # driver treats a absent field, and never raise on mixed types.
        return (value is None, value if isinstance(value, (int, float, str)) else str(value))

    def sort(self, key, direction: int = 1):
        reverse = direction < 0
        if isinstance(key, str):
            self._docs.sort(key=lambda d: self._sort_key(d.get(key)), reverse=reverse)
        elif isinstance(key, (list, tuple)):
            for field, order in reversed(key):
                self._docs.sort(key=lambda d: self._sort_key(d.get(field)), reverse=order < 0)
        return self


def _comparable(value: Any) -> Any:
    """Normalize datetimes the way PyMongo does: naive UTC on both sides.

    PyMongo returns naive UTC datetimes, so a stored ``expires_at`` is naive
    while ``datetime.now(timezone.utc)`` is aware. Comparing the two directly
    raises TypeError, so both sides are coerced to naive UTC first — exactly
    what MongoDB does server-side.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    return value


def _matches(doc: dict, query: dict) -> bool:
    for key, expected in (query or {}).items():
        if key == "$and":
            if not all(_matches(doc, q) for q in expected):
                return False
            continue
        if key == "$or":
            if not any(_matches(doc, q) for q in expected):
                return False
            continue
        if key not in doc:
            if isinstance(expected, dict) and "$exists" in expected:
                if expected["$exists"]:
                    return False
                continue
            if expected is None:
                continue
            return False
        actual = doc.get(key)
        if isinstance(expected, dict) and any(op in expected for op in ("$gt", "$lt", "$gte", "$lte", "$in", "$ne", "$exists", "$regex", "$options", "$or")):
            if "$regex" in expected:
                if not _regex_matches(actual, expected["$regex"], expected.get("$options", "")):
                    return False
                continue
            if "$ne" in expected and _comparable(actual) == _comparable(expected["$ne"]):
                return False
            if "$in" in expected and _comparable(actual) not in [_comparable(v) for v in expected["$in"]]:
                return False
            if "$gt" in expected and not (actual is not None and _comparable(actual) > _comparable(expected["$gt"])):
                return False
            if "$lt" in expected and not (actual is not None and _comparable(actual) < _comparable(expected["$lt"])):
                return False
            if "$gte" in expected and not (actual is not None and _comparable(actual) >= _comparable(expected["$gte"])):
                return False
            if "$lte" in expected and not (actual is not None and _comparable(actual) <= _comparable(expected["$lte"])):
                return False
            continue
        if expected is not None and _comparable(actual) != _comparable(expected):
            return False
    return True


def _regex_matches(value, pattern: str, options: str) -> bool:
    """Evaluate a Mongo ``$regex`` predicate the way the driver does."""
    if not isinstance(value, str):
        return False
    flags = re.IGNORECASE if "i" in str(options) else 0
    return re.search(pattern, value, flags) is not None

class FakeCollection:
    def __init__(self) -> None:
        self._docs: list[dict[str, Any]] = []
        self._next_id = 1

    def create_index(self, *args, **kwargs):
        return None

    def insert_one(self, doc: dict) -> Any:
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = self._next_id
        self._next_id += 1
        self._docs.append(d)
        return SimpleResult(1, inserted_id=d["_id"])

    def find_one(self, query: Optional[dict] = None, projection: Optional[dict] = None) -> Optional[dict]:
        for doc in self._docs:
            if _matches(doc, query or {}):
                if projection:
                    return {k: v for k, v in doc.items() if k in projection or k == "_id"}
                return dict(doc)
        return None

    def find_one_and_update(
        self,
        query: dict,
        update: dict,
        upsert: bool = False,
        return_document: Any = None,
    ) -> Optional[dict]:
        """Approximate the atomic counter allocation used by ``next_id``."""
        for doc in self._docs:
            if _matches(doc, query):
                _apply_update(doc, update)
                return dict(doc)
        if upsert:
            doc = dict(query)
            _apply_update(doc, update)
            self._docs.append(doc)
            return dict(doc)
        return None

    def find(self, query: Optional[dict] = None, projection: Optional[dict] = None) -> FakeCursor:
        matched = []
        for doc in self._docs:
            if _matches(doc, query or {}):
                if projection:
                    matched.append({k: v for k, v in doc.items() if k in projection or k == "_id"})
                else:
                    matched.append(dict(doc))
        return FakeCursor(matched)

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> Any:
        for doc in self._docs:
            if _matches(doc, query):
                _apply_update(doc, update)
                return SimpleResult(1)
        if upsert:
            doc = dict(query)
            _apply_update(doc, update)
            if "_id" not in doc:
                doc["_id"] = self._next_id
            self._next_id += 1
            self._docs.append(doc)
            return SimpleResult(1)
        return SimpleResult(0)

    def update_many(self, query: dict, update: dict) -> Any:
        modified = 0
        for doc in self._docs:
            if _matches(doc, query):
                _apply_update(doc, update)
                modified += 1
        return SimpleResult(modified)

    def delete_one(self, query: dict) -> Any:
        for index, doc in enumerate(self._docs):
            if _matches(doc, query):
                self._docs.pop(index)
                return SimpleResult(1)
        return SimpleResult(0)

    def delete_many(self, query: dict) -> Any:
        before = len(self._docs)
        self._docs = [doc for doc in self._docs if not _matches(doc, query)]
        return SimpleResult(before - len(self._docs))

    def count_documents(self, query: Optional[dict] = None) -> int:
        return sum(1 for doc in self._docs if _matches(doc, query or {}))

    def distinct(self, key: str, query: Optional[dict] = None) -> list:
        """Values of ``key`` across matching documents, in first-seen order."""
        values: list = []
        for doc in self._docs:
            if not _matches(doc, query or {}):
                continue
            if key not in doc:
                continue
            value = doc[key]
            if value not in values:
                values.append(value)
        return values

    def aggregate(self, pipeline: list, **kwargs) -> list:
        """Execute the small $match/$group/$sort/$limit subset used in tests."""
        docs = [dict(doc) for doc in self._docs]
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if _matches(d, stage["$match"])]
            elif "$group" in stage:
                docs = _apply_group(docs, stage["$group"])
            elif "$sort" in stage:
                for field, order in reversed(list(stage["$sort"].items())):
                    docs.sort(key=lambda d: (d.get(field) is None, d.get(field)), reverse=order < 0)
            elif "$limit" in stage:
                docs = docs[: stage["$limit"]]
            elif "$project" in stage:
                docs = [_apply_project(d, stage["$project"]) for d in docs]
        return docs

    def sort(self, *args, **kwargs):
        return self


def _median(ordered: list) -> float:
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _apply_group(docs: list[dict], spec: dict) -> list[dict]:
    grouped: dict = {}
    for doc in docs:
        key_parts = tuple(doc.get(field.lstrip("$")) if isinstance(field, str) else doc.get(field["$literal"]) for field in spec["_id"].values()) if isinstance(spec["_id"], dict) else (doc.get(spec["_id"].lstrip("$")),)
        bucket = grouped.setdefault(key_parts, {"_id": key_parts[0] if len(key_parts) == 1 else dict(zip(spec["_id"].keys(), key_parts)), "_values": []})
        bucket["_values"].append(doc)

    rows: list[dict] = []
    for bucket in grouped.values():
        row = {"_id": bucket["_id"]}
        for field, accumulator in spec.items():
            if field == "_id":
                continue
            op, source = next(iter(accumulator.items()))
            values = [d.get(source.lstrip("$")) for d in bucket["_values"]]
            values = [v for v in values if v is not None]
            if op == "$sum":
                row[field] = len(values) if source == 1 else sum(values)
            elif op == "$avg":
                row[field] = (sum(values) / len(values)) if values else None
            elif op == "$median":
                ordered = sorted(values)
                row[field] = _median(ordered) if ordered else None
            elif op == "$addToSet":
                row[field] = list(dict.fromkeys(values))
        rows.append(row)
    return rows


def _apply_project(doc: dict, spec: dict) -> dict:
    row: dict = {}
    for field, expression in spec.items():
        if isinstance(expression, int):
            if expression:
                row[field] = doc.get(field)
        elif isinstance(expression, dict):
            op, source = next(iter(expression.items()))
            if op == "$size":
                row[field] = len(doc.get(source.lstrip("$"), []) or [])
            elif op == "$filter":
                row[field] = doc.get(source.get("input", "").lstrip("$"), []) or []
        else:
            row[field] = doc.get(expression.lstrip("$"))
    return row


def _apply_update(doc: dict, update: dict) -> None:
    for op, payload in update.items():
        if op == "$set":
            for key, value in payload.items():
                _set_path(doc, key, value)
        elif op == "$inc":
            for key, value in payload.items():
                doc[key] = doc.get(key, 0) + value


def _set_path(doc: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    current = doc
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


class SimpleResult:
    def __init__(self, count: int, inserted_id: Any = None) -> None:
        self.deleted_count = count
        self.modified_count = count
        self.upserted_id = None
        self.inserted_id = inserted_id


class FakeDB:
    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    def collections(self) -> Iterable[FakeCollection]:
        return self._collections.values()
