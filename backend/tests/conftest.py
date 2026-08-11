"""Session-wide test isolation: point storage/DB at a temp dir before any
`app.*` module is imported, so tests never touch real dev data.
"""

import os
import tempfile
from pathlib import Path

_tmp_root = Path(tempfile.mkdtemp(prefix="bill2quote_test_"))
os.environ["APP_STORAGE_ROOT"] = str(_tmp_root / "storage")
os.environ["APP_DATABASE_PATH"] = str(_tmp_root / "data" / "app.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def sample_invoice_path() -> Path:
    return Path(__file__).parent / "fixtures" / "printed_invoice_01.pdf"
