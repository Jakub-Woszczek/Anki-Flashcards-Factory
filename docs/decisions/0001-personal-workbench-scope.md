# ADR 0001: Personal workbench scope

Date: 2026-11-17.

Status: Accepted — explicitly stated by the owner in the foundation interview.

## Context

The project is published on GitHub but serves the owner's vocabulary-learning
workflow. Its behavior is intertwined with the owner's Anki deck and note-type
structure. Public hosting could otherwise be mistaken for an intention to build
a generally configurable, standalone production service.

## Decision

Treat the project primarily as the owner's personal workbench integrated with
their existing Anki collection. Generalizing or untangling it into a standalone
production service is not a current goal.

## Rationale

This reflects how the owner uses the project and their stated plans. The current
scope is to support that vocabulary workflow, including the existing Anki setup.

## Consequences and trade-offs

- Document the owner's relevant Anki assumptions as actual integration context.
- Do not introduce requirements for arbitrary users, collection structures, or
  production hosting merely because the repository is public.
- General portability and standalone-service behavior are not promised by this
  scope decision. Existing configurable features can still serve the workflow.
- This does not settle which current collection-specific details are intentional;
  those will be reviewed in the Anki portion of the walkthrough.
- Revisit the scope if the owner's intended audience or deployment goals change.

## Source and related documentation

- Owner's foundation-interview answer: this is mainly a personal workbench, tied
  to their Anki structure, with no current plan for a standalone production service.
- [Project purpose and scope](../project.md).
- [Walkthrough checkpoint](../review.md).

Supersedes: none. Superseded by: none.
