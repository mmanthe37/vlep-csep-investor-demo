# Model Card - VLEP Deterministic Research Scoring

## Version

`0.3.0-research`

## Intended use

Demonstrate evidence normalization, temporal weighting, six-dimensional CSEP assembly, profile hashing, and nosology-aware terminology reinterpretation using one bundled fictional case.

## Prohibited use

- Diagnosis, triage, prognosis, treatment selection, medication adjustment, or emergency guidance.
- Processing protected health information in the public demo.
- Substitution for an epileptologist, clinician, formal coding specialist, or regulatory review.
- Performance benchmarking against real patients.

## Method

The MVP uses deterministic phrase rules, declared source-reliability factors, fixed temporal half-lives, and a transparent weighted score. The displayed values are labeled `demo score` and are not calibrated probabilities.

The public MVP does **not** execute the proposed Stan joint model, GLMM, HMM, survival ensembles, hyperbolic embeddings, BioClinicalBERT extraction, or Bayesian posterior inference described in project research documents.

## Inputs

Five synthetic observations: clinical note, EEG finding, MRI finding, medication record, and patient diary entry. Each contains a fictional source reference and declared source confidence.

## Outputs

- Hash-chained evidence ledger
- Evidence-linked assertions
- Six-dimensional CSEP
- Mapping audit record
- Run, profile, ledger, and bundle hashes

## Known limitations

- One small, authored fixture cannot characterize generalization.
- Phrase rules do not understand clinical context, negation, temporality, or competing diagnoses beyond their explicit cases.
- Fixed weights and half-lives have not been clinically calibrated.
- The mapping registry contains one demonstration mapping.
- No real-world clinical evaluation has been performed.

## Human oversight

Syndrome outputs and conditional terminology mappings require review. A future governed system must record reviewer identity, decision, rationale, and versioned approval.
