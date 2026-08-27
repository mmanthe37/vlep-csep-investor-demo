"""
VLEP Pipeline — FHIR R4 Utilities.

Provides a parser for FHIR R4 Bundle and resource types (Condition, MedicationRequest,
Observation, DiagnosticReport) to extract clinical events and their timestamps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fhir.resources.bundle import Bundle
from fhir.resources.condition import Condition
from fhir.resources.diagnosticreport import DiagnosticReport
from fhir.resources.medicationrequest import MedicationRequest
from fhir.resources.observation import Observation
from fhir.resources.resource import Resource


class FHIRParser:
    """Parser to extract VLEP ledger-compatible payloads from FHIR R4 resources."""

    @staticmethod
    def parse_bundle(bundle_json: dict[str, Any]) -> list[tuple[str, datetime, str, dict[str, Any], list[dict[str, str]]]]:
        """
        Parse a FHIR Bundle and extract VLEP events.
        
        Returns:
            A list of tuples: (resource_type, observed_at, external_id, data_element, normalized_codes)
        """
        bundle = Bundle.model_validate(bundle_json)
        events = []

        if not bundle.entry:
            return events

        for entry in bundle.entry:
            if not entry.resource:
                continue

            parsed = FHIRParser.parse_resource(entry.resource)
            if parsed:
                events.append(parsed)

        return events

    @staticmethod
    def parse_resource(resource: Resource | dict[str, Any]) -> tuple[str, datetime, str, dict[str, Any], list[dict[str, str]]] | None:
        """
        Parse an individual FHIR resource.
        
        Returns:
            A tuple of (resource_type, observed_at, external_id, data_element, normalized_codes) or None.
        """
        if isinstance(resource, dict):
            res_type = resource.get("resourceType")
            try:
                if res_type == "Condition":
                    resource = Condition.model_validate(resource)
                elif res_type == "Observation":
                    resource = Observation.model_validate(resource)
                elif res_type == "MedicationRequest":
                    resource = MedicationRequest.model_validate(resource)
                elif res_type == "DiagnosticReport":
                    resource = DiagnosticReport.model_validate(resource)
                else:
                    return None
            except Exception:
                return None

        resource_type = resource.__resource_type__
        external_id = resource.id or ""

        if isinstance(resource, Condition):
            return FHIRParser._parse_condition(resource, resource_type, external_id)
        elif isinstance(resource, MedicationRequest):
            return FHIRParser._parse_medication_request(resource, resource_type, external_id)
        elif isinstance(resource, Observation):
            return FHIRParser._parse_observation(resource, resource_type, external_id)
        elif isinstance(resource, DiagnosticReport):
            return FHIRParser._parse_diagnostic_report(resource, resource_type, external_id)

        return None

    @staticmethod
    def _parse_condition(resource: Condition, resource_type: str, external_id: str) -> tuple[str, datetime, str, dict[str, Any], list[dict[str, str]]]:
        # Onset date time or recorded date
        observed_at = datetime.now(UTC)
        if resource.onsetDateTime:
            observed_at = resource.onsetDateTime
        elif resource.recordedDate:
            observed_at = resource.recordedDate

        codes = FHIRParser._extract_codings(resource.code)

        display = ""
        if resource.code:
            display = resource.code.text or (resource.code.coding[0].display if resource.code.coding else "")

        data_element: dict[str, Any] = {
            "clinical_status": resource.clinicalStatus.coding[0].code if resource.clinicalStatus and resource.clinicalStatus.coding else "unknown",
            "verification_status": resource.verificationStatus.coding[0].code if resource.verificationStatus and resource.verificationStatus.coding else "unknown",
            "severity": resource.severity.coding[0].display if resource.severity and resource.severity.coding else None,
            "display": display,
        }

        return resource_type, observed_at, external_id, data_element, codes

    @staticmethod
    def _parse_medication_request(resource: MedicationRequest, resource_type: str, external_id: str) -> tuple[str, datetime, str, dict[str, Any], list[dict[str, str]]]:
        # Authored on date
        observed_at = datetime.now(UTC)
        if resource.authoredOn:
            observed_at = resource.authoredOn

        codes = []
        display = ""
        if resource.medication:
            med = resource.medication
            concept = getattr(med, "concept", None)
            reference = getattr(med, "reference", None)

            if concept is not None or (reference is not None and not isinstance(reference, str)):
                if concept:
                    codes = FHIRParser._extract_codings(concept)
                    display = concept.text or (concept.coding[0].display if concept.coding else "")
                elif reference:
                    display = getattr(reference, "display", None) or getattr(reference, "reference", None) or ""
            else:
                if hasattr(med, "coding"):
                    codes = FHIRParser._extract_codings(med)
                    display = getattr(med, "text", None) or (med.coding[0].display if med.coding else "")
                else:
                    display = getattr(med, "display", None) or getattr(med, "reference", None) or ""

        data_element: dict[str, Any] = {
            "status": resource.status,
            "intent": resource.intent,
            "display": display,
            "dosage_instruction": [inst.model_dump() for inst in resource.dosageInstruction] if resource.dosageInstruction else [],
        }

        return resource_type, observed_at, external_id, data_element, codes

    @staticmethod
    def _parse_observation(resource: Observation, resource_type: str, external_id: str) -> tuple[str, datetime, str, dict[str, Any], list[dict[str, str]]]:
        # Effective date time
        observed_at = datetime.now(UTC)
        if resource.effectiveDateTime:
            observed_at = resource.effectiveDateTime
        elif resource.issued:
            observed_at = resource.issued

        codes = FHIRParser._extract_codings(resource.code)

        display = ""
        if resource.code:
            display = resource.code.text or (resource.code.coding[0].display if resource.code.coding else "")

        value_data: Any = None
        if resource.valueQuantity:
            raw_val = resource.valueQuantity.value
            val_num = float(raw_val) if raw_val is not None else None
            value_data = {
                "value": val_num,
                "unit": resource.valueQuantity.unit,
                "system": resource.valueQuantity.system,
                "code": resource.valueQuantity.code,
            }
        elif resource.valueCodeableConcept:
            value_data = {
                "text": resource.valueCodeableConcept.text,
                "codes": FHIRParser._extract_codings(resource.valueCodeableConcept),
            }
        elif resource.valueString:
            value_data = resource.valueString

        data_element: dict[str, Any] = {
            "status": resource.status,
            "display": display,
            "value": value_data,
        }

        return resource_type, observed_at, external_id, data_element, codes

    @staticmethod
    def _parse_diagnostic_report(resource: DiagnosticReport, resource_type: str, external_id: str) -> tuple[str, datetime, str, dict[str, Any], list[dict[str, str]]]:
        # Effective date time
        observed_at = datetime.now(UTC)
        if resource.effectiveDateTime:
            observed_at = resource.effectiveDateTime
        elif resource.issued:
            observed_at = resource.issued

        codes = FHIRParser._extract_codings(resource.code)

        display = ""
        if resource.code:
            display = resource.code.text or (resource.code.coding[0].display if resource.code.coding else "")

        data_element: dict[str, Any] = {
            "status": resource.status,
            "display": display,
            "category": [cat.coding[0].code for cat in resource.category if cat.coding] if resource.category else [],
            "conclusion": resource.conclusion,
        }

        return resource_type, observed_at, external_id, data_element, codes

    @staticmethod
    def _extract_codings(codeable_concept: Any) -> list[dict[str, str]]:
        codings = []
        if codeable_concept and hasattr(codeable_concept, "coding") and codeable_concept.coding:
            for coding in codeable_concept.coding:
                codings.append({
                    "system": coding.system or "",
                    "code": coding.code or "",
                    "display": coding.display or "",
                })
        return codings
