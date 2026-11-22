import os
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

os.environ["FITS_UPLOAD_DIR"] = str(PROJECT / "data" / "test_uploads")
os.environ["FITS_SAMPLES_DIR"] = str(PROJECT / "samples")

from backend.samples.make_samples import make_all  # noqa: E402

make_all(os.environ["FITS_SAMPLES_DIR"])

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(scope="session")
def loaded(client):
    """加载全部样例，返回 {样例名: (file_id, report)}。"""
    out = {}
    for s in client.get("/api/samples").json()["samples"]:
        r = client.post(f"/api/samples/{s['name']}/load")
        assert r.status_code == 200, r.text
        body = r.json()
        out[s["name"]] = (body["file_id"], body["report"])
    return out
