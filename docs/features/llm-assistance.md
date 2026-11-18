# LLM assistance for understanding words and translations

Last updated: 2026-11-17.

Specification status: original purpose confirmed by the owner; future
definition-related ideas are deferred for a separate discussion.

Implementation status: optional Gemini translation and comparison requests are
present. This document distinguishes that implementation from its motivation.

## Problem and rationale

An English word can have several Polish translations that seem very different.
Choosing useful meanings can require understanding the English concept and how
those translations relate. The owner wanted a quick way to investigate that
uncertainty instead of manually searching the web each time.

The LLM is a convenient aid to human understanding: an English definition, possible
translation, or interpretation of apparently disparate translations can help the
owner understand what is going on and make their selection.

The owner describes this as an LLM role in general; Gemini is the current
integration. This explanation does not request implementing additional providers.

## Intended role in the main workflow

- Help the owner interpret a word and its diverse translation alternatives.
- Provide a quick explanatory response when selection is difficult.
- Support the owner's judgment about what is worth learning.
- A discrepancy with Gemini can be marked `GEMINI_DIFF` for closer manual
  examination after addition, as already explained in the
  [Anki tag lifecycle](../contracts/anki.md#owner-confirmed-tag-lifecycle).

This does not turn model output into an automatic replacement for the owner's
selection or redefine [Diki compatibility](../contracts/diki.md). The owner has
not specified an automatic per-word invocation or mandatory model approval.

## Current implementation evidence

- `frontend/src/App.tsx`, `askGemini`, requests assistance through UI actions and
  displays the returned text.
- `external_APIs/geminiAPI.py`, `word_translation_prompt`, asks for an
  English-to-Polish translation and includes original Diki alternatives when
  available. It does not explicitly request an English definition.
- `backend/services.py`, `gemini_review`, asks for comparison of an existing
  translation with proposed selected translations.
- Assistance is optional and depends on configured Gemini credentials. The
  response is advisory text, not an automatically applied Anki field update.

The owner's explanation establishes the purpose; it does not settle whether
future prompts should be independent of Diki, the precise output format, or
provider choice. Those implementation details need not block the broad walkthrough.

## Deferred direction

The owner has newer ideas involving word definitions and explicitly wants to
discuss those later. Do not expand this explanation into a structured-definition
generation/storage feature now. See [future work](../roadmap.md#future-discussion-word-definitions-and-llm-ideas).

## Authority and verification

Purpose comes from interview batch 11 on 2026-11-17. Implementation facts come
from source inspection. No model requests or prompt/code changes were made as
part of documenting this explanation.
