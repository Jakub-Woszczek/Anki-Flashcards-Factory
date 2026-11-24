# ADR 0010: Strict existing-note HTML coverage and saved-first reconciliation

Date: 2026-11-24. Status: accepted and implemented.

## Decision

The owner requested a percentage bar for cached HTML categories on existing Anki
notes, with `entries` as the strict goal and a clear manual-review list for every
note outside that category. Download/preparation behavior is unchanged.

1. Use the existing normal-vocabulary scope: `Basic [reverse+audio]` and
   `Basic [reverse+audio+image]`, excluding Diki-missing/image-only types. Count each
   note once, independently of its number of cards. The owner's vocabulary model is
   one word per note. Word order is irrelevant to these statistics.
2. Extend the saved inventory at the existing data-root path with note IDs, English
   values, model names, and full per-note validation errors. Retain the case-sensitive
   word list for the existing downloader. Version-1 inventories remain readable by
   preparation; they need a successful Anki reconciliation/export before they can
   identify notes for this report.
3. At application startup, a background worker first publishes statistics from the
   saved note inventory and local HTML. It then reads Anki once, validates complete
   batches and a stable active profile, and atomically replaces the inventory.
   Recompute statistics and report inventory additions/changes/removals. A different
   saved profile is an error requiring a profile switch or explicit export.
4. Compare that Anki snapshot with the advisory local note index. Report missing
   indexed notes, different note IDs/English values, and indexed notes outside the
   inventory. An outside-inventory record is not proof of deletion. Report findings
   without repairing the index or changing notes. Index-read failure does not hide
   otherwise valid HTML coverage.
5. Classify integrity-checked cached HTML using the shared inspector's primary
   `entries`, `suggestions`, `related`, `collocation`, `not_found`, or `unknown`
   result. Include separate missing-HTML, unusable-HTML, and unprocessable-English buckets
   so every scoped note remains in the denominator. Only `entries` meets the goal;
   audio, old exact-match metadata, headword order, and translation selection do
   not determine this statistic. This is source-HTML classification, not an audit
   of stored English identity or Polish compatibility.
6. Present a segmented bar and a count/percentage legend, followed by a
   category-filterable list of every note outside `entries`: English value, note
   ID, model, category, and reason. Classification never fetches/replaces HTML or
   writes to Anki. Human review decides how to handle non-entry results. Following
   the owner's clarification, missing HTML means no local file exists; unusable
   HTML means an existing file cannot be read or verified. Hide missing downloads
   from the default Needs review list/count; retain explicit Missing HTML and
   All outside entries filters. Both categories remain in coverage percentages.
7. The worker exists independently of remote configuration. Dashboard refreshes
   request local-only recalculation and never repeat the Anki scan. Reuse parsed
   classifications by content digest, bounded to the current inventory. Successful
   inventory reconciliation notifies existing remote preparation to reconsider
   missing HTML, under its unchanged goals and resource-retention rules.
8. Keep saved statistics/date/profile visible when Anki is unavailable or its scan
   fails. Preserve the prior export on incomplete reads or profile changes. Shutdown
   signals cancellation without joining Anki waits or saving a late export.
9. Show real per-stage loading progress for local cache validation and note HTML
   classification: processed/total, remaining, and percentage. Unknown totals use
   an indeterminate bar, with no estimated overall percentage. HTTP requests read
   in-memory state; pending-list scanning runs in a separate application-scoped
   worker. Progress polling never queues follow-up scans while one is active.
   Both workers retain previous results on refresh/failure and allow polling to
   request another local scan only after 60 idle seconds. The one-time Anki scan
   is not repeated by progress polling.

This supersedes ADR 0009's explicit-export-only/no-startup-Anki-scan rule. Manual
export remains available. Remote priorities, the finite startup drain, immediate
imports/ACKs, and snapshot retention retain their existing rules.

The Offline downloads panel also removes the requested explanatory text, manual
Refresh coverage button, routine remote-preparation summary, mode explanation,
and pacing counters. Actual errors remain visible.
