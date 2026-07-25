#!/usr/bin/env python3
import sys
import os

# Allow importing from project root regardless of where the script is called from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from external_APIs.dikiApi import DikiApi
from rich.console import Console
from rich.rule import Rule

WORDS_FILE = os.path.join(os.path.dirname(__file__), "..", "words_to_add.txt")

console = Console()


def display_translations(word, translations):
    console.print(f"\n[bold]{word}[/bold]")
    console.print(Rule(style="dim"))
    for i, synonyms in enumerate(translations, 1):
        console.print(f"  {i}. {', '.join(synonyms)}")


def load_existing_words():
    try:
        with open(WORDS_FILE, "r") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def ask_save(word):
    if word.lower() in load_existing_words():
        console.print(f"[yellow]'{word}' is already in words_to_add.txt[/yellow]")
        return
    try:
        answer = input(f"\nSave '{word}'? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return
    if answer == "y":
        with open(WORDS_FILE, "a") as f:
            f.write(f"{word}\n")
        console.print(f"[green]✓[/green] Appended to words_to_add.txt")


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

    phrase = " ".join(sys.argv[1:]).strip().lower()
    api = DikiApi()

    translations = api.get_translations(phrase)

    if translations:
        display_translations(phrase, translations)
        ask_save(phrase)
        return

    # No exact match — look for similar words
    spellings = api.possible_spellings(phrase)
    spellings.discard(phrase)

    if not spellings:
        console.print(f"[red]No results found for '{phrase}'.[/red]")
        sys.exit(1)

    console.print(f"\n[yellow]No exact match.[/yellow] Did you mean:")
    chosen = pick_from_list(spellings)

    if chosen is None:
        return

    translations = api.get_translations(chosen)
    if not translations:
        console.print(f"[red]No translations found for '{chosen}'.[/red]")
        sys.exit(1)

    display_translations(chosen, translations)
    ask_save(chosen)


if __name__ == "__main__":
    main()
