# Validation Plan

## Current claim

The MVP demonstrates software traceability and deterministic reinterpretation over synthetic data. It makes no claim about diagnosis, prognosis, treatment selection, clinical performance, clinical utility, or patient safety.

## Implemented checks

- Deterministic replay produces byte-equivalent structured output.
- Every CSEP contains all six declared dimensions.
- Ledger verification detects altered event content.
- ILAE 2017 and ILAE 2025 runs preserve the same ledger head.
- Framework reinterpretation changes the profile hash.
- The 2025 terminology mapping is conditional and reviewable.
- Non-synthetic public payloads are rejected.
- The React application passes strict TypeScript checking and a production build.

## Research beta gate

1. Add property-based tests for causality, monotonic time, replay, supersession, and hash-chain invariants.
2. Implement a versioned mapping registry with provenance, effective dates, reviewer signatures, and rollback.
3. Add a synthetic trajectory generator with missingness, irregular sampling, label noise, and controlled latent states.
4. Measure parameter/state recovery only after an executable probabilistic model is selected and frozen.
5. Report calibration and discrimination separately; prohibit isolated headline metrics.
6. Conduct external epileptologist review of phenotype definitions and mapping decisions.

## Clinical research gate

- Independent data-governance and security review.
- Retrospective protocol with pre-specified endpoints and gold-standard adjudication.
- Bias and subgroup performance analysis with uncertainty intervals.
- Prospective validation and human-factors evaluation.
- Regulatory determination before any clinical decision-support claim.
- Institutional authorization, informed governance, and monitored incident response.

## Failure handling

The target behavior for missing, contradictory, or non-mappable evidence is to preserve the source, reduce certainty, emit `review_required`, and avoid a silent forced classification.

## Non-claims from source material

Documentary values such as 239 extracted claims, 97.4% accuracy, 91% concordance, precision >0.88, and recall >0.85 are not treated as validated results. The required source artifacts, protocols, cohort definitions, and independent adjudication evidence are not included in the supplied repository.
