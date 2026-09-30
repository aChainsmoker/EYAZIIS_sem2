import datetime as dt

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    source_language: Mapped[str] = mapped_column(String(16), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary_s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)
