# ============================================
# ContentFlow — SQLAlchemy ORM 모델
# ============================================
from sqlalchemy import (
    Column, String, Boolean, Integer, Text,
    ForeignKey, DateTime, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String(255), unique=True, nullable=False)
    name            = Column(String(100))
    onboarding_done = Column(Boolean, default=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    personas    = relationship("UserPersona",    back_populates="user", cascade="all, delete")
    categories  = relationship("Category",       back_populates="user", cascade="all, delete")
    channels    = relationship("ChannelConfig",  back_populates="user", cascade="all, delete")
    sessions    = relationship("ContentSession", back_populates="user", cascade="all, delete")


class UserPersona(Base):
    __tablename__ = "user_personas"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    raw_answers = Column(JSON, nullable=False)   # 온보딩 원본 답변
    persona_md  = Column(Text, nullable=False)   # 생성된 persona.md
    style_md    = Column(Text, nullable=False)   # 생성된 style.md
    topic_md    = Column(Text, nullable=True, default="")  # 생성된 topic.md
    version     = Column(Integer, default=1)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="personas")


class Category(Base):
    __tablename__ = "categories"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(100), nullable=False)
    description = Column(Text)
    color       = Column(String(20))
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=0)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    user     = relationship("User",    back_populates="categories")
    keywords = relationship("Keyword", back_populates="category", cascade="all, delete")


class Keyword(Base):
    __tablename__ = "keywords"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id",       ondelete="CASCADE"), nullable=False)
    category_id    = Column(UUID(as_uuid=True), ForeignKey("categories.id",  ondelete="CASCADE"), nullable=False)
    keyword        = Column(String(200), nullable=False)
    target_emotion = Column(Text)
    memo           = Column(Text)
    exclude_topics = Column(Text)
    usage_count    = Column(Integer, default=0)
    last_used_at   = Column(DateTime(timezone=True))
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("Category", back_populates="keywords")


class ChannelConfig(Base):
    __tablename__ = "channel_configs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel_type = Column(String(50), nullable=False)  # blog|newsletter|youtube|shortform
    channel_name = Column(String(100))
    api_endpoint = Column(Text)
    api_key_enc  = Column(Text)                        # 암호화 저장
    extra_config = Column(JSON)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="channels")


class ContentSession(Base):
    __tablename__ = "content_sessions"

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id",       ondelete="CASCADE"), nullable=False)
    category_id      = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    keyword_id       = Column(UUID(as_uuid=True), ForeignKey("keywords.id"),   nullable=True)
    input_keyword    = Column(Text, nullable=False)
    input_emotion    = Column(Text)
    input_memo       = Column(Text)
    input_exclude    = Column(Text)
    topic_candidates = Column(JSON)   # 오케스트레이터가 제안한 주제 후보 3개
    selected_topic   = Column(JSON)   # 사용자가 선택한 주제
    status           = Column(String(50), default="pending")
    error_message    = Column(Text)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    user   = relationship("User", back_populates="sessions")
    drafts = relationship("ContentDraft", back_populates="session", cascade="all, delete")


class ContentDraft(Base):
    __tablename__ = "content_drafts"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id    = Column(UUID(as_uuid=True), ForeignKey("content_sessions.id", ondelete="CASCADE"), nullable=False)
    user_id       = Column(UUID(as_uuid=True), ForeignKey("users.id",            ondelete="CASCADE"), nullable=False)
    channel_type  = Column(String(50), nullable=False)
    title         = Column(Text)
    body_md       = Column(Text)
    body_html     = Column(Text)
    meta          = Column(JSON)
    qc_passed     = Column(Boolean)
    qc_results    = Column(JSON)
    status        = Column(String(50), default="pending")
    revision_memo  = Column(Text)
    notion_page_id = Column(String(100))
    published_at   = Column(DateTime(timezone=True))
    published_url  = Column(Text)
    llm_model     = Column(String(100))
    generation_ms = Column(Integer)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    session      = relationship("ContentSession", back_populates="drafts")
    review_logs  = relationship("ReviewLog",      back_populates="draft", cascade="all, delete")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id   = Column(UUID(as_uuid=True), ForeignKey("content_drafts.id", ondelete="CASCADE"), nullable=False)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id",          ondelete="CASCADE"), nullable=False)
    action     = Column(String(50), nullable=False)  # approved|revision|rejected
    memo       = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    draft = relationship("ContentDraft", back_populates="review_logs")
