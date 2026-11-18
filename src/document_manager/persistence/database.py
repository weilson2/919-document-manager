from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def create_database_engine(path: Path) -> Engine:
    engine = create_engine(URL.create("sqlite", database=str(path)), hide_parameters=True)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    return engine


@contextmanager
def migration_config(engine: Engine):
    config = Config()
    config.set_main_option("script_location", "document_manager.persistence:migrations")
    with engine.begin() as connection:
        # SQLite's legacy driver does not start a transaction for DDL.
        # Acquire the write lock before Alembic reads the current revision.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        config.attributes["connection"] = connection
        yield config


def upgrade_database(engine: Engine) -> None:
    with migration_config(engine) as config:
        tables = inspect(config.attributes["connection"]).get_table_names()
        if tables and "alembic_version" not in tables:
            raise RuntimeError("The workspace contains an unrecognized database.")
        command.upgrade(config, "head")


@contextmanager
def write_session(engine: Engine):
    with Session(engine) as session, session.begin():
        # Serialize validation reads with the following mutations.
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield session
