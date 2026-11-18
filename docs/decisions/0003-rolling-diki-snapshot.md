# ADR 0003: Retain a rolling Diki snapshot

Date: 2026-11-17.

Status: Accepted — explicitly described by the owner in interview batch 13.

## Context

Diki source HTML supports offline vocabulary creation and repeated checks or
future refinements of existing Anki notes. Re-downloading the same content on
each run is costly and unnecessary for those goals.

The collection is prepared over time, potentially across multiple weeks. Diki's
content and HTML can change independently while that preparation is ongoing.

## Decision

Retain and reuse successfully downloaded source material as an accumulated,
rolling Diki snapshot. Ordinary checks use that local reference. Do not introduce
routine expiry or periodic refreshing of already available content as a default
requirement.

If assertions/tests expose discrepancies involving source changes, the owner
will evaluate them manually. A failure does not automatically authorize fetching
new data, accepting new expected results, or rewriting stored Anki content.

## Rationale and trade-offs

- Preserves offline use and avoids repeated downloads for contract/refinement work.
- The owner considers a dictionary snapshot collected over weeks good enough.
- Per-resource snapshots have different capture dates; this is not a single-day
  dictionary export or a promise of current online freshness.
- Source changes may require manual investigation to distinguish changed content
  from code defects. The owner explicitly accepts that responsibility.

## Consequences

- Interpret Diki compatibility against the saved source used for the comparison.
- Existing download time/source/digest metadata provides useful snapshot context.
- Explicit refresh may remain available, but is not a maintenance obligation.
- Failed/missing download retry is distinct from refreshing successful content.
- No source-version archive, migration algorithm, or automatic failure-resolution
  workflow is chosen by this decision.

See [cache goals and priority](../features/offline-cache.md) and
[Diki compatibility](../contracts/diki.md).

Supersedes: none. Superseded by: none.
