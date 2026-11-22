#!/usr/bin/env python3
import os
import signal
import sys
from contextlib import contextmanager

# Allow importing from project root regardless of where the script is called from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rich.console import Console
from rich.padding import Padding
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from backend.settings import configured_words_to_add_path, load_environment
from backend.word_list import append_word
from external_apis.diki_api import DikiApi
from external_apis.diki_resources import DikiResources, DikiTimeout, ResourceError

console = Console()
LOOKUP_TIMEOUT = 30


@contextmanager
def lookup_timeout(seconds: float = LOOKUP_TIMEOUT):
    """CLI/main-thread wall-clock limit, including DNS, locks and trickled bodies.

    Requests' read timeout alone only bounds inactivity, not the entire lookup.
    This command already targets Unix (the resource layer uses flock).
    """

    def timed_out(signum, frame):
        raise DikiTimeout(f"Diki lookup timed out after {seconds:g}s; try again later")

    previous_handler = signal.signal(signal.SIGALRM, timed_out)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def lookup_meanings(api, phrase):
    try:
        with console.status(f"Fetching '{phrase}'…"), lookup_timeout():
            return api.get_meanings(phrase)
    except DikiTimeout as error:
        api.last_error = str(error)
        return []


def display_meanings(word, meanings):
    console.print()
    header = Table.grid(expand=True)
    header.add_column()
    header.add_column(justify="right")
    header.add_row(Text(word, style="bold cyan"), Text("DIKI · EN → PL", style="dim"))
    console.print(Padding(header, (0, 2)))
    console.print(Padding(Rule(style="dim"), (0, 2)))

    number_width = len(str(len(meanings)))
    for i, meaning in enumerate(meanings, 1):
        console.print()
        title = Text(f"{i:>{number_width}}  ", style="green")
        title.append(", ".join(meaning["translations"]), style="bold")
        console.print(Padding(title, (0, 2)))
        for example in meaning["examples"]:
            sentence = Text(example["english"])
            if example["polish"]:
                sentence.append(f" ({example['polish']})", style="dim")
            console.print(Padding(sentence, (0, 2, 0, number_width + 4)))

    console.print()
    console.print(Padding(Rule(style="dim"), (0, 2)))


def load_existing_words():
    try:
        with configured_words_to_add_path().open(encoding="utf-8-sig") as f:
            return {" ".join(line.split()) for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def ask_save(word):
    if word in load_existing_words():
        console.print(f"[yellow]'{word}' is already in words_to_add.txt[/yellow]")
        return
    try:
        answer = input(f"\nSave '{word}'? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return
    if answer == "y":
        if append_word(configured_words_to_add_path(), word):
            console.print("[green]✓[/green] Appended to words_to_add.txt")
        else:
            console.print(f"[yellow]'{word}' is already in words_to_add.txt[/yellow]")


def pick_from_list(options, prompt="Pick"):
    options = sorted(options)
    for i, opt in enumerate(options, 1):
        console.print(f"  {i}. {opt}")
    try:
        raw = input(f"\n{prompt} [1-{len(options)}/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return None
    if raw == "n" or raw == "":
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return None


def main():
    if len(sys.argv) < 2:
        console.print("[red]Usage:[/red] diki <word>")
        sys.exit(1)

    phrase = " ".join(sys.argv[1:]).strip()
    load_environment()
    with DikiResources(profile="interactive") as resources:
        return run_lookup(DikiApi(resources), phrase)


def run_lookup(api, phrase):
    try:
        with console.status(f"Fetching '{phrase}'…"), lookup_timeout():
            result = api.lookup(phrase)
    except ResourceError as error:
        console.print(f"[red]{error}[/red]")
        sys.exit(1)

    if result.meanings:
        display_meanings(result.word, result.meanings)
        ask_save(result.word)
        return

    # No exact match — look for similar words
    spellings = set(result.suggestions)
    spellings.discard(phrase)

    if not spellings:
        console.print(f"[red]No results found for '{phrase}'.[/red]")
        sys.exit(1)

    console.print("\n[yellow]No exact match.[/yellow] Did you mean:")
    chosen = pick_from_list(spellings)

    if chosen is None:
        return

    meanings = lookup_meanings(api, chosen)
    if api.last_error:
        console.print(f"[red]{api.last_error}[/red]")
        sys.exit(1)
    if not meanings:
        console.print(f"[red]No translations found for '{chosen}'.[/red]")
        sys.exit(1)

    display_meanings(chosen, meanings)
    ask_save(chosen)


if __name__ == "__main__":
    main()
