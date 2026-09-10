import json
import logging
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy_utils import database_exists, create_database

from src.config import DB_URL
from src.db.models import Base, Document, Term, InvertedIndex, EvaluationQuery, EvaluationJudgment

logger = logging.getLogger(__name__)


engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> bool:
    created = False
    try:
        if not database_exists(engine.url):
            create_database(engine.url)
            created = True
    except Exception:
        try:
            create_database(engine.url)
            created = True
        except Exception:
            pass
    insp = inspect(engine)
    tables_existed = all(
        insp.has_table(t) for t in ("documents", "terms", "inverted_index")
    )
    Base.metadata.create_all(engine)
    _ensure_embedding_column()
    _ensure_s3_key_column()
    _ensure_s3_original_key_column()
    return created or not tables_existed


def _ensure_embedding_column():
    insp = inspect(engine)
    if insp.has_table("documents"):
        columns = {col["name"] for col in insp.get_columns("documents")}
        if "embedding" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN embedding TEXT"))


def _ensure_s3_key_column():
    insp = inspect(engine)
    if insp.has_table("documents"):
        columns = {col["name"] for col in insp.get_columns("documents")}
        if "s3_key" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN s3_key VARCHAR(1024)"))


def _ensure_s3_original_key_column():
    insp = inspect(engine)
    if insp.has_table("documents"):
        columns = {col["name"] for col in insp.get_columns("documents")}
        if "s3_original_key" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN s3_original_key VARCHAR(1024)"))


def get_session() -> Session:
    return SessionLocal()


def add_document(title: str, file_path: str, doc_length: int, s3_key: str | None = None, s3_original_key: str | None = None) -> Document:
    session = get_session()
    try:
        doc = Document(title=title, file_path=file_path, doc_length=doc_length, s3_key=s3_key, s3_original_key=s3_original_key)
        session.add(doc)
        session.commit()
        session.refresh(doc)
        return doc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_document_by_path(file_path: str) -> Document | None:
    session = get_session()
    try:
        return session.query(Document).filter_by(file_path=file_path).first()
    finally:
        session.close()


def get_document(doc_id: int) -> Document | None:
    session = get_session()
    try:
        return session.query(Document).filter_by(id=doc_id).first()
    finally:
        session.close()


def get_all_documents() -> list[Document]:
    session = get_session()
    try:
        return session.query(Document).all()
    finally:
        session.close()


def count_documents() -> int:
    session = get_session()
    try:
        return session.query(func.count(Document.id)).scalar() or 0
    finally:
        session.close()


def count_terms() -> int:
    session = get_session()
    try:
        return session.query(func.count(Term.id)).scalar() or 0
    finally:
        session.close()


def get_or_create_terms(term_texts: list[str]) -> dict[str, int]:
    term_texts = list(set(term_texts))
    session = get_session()
    try:
        existing = session.query(Term).filter(Term.term_text.in_(term_texts)).all()
        result = {t.term_text: t.id for t in existing}
        missing = [t for t in term_texts if t not in result]
        if missing:
            new_terms = [Term(term_text=text, df=0, idf=0.0) for text in missing]
            session.add_all(new_terms)
            session.flush()
            for t in new_terms:
                result[t.term_text] = t.id
            session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def add_inverted_entries(doc_id: int, entries: list[tuple[int, float, list[int]]]):
    session = get_session()
    try:
        session.add_all(
            InvertedIndex(doc_id=doc_id, term_id=term_id, tf=tf, positions=json.dumps(pos))
            for term_id, tf, pos in entries
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_term_stats(term_id: int, df: int, idf: float):
    session = get_session()
    try:
        session.query(Term).filter_by(id=term_id).update({"df": df, "idf": idf})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_collection_stats() -> tuple[int, float] | None:
    session = get_session()
    try:
        total_docs = session.query(func.count(Document.id)).scalar() or 0
        if total_docs == 0:
            return None
        avg_doc_length = session.query(func.avg(Document.doc_length)).scalar() or 0.0
        return total_docs, float(avg_doc_length)
    finally:
        session.close()


def recalculate_term_stats():
    logger.info("Recalculating term statistics...")
    session = get_session()
    try:
        total_docs = session.query(func.count(Document.id)).scalar() or 0
        if total_docs == 0:
            session.execute(text("UPDATE terms SET df = 0, idf = 0.0"))
            session.commit()
            return

        query = text("""
            WITH counts AS (
                SELECT term_id, COUNT(doc_id) AS df_val
                FROM inverted_index
                GROUP BY term_id
            )
            UPDATE terms
            SET
                df = COALESCE(counts.df_val, 0),
                idf = CASE
                    WHEN counts.df_val > 0
                    THEN LOG(10, :total_docs / counts.df_val)
                    ELSE 0.0
                END
            FROM terms t
            LEFT JOIN counts ON t.id = counts.term_id
            WHERE terms.id = t.id;
        """)
        session.execute(query, {"total_docs": float(total_docs)})
        session.commit()
        logger.info("Term statistics recalculated successfully.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_terms_for_query(term_texts: list[str]) -> list[Term]:
    session = get_session()
    try:
        return session.query(Term).filter(Term.term_text.in_(term_texts)).all()
    finally:
        session.close()


def get_entries_for_terms(term_ids: list[int]) -> list[InvertedIndex]:
    if not term_ids:
        return []
    session = get_session()
    try:
        return session.query(InvertedIndex).filter(InvertedIndex.term_id.in_(term_ids)).all()
    finally:
        session.close()


def get_documents_by_ids(doc_ids: list[int]) -> dict[int, Document]:
    if not doc_ids:
        return {}
    session = get_session()
    try:
        return {d.id: d for d in session.query(Document).filter(Document.id.in_(doc_ids)).all()}
    finally:
        session.close()


def update_document_embedding(doc_id: int, embedding: list[float]):
    session = get_session()
    try:
        session.query(Document).filter_by(id=doc_id).update({"embedding": json.dumps(embedding)})
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_document_embedding(doc_id: int) -> list[float] | None:
    doc = get_document(doc_id)
    if doc and doc.embedding:
        try:
            return json.loads(doc.embedding)
        except Exception:
            return None
    return None


def get_document_embeddings(doc_ids: list[int]) -> dict[int, list[float]]:
    session = get_session()
    try:
        result = {}
        for doc in session.query(Document).filter(Document.id.in_(doc_ids)).all():
            if doc.embedding:
                try:
                    result[doc.id] = json.loads(doc.embedding)
                except Exception:
                    continue
        return result
    finally:
        session.close()


def delete_all_data():
    session = get_session()
    try:
        session.query(EvaluationJudgment).delete()
        session.query(EvaluationQuery).delete()
        session.query(InvertedIndex).delete()
        session.query(Term).delete()
        session.query(Document).delete()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_term_by_text(term_text: str) -> Term | None:
    session = get_session()
    try:
        return session.query(Term).filter_by(term_text=term_text).first()
    finally:
        session.close()


def delete_document(file_path: str):
    session = get_session()
    try:
        doc = session.query(Document).filter_by(file_path=file_path).first()
        if not doc:
            return
        logger.info(f"Deleting document from DB: {file_path}")
        session.query(EvaluationJudgment).filter_by(doc_id=doc.id).delete()
        session.query(InvertedIndex).filter_by(doc_id=doc.id).delete()
        session.delete(doc)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    recalculate_term_stats()
    logger.info(f"Document deleted successfully: {file_path}")


def add_evaluation_query(query_text: str) -> EvaluationQuery:
    session = get_session()
    try:
        query = EvaluationQuery(query_text=query_text)
        session.add(query)
        session.commit()
        session.refresh(query)
        return query
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_all_evaluation_queries() -> list[EvaluationQuery]:
    session = get_session()
    try:
        return session.query(EvaluationQuery).order_by(EvaluationQuery.id).all()
    finally:
        session.close()


def delete_evaluation_query(query_id: int):
    session = get_session()
    try:
        session.query(EvaluationJudgment).filter_by(query_id=query_id).delete()
        session.query(EvaluationQuery).filter_by(id=query_id).delete()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upsert_judgment(query_id: int, doc_id: int, relevant: bool):
    session = get_session()
    try:
        judgment = session.query(EvaluationJudgment).filter_by(query_id=query_id, doc_id=doc_id).first()
        if judgment:
            judgment.relevant = 1 if relevant else 0
        else:
            judgment = EvaluationJudgment(query_id=query_id, doc_id=doc_id, relevant=1 if relevant else 0)
            session.add(judgment)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_judgments(query_id: int) -> dict[int, bool]:
    session = get_session()
    try:
        result = {}
        for j in session.query(EvaluationJudgment).filter_by(query_id=query_id).all():
            result[j.doc_id] = bool(j.relevant)
        return result
    finally:
        session.close()
