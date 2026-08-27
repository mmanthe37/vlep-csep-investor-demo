-- 003_literature_documents_claims.sql
-- Literature documents, exact offset sections, phenotype claims, heuristic tiering, corpus releases.

BEGIN;

CREATE TABLE IF NOT EXISTS literature.documents (
  document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_kind literature.document_source_kind NOT NULL,
  external_id TEXT,
  doi TEXT,
  pmid TEXT,
  pmcid TEXT,
  title TEXT NOT NULL,
  journal TEXT,
  publication_date DATE,
  authors JSONB NOT NULL DEFAULT '[]'::jsonb,
  peer_review_status TEXT,
  license TEXT,
  access_policy TEXT NOT NULL DEFAULT 'metadata_or_permitted_text',
  source_uri TEXT,
  object_uri TEXT,
  sha256 TEXT,
  text_extraction_status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source_kind, external_id),
  UNIQUE (doi)
);

CREATE TABLE IF NOT EXISTS literature.document_sections (
  section_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES literature.documents(document_id) ON DELETE CASCADE,
  section_kind literature.document_section_kind NOT NULL,
  section_label TEXT,
  ordinal INTEGER NOT NULL DEFAULT 0 CHECK (ordinal >= 0),
  char_start INTEGER CHECK (char_start IS NULL OR char_start >= 0),
  char_end INTEGER CHECK (char_end IS NULL OR char_end >= 0),
  text_content TEXT,
  token_count INTEGER CHECK (token_count IS NULL OR token_count >= 0),
  extraction_model_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (char_end IS NULL OR char_start IS NULL OR char_end >= char_start)
);

CREATE TABLE IF NOT EXISTS literature.heuristic_rulesets (
  ruleset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  version_label TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  rules_json JSONB NOT NULL,
  description TEXT,
  created_by TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version_label)
);

CREATE TABLE IF NOT EXISTS literature.phenotype_claims (
  claim_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_key TEXT UNIQUE,
  subject_concept_id UUID REFERENCES ontology.concepts(concept_id) ON DELETE SET NULL,
  subject_text TEXT NOT NULL,
  predicate TEXT NOT NULL,
  object_concept_id UUID REFERENCES ontology.concepts(concept_id) ON DELETE SET NULL,
  object_text TEXT NOT NULL,
  relation_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  negation_status BOOLEAN NOT NULL DEFAULT FALSE,
  conditionality TEXT,
  temporal_context TEXT,
  age_context TEXT,
  sex_context TEXT,
  source_document_id UUID NOT NULL REFERENCES literature.documents(document_id) ON DELETE RESTRICT,
  source_section_id UUID REFERENCES literature.document_sections(section_id) ON DELETE SET NULL,
  source_start_offset INTEGER NOT NULL CHECK (source_start_offset >= 0),
  source_end_offset INTEGER NOT NULL CHECK (source_end_offset >= source_start_offset),
  source_sentence TEXT NOT NULL,
  extraction_model_version TEXT NOT NULL,
  extraction_confidence NUMERIC(5,4) CHECK (extraction_confidence IS NULL OR extraction_confidence BETWEEN 0 AND 1),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS literature.claim_evidence_metadata (
  claim_id UUID PRIMARY KEY REFERENCES literature.phenotype_claims(claim_id) ON DELETE CASCADE,
  study_design TEXT,
  n_subjects INTEGER CHECK (n_subjects IS NULL OR n_subjects >= 0),
  p_value NUMERIC CHECK (p_value IS NULL OR p_value >= 0),
  confidence_interval TEXT,
  correction_method TEXT,
  effect_size NUMERIC,
  causal_method TEXT NOT NULL DEFAULT 'none',
  peer_review_status TEXT,
  journal_metric NUMERIC,
  replication_density NUMERIC(8,4),
  publication_recency_days INTEGER CHECK (publication_recency_days IS NULL OR publication_recency_days >= 0),
  parsed_from_section literature.document_section_kind,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS literature.claim_tiering_results (
  claim_tiering_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  claim_id UUID NOT NULL REFERENCES literature.phenotype_claims(claim_id) ON DELETE CASCADE,
  ruleset_id UUID NOT NULL REFERENCES literature.heuristic_rulesets(ruleset_id) ON DELETE RESTRICT,
  tier literature.claim_tier NOT NULL,
  scalar_weight NUMERIC(6,5) NOT NULL CHECK (scalar_weight >= 0 AND scalar_weight <= 1),
  confidence_score NUMERIC(6,5) CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
  tier_rationale TEXT,
  evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  evidence_features JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (claim_id, ruleset_id)
);

CREATE TABLE IF NOT EXISTS literature.claim_supporting_sources (
  support_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  primary_claim_id UUID NOT NULL REFERENCES literature.phenotype_claims(claim_id) ON DELETE CASCADE,
  supporting_document_id UUID NOT NULL REFERENCES literature.documents(document_id) ON DELETE RESTRICT,
  supporting_section_id UUID REFERENCES literature.document_sections(section_id) ON DELETE SET NULL,
  support_type TEXT NOT NULL DEFAULT 'replication',
  similarity_score NUMERIC(5,4) CHECK (similarity_score IS NULL OR similarity_score BETWEEN 0 AND 1),
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS literature.corpus_releases (
  corpus_release_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  version_label TEXT NOT NULL,
  description TEXT,
  intended_claim_count INTEGER CHECK (intended_claim_count IS NULL OR intended_claim_count >= 0),
  ruleset_id UUID REFERENCES literature.heuristic_rulesets(ruleset_id) ON DELETE SET NULL,
  release_status TEXT NOT NULL DEFAULT 'draft',
  tier_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
  artifact_uri TEXT,
  artifact_sha256 TEXT,
  released_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version_label)
);

CREATE TABLE IF NOT EXISTS literature.corpus_claims (
  corpus_release_id UUID NOT NULL REFERENCES literature.corpus_releases(corpus_release_id) ON DELETE CASCADE,
  claim_id UUID NOT NULL REFERENCES literature.phenotype_claims(claim_id) ON DELETE CASCADE,
  included BOOLEAN NOT NULL DEFAULT TRUE,
  inclusion_reason TEXT,
  ordinal INTEGER CHECK (ordinal IS NULL OR ordinal >= 0),
  PRIMARY KEY (corpus_release_id, claim_id)
);

COMMIT;

