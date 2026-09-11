"""RealEstateGPT - Platform repositories (MongoDB).

Audit logs, AI conversations/messages, documents, notifications and nearby
places. All reads are ownership-scoped where a user is involved.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pymongo.database import Database

from app.core.database import next_id
from app.models.platform import (
    AuditLog, Conversation, Message, Document, DocumentChunk, Notification,
    NearbyPlace,
)


def _utcnow():
    return datetime.now(timezone.utc)


class AuditRepository:
    def __init__(self, db: Database):
        self.db = db
        self.coll = db["audit_logs"]

    def log(
        self,
        action: str,
        user_id: Optional[int] = None,
        entity: Optional[str] = None,
        entity_id: Optional[int] = None,
        detail: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        aid = next_id(self.db, "audit_logs")
        doc = {
            "_id": aid, "action": action, "user_id": user_id, "entity": entity,
            "entity_id": entity_id, "detail": detail, "ip_address": ip_address,
            "created_at": _utcnow(),
        }
        self.coll.insert_one(doc)
        return AuditLog.from_doc(doc)

    def list(self, limit: int = 100, offset: int = 0) -> List[AuditLog]:
        docs = self.coll.find().sort("created_at", -1).skip(offset).limit(limit)
        return [AuditLog.from_doc(doc) for doc in docs if doc]

    def count(self) -> int:
        return self.coll.count_documents({})

    def count_by_action(self, limit: int = 20) -> dict:
        pipeline = [
            {"$group": {"_id": "$action", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}, {"$limit": limit},
        ]
        return {row["_id"]: row["count"] for row in self.coll.aggregate(pipeline)}


class AIConversationRepository:
    def __init__(self, db: Database):
        self.db = db
        self.conversations = db["conversations"]
        self.messages_coll = db["messages"]

    def create(
        self,
        user_id: int,
        title: Optional[str] = None,
        property_id: Optional[int] = None,
    ) -> Conversation:
        cid = next_id(self.db, "conversations")
        doc = {
            "_id": cid, "user_id": user_id, "title": title or "New chat",
            "property_id": property_id, "created_at": _utcnow(), "updated_at": _utcnow(),
        }
        self.conversations.insert_one(doc)
        return Conversation.from_doc(doc)

    def get(self, conversation_id: int, user_id: int) -> Optional[Conversation]:
        return Conversation.from_doc(
            self.conversations.find_one({"_id": conversation_id, "user_id": user_id})
        )

    def list_for_user(self, user_id: int) -> List[Conversation]:
        docs = self.conversations.find({"user_id": user_id}).sort("updated_at", -1).limit(60)
        return [Conversation.from_doc(doc) for doc in docs if doc]

    def delete(self, conversation_id: int, user_id: int) -> bool:
        conv = self.conversations.find_one_and_delete(
            {"_id": conversation_id, "user_id": user_id}
        )
        if conv:
            self.messages_coll.delete_many({"conversation_id": conversation_id})
            return True
        return False

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        meta: Optional[dict] = None,
    ) -> Message:
        mid = next_id(self.db, "messages")
        doc = {
            "_id": mid, "conversation_id": conversation_id, "role": role,
            "content": content, "meta_json": meta, "created_at": _utcnow(),
        }
        self.messages_coll.insert_one(doc)
        self.conversations.update_one(
            {"_id": conversation_id}, {"$set": {"updated_at": _utcnow()}}
        )
        return Message.from_doc(doc)

    def messages(self, conversation_id: int) -> List[Message]:
        docs = self.messages_coll.find({"conversation_id": conversation_id}).sort("created_at", 1)
        return [Message.from_doc(doc) for doc in docs if doc]

    def count_conversations(self, user_id: Optional[int] = None) -> int:
        query = {"user_id": user_id} if user_id else {}
        return self.conversations.count_documents(query)

    def count_messages(self, user_id: Optional[int] = None) -> int:
        if user_id is None:
            return self.messages_coll.count_documents({})
        ids = [doc["_id"] for doc in self.conversations.find({"user_id": user_id}, {"_id": 1})]
        return self.messages_coll.count_documents({"conversation_id": {"$in": ids}})


class NearbyPlaceRepository:
    def __init__(self, db: Database):
        self.coll = db["nearby_places"]

    def by_city(self, city: str) -> List[NearbyPlace]:
        docs = self.coll.find({"city": city})
        return [NearbyPlace.from_doc(doc) for doc in docs if doc]

    def by_cities(self, cities: List[str]) -> List[NearbyPlace]:
        if not cities:
            return []
        docs = self.coll.find({"city": {"$in": cities}})
        return [NearbyPlace.from_doc(doc) for doc in docs if doc]

    def by_type_in_city(self, city: str, place_type: str) -> List[NearbyPlace]:
        docs = self.coll.find({"city": city, "place_type": place_type})
        return [NearbyPlace.from_doc(doc) for doc in docs if doc]


class DocumentRepository:
    def __init__(self, db: Database):
        self.db = db
        self.documents = db["documents"]
        self.chunks_coll = db["document_chunks"]

    def create(
        self,
        user_id: int,
        filename: str,
        property_id: Optional[int] = None,
        content_type: Optional[str] = None,
        size_bytes: Optional[int] = None,
        storage_key: Optional[str] = None,
    ) -> Document:
        did = next_id(self.db, "documents")
        doc = {
            "_id": did, "user_id": user_id, "property_id": property_id,
            "filename": filename, "content_type": content_type,
            "size_bytes": size_bytes, "storage_key": storage_key,
            "status": "uploaded", "created_at": _utcnow(),
        }
        self.documents.insert_one(doc)
        return Document.from_doc(doc)

    def get(self, document_id: int, user_id: int) -> Optional[Document]:
        return Document.from_doc(
            self.documents.find_one({"_id": document_id, "user_id": user_id})
        )

    def list_for_user(self, user_id: int) -> List[Document]:
        docs = self.documents.find({"user_id": user_id}).sort("created_at", -1)
        return [Document.from_doc(doc) for doc in docs if doc]

    def delete(self, document_id: int, user_id: int) -> bool:
        result = self.documents.delete_one({"_id": document_id, "user_id": user_id})
        if result.deleted_count:
            self.chunks_coll.delete_many({"document_id": document_id})
            return True
        return False

    def set_status(
        self,
        document: Document,
        status: str,
        text_preview: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Document:
        updates: dict = {"status": status}
        if text_preview is not None:
            updates["text_preview"] = text_preview
        if error is not None:
            updates["extraction_error"] = error
        updated = self.documents.find_one_and_update(
            {"_id": document.id}, {"$set": updates}
        )
        return Document.from_doc(updated) or document

    def add_chunks(self, document_id: int, chunks: List[dict]) -> None:
        for chunk in chunks:
            cid = next_id(self.db, "document_chunks")
            self.chunks_coll.insert_one(
                {
                    "_id": cid,
                    "document_id": document_id,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "content": chunk.get("content", ""),
                    "page_number": chunk.get("page_number"),
                    "embedding": chunk.get("embedding"),
                    "metadata_json": chunk.get("metadata_json"),
                    "created_at": _utcnow(),
                }
            )

    def chunks(self, document_id: int) -> List[DocumentChunk]:
        docs = self.chunks_coll.find({"document_id": document_id}).sort("chunk_index", 1)
        return [DocumentChunk.from_doc(doc) for doc in docs if doc]

    def count(self) -> int:
        return self.documents.count_documents({})


class NotificationRepository:
    def __init__(self, db: Database):
        self.db = db
        self.coll = db["notifications"]

    def create(
        self,
        user_id: int,
        type_: str,
        title: str,
        body: Optional[str] = None,
        link: Optional[str] = None,
    ) -> Notification:
        nid = next_id(self.db, "notifications")
        doc = {
            "_id": nid, "user_id": user_id, "type": type_, "title": title,
            "body": body, "link": link, "is_read": False, "created_at": _utcnow(),
        }
        self.coll.insert_one(doc)
        return Notification.from_doc(doc)

    def list_for_user(self, user_id: int, unread_only: bool = False) -> List[Notification]:
        query: dict = {"user_id": user_id}
        if unread_only:
            query["is_read"] = False
        docs = self.coll.find(query).sort("created_at", -1).limit(50)
        return [Notification.from_doc(doc) for doc in docs if doc]

    def mark_read(self, user_id: int, notification_id: int) -> bool:
        result = self.coll.update_one(
            {"_id": notification_id, "user_id": user_id},
            {"$set": {"is_read": True}},
        )
        return result.matched_count > 0