-- 002_core_ingestion_ontology_nosology_base.sql
-- Pseudonymous patient/cohort identity, ingestion metadata, ontology graph, and base nosology versions.

BEGIN;

CREATE TABLE IF NOT EXISTS core.patients (
  patient_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_patient_hash TEXT NOT NULL UNIQUE,
  birth_year SMALLINT CHECK (birth_year BETWEEN 1900 AND EXTRACT(YEAR FROM now())::INT),
  sex_at_birth TEXT,
  gender_identity TEXT,
  race_ethnicity JSONB NOT NULL DEFAULT '{}'::jsonb,
  deceased_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TRIGGER trg_patients_updated_at
BEFORE UPDATE ON core.patients
FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE IF NOT EXISTS core.cohorts (
  cohort_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  protocol_id TEXT,
  irb_id TEXT,
  inclusion_criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
  exclusion_criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS core.cohort_memberships (
  cohort_id UUID NOT NULL REFERENCES core.cohorts(cohort_id) ON DELETE CASCADE,
  patient_id UUID NOT NULL REFERENCES core.patients(patient_id) ON DELETE CASCADE,
  enrolled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  exited_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (cohort_id, patient_id)
);

CREATE TABLE IF NOT EXISTS ingestion.source_systems (
  source_system_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  kind ingestion.source_system_kind NOT NULL,
  base_uri TEXT,
  owning_institution TEXT,
  version TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ingestion.ingestion_runs (
  ingestion_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_system_id UUID REFERENCES ingestion.source_systems(source_system_id),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  status ingestion.ingestion_status NOT NULL DEFAULT 'RECEIVED',
  input_uri TEXT,
  input_sha256 TEXT,
  records_received INTEGER NOT NULL DEFAULT 0 CHECK (records_received >= 0),
  records_normalized INTEGER NOT NULL DEFAULT 0 CHECK (records_normalized >= 0),
  records_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (records_quarantined >= 0),
  error_summary TEXT,
  pipeline_version TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ingestion.raw_resources (
  raw_resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id UUID REFERENCES ingestion.ingestion_runs(ingestion_run_id) ON DELETE SET NULL,
  source_system_id UUID REFERENCES ingestion.source_systems(source_system_id) ON DELETE SET NULL,
  external_resource_id TEXT,
  resource_type TEXT NOT NULL,
  resource_version TEXT,
  patient_id UUID REFERENCES core.patients(patient_id) ON DELETE SET NULL,
  captured_at TIMESTAMPTZ,
  raw_json JSONB,
  object_uri TEXT,
  sha256 TEXT,
  status ingestion.ingestion_status NOT NULL DEFAULT 'RECEIVED',
  quarantine_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ontology.vocabularies (
  vocabulary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind ontology.vocabulary_kind NOT NULL,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  release_date DATE,
  uri TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (kind, version)
);

CREATE TABLE IF NOT EXISTS ontology.concepts (
  concept_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  vocabulary_id UUID NOT NULL REFERENCES ontology.vocabularies(vocabulary_id) ON DELETE RESTRICT,
  code TEXT NOT NULL,
  display TEXT NOT NULL,
  normalized_display TEXT GENERATED ALWAYS AS (lower(display)) STORED,
  concept_class TEXT,
  domain TEXT,
  valid_start_date DATE,
  valid_end_date DATE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (vocabulary_id, code)
);

CREATE TABLE IF NOT EXISTS ontology.concept_synonyms (
  synonym_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_id UUID NOT NULL REFERENCES ontology.concepts(concept_id) ON DELETE CASCADE,
  synonym TEXT NOT NULL,
  source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (concept_id, synonym)
);

CREATE TABLE IF NOT EXISTS ontology.concept_mappings (
  mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_concept_id UUID NOT NULL REFERENCES ontology.concepts(concept_id) ON DELETE CASCADE,
  target_concept_id UUID NOT NULL REFERENCES ontology.concepts(concept_id) ON DELETE CASCADE,
  relation TEXT NOT NULL,
  mapping_confidence NUMERIC(5,4) NOT NULL DEFAULT 1.0 CHECK (mapping_confidence BETWEEN 0 AND 1),
  mapping_source TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_concept_id, target_concept_id, relation)
);

CREATE TABLE IF NOT EXISTS ontology.concept_edges (
  edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_concept_id UUID NOT NULL REFERENCES ontology.concepts(concept_id) ON DELETE CASCADE,
  child_concept_id UUID NOT NULL REFERENCES ontology.concepts(concept_id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'is_a',
  depth INTEGER CHECK (depth IS NULL OR depth >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (parent_concept_id, child_concept_id, relation)
);

CREATE TABLE IF NOT EXISTS ontology.embedding_versions (
  embedding_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  algorithm TEXT NOT NULL,
  dimensionality INTEGER NOT NULL CHECK (dimensionality > 0),
  vocabulary_scope JSONB NOT NULL DEFAULT '{}'::jsonb,
  trained_at TIMESTAMPTZ,
  artifact_uri TEXT,
  artifact_sha256 TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (name, algorithm, dimensionality)
);

CREATE TABLE IF NOT EXISTS ontology.concept_embeddings (
  concept_id UUID NOT NULL REFERENCES ontology.concepts(concept_id) ON DELETE CASCADE,
  embedding_version_id UUID NOT NULL REFERENCES ontology.embedding_versions(embedding_version_id) ON DELETE CASCADE,
  embedding DOUBLE PRECISION[] NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (concept_id, embedding_version_id)
);

CREATE TABLE IF NOT EXISTS nosology.framework_versions (
  nosology_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_name TEXT NOT NULL,
  version_label TEXT NOT NULL,
  authority TEXT,
  effective_from DATE NOT NULL,
  effective_to DATE,
  source_uri TEXT,
  source_document_id UUID,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'active',
  ruleset_hash TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (framework_name, version_label)
);

COMMIT;

