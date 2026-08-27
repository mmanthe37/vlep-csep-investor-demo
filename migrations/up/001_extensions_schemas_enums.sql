-- 001_extensions_schemas_enums.sql
-- VLEP PostgreSQL schema bootstrap.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS btree_gin;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ingestion;
CREATE SCHEMA IF NOT EXISTS ontology;
CREATE SCHEMA IF NOT EXISTS literature;
CREATE SCHEMA IF NOT EXISTS evidence;
CREATE SCHEMA IF NOT EXISTS phenotyping;
CREATE SCHEMA IF NOT EXISTS nosology;
CREATE SCHEMA IF NOT EXISTS modeling;
CREATE SCHEMA IF NOT EXISTS csep;
CREATE SCHEMA IF NOT EXISTS review;
CREATE SCHEMA IF NOT EXISTS governance;

CREATE OR REPLACE FUNCTION core.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END $$;

DO $$ BEGIN
  CREATE TYPE ingestion.source_system_kind AS ENUM (
    'FHIR_R4',
    'OMOP_CDM',
    'BULK_FHIR',
    'CDS_HOOKS',
    'SMART_ON_FHIR',
    'PATIENT_PORTAL',
    'MOBILE_DIARY',
    'EEG_SYSTEM',
    'IMAGING_SYSTEM',
    'GENETICS_LAB',
    'LITERATURE_API',
    'MANUAL_UPLOAD',
    'OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE ingestion.ingestion_status AS ENUM (
    'RECEIVED',
    'NORMALIZED',
    'QUARANTINED',
    'FAILED',
    'COMPLETED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE ontology.vocabulary_kind AS ENUM (
    'SNOMED_CT',
    'RxNorm',
    'LOINC',
    'ICD_10',
    'ICD_11',
    'CPT_HCPCS',
    'HPO',
    'UMLS',
    'OMOP_CONCEPT',
    'ILAE',
    'DSM_5',
    'LOCAL',
    'OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE literature.document_source_kind AS ENUM (
    'PubMed_MEDLINE',
    'PMC_OPEN_ACCESS',
    'Embase',
    'ClinicalTrials_gov',
    'Institutional_Guideline',
    'Cochrane',
    'Preprint',
    'Manual',
    'Other'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE literature.document_section_kind AS ENUM (
    'TITLE',
    'ABSTRACT',
    'INTRODUCTION',
    'METHODS',
    'RESULTS',
    'DISCUSSION',
    'CONCLUSION',
    'GUIDELINE',
    'TABLE',
    'FIGURE',
    'SUPPLEMENT',
    'METADATA',
    'FULL_TEXT',
    'UNKNOWN'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE literature.claim_tier AS ENUM (
    'TIER_1',
    'TIER_2',
    'TIER_3',
    'TIER_4',
    'EXCLUDED',
    'UNREVIEWED'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE evidence.ledger_domain AS ENUM (
    'clinical_observation',
    'medication_change',
    'EEG_biomarker',
    'imaging_biomarker',
    'genetic_result',
    'patient_reported_outcome',
    'literature_claim',
    'outcome_event',
    'model_output',
    'manual_review',
    'other'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE evidence.source_attribution AS ENUM (
    'clinician',
    'automated_system',
    'patient_reported',
    'external_registry',
    'literature_pipeline',
    'model',
    'manual_curator'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE evidence.validation_status AS ENUM (
    'raw',
    'normalized',
    'verified',
    'disputed',
    'superseded',
    'rejected'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE phenotyping.phenotype_dimension AS ENUM (
    'seizure_type',
    'epilepsy_type',
    'syndrome',
    'etiology',
    'biomarker',
    'comorbidity',
    'treatment_response',
    'drug_resistance',
    'risk',
    'other'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE phenotyping.assertion_status AS ENUM (
    'active',
    'conflicting',
    'superseded',
    'under_review',
    'rejected'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE modeling.model_family AS ENUM (
    'GLMM',
    'HMM',
    'SURVIVAL_ENSEMBLE',
    'RANDOM_SURVIVAL_FOREST',
    'LOGISTIC_REGRESSION',
    'MIXED_POISSON_EXPONENTIAL',
    'LSTM',
    'XGBOOST',
    'NLP_TRANSFORMER',
    'OTHER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE review.review_decision AS ENUM (
    'accept',
    'reject',
    'needs_revision',
    'escalate',
    'no_action'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE governance.alert_severity AS ENUM (
    'passive',
    'low',
    'moderate',
    'high',
    'critical'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

COMMIT;

