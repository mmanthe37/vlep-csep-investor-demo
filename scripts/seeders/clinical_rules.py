"""
VLEP Pipeline — Clinical Rule Seeders.
Translates Mmanthe37/Epilepsy-Phenotype-Project guidelines into ResolutionRules.
"""

from __future__ import annotations

import logging
import uuid
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from vlep.models.nosology import FrameworkVersion, ResolutionRule

logger = logging.getLogger(__name__)

ILAE_2017_RULES = [
    {
        "rule_name": "Genetic Etiology Priority Override",
        "dimension": "etiology",
        "priority": 10,
        "expression": {"condition": "has_label", "value": "genetic"},
        "action": {"set_rank": 1, "decay_multiplier": 1.0}
    },
    {
        "rule_name": "MRI Lesional Priority over old EEG",
        "dimension": "biomarker",
        "priority": 20,
        "expression": {"condition": "modality", "value": "MRI", "recency_days": "<180"},
        "action": {"weight_multiplier": 1.5}
    },
    {
        "rule_name": "Seizure Type Drug-Resistance Shift",
        "dimension": "treatment_response",
        "priority": 5,
        "expression": {"condition": "failed_trials", "value": ">=2"},
        "action": {"assert_label": "drug_resistant", "confidence": 0.95}
    }
]

async def seed_clinical_rules(session: AsyncSession):
    # Get 2017 Framework
    stmt = select(FrameworkVersion).where(FrameworkVersion.version_tag == "2017")
    res = await session.execute(stmt)
    framework = res.scalar_one_or_none()
    
    if not framework:
        logger.warning("ILAE 2017 framework not found, skipping rule seeding")
        return

    for rule_data in ILAE_2017_RULES:
        rule = ResolutionRule(
            nosology_version_id=framework.nosology_version_id,
            rule_name=rule_data["rule_name"],
            applies_to_dimension=rule_data["dimension"],
            priority=rule_data["priority"],
            rule_expression=rule_data["expression"],
            action=rule_data["action"],
            active=True
        )
        session.add(rule)
        
    await session.commit()
    logger.info("Seeded %d clinical resolution rules.", len(ILAE_2017_RULES))
