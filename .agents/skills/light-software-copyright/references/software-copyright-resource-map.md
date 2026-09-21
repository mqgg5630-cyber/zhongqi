# Software copyright resource map

Last checked: 2026-07-05. Software copyright forms, portals and acceptance
requirements can change; verify official pages again before real submission.

## Peer skills and what Light borrowed

| Source | Observed signal | Useful mechanism | Light boundary |
|---|---:|---|---|
| [`Fokkyp/SoftwareCopyright-Skill`](https://github.com/Fokkyp/SoftwareCopyright-Skill) | ~4.2k stars, MIT, HEAD `0a27d1143eca253b7b7e953794a24ef6e5488b0d` | Real-project analysis, application worksheet, business-context/manual drafting, front/back 30 source extraction, staged confirmations, formal folder | Light adds a machine evidence gate, stricter secret/version/hash checks and avoids “可提交” overclaim |
| [`na57/chinese-copyright-application-skill`](https://github.com/na57/chinese-copyright-application-skill) | ~151 stars, HEAD `04081d0` | China-oriented application fields, manual/source-material templates | Lower process fidelity; use as checklist inspiration only |
| [`jaccen/AI-Copyright-Skill`](https://github.com/jaccen/AI-Copyright-Skill) | Adjacent patent + soft-copyright skill, HEAD `20908b7` | IP material framing and combined documentation prompts | Do not import AI-specific assumptions or generated-code shortcuts |

Deep read record: [`../../../docs/learning/ip/software-copyright-deep-read-report.md`](../../../docs/learning/ip/software-copyright-deep-read-report.md).

## Official and high-trust anchors

- National Copyright Administration PDF, `计算机软件著作权登记办法`:
  <https://www.ncac.gov.cn/xxfb/flfg/bmgz/202410/P020241015604759788122.pdf>.
  It anchors the application materials, China Copyright Protection Center role,
  software identification materials, first/last 30-page logic, all-material
  logic under 60 pages, line-count norms and unified Chinese/A4 form language.
- Beijing government service guide, `计算机软件著作权登记初审`:
  <https://banshi.beijing.gov.cn/pubtask/task/1/110000000000/3e283672-76be-4c8c-98e8-0bebe9bd06bf.html?locationCode=110000000000>.
  Useful as a service-guide consolidation of current material requirements,
  signature/seal notes and version consistency reminders.
- U.S. Copyright Office Circular 61:
  <https://www.copyright.gov/circs/circ61.pdf>.
  Use only when the user explicitly asks for US computer-program registration;
  US deposit rules differ from China and must not be mixed.
- `计算机软件保护条例`:
  <https://xzfg.moj.gov.cn/front/law/detail?LawID=914>.
  Use for the boundary that software copyright protects expression, not ideas,
  processing methods, operation methods or mathematical concepts.

## Light material packet contract

A credible China software copyright packet has:

1. `jurisdiction: CN` and explicit non-legal-advice acknowledgement;
2. application fields with user-confirmed software name and version;
3. a real source-file manifest with relative paths and SHA-256;
4. code material from real source, with page mode and line-count rule;
5. documentation/manual material with page mode and line-count rule;
6. confirmation gates for environment, application fields, business context,
   code selection, markdown draft and final export;
7. version/name consistency evidence across worksheet, manual, code headers and
   formal output filenames;
8. secret/private-data scan result;
9. formal output file paths and SHA-256.
10. source-deposit plan SHA, verified rights basis and third-party/open-source
    code review.

The machine gate is [`../scripts/materials_gate.py`](../scripts/materials_gate.py).
It intentionally blocks:

- AI-generated or padded source code;
- missing user confirmations;
- front/back page-rule mismatch;
- software version mismatch;
- missing formal output hashes;
- secret-scan failures;
- submission or approval guarantees.

The lightweight source planner is
[`../scripts/source_deposit_plan.py`](../scripts/source_deposit_plan.py). It
creates `light.software_copyright.source_deposit_plan.v1` records with
candidate files, SHA-256, line/page estimates, recommended selection and a
secret scan. The model/user must still confirm the final selection.

## Prompting stance

The useful expert posture is:

> “I will package what your real software already contains, keep every field and
> version consistent, show exactly which source files became code material, and
> stop where ownership, publication, third-party code, secrets or official-rule
> changes need human/professional confirmation.”

If there is no real project source, produce a readiness checklist instead of
creating fake registration material.
