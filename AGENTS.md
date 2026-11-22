# Working on Anki Flashcards Factory

- Start with `docs/index.md`, then the contracts and feature pages relevant to the
  task. They distinguish intended behavior from implementation and historical plans.
- If a behavior decision is missing or ambiguous, ask the owner before changing it.
- Keep the owner's pending loose thoughts in `docs/todo.md`. Entries are not
  specifications, confirmed diagnoses, priorities, implementation plans, or
  authorization to implement; clarify scope when the owner chooses an item.
- Document implemented behavior and completed work in the relevant
  `docs/features/` page and link it from `docs/features.md`; then remove the pending
  thought from `docs/todo.md`. Contracts/ADRs own detailed rules and decisions;
  `docs/roadmap.md` provides future-work context. Do not recreate a root todo list
  or mix completed-work records into the pending list.
- This is a personal, local Mac workbench. Preserve existing launch commands,
  resource paths, Anki field contracts, and collection state during cleanup work.
- Run `python -m tools.check` after code changes. It checks Ruff lint/formatting,
  Pyright, guarded offline tests, and the frontend TypeScript/build pipeline.
- Use `python -m tools.test_offline` for routine test-only verification. Real Anki
  and Diki checks must be explicitly requested; do not run collection audits as
  routine tests or refresh dictionary fixtures to hide failures.
- Formatting fixes: `python -m ruff check --fix .` and `python -m ruff format .`.
  Review fixes; do not use unsafe fixes or weaken contracts to satisfy diagnostics.
- Python development dependencies are in `requirements-dev.txt`; activate the
  project's environment before running checks or committing. Install local hooks
  with `python -m pre_commit install` once per checkout.
- Keep generated data, credentials, environments, and IDE state out of Git. Shared
  VS Code configuration belongs in the explicitly allowed `.vscode` files.
