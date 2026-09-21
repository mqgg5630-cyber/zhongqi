# Stage-11 build contract

## Input

`light.typesetting_input.v1` names every author-controlled input. Paths are
resolved relative to the input JSON. The build snapshot copies only declared
manuscript files, figure artifacts and citation delivery files; each row keeps
its original path, declared producer, byte size and SHA-256.

`output_dir` must be new or empty. The builder refuses a non-empty directory
instead of allowing stale `.aux`, source, figure or PDF files to contaminate a
new manifest. Use a fresh run directory for every repair iteration.

The citation handoff must be `light.citation_delivery.v1` with
`status=DELIVERED`, `deliverable_hashes`, empty `citation-failures.json`, and
empty `claim-citation-review.json`. Typesetting consumes `references.bib` and
`citekey-audit.json`, verifies that every named deliverable still matches its
`sha256:` hash, then checks the staged manuscript against that BibTeX. It does
not revisit DOI existence, metadata conflicts, retraction direction or claim
relevance.

Every figure row must name a source manifest. Supported schemas are
`light.figure_delivery.v1` and `light.figure_build.v1`. The figure file staged
into LaTeX must match one declared output SHA-256 in that manifest. For
empirical `light.figure_delivery.v1` rows, typesetting also requires
`evidence_binding.binding_status=CONFIRMED` from `RESULT-ANALYSIS`; it does not
rejudge the visual or statistical claim.

`light.typesetting_venue_profile.v1` is supplied by the user or built from the
current authoritative venue instructions. Its `source` records kind, URL,
check date and notes. No default page limit, anonymity rule, template version
or font rule is treated as universal truth.

## Compile states

| Status | Meaning | Process exit |
|---|---|---:|
| `PASS` | compiler returned zero, PDF exists, citations/references converged | 0 |
| `ERROR` | manuscript, declared backend or input contract is wrong | 1 |
| `UNAVAILABLE` | compiler, engine, backend, package or local resource cannot run | 0 |
| `UNRESOLVED` | PDF exists but citation/reference rerun signals remain | 1 |

`UNAVAILABLE` is not `PASS`: it may pass the command gate's non-critical
environment boundary, but the delivery remains `UNAVAILABLE`, never
`DELIVERED`. A compile timeout/launch failure is classified as toolchain
availability rather than blamed on the manuscript. The same applies when a
profile requires page-box/font/page checks but the local PDF inspector cannot
produce the required fact.

Compile state is only one layer. `submission_readiness.py` derives the separate
chain `INVENTORIED → SOURCE_BUILDABLE → TECHNICALLY_CHECKED →
VISUALLY_CHECKED → METADATA_MATCHED → VENUE_READY → USER_APPROVED`.
The chain cannot skip a failed predecessor. Visual status requires compile
`page_count`, the same `compile.pdf_sha256`, and one render-hash/review row per
PDF page with render tool, reviewer/reviewer_id and non-future review date.
Metadata, compliance and user approval also bind to the same PDF hash.
Venue-ready additionally requires a current official profile bound to the exact
article type and a passing compliance report whose `venue` and `article_type`
match the profile. User-approved records authority but never submits.

## Canonical outputs

`build_submission.py` writes:

- `source/`: immutable build snapshot;
- `build-manifest.json` (`light.typesetting_build.v1`): provenance, preflight,
  exact command/working directory, upstream handoff status/hashes, tool
  versions, rounds, hashes and status;
- `compile-report.json` (`light.typesetting_compile.v1`);
- `compile/*.log` and `compile/*.pdf` when produced;
- `compliance-report.json` (`light.typesetting_compliance.v1`);
- `failure.json` (`light.typesetting_failure.v1`) for failed/unavailable runs;
- `venue-handoff.json` (`light.typesetting_venue_handoff.v1`);
- `delivery.json` (`light.typesetting_delivery.v1`).
- `submission-readiness-report.json` (`light.submission_readiness_report.v1`)
  when the readiness packet is evaluated; it keeps page, profile, metadata and
  artifact evidence separate and does not award institutional badges.

The venue handoff contains PDF path/hash, page count, page size, compliance
report, profile name/source and caveat. Venue-matching consumes these facts; it
does not reinterpret stage-11 compilation.

## Stage 11

Run `compile_driver.py` as the `compile` command gate and
`desk_reject_gate.py` as the `desk_reject` findings producer. A manuscript
compile error or objective profile breach can block stage 11. Missing local
tools and network resources do not become manuscript critical. `ROUTES` has no
key 11: fix stage-11 failures in stage 11 and do not invent a back-edge. On
Windows use `--json-out ... --quiet` for the command gate so the orchestrator
does not decode a UTF-8 human report through a legacy local code page.
