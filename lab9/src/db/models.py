from sqlalchemy import Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(2048), unique=True)
    source_language: Mapped[str] = mapped_column(String(16))
    file_hash: Mapped[str] = mapped_column(String(64))
    source_s3_key: Mapped[str] = mapped_column(String(1024))


class SearchDocument(Base):
    __tablename__ = "search_documents"

    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    doc_length: Mapped[int] = mapped_column(Integer)
    indexed_hash: Mapped[str] = mapped_column(String(64))
    processing_version: Mapped[int] = mapped_column(Integer, server_default="0")


class Term(Base):
    __tablename__ = "terms"
    __table_args__ = (UniqueConstraint("language", "term_text", name="uq_terms_language_text"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_text: Mapped[str] = mapped_column(String(256))
    language: Mapped[str] = mapped_column(String(16), server_default="en")
    df: Mapped[int] = mapped_column(Integer, default=0)
    idf: Mapped[float] = mapped_column(Float, default=0.0)


class InvertedIndex(Base):
    __tablename__ = "inverted_index"

    doc_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    term_id: Mapped[int] = mapped_column(ForeignKey("terms.id", ondelete="CASCADE"), primary_key=True, index=True)
    tf: Mapped[float] = mapped_column(Float)
    positions: Mapped[list[int]] = mapped_column(JSON)
