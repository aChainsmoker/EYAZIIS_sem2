import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False, unique=True)
    s3_key = Column(String(1024), nullable=True)
    s3_original_key = Column(String(1024), nullable=True)
    doc_length = Column(Integer, nullable=False)
    date_added = Column(DateTime, default=datetime.datetime.utcnow)
    embedding = Column(Text, nullable=True)

    inverted_entries = relationship("InvertedIndex", back_populates="document", cascade="all, delete-orphan")


class Term(Base):
    __tablename__ = "terms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    term_text = Column(String(256), nullable=False, unique=True)
    df = Column(Integer, default=0)
    idf = Column(Float, default=0.0)

    inverted_entries = relationship("InvertedIndex", back_populates="term", cascade="all, delete-orphan")


class InvertedIndex(Base):
    __tablename__ = "inverted_index"

    doc_id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    term_id = Column(Integer, ForeignKey("terms.id"), primary_key=True)
    tf = Column(Float, nullable=False)
    positions = Column(Text, nullable=False)

    document = relationship("Document", back_populates="inverted_entries")
    term = relationship("Term", back_populates="inverted_entries")


class EvaluationQuery(Base):
    __tablename__ = "evaluation_query"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EvaluationJudgment(Base):
    __tablename__ = "evaluation_judgment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(Integer, ForeignKey("evaluation_query.id"), nullable=False)
    doc_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    relevant = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("query_id", "doc_id", name="uq_judgment_query_doc"),)
