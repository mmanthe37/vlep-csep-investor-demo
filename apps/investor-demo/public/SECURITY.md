# Security Policy

## Supported scope

The public investor demo is a static, synthetic-data application. It should not collect, transmit, or store PHI, credentials, tokens, or user-submitted clinical data.

The database-backed API prototype is not approved for internet-facing clinical deployment.

## Reporting a vulnerability

Open a private GitHub security advisory for the repository owner. Do not include patient data, credentials, exploit payloads containing third-party secrets, or public proof-of-concept details before triage.

Include:

- affected commit and component;
- reproduction steps using synthetic data;
- expected and observed behavior;
- impact and suggested mitigation, if known.

## Secret handling

- Commit only `.env.example`, never `.env`.
- Use GitHub environment/repository secrets for deployment credentials.
- Rotate any exposed credential immediately; removal from Git history is not sufficient.
- Never place PHI or real patient records in issues, pull requests, fixtures, logs, screenshots, or Pages artifacts.

## Pre-clinical requirements

Threat modeling, authorization hardening, audit-log review, encryption design, dependency scanning, incident response, privacy assessment, and independent penetration testing are required before any governed research integration.
