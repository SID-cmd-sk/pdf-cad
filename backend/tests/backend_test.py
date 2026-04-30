"""Backend integration tests for CAD Assist (FastAPI + SQLite).

Covers:
- Health
- Job lifecycle: upload -> auto-process -> get -> preview -> dxf -> reprocess -> delete
- Validation: unsupported file extension
- Rules: list, correct(create rule), patch toggle, delete
"""
from __future__ import annotations
import os
import time
import pytest
import requests
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cad-autofix.preview.emergentagent.com").rstrip("/")
SAMPLES_DIR = Path("/app/samples")


def _upload(api_client, sample_path: Path):
    with sample_path.open("rb") as f:
        files = {"file": (sample_path.name, f, "image/png")}
        # don't send the JSON header for multipart
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/jobs/upload", files=files, timeout=60)
    return r


def _wait_for_done(job_id: str, timeout: int = 60) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=30)
        assert r.status_code == 200, f"get_job failed: {r.status_code} {r.text}"
        last = r.json()
        status = last["job"]["status"]
        if status in ("done", "error"):
            return last
        time.sleep(2)
    return last or {}


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    return s


# ---------- Health ----------
class TestHealth:
    def test_health(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["tesseract"] is True
        assert data["fitz"] is True


# ---------- Job lifecycle (mechanical_part) ----------
class TestJobMechanical:
    job_id = None

    def test_upload_mechanical(self, api_client):
        r = _upload(api_client, SAMPLES_DIR / "mechanical_part.png")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "job_id" in data
        assert data["filename"] == "mechanical_part.png"
        TestJobMechanical.job_id = data["job_id"]

    def test_job_processed_done(self, api_client):
        assert TestJobMechanical.job_id, "upload must succeed first"
        result = _wait_for_done(TestJobMechanical.job_id, timeout=60)
        assert result and result["job"]["status"] == "done", f"job did not reach done: {result}"
        # Validate structure
        assert isinstance(result["pages"], list) and len(result["pages"]) >= 1
        assert "entities" in result
        assert "summary" in result and "counts" in result["summary"]
        assert "uncertain" in result["summary"]

    def test_jobs_list_contains(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/jobs", timeout=20)
        assert r.status_code == 200
        ids = [j["id"] for j in r.json()["jobs"]]
        assert TestJobMechanical.job_id in ids

    def test_preview_jpeg(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/jobs/{TestJobMechanical.job_id}/preview/0", timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/jpeg")
        assert len(r.content) > 1000

    def test_dxf_download(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/jobs/{TestJobMechanical.job_id}/dxf", timeout=30)
        assert r.status_code == 200
        text = r.text
        # DXF must begin with section marker
        assert text.lstrip().startswith("0\nSECTION") or text.startswith("  0\nSECTION") or "SECTION" in text[:50]

    def test_reprocess(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/jobs/{TestJobMechanical.job_id}/reprocess", timeout=30)
        assert r.status_code == 200
        assert r.json().get("ok") is True
        # Wait again for completion
        result = _wait_for_done(TestJobMechanical.job_id, timeout=60)
        assert result["job"]["status"] == "done"


# ---------- Job lifecycle (geometry_demo) ----------
class TestJobGeometryDemo:
    job_id = None

    def test_upload_geometry(self, api_client):
        r = _upload(api_client, SAMPLES_DIR / "geometry_demo.png")
        assert r.status_code == 200, r.text
        TestJobGeometryDemo.job_id = r.json()["job_id"]

    def test_geometry_done(self, api_client):
        result = _wait_for_done(TestJobGeometryDemo.job_id, timeout=60)
        assert result["job"]["status"] == "done"
        # Should have at least some entities
        counts = result["summary"]["counts"]
        assert sum(counts.values()) > 0


# ---------- Validation ----------
class TestValidation:
    def test_unsupported_extension(self, api_client, tmp_path):
        bad = tmp_path / "bad.txt"
        bad.write_text("hello")
        with bad.open("rb") as f:
            files = {"file": ("bad.txt", f, "text/plain")}
            r = requests.post(f"{BASE_URL}/api/jobs/upload", files=files, timeout=15)
        assert r.status_code == 400


# ---------- Rules ----------
class TestRules:
    rule_id = None
    job_id = None
    entity_id = None

    def test_seeded_rules(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/rules", timeout=15)
        assert r.status_code == 200
        rules = r.json()["rules"]
        assert len(rules) >= 2, f"expected >=2 seeded rules, got {len(rules)}"

    def test_create_rule_via_correction(self, api_client):
        # Reuse mechanical job
        job_id = TestJobMechanical.job_id
        assert job_id, "needs mechanical job"
        TestRules.job_id = job_id

        # Get an entity
        r = api_client.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=20)
        ents = r.json()["entities"]
        # filter out already-deleted entities
        ents = [e for e in ents if not e.get("deleted")]
        assert ents, "need at least one entity"
        entity_id = ents[0]["id"]
        TestRules.entity_id = entity_id

        payload = {
            "entity_id": entity_id,
            "action_type": "delete",
            "apply_to_similar": True,
            "notes": "TEST_correction",
        }
        r = api_client.post(f"{BASE_URL}/api/jobs/{job_id}/correct", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("rule_id"), f"expected rule_id, got {body}"
        TestRules.rule_id = body["rule_id"]

        # Verify entity is filtered out (deleted entities excluded by default in GET)
        r2 = api_client.get(f"{BASE_URL}/api/jobs/{job_id}", timeout=20)
        target = next((e for e in r2.json()["entities"] if e["id"] == entity_id), None)
        assert target is None, "deleted entity should be excluded from default GET"

    def test_toggle_rule_off(self, api_client):
        rule_id = TestRules.rule_id
        assert rule_id
        r = api_client.patch(f"{BASE_URL}/api/rules/{rule_id}", json={"active": False}, timeout=15)
        assert r.status_code == 200
        rule = r.json()["rule"]
        assert bool(rule["active"]) is False

    def test_delete_rule(self, api_client):
        rule_id = TestRules.rule_id
        r = api_client.delete(f"{BASE_URL}/api/rules/{rule_id}", timeout=15)
        assert r.status_code == 200
        # Confirm gone
        r2 = api_client.get(f"{BASE_URL}/api/rules", timeout=15)
        ids = [x["id"] for x in r2.json()["rules"]]
        assert rule_id not in ids


# ---------- Cleanup: delete jobs ----------
class TestCleanup:
    def test_delete_jobs(self, api_client):
        for jid in [TestJobMechanical.job_id, TestJobGeometryDemo.job_id]:
            if not jid:
                continue
            r = api_client.delete(f"{BASE_URL}/api/jobs/{jid}", timeout=15)
            assert r.status_code == 200
            # Verify 404 on subsequent get
            r2 = api_client.get(f"{BASE_URL}/api/jobs/{jid}", timeout=15)
            assert r2.status_code == 404
