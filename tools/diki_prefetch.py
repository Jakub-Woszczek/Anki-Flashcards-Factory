"""Run with `python -m tools.diki_prefetch`; safe to resume on each invocation."""

import argparse
import json
import time

from dotenv import load_dotenv

from external_APIs.diki_lists import coverage, discover_lists
from external_APIs.diki_resources import (
    ROOT, BatchDeadline, Deferred, DikiResources, DikiServerError, DikiTimeout,
    NoAudio, ResourceError, file_lock,
)


def run_batch(resources, lists, *, batch_size=25, refresh=False):
    summary = {"startedAt": resources.clock(), "finishedAt": None, "status": "running",
               "attempted": 0, "html": 0, "audio": 0, "noAudio": 0,
               "errors": 0, "message": None}
    try:
        with file_lock(resources.root / "prefetch.lock", blocking=False):
            resources.set_setting("last_run", summary)
            try:
                _download_batch(resources, lists, summary, batch_size, refresh)
            except BatchDeadline as error:
                summary.update(status="time_limit", message=str(error))
            except KeyboardInterrupt:
                summary.update(status="interrupted", message="Interrupted; downloads will resume next run")
            except (OSError, ValueError) as error:
                summary.update(status="error", message=str(error))
            finally:
                if summary["status"] == "running":
                    summary["status"] = "partial" if summary["errors"] else "complete"
                summary["finishedAt"] = resources.clock()
                resources.set_setting("last_run", summary)
    except BlockingIOError:
        summary.update(status="already_running", finishedAt=resources.clock(),
                       message="Another prefetch process is running")
    return summary


def _download_batch(resources, lists, summary, batch_size, refresh):
    if resources.offline:
        summary.update(status="offline", message="DIKI_OFFLINE is enabled; no downloads attempted")
        return
    if resources.setting("cooldown_until", 0) > resources.clock():
        summary.update(status="cooldown", message=resources.setting("cooldown_reason"))
        return
    snapshot = resources.snapshot()
    words = dict.fromkeys(word for source in lists for word in source.words)
    # Fresh work goes ahead of previously failed resources; main-list ordering is
    # retained within each group so a failing head word cannot starve book lists.
    ordered = sorted(words, key=lambda word: any(
        snapshot.get((word, kind), {}).get("state") == "error" for kind in ("html", "audio")))
    consecutive_failures = 0
    for word in ordered:
        html = snapshot.get((word, "html"), {})
        audio = snapshot.get((word, "audio"), {})
        if not refresh:
            if html.get("state") == "ready":
                if not html.get("exact_match") or audio.get("state") in {"ready", "no_audio"}:
                    continue
                needed = [audio]
            else:
                needed = [html]
            if any(item.get("retry_at", 0) > resources.clock() for item in needed):
                continue
        if summary["attempted"] >= batch_size:
            summary["status"] = "batch_limit"
            break
        resources._check_budget()
        summary["attempted"] += 1
        resources.set_setting("last_run", summary)
        try:
            resources.fetch_html(word, refresh=refresh)
            if refresh or html.get("state") != "ready":
                summary["html"] += 1
            resources.set_setting("last_run", summary)
            # Suggestion-only pages are complete HTML downloads, but fetching six
            # guessed pronunciation variants for a miss would waste the budget.
            if resources.metadata(word, "html")["exact_match"]:
                try:
                    resources.fetch_audio(word, refresh=refresh)
                    if refresh or audio.get("state") != "ready":
                        summary["audio"] += 1
                except NoAudio:
                    summary["noAudio"] += 1
            consecutive_failures = 0
        except BatchDeadline:
            raise
        except ResourceError as error:
            summary["errors"] += 1
            summary["message"] = f"{word}: {error}"
            if resources.setting("cooldown_until", 0) > resources.clock():
                summary["status"] = "cooldown"
                break
            if isinstance(error, (DikiTimeout, DikiServerError)):
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    reason = f"Three consecutive Diki response failures; last error: {error}"
                    resources._cooldown(300, reason)
                    summary.update(status="cooldown", message=reason)
                    break
            elif not isinstance(error, Deferred):
                summary["status"] = "error"
                break
        resources.set_setting("last_run", summary)
    source_errors = [f"{source.name}: {source.error}" for source in lists if source.error]
    if source_errors and summary["status"] == "running":
        summary.update(status="source_error", message="; ".join(source_errors))


def main(argv=None):
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Cache Diki HTML and MP3s for all word lists")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-runtime", type=float, default=600, help="Seconds, including request spacing")
    parser.add_argument("--words-dir", help="Folder of .txt lists (recursive); main list takes priority")
    parser.add_argument("--cache-dir", help="Shared cache directory, also configurable with DIKI_CACHE_DIR")
    parser.add_argument("--refresh", action="store_true", help="Explicitly re-fetch resources, including confirmed misses")
    parser.add_argument("--report", action="store_true", help="Print local coverage without network requests")
    args = parser.parse_args(argv)
    if args.batch_size < 1 or args.max_runtime <= 0:
        parser.error("batch-size and max-runtime must be positive")
    resources = DikiResources(args.cache_dir, deadline=time.time() + args.max_runtime)
    lists = discover_lists(args.words_dir)
    result = coverage(resources, lists) if args.report else run_batch(
        resources, lists, batch_size=args.batch_size, refresh=args.refresh)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("status") in {"error", "source_error"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
