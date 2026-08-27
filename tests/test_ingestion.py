"""
Unit tests for FHIR Parser and Ingestion Service.
"""

from datetime import datetime

import pytest
from fhir.resources.medicationrequest import MedicationRequest
from fhir.resources.observation import Observation

from vlep.models.core import Patient
from vlep.models.ontology import Concept, ConceptMapping, Vocabulary
from vlep.services.ingestion import IngestionService
from vlep.utils.fhir import FHIRParser


@pytest.mark.asyncio
async def test_fhir_parser_observation():
    raw_obs = {
        "resourceType": "Observation",
        "id": "obs-123",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "29463-7",
                    "display": "Body Weight"
                }
            ],
            "text": "Body Weight"
        },
        "effectiveDateTime": "2026-06-24T12:00:00Z",
        "valueQuantity": {
            "value": 75.5,
            "unit": "kg",
            "system": "http://unitsofmeasure.org",
            "code": "kg"
        }
    }

    parsed = FHIRParser.parse_resource(Observation.model_validate(raw_obs))
    assert parsed is not None
    res_type, observed_at, ext_id, data, codes = parsed

    assert res_type == "Observation"
    assert observed_at == datetime.fromisoformat("2026-06-24T12:00:00+00:00")
    assert ext_id == "obs-123"
    assert data["display"] == "Body Weight"
    assert data["value"]["value"] == 75.5
    assert len(codes) == 1
    assert codes[0]["code"] == "29463-7"

@pytest.mark.asyncio
async def test_ingestion_service_flow(db_session):
    # 1. Register Source System
    system = await IngestionService.register_source_system(
        db_session, "Test EHR", "FHIR_R4", "https://ehr.example.com/fhir"
    )
    assert system.name == "Test EHR"
    assert system.kind == "FHIR_R4"

    # 2. Start Ingestion Run
    run = await IngestionService.start_ingestion_run(
        db_session, system.source_system_id
    )
    assert run.status == "RECEIVED"

    # 3. Create Patient
    patient = Patient(source_patient_hash="test-patient-hash-123")
    db_session.add(patient)
    await db_session.commit()

    # 4. Ingest Raw Resource
    raw_json = {
        "resourceType": "Condition",
        "id": "cond-456",
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active"
                }
            ]
        },
        "subject": {
            "reference": "Patient/test-patient"
        },
        "code": {
            "coding": [
                {
                    "system": "http://hl7.org/fhir/sid/icd-10",
                    "code": "G40.909",
                    "display": "Epilepsy, unspecified"
                }
            ],
            "text": "Epilepsy"
        },
        "onsetDateTime": "2026-06-24T10:00:00Z"
    }
    raw_res = await IngestionService.ingest_raw_resource(
        db_session, run.ingestion_run_id, system.source_system_id, "Condition", raw_json, patient.patient_id, "cond-456"
    )
    assert raw_res.status == "RECEIVED"

    # Setup Ontology seed data in transaction for normalization test
    vocab_icd = Vocabulary(kind="ICD_10", name="ICD-10", version="2026", uri="http://hl7.org/fhir/sid/icd-10")
    vocab_sct = Vocabulary(kind="SNOMED_CT", name="SNOMED CT", version="2026", uri="http://snomed.info/sct")
    db_session.add_all([vocab_icd, vocab_sct])
    await db_session.commit()

    concept_icd = Concept(vocabulary_id=vocab_icd.vocabulary_id, code="G40.909", display="Epilepsy, unspecified")
    concept_sct = Concept(vocabulary_id=vocab_sct.vocabulary_id, code="84757009", display="Epilepsy (disorder)")
    db_session.add_all([concept_icd, concept_sct])
    await db_session.commit()

    mapping = ConceptMapping(
        source_concept_id=concept_icd.concept_id,
        target_concept_id=concept_sct.concept_id,
        relation="maps_to",
        mapping_confidence=1.0
    )
    db_session.add(mapping)
    await db_session.commit()

    # 5. Normalize and ledger
    event = await IngestionService.normalize_and_ledger(db_session, raw_res)
    assert event is not None
    assert event.domain == "clinical_observation"
    assert event.patient_id == patient.patient_id
    assert event.validation_status == "normalized"

    # Assert that the code was normalized from ICD-10 G40.909 to SNOMED 84757009
    assert len(event.normalized_codes) == 1
    norm_code = event.normalized_codes[0]
    assert norm_code["normalized"] is True
    assert norm_code["code"] == "84757009"
    assert norm_code["system"] == "https://www.snomed.org/" or norm_code["system"] == "http://snomed.info/sct"
    assert norm_code["original_code"] == "G40.909"


@pytest.mark.asyncio
async def test_fhir_parser_medication_request():
    raw_med = {
        "resourceType": "MedicationRequest",
        "id": "med-123",
        "status": "active",
        "intent": "order",
        "subject": {
            "reference": "Patient/pat-123"
        },
        "medication": {
            "concept": {
                "coding": [
                    {
                        "system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": "284399",
                        "display": "Levetiracetam 500 MG Oral Tablet"
                    }
                ],
                "text": "Levetiracetam"
            }
        },
        "authoredOn": "2026-06-24T12:00:00Z"
    }

    parsed = FHIRParser.parse_resource(MedicationRequest.model_validate(raw_med))
    assert parsed is not None
    res_type, observed_at, ext_id, data, codes = parsed

    assert res_type == "MedicationRequest"
    assert observed_at == datetime.fromisoformat("2026-06-24T12:00:00+00:00")
    assert ext_id == "med-123"
    assert data["display"] == "Levetiracetam"
    assert data["status"] == "active"
    assert data["intent"] == "order"
    assert len(codes) == 1
    assert codes[0]["code"] == "284399"
