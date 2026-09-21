# Software copyright materials workflow

Use this reference for China software copyright material preparation. It is not legal advice and does not submit applications.

## 1. Official-rule posture

Default jurisdiction is `CN` only when the user asks for China software copyright. Do not reuse CN rules for US/EU work. Recheck official pages on the day of real filing. Preserve `UNKNOWN` or `PLANNED` when form, page, fee, signature or portal facts are not verified.

## 2. Business understanding before forms

Before writing application fields or a manual, read real project evidence:

- README, PRD/BRD/design docs, route/page/component names, API docs, CLI help, screenshots, product text and user-provided descriptions.
- Identify domain, target users, main functions, technical characteristics, operation flow and system requirements.
- Distinguish project evidence from external industry references.

The manual should read like a real user/operation manual: where the user enters, what they see, what they click/type, what validation/error appears and what result is produced. Avoid code implementation, framework internals, marketing slogans and uniform AI-style section templates.

## 3. Source deposit plan

Run the source planner before code extraction:

```bash
python scripts/source_deposit_plan.py --root <project-root> --out 软件著作权申请资料/草稿/source-deposit-plan.json --software-name "<软件全称>" --version "<版本号>"
python scripts/source_deposit_plan.py --selftest
```

Use the plan to inspect:

- candidate source files, relative paths and SHA-256;
- source/material line counts and estimated pages;
- recommended files and model reasons;
- `front_back_30` vs `all_source` mode;
- secret findings.

If `secret_scan.status` is `FOUND`, stop for redaction. Do not export code material until the scan is `PASS` or `REDACTED_AND_VERIFIED`.

## 4. Code selection rules

Select real source that best represents the registered software expression:

- Prefer entry, routes/pages, components, API/services, state/data handling, core backend/business logic and user-visible workflows.
- Exclude dependencies, build output, minified bundles, generated files, lock files, vendored/unrelated third-party code and private data.
- If selected source is fewer than 60 pages and all relevant source is fewer than 60 pages, use all real source; never pad or AI-generate code.
- If selected source is fewer than 60 pages but relevant candidate source can reach 60 pages, ask the user/model to supplement selection before extraction.
- Keep the plan hash and confirmation basis in the materials packet.

## 5. Rights and third-party review

Before formal export, record:

- `rights_basis`: independent/cooperative/commissioned/assigned/inherited/derivative basis and supporting locator if available.
- `third_party_code_review`: whether third-party, open-source, generated, template, dataset, model-weight or unrelated code is included or excluded.

If rights are not verified, do not mark the packet PASS. If third-party code needs exclusion, list excluded relative paths.

## 6. Application worksheet

Keep these fields consistent across all materials:

- software full name, optional abbreviation, version;
- copyright owner/applicant, developer and development mode;
- completion/publication dates;
- development/operation hardware and software environment;
- programming languages, source program quantity, document quantity;
- development purpose, domain, main functions and technical characteristics.

Names and versions in worksheet, manual title/header, code material header and formal filenames must match.

## 7. Documentation material and screenshots

The documentation material can be an operation/user manual, design document or other official-accepted document depending on current rules. For normal material logic:

- document pages at least 60: front/back 30 pages;
- fewer than 60: include all;
- full document pages normally use at least 30 lines unless an official exception is documented.

Screenshots are optional depending on workflow and local practice. If used, bind each screenshot to real running UI or user-provided image with SHA-256. If skipped, record why and keep visible screenshot placeholders when the manual expects them.

## 8. Gate before review

Create `software-copyright-materials.json`, then run:

```bash
python scripts/materials_gate.py --packet software-copyright-materials.json --base <project-root> --as-of 2026-07-05
python scripts/materials_gate.py --selftest
```

The gate checks jurisdiction, legal boundary, application fields, source plan, source files, confirmations, rights basis, third-party review, code/page rules, document/page rules, version consistency, secret scan, screenshots and formal-output hashes.
