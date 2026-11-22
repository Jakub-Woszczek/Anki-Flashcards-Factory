# Loose thoughts and possible work

These are the owner's informal ideas, observations, and reminders. They are not
specifications, confirmed diagnoses, priorities, implementation plans, or
authorization to implement. List order does not imply priority. Clarify scope and
behavior when the owner chooses an item to work on.

- **Existing-note matching:** `Demeanor` does not show an existing note; casing
  is a suspected cause to investigate.
- **Sentences:** Explore adding sentences to notes. This is a separately scoped
  feature; see the [deferred discussion](roadmap.md#future-discussion-example-sentences-in-anki-notes).
- **Performance:** Investigate long requests.
- **Usage:** Review logs to understand how the owner actually uses the app.
- **Optional simplification (`Q-002`):** Consider removing unfinished-word draft
  autosave/resume. Reselecting translations is acceptable and interruptions are
  rare. This does not concern the Diki cache or durable save-recovery journal.
  See [draft expectations](features/vocabulary-queues.md#unfinished-word-drafts).

## Maintenance

Keep only pending thoughts here. When work is completed, document the implemented
behavior and relevant evidence in the appropriate [feature page](features.md),
then remove the thought from this file. Contracts and ADRs own detailed rules and
decisions; the [roadmap](roadmap.md) provides broader future-work context.
