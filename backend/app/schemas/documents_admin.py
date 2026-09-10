"""RealEstateGPT - Document & admin schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class DocumentResponse(BaseModel):
    id: int
    filename: str
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    property_id: Optional[int] = None
    status: str
    text_preview: Optional[str] = None
    chunk_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    id: int
    filename: str
    status: str
    message: str


class DocumentAskResponse(BaseModel):
    document_id: int
    question: str
    answer: str
    citations: List[dict] = []
    disclaimer: str = ("AI analysis is informational and not legal advice. "
                       "Verify critical facts with qualified professionals.")


# ─── Admin ─────────────────────────────────────────────────────────────

class AdminUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    is_email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserListResponse(BaseModel):
    users: List[AdminUserResponse]
    total: int


class AdminPropertyItemResponse(BaseModel):
    id: int
    title: str
    city: str
    locality: Optional[str] = None
    price: float
    property_type: str
    verification_status: str
    is_active: bool
    is_synthetic: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminPropertyListResponse(BaseModel):
    properties: List[AdminPropertyItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    action: str
    entity: Optional[str] = None
    entity_id: Optional[int] = None
    detail: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAiUsageResponse(BaseModel):
    total_messages: int
    total_conversations: int
    tool_calls: int
    offline_mode: bool
    provider: str
    by_action: dict = {}