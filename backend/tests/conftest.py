import os
import sys

import pytest
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

# Point the app at the TEST database before anything imports database.py.
_test_url = os.getenv("TEST_DATABASE_URL")
if _test_url:
    os.environ["DATABASE_URL"] = _test_url
# Tests never touch the real LLM.
os.environ["LLM_API_KEY"] = ""
os.environ["LLM_MODEL"] = ""
# Uploaded test photos go to a throwaway folder, not backend/uploads.
import tempfile  # noqa: E402

os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="triage_uploads_")

from database import Base, engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def schema():
    """Create the schema from the Alembic migrations on the test database."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"))
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        for t in ("category", "urgency", "status"):
            conn.exec_driver_sql(f"DROP TYPE IF EXISTS {t} CASCADE")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db(schema):
    import rate_limit

    rate_limit.reset()
    yield
    with engine.begin() as conn:
        tables = [t.name for t in reversed(Base.metadata.sorted_tables)]
        if tables:
            conn.exec_driver_sql("TRUNCATE " + ", ".join(tables) + " CASCADE")
