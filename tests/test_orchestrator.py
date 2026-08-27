import uuid
import pytest
from datetime import datetime, UTC
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from vlep.api.main import create_app
from vlep.api.deps import get_db
from vlep.models.core import Patient
from vlep.models.nosology import FrameworkVersion

NOW = datetime.now(UTC)

@pytest.mark.asyncio
async def test_trigger_pipeline_api(db_session: AsyncSession):
    # Setup Patient and Framework
    patient_id = uuid.uuid4()
    patient = Patient(
        patient_id=patient_id,
        source_patient_hash=f"hash-{patient_id.hex}",
        birth_year=1980
    )
    db_session.add(patient)

    framework = FrameworkVersion(
        framework_name="ILAE 2017 Integration",
        version_label=f"2017-{uuid.uuid4().hex[:4]}",
        effective_from=NOW.date()
    )
    db_session.add(framework)
    await db_session.flush()

    app = create_app()
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Actor-ID": "test_epileptologist", "X-Actor-Role": "epileptologist"}
    ) as client:
        # Trigger orchestrator
        response = await client.post(
            f"/api/v1/patients/{patient_id}/analyze?nosology_version_id={framework.nosology_version_id}"
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "success"
        assert data["patient_id"] == str(patient_id)
        assert "csep_id" in data
