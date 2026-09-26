from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker


class DatabaseStartupError(RuntimeError):
    pass


class Database:
    def __init__(self, url: str, *, echo: bool = False) -> None:
        try:
            connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
            self.engine: Engine = create_engine(
                url, echo=echo, pool_pre_ping=True, connect_args=connect_args
            )
            if url.startswith("sqlite"):
                @event.listens_for(self.engine, "connect")
                def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()
            self.session_factory = sessionmaker(
                bind=self.engine, class_=Session, expire_on_commit=False
            )
        except (SQLAlchemyError, ValueError) as exc:
            raise DatabaseStartupError("Database configuration is invalid.") from exc

    def validate(self) -> None:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            required = {
                "regflow_runs", "preflight_snapshots", "artifact_metadata",
                "audit_events", "idempotency_records", "mapping_profiles",
                "mapping_profile_versions",
                "users", "external_identities", "organisations",
                "organisation_memberships", "invitations", "user_sessions",
                "oidc_transactions",
            }
            missing = required.difference(inspect(self.engine).get_table_names())
            if missing:
                raise DatabaseStartupError(
                    "Required persistence schema is unavailable; run Alembic migrations."
                )
        except DatabaseStartupError:
            raise
        except SQLAlchemyError as exc:
            raise DatabaseStartupError("Database is unreachable.") from exc

    def is_ready(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    def sessions(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()
