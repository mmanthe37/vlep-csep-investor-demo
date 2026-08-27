import pytest
from vlep.tasks import io_fetch_fhir, nlp_phenotyping

@pytest.mark.asyncio
async def test_fhir_parsing_integration():
    """Test FHIR data fetching and parsing against synthetic data."""
    # Synthetic patient ID
    patient_id = "synth-12345"
    
    # Call the IO bound task
    result = io_fetch_fhir.delay(patient_id)
    # For testing, we mock or just call the function directly if not testing celery itself
    direct_result = io_fetch_fhir(patient_id)
    
    assert direct_result["status"] == "success"
    assert direct_result["patient_id"] == patient_id

@pytest.mark.asyncio
async def test_ml_phenotyping_integration():
    """Test ML phenotyping predictions against synthetic clinical data."""
    # Synthetic clinical note
    clinical_note = "Patient presents with generalized tonic-clonic seizures."
    
    # Call the GPU/NLP heavy task
    direct_result = nlp_phenotyping(clinical_note)
    
    assert direct_result["status"] == "success"
    assert direct_result["phenotype"] == "extracted"
