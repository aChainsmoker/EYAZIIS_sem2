from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.config import DB_URL
from src.db.models import Base, Document


engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_all_documents() -> list[Document]:
    with SessionLocal() as session:
        return list(session.scalars(select(Document).order_by(Document.title)))


def save_document(
    data: dict,
    existing: Document | None = None,
) -> Document:
    with SessionLocal() as session:
        document = existing
        if document is None:
            document = Document(**data)
            session.add(document)
            session.flush()
        else:
            session.query(Document).filter(Document.id == document.id).update(data)
            for key, value in data.items():
                setattr(document, key, value)
        session.commit()
        if existing is None:
            session.refresh(document)
        return document


def delete_document(path: str, existing: Document | None = None) -> Document | None:
    with SessionLocal() as session:
        document = existing
        if document is None:
            document = session.scalar(select(Document).where(Document.file_path == path))
        if document is None:
            return None
        session.query(Document).filter(Document.id == document.id).delete()
        session.commit()
        return document
