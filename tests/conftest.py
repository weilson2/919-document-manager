import os

import pytest

from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def database_engine(tmp_path):
    engine = create_database_engine(tmp_path / "document-manager.sqlite3")
    try:
        upgrade_database(engine)
        yield engine
    finally:
        engine.dispose()
