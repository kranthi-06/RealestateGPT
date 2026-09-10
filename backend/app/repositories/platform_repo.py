"""RealEstateGPT - Repositories for platform models (audit, AI, documents, notifications)."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.platform import (
    AuditLog, Conversation, Message, Document, DocumentChunk, Notification,
)


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def log(self, action: str, user_id: Optional[int] = None, entity: Optional[str] = None,
            entity_id: Optional[int] = None, detail: Optional[dict] = None,
            ip_address: Optional[str] = None) -> AuditLog:
        entry = AuditLog(
            user_id=user_id, action=action, entity=entity, entity_id=entity_id,
            detail=detail, ip_address=ip_address,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def list(self, limit: int = 100, offset: int = 0) -> List[AuditLog]:
        return (
            self.db.query(AuditLog)
            .order_by(AuditLog.id.desc())
            .limit(limit).offset(offset).all()
        )

    def count(self) -> int:
        return self.db.query(AuditLog).count()

    def count_by_action(self, limit: int = 20) -> dict:
        rows = self.db.query(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action).all()
        return {action: count for action, count in rows}


class AIConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, title: Optional[str] = None,
               property_id: Optional[int] = None) -> Conversation:
        conv = Conversation(user_id=user_id, title=title or "New chat", property_id=property_id)
        self.db.add(conv)
        self.db.commit()
        self.db.refresh(conv)
        return conv

    def get(self, conversation_id: int, user_id: int) -> Optional[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )

    def list_for_user(self, user_id: int) -> List[Conversation]:
        return (
            self.db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(60)
            .all()
        )

    def delete(self, conversation_id: int, user_id: int) -> bool:
        result = (
            self.db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .delete()
        )
        self.db.commit()
        return result > 0

    def add_message(self, conversation_id: int, role: str, content: str,
                    meta: Optional[dict] = None) -> Message:
        msg = Message(conversation_id=conversation_id, role=role, content=content, meta_json=meta)
        self.db.add(msg)
        self.db.commit()
        self.db.refresh(msg)
        conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conv:
            conv.updated_at = func.now()
            self.db.commit()
        return msg

    def messages(self, conversation_id: int) -> List[Message]:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.asc())
            .all()
        )
class DocumentRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, filename: str, content_type: Optional[str],
               size_bytes: Optional[int], storage_key: str,
               property_id: Optional[int] = None, status: str = "uploaded") -> Document:
        doc = Document(
            user_id=user_id, filename=filename, content_type=content_type,
            size_bytes=size_bytes, storage_key=storage_key,
            property_id=property_id, status=status,
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get(self, document_id: int, user_id: Optional[int] = None) -> Optional[Document]:
        query = self.db.query(Document).filter(Document.id == document_id)
        if user_id:
            query = query.filter(Document.user_id == user_id)
        return query.first()

    def list_for_user(self, user_id: int) -> List[Document]:
        return (
            self.db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .all()
        )

    def delete(self, document_id: int, user_id: int) -> bool:
        result = (
            self.db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user_id)
            .delete()
        )
        self.db.commit()
        return result > 0

    def set_status(self, document: Document, status: str,
                   text_preview: Optional[str] = None,
                   error: Optional[str] = None) -> Document:
        document.status = status
        if text_preview is not None:
            document.text_preview = text_preview
        if error is not None:
            document.extraction_error = error
        self.db.commit()
        self.db.refresh(document)
        return document

    def add_chunks(self, document_id: int, chunks: List[dict]) -> None:
        for chunk in chunks:
            row = DocumentChunk(
                document_id=document_id,
                chunk_index=chunk.get("chunk_index", 0),
                content=chunk.get("content", ""),
                page_number=chunk.get("page_number"),
                embedding=chunk.get("embedding"),
                metadata_json=chunk.get("metadata_json"),
            )
            self.db.add(row)
        self.db.commit()

    def chunks(self, document_id: int) -> List[DocumentChunk]:
        return (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
            .all()
        )

    def count(self) -> int:
        return self.db.query(Document).count()


class NotificationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, user_id: int, type_: str, title: str, body: Optional[str] = None,
               link: Optional[str] = None) -> Notification:
        note = Notification(user_id=user_id, type=type_, title=title, body=body, link=link)
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def list_for_user(self, user_id: int, unread_only: bool = False) -> List[Notification]:
        query = self.db.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            query = query.filter(Notification.is_read == False)  # noqa: E712
        return query.order_by(Notification.created_at.desc()).limit(50).all()

    def mark_read(self, user_id: int, notification_id: int) -> bool:
        note = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if not note:
            return False
        note.is_read = True
        self.db.commit()
        return True

    def count_messages(self, user_id: Optional[int] = None) -> int:
        query = self.db.query(Message).join(Conversation)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        return query.count()

    def count_conversations(self, user_id: Optional[int] = None) -> int:
        query = self.db.query(Conversation)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        return query.count()
