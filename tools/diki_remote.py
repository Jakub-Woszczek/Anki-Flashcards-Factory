"""Submit missing words, pull completed downloads, or inspect the remote worker."""

import argparse
import json
import os

from backend.settings import load_environment
from external_apis.diki_lists import discover_lists
from external_apis.diki_remote import RemoteDownloads, RemoteError
from external_apis.diki_resources import DikiResources, normalize_word


def main(argv=None):
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=os.getenv("DIKI_REMOTE_URL", ""))
    parser.add_argument("--cache-dir")
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser(
        "submit", help="Submit missing words; parse cached HTML locally for audio-only jobs"
    )
    submit.add_argument("words", nargs="*")
    submit.add_argument("--words-dir")
    submit.add_argument(
        "--redownload-delivered",
        action="store_true",
        help="Explicitly requeue previously delivered words that are missing locally",
    )
    submit.add_argument(
        "--retry-failed",
        action="store_true",
        help="Explicitly retry words that reached the server's attempt limit",
    )
    pull = commands.add_parser(
        "pull", help="Download, validate, import, and then acknowledge deletion"
    )
    pull.add_argument("--max-batches", type=int, default=100)
    commands.add_parser("status")
    args = parser.parse_args(argv)
    client = None
    try:
        client = RemoteDownloads(args.url, os.getenv("DIKI_REMOTE_TOKEN", ""))
        if args.command == "status":
            result = client.status()
        else:
            # These commands never contact Diki or fall back to local downloading.
            with DikiResources(args.cache_dir, offline=True) as resources:
                if args.command == "pull":
                    result = client.pull(resources, max_batches=args.max_batches)
                else:
                    if args.words:
                        words = [normalize_word(word) for word in args.words]
                    else:
                        lists = discover_lists(args.words_dir)
                        if any(source.error for source in lists):
                            raise RemoteError(
                                "A word list could not be read; fix it before submitting"
                            )
                        words = [word for source in lists for word in source.words]
                    result = client.submit(
                        words,
                        resources,
                        redownload=args.redownload_delivered,
                        retry_failed=args.retry_failed,
                    )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (RemoteError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
