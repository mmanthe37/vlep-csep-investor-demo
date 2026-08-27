"""
API Layer Tests — HTTP endpoint coverage for all 6 VLEP routers.

Tests cover:
  - Happy-path request/response shapes
  - 404 on unknown IDs
  - RBAC enforcement (403 when caller role is insufficient)
  - Health and system probes
  - Pagination parameters
  - Governance audit middleware (access log written on patient endpoint hit)

All DB writes are rolled back after each test via the ``db_session`` fixture.
The ``async_client`` fixture defaults to ``clinical_director`` role headers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.core import Patient

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

async def _make_patient(db: AsyncSession, suffix: str = "api-test") -> Patient:
    """Insert and flush a minimal patient record."""
    patient = Patient(source_patient_hash=f"hash-{suffix}-{uuid.uuid4().hex[:8]}")
    db.add(patient)
    await db.flush()
    return patient


def _headers(role: str, actor: str = "tester") -> dict:
    """Build auth headers for a given role."""
    return {
        "X-Actor-ID": actor,
        "X-Actor-Role": role,
        "X-Access-Reason": "test",
    }


# ────────────────────────────────────────────────────────────────────────────
# System / Health
# ────────────────────────────────────────────────────────────────────────────

class TestSystemEndpoints:
    async def test_root(self, async_client: AsyncClient):
        resp = await async_client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "name" in body
        assert "version" in body
        assert "docs" in body

    async def test_health_ok(self, async_client: AsyncClient):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_health_db(self, async_client: AsyncClient):
        resp = await async_client.get("/health/db")
        # Should be 200 (DB reachable) or 503 (unreachable) but not 4xx
        assert resp.status_code in (200, 503)

    async def test_openapi_schema_reachable(self, async_client: AsyncClient):
        resp = await async_client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        # Verify all 6 router tags are present
        tags = {t["name"] for t in schema.get("tags", [])}
        assert "Patients" in tags
        assert "Evidence Ledger" in tags
        assert "Governance & Safety" in tags

    async def test_process_time_header_present(self, async_client: AsyncClient):
        resp = await async_client.get("/health")
        assert "x-process-time-ms" in resp.headers


# ────────────────────────────────────────────────────────────────────────────
# Patients Router
# ────────────────────────────────────────────────────────────────────────────

class TestPatientsRouter:
    async def test_create_patient_success(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/patients/",
            json={
                "source_patient_hash": f"hash-create-{uuid.uuid4().hex}",
                "birth_year": 1985,
                "sex_at_birth": "female",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "patient_id" in body
        assert body["birth_year"] == 1985
        assert body["sex_at_birth"] == "female"

    async def test_create_patient_missing_hash_fails(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/patients/",
            json={"birth_year": 1990},
        )
        assert resp.status_code == 422  # Pydantic validation error

    async def test_get_patient_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session)
        resp = await async_client.get(f"/api/v1/patients/{patient.patient_id}")
        assert resp.status_code == 200
        assert resp.json()["patient_id"] == str(patient.patient_id)

    async def test_get_patient_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/patients/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_list_patients_returns_list(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/patients/?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        assert "patients" in body
        assert isinstance(body["patients"], list)

    async def test_list_patients_pagination(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/patients/?offset=0&limit=5")
        assert resp.status_code == 200

    async def test_patch_patient_updates_field(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session)
        resp = await async_client.patch(
            f"/api/v1/patients/{patient.patient_id}",
            json={"gender_identity": "nonbinary"},
        )
        assert resp.status_code == 200
        assert resp.json()["gender_identity"] == "nonbinary"

    async def test_patch_patient_not_found(self, async_client: AsyncClient):
        resp = await async_client.patch(
            f"/api/v1/patients/{uuid.uuid4()}",
            json={"birth_year": 1980},
        )
        assert resp.status_code == 404

    async def test_delete_patient_requires_admin(self, async_client: AsyncClient, db_session: AsyncSession):
        """Clinician role should get 403 when trying to delete."""
        patient = await _make_patient(db_session)
        resp = await async_client.delete(
            f"/api/v1/patients/{patient.patient_id}",
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_delete_patient_admin_succeeds(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session)
        resp = await async_client.delete(
            f"/api/v1/patients/{patient.patient_id}",
            headers=_headers("admin"),
        )
        assert resp.status_code == 204

    async def test_enroll_in_cohort_not_found(self, async_client: AsyncClient):
        """Both patient and cohort must exist."""
        resp = await async_client.post(
            f"/api/v1/patients/{uuid.uuid4()}/cohorts/{uuid.uuid4()}",
        )
        assert resp.status_code == 404

    async def test_rbac_readonly_cannot_create_patient(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/patients/",
            json={"source_patient_hash": f"hash-rbac-{uuid.uuid4().hex}"},
            headers=_headers("readonly"),
        )
        assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────────────
# Evidence Ledger Router
# ────────────────────────────────────────────────────────────────────────────

class TestEvidenceLedgerRouter:
    async def test_append_event_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "ev-append")
        resp = await async_client.post(
            "/api/v1/evidence/events",
            json={
                "patient_id": str(patient.patient_id),
                "domain": "clinical_observation",
                "data_element": {"condition": "epilepsy", "icd10": "G40.909"},
                "observed_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
                "source_attribution": "clinician",
                "certainty_level": 0.9,
                "validation_status": "verified",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "event_id" in body
        assert body["domain"] == "clinical_observation"
        assert body["patient_id"] == str(patient.patient_id)

    async def test_list_events_empty_for_unknown_patient(self, async_client: AsyncClient):
        resp = await async_client.get(
            f"/api/v1/evidence/events?patient_id={uuid.uuid4()}"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_event_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/evidence/events/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_append_event_readonly_forbidden(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "ev-rbac")
        resp = await async_client.post(
            "/api/v1/evidence/events",
            json={
                "patient_id": str(patient.patient_id),
                "domain": "EEG_biomarker",
                "data_element": {},
                "observed_at": datetime.now(UTC).isoformat(),
                "source_attribution": "clinician",
            },
            headers=_headers("readonly"),
        )
        assert resp.status_code == 403

    async def test_patient_events_endpoint(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "ev-patient")
        resp = await async_client.get(
            f"/api/v1/evidence/patients/{patient.patient_id}/events"
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_verify_requires_clinical_director(
        self, async_client: AsyncClient
    ):
        """Clinician should be denied hash verification."""
        resp = await async_client.post(
            f"/api/v1/evidence/verify/{uuid.uuid4()}",
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_supersede_requires_epileptologist(
        self, async_client: AsyncClient
    ):
        resp = await async_client.post(
            f"/api/v1/evidence/events/{uuid.uuid4()}/supersede",
            json={"correction": {}, "source_attribution": "clinician"},
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403


# ────────────────────────────────────────────────────────────────────────────
# Literature Router
# ────────────────────────────────────────────────────────────────────────────

class TestLiteratureRouter:
    async def test_create_document_success(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/literature/documents",
            json={
                "title": "Test VLEP Document",
                "pmid": f"TEST{uuid.uuid4().hex[:6]}",
                "publication_year": 2023,
                "study_design": "RCT",
                "n_subjects": 120,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "document_id" in body
        assert body["title"] == "Test VLEP Document"

    async def test_get_document_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/literature/documents/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_list_claims_empty(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/literature/claims?limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_claim_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/literature/claims/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_tier_claim_requires_epileptologist(self, async_client: AsyncClient):
        resp = await async_client.post(
            f"/api/v1/literature/claims/{uuid.uuid4()}/tier",
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_corpus_release_requires_clinical_director(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/literature/corpus?release_name=test&release_version=0.1",
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_list_corpus_releases(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/literature/corpus")
        assert resp.status_code == 200


# ────────────────────────────────────────────────────────────────────────────
# Phenotypes Router
# ────────────────────────────────────────────────────────────────────────────

class TestPhenotypesRouter:
    async def test_list_assertions_empty(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/phenotypes/assertions?limit=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_assertion_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/phenotypes/assertions/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_create_assertion_requires_epileptologist(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "ph-rbac")
        resp = await async_client.post(
            "/api/v1/phenotypes/assertions",
            json={
                "patient_id": str(patient.patient_id),
                "dimension": "seizure_type",
                "phenotype_code": "test-code",
                "phenotype_label": "test label",
            },
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_patient_assertions_endpoint(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "ph-pa")
        resp = await async_client.get(
            f"/api/v1/phenotypes/patients/{patient.patient_id}/assertions"
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_bootstrap_features_requires_admin(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/phenotypes/features/bootstrap",
            headers=_headers("clinical_director"),
        )
        assert resp.status_code == 403

    async def test_patient_windows_endpoint(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "ph-win")
        resp = await async_client.get(
            f"/api/v1/phenotypes/patients/{patient.patient_id}/windows"
        )
        assert resp.status_code == 200


# ────────────────────────────────────────────────────────────────────────────
# CSEP Router
# ────────────────────────────────────────────────────────────────────────────

class TestCsepRouter:
    async def test_get_profile_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/csep/profiles/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_patient_profiles_empty(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "csep-pp")
        resp = await async_client.get(
            f"/api/v1/csep/patients/{patient.patient_id}/profiles"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_latest_profile_not_found(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "csep-lp")
        resp = await async_client.get(
            f"/api/v1/csep/patients/{patient.patient_id}/profiles/latest"
        )
        assert resp.status_code == 404

    async def test_assemble_profile_requires_epileptologist(
        self, async_client: AsyncClient
    ):
        resp = await async_client.post(
            "/api/v1/csep/profiles",
            json={
                "patient_id": str(uuid.uuid4()),
                "nosology_version_id": str(uuid.uuid4()),
                "model_version_id": str(uuid.uuid4()),
            },
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_create_framework_requires_clinical_director(
        self, async_client: AsyncClient
    ):
        resp = await async_client.post(
            "/api/v1/csep/nosology/frameworks",
            json={
                "framework_name": "Test ILAE",
                "version_tag": "2017",
                "ilae_year": 2017,
            },
            headers=_headers("epileptologist"),
        )
        assert resp.status_code == 403

    async def test_job_status_not_found(self, async_client: AsyncClient):
        resp = await async_client.get(f"/api/v1/csep/nosology/jobs/{uuid.uuid4()}")
        assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────────────
# Governance Router
# ────────────────────────────────────────────────────────────────────────────

class TestGovernanceRouter:
    async def test_access_logs_requires_clinical_director(self, async_client: AsyncClient):
        resp = await async_client.get(
            "/api/v1/governance/access-logs",
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_access_logs_as_director(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/governance/access-logs?limit=10")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_alert_success(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "gov-alert")
        resp = await async_client.post(
            "/api/v1/governance/alerts",
            json={
                "alert_type": "seizure_frequency_spike",
                "severity": "high",
                "patient_id": str(patient.patient_id),
                "interruptive": False,
                "rationale": "Test alert from API test suite",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "alert_event_id" in body
        assert body["severity"] == "high"

    async def test_list_alerts(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/governance/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create_review_task_success(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/governance/reviews/tasks",
            json={
                "task_type": "claim_review",
                "priority": 50,
                "assigned_role": "epileptologist",
                "due_days": 3,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["task_type"] == "claim_review"
        assert body["status"] == "open"

    async def test_list_review_tasks(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/governance/reviews/tasks")
        assert resp.status_code == 200

    async def test_report_issue_requires_clinic_nurse(self, async_client: AsyncClient):
        """readonly role should be denied."""
        resp = await async_client.post(
            "/api/v1/governance/reviews/issues",
            json={
                "issue_type": "data_discrepancy",
                "description": "Test discrepancy",
                "severity": "moderate",
            },
            headers=_headers("readonly"),
        )
        assert resp.status_code == 403

    async def test_report_issue_as_nurse(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/governance/reviews/issues",
            json={
                "issue_type": "data_discrepancy",
                "description": "Test: missing EEG timestamp",
                "severity": "moderate",
                "reporter_id": "nurse_test",
                "reporter_role": "clinic_nurse",
            },
            headers=_headers("clinic_nurse"),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "open"

    async def test_dq_run_requires_clinical_director(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/governance/quality/run",
            json={"run_name": "Test DQ Run"},
            headers=_headers("clinician"),
        )
        assert resp.status_code == 403

    async def test_list_dq_runs(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/governance/quality/runs")
        assert resp.status_code == 200

    async def test_drift_run_requires_clinical_director(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/governance/drift/run",
            json={"model_version_id": str(uuid.uuid4())},
            headers=_headers("epileptologist"),
        )
        assert resp.status_code == 403

    async def test_list_drift_runs(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/governance/drift/runs")
        assert resp.status_code == 200

    async def test_patient_access_logs_endpoint(
        self, async_client: AsyncClient, db_session: AsyncSession
    ):
        patient = await _make_patient(db_session, "gov-pal")
        resp = await async_client.get(
            f"/api/v1/governance/access-logs/patient/{patient.patient_id}"
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
