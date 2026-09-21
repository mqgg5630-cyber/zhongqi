# Venue source and evidence policy

All venue facts are per-run evidence. This file contains no journal metrics,
deadlines, warning lists, or cached recommendations.

## Source roles

| Source | Access | Use | Never infer |
|---|---|---|---|
| Official venue/publisher Aims & Scope and author instructions | free public or login | scope, article type, length, figures/tables, supplement, template, anonymity, fee/OA, timing if published | acceptance likelihood from silence |
| Official conference CFP | free public | track, article type, page limit, deadline, notification date, location/presentation obligations | reuse last year's dates |
| Crossref REST API | free public, no signup | candidate discovery, DOI/container/ISSN identity, example works | scope fit, index membership, rank, safety |
| DOAJ API/site | free public | positive evidence that a fully OA journal is currently listed; OA metadata | “not listed” when query failed; predatory verdict from absence |
| OpenAlex Sources/Works | free key; some access may be unavailable | topics, recent works, source identity/coverage signals | official venue policy, acceptance rate, JCR/Scopus membership |
| ISSN Portal | public web with restricted features | title/ISSN identity and hijack cross-check | editorial quality |
| Clarivate Master Journal List | public lookup | current WoS collection membership | JIF/quartile without JCR access |
| JCR | institutional/paid | current JIF/JCR category/quartile | copy from an unlicensed aggregator |
| Scopus Sources/CiteScore | login/key/institution varies | current Scopus source status and CiteScore fields | “not indexed” from API/login failure |
| SCImago SJR portal | free web, no supported core API assumption | secondary Scopus-derived SJR/quartile evidence with year | JCR quartile; automate around 403/robots |
| CCF/CAS/北大核心/CSSCI/CSCD official or institutional source | public or institutional | context-specific recognition with edition/year | mix one scheme with another |
| Think.Check.Submit | free public | human checklist for publisher/journal identity, transparency, peer review and fees | whitelist or final verdict |
| Retraction Watch hijacked-journal checker | free public | current hijack lead for manual verification | entire predatory verdict |
| Cabells Predatory Reports/Journalytics | paid | optional multi-indicator evidence when user has lawful access | core-path dependency or fabricated “not listed” |
| Beall archives | free archive | historical lead only | current authoritative blacklist |
| Publisher journal finders | usually free public | publisher-bounded candidate discovery | neutral whole-market ranking |

OpenAlex authentication/pricing numbers have one repository truth source:
`../light-literature-search/references.md` under “OpenAlex 接入真相源”. Do not
duplicate changing quotas here.

## Authority precedence

1. Use official venue/CFP pages for submission rules.
2. Use the named authoritative index for its own membership/metric.
3. Use DOI/ISSN registration metadata for identity.
4. Use independent public databases as corroboration.
5. Use publisher finders and aggregators for discovery only unless the exact
   field is source-attributed and current.
6. Use anecdotal author reports only as labelled soft context; never as
   acceptance probability or official review time.

When sources conflict, preserve both values/source IDs and mark the canonical
field `UNKNOWN` pending human resolution. Do not average or silently prefer the
more favorable value.

## Field freshness

The canonical workflow requires same-day evidence for:

- acceptance rate;
- review/first-decision/publication time;
- APC and OA model;
- indexing, JIF/CiteScore/SJR/quartile;
- CFP/submission deadline.

Scope, article type, page/word limit, supplement and format rules should also be
checked on the run date because publisher pages change without versioned URLs.
If a page only shows a year, record that year plus retrieval date.

## Failure semantics

| Observation | Status | Meaning |
|---|---|---|
| Current source returns the field | `AVAILABLE` | retain value + source + date |
| Source accessible but field absent/ambiguous/conflicting | `UNKNOWN` | no usable conclusion |
| 403/429/5xx, timeout, robots, key/login/institution/subscription needed | `UNAVAILABLE` | source could not answer |
| Volatile field not checked on the run date | `STALE` | do not use value for decision |

`UNAVAILABLE` and `UNKNOWN` are not risk signals. DOAJ query failure is not
“not in DOAJ”; Scopus/JCR login failure is not “not indexed”; missing APC is
not zero APC.

## Predatory and hijack review

Use multiple independent checks:

- verify exact name, ISSN, publisher domain and submission domain;
- compare official/ISSN/Crossref identities;
- check transparent scope, editorial board, peer-review process, fees and
  archiving;
- check DOAJ/COPE/OASPA claims at their current sources where relevant;
- check current hijack warnings and optional Cabells evidence;
- treat archived Beall entries, solicitations, high APC, rapid review, volume
  growth, and self-citation as leads, not verdicts.

Record each lead as `WARN` with evidence and missing checks. Let the author make
the final risk decision. Never label a venue predatory solely because it is new,
regional, non-English, not in one commercial index, or unavailable to a query.

## Publisher finder boundary

Elsevier, Springer Nature, Wiley and IEEE recommend within their own catalogues.
Use title/abstract matching and displayed decision columns to expand candidates,
then verify each candidate at its official page and compare across publishers.
Do not describe a publisher-bounded result as the globally best venue.

## Related contract

Read `references/workflow_contract.md` for field envelopes, canonical outputs,
and the enforced user-selection transition.
