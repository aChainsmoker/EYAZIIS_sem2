"""Идемпотентная миграция служебных таблиц PostgreSQL."""

from sqlalchemy import inspect, text

from src.db.models import Base


def initialize_schema(engine):
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(900209)"))
        Base.metadata.create_all(connection)
        inspector = inspect(connection)
        search_columns = {column["name"] for column in inspector.get_columns("search_documents")}
        if "processing_version" not in search_columns:
            connection.execute(text(
                "ALTER TABLE search_documents ADD COLUMN processing_version INTEGER NOT NULL DEFAULT 0"
            ))
        term_columns = {column["name"] for column in inspector.get_columns("terms")}
        if "language" not in term_columns:
            connection.execute(text("ALTER TABLE terms ADD COLUMN language VARCHAR(16) NOT NULL DEFAULT 'en'"))
        constraints = inspector.get_unique_constraints("terms")
        quote = connection.dialect.identifier_preparer.quote
        for constraint in constraints:
            if constraint["column_names"] == ["term_text"]:
                name = quote(constraint["name"])
                connection.execute(text(f"ALTER TABLE terms DROP CONSTRAINT {name}"))
        if not any(set(constraint["column_names"]) == {"language", "term_text"} for constraint in constraints):
            connection.execute(text(
                "ALTER TABLE terms ADD CONSTRAINT uq_terms_language_text UNIQUE (language, term_text)"
            ))
