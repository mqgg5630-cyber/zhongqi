# Canonical citation registry contract

`citation_registry.py` emits `light.citation_registry.v1`. The registry is the
author-facing single source of truth for stage 10; `.bib` and CSL are derived
views, not competing truth stores.

## Required work fields

Each `works[]` row contains:

- `work_id`: stable hash of the strongest normalized identity.
- `identifiers`: arrays for DOI, arXiv, PMID, ISBN and URL.
- `versions`: every identifier/version with the inventory row that supplied it.
- `inventory_ids`: links back to raw author artifacts.
- `status`: `CONFIRMED`, `CONFIRMED-MISSING`, `UNAVAILABLE`, or `UNRESOLVED`.
- `canonical_source` and `metadata`: fields selected from the DOI registration
  agency; fuzzy matching never overwrites the author's citation.
- `source_evidence`: one row per queried source with endpoint, HTTP status,
  outcome, retrieval time, source-level field values and
  `normalized_payload_sha256`。哈希绑定实际用于判定的规范化字段，不冒充原始响应归档；
  endpoint 永不持久化 email、API key 或 token。
- `field_conflicts`: per-field values grouped by source.
- `publication_updates`: Crossref `updated-by` facts applying to the queried
  work. A notice's inverse `update-to` is not treated as a status of the notice.
- `is_chimeric` / `mismatch_fields`: claimed versus canonical core-field audit.

`citation_four_gate.py --registry citation-registry.json` converts these rows
into `light.citation_four_gate.v1` records. Use that path for real audits so
existence, identity, directed publication status and claim support are derived
from the canonical registry instead of retyped into a fixture.

## Status state machine

| State | Evidence requirement | Gate effect |
|---|---|---|
| `CONFIRMED` | registration metadata plus at least one independent field source | existence passes |
| `CONFIRMED-MISSING` | DOI RA explicitly says the DOI does not exist and Crossref + DataCite both return 404/410 | citation_verify critical |
| `UNAVAILABLE` | transport, 401/403, 429 or retryable 5xx prevents authoritative lookup | warn; retry |
| `UNRESOLVED` | registered/partly found but two-source confirmation is incomplete | warn; investigate |

An index miss at Semantic Scholar, PubMed or OpenAlex cannot by itself prove a
work does not exist. A Crossref 404 cannot disprove a DataCite DOI.

## Claim edges

`claim_edges[]` links `claim_id` and exact claim/locator to `work_id` and
citekey. Metadata confirmation proves only that the work exists. `SUPPORTS`
requires a real non-placeholder source locator plus a review. `claim_text_sha256`
is the SHA-256 of the current exact claim text; `reviewed_claim_sha256` is the
claim text hash the reviewer actually checked. They must match, otherwise the
review is stale and is demoted to `REVIEW_REQUIRED`. `reviewed_at` must parse as
an ISO date/time that has already occurred; future review times or template
locators are demoted to `REVIEW_REQUIRED`. `PARTIAL`,
`RELATED_ONLY`, `UNSUPPORTED`, and `REVIEW_REQUIRED` all produce relevance
warnings for human resolution; they never enlarge stage 10's critical surface.

## Derived delivery

- `references.bib`: only confirmed, non-chimeric works.
- `references.csl.json`: CSL JSON view of the same accepted works.
- `citation-evidence.json`: source-level lookup evidence and update facts.
- `citation-failures.json`: missing, unavailable, unresolved or chimeric works.
- `claim-citation-review.json`: every non-`SUPPORTS` claim edge.
- `citekey-audit.json`: manuscript ↔ generated BibTeX key audit.
- `delivery.json`: stage-10 handoff contract for typesetting. It records
  `status` (`DELIVERED`, `ERROR`, or `REVIEW_REQUIRED`) and
  `deliverable_hashes` using `sha256:<64 hex>` for every file it names.
  Typesetting must reject a delivery that is not `DELIVERED`, has missing or
  mismatched hashes, has non-empty failures, or has non-`SUPPORTS` claim edges.
