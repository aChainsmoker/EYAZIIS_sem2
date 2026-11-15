import math
from collections import Counter

from sqlalchemy import create_engine, delete as sql_delete, func, select, text, true
from sqlalchemy.orm import Session

from src.config import CONFIG
from src.db.migrations import initialize_schema
from src.db.models import Document, InvertedIndex, SearchDocument, Term

# Версия 3 пересчитывает язык и индекс с корпусным русским профилем FrequencyWords.
PROCESSING_VERSION = 3
engine = create_engine(CONFIG["database"]["url"], pool_pre_ping=True)


def initialize():
    initialize_schema(engine)


def all_documents():
    with Session(engine) as session:
        return list(session.scalars(select(Document).order_by(Document.title, Document.id)))


def get_document(document_id: int):
    with Session(engine) as session:
        return session.get(Document, document_id)


def indexed_states() -> dict[int, tuple[str, int]]:
    with Session(engine) as session:
        return {
            row.doc_id: (row.indexed_hash, row.processing_version)
            for row in session.execute(select(
                SearchDocument.doc_id, SearchDocument.indexed_hash, SearchDocument.processing_version,
            ))
        }


def is_index_current(document) -> bool:
    with Session(engine) as session:
        stats = session.get(SearchDocument, document.id)
        return (
            stats is not None
            and stats.indexed_hash == document.file_hash
            and stats.processing_version == PROCESSING_VERSION
        )


def _current_index_conditions():
    return (
        SearchDocument.processing_version == PROCESSING_VERSION,
        SearchDocument.indexed_hash == Document.file_hash,
        SearchDocument.doc_length > 0,
    )


def _recalculate_terms(session: Session):
    session.flush()
    counts = dict(session.execute(
        select(Document.source_language, func.count())
        .join(SearchDocument, SearchDocument.doc_id == Document.id)
        .where(*_current_index_conditions())
        .group_by(Document.source_language)
    ).all())
    frequencies = dict(session.execute(
        select(InvertedIndex.term_id, func.count())
        .join(Document, Document.id == InvertedIndex.doc_id)
        .join(SearchDocument, SearchDocument.doc_id == Document.id)
        .join(Term, Term.id == InvertedIndex.term_id)
        .where(*_current_index_conditions(), Term.language == Document.source_language)
        .group_by(InvertedIndex.term_id)
    ).all())
    for term in session.scalars(select(Term)):
        term.df = frequencies.get(term.id, 0)
        document_count = counts.get(term.language, 0)
        term.idf = math.log10(document_count / term.df) if document_count and term.df else 0.0
        if not term.df:
            session.delete(term)


def save_indexed_document(values: dict, lemmas: list[str], positions: dict[str, list[int]]):
    language = values["source_language"]
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(900209)"))
        row = session.scalar(select(Document).where(Document.file_path == values["file_path"]))
        if row is None:
            row = Document(**values)
            session.add(row)
            session.flush()
        else:
            for key, value in values.items():
                setattr(row, key, value)
        session.execute(sql_delete(InvertedIndex).where(InvertedIndex.doc_id == row.id))
        stats = session.get(SearchDocument, row.id)
        if stats is None:
            stats = SearchDocument(doc_id=row.id)
            session.add(stats)
        stats.doc_length = len(lemmas)
        stats.indexed_hash = values["file_hash"]
        stats.processing_version = PROCESSING_VERSION
        frequencies = Counter(lemmas)
        terms = {}
        if frequencies:
            terms = {
                term.term_text: term
                for term in session.scalars(select(Term).where(
                    Term.language == language, Term.term_text.in_(list(frequencies)),
                ))
            }
        for lemma in frequencies:
            if lemma not in terms:
                term = Term(term_text=lemma, language=language)
                terms[lemma] = term
                session.add(term)
        session.flush()
        session.add_all([
            InvertedIndex(
                doc_id=row.id, term_id=terms[lemma].id,
                tf=frequency / len(lemmas), positions=positions[lemma],
            )
            for lemma, frequency in frequencies.items()
        ])
        _recalculate_terms(session)


def delete(document_id: int):
    with Session(engine) as session, session.begin():
        session.execute(text("SELECT pg_advisory_xact_lock(900209)"))
        session.execute(sql_delete(Document).where(Document.id == document_id))
        _recalculate_terms(session)


def search_entries(query_terms: list[str], document_id: int, language: str) -> list[dict]:
    collection = (
        select(func.avg(SearchDocument.doc_length).label("average_length"))
        .select_from(Document)
        .join(SearchDocument, SearchDocument.doc_id == Document.id)
        .where(Document.source_language == language, *_current_index_conditions())
        .subquery()
    )
    statement = (
        select(Document, SearchDocument.doc_length, InvertedIndex.tf,
               InvertedIndex.positions, Term.idf, collection.c.average_length)
        .select_from(Document)
        .join(SearchDocument, SearchDocument.doc_id == Document.id)
        .join(InvertedIndex, InvertedIndex.doc_id == Document.id)
        .join(Term, Term.id == InvertedIndex.term_id)
        .join(collection, true())
        .where(
            Document.id == document_id, Document.source_language == language,
            Term.language == language, Term.term_text.in_(set(query_terms)),
            *_current_index_conditions(),
        )
        .order_by(Term.id)
    )
    with Session(engine) as session:
        return [
            dict(document=row[0], doc_length=row[1], tf=row[2], positions=row[3],
                 idf=row[4], average_length=float(row[5]))
            for row in session.execute(statement)
        ]
