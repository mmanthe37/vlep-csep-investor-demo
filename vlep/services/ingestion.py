"""
VLEP Pipeline — Ingestion & Normalization Service.

Coordinates source system registration, ingestion runs, raw resource staging,
ontological code mapping, and evidence ledger event creation.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.evidence import LedgerEvent
from vlep.models.ingestion import IngestionRun, RawResource, SourceSystem
from vlep.models.ontology import Concept, ConceptMapping, Vocabulary
from vlep.utils.fhir import FHIRParser

logger = logging.getLogger(__name__)


class IngestionService:
    """Service handling Stage 1: Data Ingestion and Normalization."""

    @staticmethod
    async def register_source_system(
        session: AsyncSession,
        name: str,
        kind: str,
        base_uri: str | None = None,
        owning_institution: str | None = None,
        version: str | None = None,
    ) -> SourceSystem:
        """Register a new source clinical system if it doesn't exist."""
        stmt = select(SourceSystem).where(SourceSystem.name == name)
        result = await session.execute(stmt)
        system = result.scalar_one_or_none()

        if not system:
            system = SourceSystem(
                name=name,
                kind=kind,
                base_uri=base_uri,
                owning_institution=owning_institution,
                version=version,
                active=True,
            )
            session.add(system)
            await session.commit()
            logger.info("Registered source system: %s", name)

        return system

    @staticmethod
    async def start_ingestion_run(
        session: AsyncSession,
        source_system_id: uuid.UUID,
        input_uri: str | None = None,
        input_sha256: str | None = None,
        pipeline_version: str = "0.1.0",
    ) -> IngestionRun:
        """Start a new ingestion run tracking session."""
        run = IngestionRun(
            source_system_id=source_system_id,
            status="RECEIVED",
            input_uri=input_uri,
            input_sha256=input_sha256,
            records_received=0,
            records_normalized=0,
            records_quarantined=0,
            pipeline_version=pipeline_version,
        )
        session.add(run)
        await session.commit()
        logger.info("Started ingestion run: %s", run.ingestion_run_id)
        return run

    @staticmethod
    async def complete_ingestion_run(
        session: AsyncSession,
        run_id: uuid.UUID,
        records_received: int,
        records_normalized: int,
        records_quarantined: int,
    ) -> IngestionRun:
        """Mark an ingestion run as completed successfully."""
        stmt = select(IngestionRun).where(IngestionRun.ingestion_run_id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one()

        run.status = "COMPLETED"
        run.finished_at = func.now()
        run.records_received = records_received
        run.records_normalized = records_normalized
        run.records_quarantined = records_quarantined

        await session.commit()
        logger.info("Completed ingestion run: %s", run_id)
        return run

    @staticmethod
    async def fail_ingestion_run(
        session: AsyncSession,
        run_id: uuid.UUID,
        error_summary: str,
    ) -> IngestionRun:
        """Mark an ingestion run as failed."""
        stmt = select(IngestionRun).where(IngestionRun.ingestion_run_id == run_id)
        result = await session.execute(stmt)
        run = result.scalar_one()

        run.status = "FAILED"
        run.finished_at = func.now()
        run.error_summary = error_summary

        await session.commit()
        logger.error("Failed ingestion run %s: %s", run_id, error_summary)
        return run

    @staticmethod
    async def ingest_raw_resource(
        session: AsyncSession,
        run_id: uuid.UUID,
        source_system_id: uuid.UUID,
        resource_type: str,
        raw_json: dict[str, Any],
        patient_id: uuid.UUID | None = None,
        external_resource_id: str | None = None,
    ) -> RawResource:
        """Persist a raw resource in the ingestion staging table."""
        # Calculate raw JSON SHA-256 for integrity checks
        json_str = json.dumps(raw_json, sort_keys=True)
        import hashlib
        sha256_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()

        resource = RawResource(
            ingestion_run_id=run_id,
            source_system_id=source_system_id,
            external_resource_id=external_resource_id,
            resource_type=resource_type,
            patient_id=patient_id,
            captured_at=func.now(),
            raw_json=raw_json,
            sha256=sha256_hash,
            status="RECEIVED",
        )
        session.add(resource)
        await session.commit()
        return resource

    @staticmethod
    async def normalize_and_ledger(
        session: AsyncSession,
        raw_resource: RawResource,
    ) -> LedgerEvent | None:
        """Normalize a staged raw resource and append it to the evidence ledger."""
        # Only parse supported resources
        parsed = FHIRParser.parse_resource(raw_resource.raw_json)
        if not parsed:
            raw_resource.status = "FAILED"
            raw_resource.quarantine_reason = f"Unsupported or unparseable resource type: {raw_resource.resource_type}"
            await session.commit()
            return None

        res_type, observed_at, ext_id, data_element, codes = parsed

        # Normalize source codes to internal vocabularies (e.g. SNOMED_CT, RxNorm, HPO)
        normalized_codes = []
        for code_entry in codes:
            norm_code = await IngestionService._normalize_code(
                session, code_entry["system"], code_entry["code"], code_entry["display"]
            )
            normalized_codes.append(norm_code)

        # Determine ledger domain
        domain = IngestionService._map_resource_to_domain(res_type)

        # Create Ledger Event
        event = LedgerEvent(
            patient_id=raw_resource.patient_id,
            observed_at=observed_at,
            domain=domain,
            data_element=data_element,
            normalized_codes=normalized_codes,
            source_attribution="automated_system",
            source_system_id=raw_resource.source_system_id,
            raw_resource_id=raw_resource.raw_resource_id,
            validation_status="normalized",
            certainty_level=1.0,
            ingestion_run_id=raw_resource.ingestion_run_id,
        )
        session.add(event)

        # Mark raw resource as completed
        raw_resource.status = "NORMALIZED"
        await session.commit()

        return event

    @staticmethod
    def _map_resource_to_domain(resource_type: str) -> str:
        """Map FHIR resource types to VLEP ledger domains."""
        mapping = {
            "Condition": "clinical_observation",
            "Observation": "clinical_observation",
            "MedicationRequest": "medication_change",
            "DiagnosticReport": "imaging_biomarker" if "imaging" in resource_type.lower() else "EEG_biomarker",
        }
        return mapping.get(resource_type, "other")

    @staticmethod
    async def _normalize_code(
        session: AsyncSession,
        system_url: str,
        code: str,
        display: str,
    ) -> dict[str, Any]:
        """Perform ontological mapping (e.g. ICD-10 -> SNOMED, drugs -> RxNorm, phenotypes -> HPO)."""
        # 1. Resolve source concept
        stmt_src = (
            select(Concept)
            .join(Vocabulary)
            .where(Vocabulary.uri == system_url)
            .where(Concept.code == code)
        )
        res_src = await session.execute(stmt_src)
        src_concept = res_src.scalar_one_or_none()

        if not src_concept:
            # Fallback: concept not in seed vocabulary
            return {
                "system": system_url,
                "code": code,
                "display": display,
                "normalized": False,
                "mapping_confidence": 1.0,
            }

        # 2. Check if a mapping exists for this concept
        stmt_map = (
            select(ConceptMapping, Concept)
            .join(Concept, ConceptMapping.target_concept_id == Concept.concept_id)
            .join(Vocabulary, Concept.vocabulary_id == Vocabulary.vocabulary_id)
            .where(ConceptMapping.source_concept_id == src_concept.concept_id)
            .order_by(ConceptMapping.mapping_confidence.desc())
            .limit(1)
        )
        res_map = await session.execute(stmt_map)
        mapping_tuple = res_map.first()

        if mapping_tuple:
            mapping, target_concept = mapping_tuple
            stmt_vocab = select(Vocabulary).where(Vocabulary.vocabulary_id == target_concept.vocabulary_id)
            res_vocab = await session.execute(stmt_vocab)
            vocab = res_vocab.scalar_one()

            return {
                "system": vocab.uri,
                "code": target_concept.code,
                "display": target_concept.display,
                "normalized": True,
                "original_system": system_url,
                "original_code": code,
                "original_display": display,
                "mapping_confidence": float(mapping.mapping_confidence) if mapping.mapping_confidence is not None else 1.0,
            }

        # No mapping found, return original concept
        return {
            "system": system_url,
            "code": code,
            "display": src_concept.display,
            "normalized": True,
            "mapping_confidence": 1.0,
        }
