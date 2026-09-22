"""In-memory MongoDB emulation for fast, DB-free unit tests.

Implements exactly the subset of PyMongo operations the discovery layer uses:
insert_one, find_one, find (with limit/sort), update_one (with ``$set`` and
upsert), update_many, delete_one, delete_many, count_documents and
create_index (no-op). Only the query operators actually used are supported
(``$gt``, ``$lt``, ``$in``, ``$ne``, ``$exists``).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional


class FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def __iter__(self):
        return iter(self._docs)

    def limit(self, n: Optional[int]):
        self._docs = self._docs[:n] if n else self._docs
        return self

    def sort(self, key, direction: int = 1):
        reverse = direction < 0
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=reverse)
        elif isinstance(key, (list, tuple)):
            for field, order in reversed(key):
                self._docs.sort(key=lambda d: d.get(field), reverse=order < 0)
        return self


def _matches(doc: dict, query: dict) -> bool:
    for key, expected in (query or {}).items():
        if key == "$and":
            if not all(_matches(doc, q) for q in expected):
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
        if isinstance(expected, dict) and any(op in expected for op in ("$gt", "$lt", "$gte", "$lte", "$in", "$ne", "$exists")):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$gt" in expected and not (actual > expected["$gt"]):
                return False
            if "$lt" in expected and not (actual < expected["$lt"]):
                return False
            if "$gte" in expected and not (actual >= expected["$gte"]):
                return False
            if "$lte" in expected and not (actual <= expected["$lte"]):
                return False
            continue
        if expected is not None and actual != expected:
            return False
    return True

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
        return SimpleResult(1)

    def find_one(self, query: Optional[dict] = None, projection: Optional[dict] = None) -> Optional[dict]:
        for doc in self._docs:
            if _matches(doc, query or {}):
                if projection:
                    return {k: v for k, v in doc.items() if k in projection or k == "_id"}
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

    def sort(self, *args, **kwargs):
        return self


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
    def __init__(self, count: int) -> None:
        self.deleted_count = count
        self.modified_count = count
        self.upserted_id = None


class FakeDB:
    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]

    def collections(self) -> Iterable[FakeCollection]:
        return self._collections.values()
