#!/usr/bin/env python3
import sys
import os

# Allow importing from project root regardless of where the script is called from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from external_APIs.dikiApi import DikiApi
from rich.console import Console
from rich.padding import Padding
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

WORDS_FILE = os.path.join(os.path.dirname(__file__), "..", "words_to_add", "words_to_add.txt")

console = Console()


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

    meanings = api.get_meanings(phrase)

    if meanings:
        display_meanings(phrase, meanings)
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

    meanings = api.get_meanings(chosen)
    if not meanings:
        console.print(f"[red]No translations found for '{chosen}'.[/red]")
        sys.exit(1)

    display_meanings(chosen, meanings)
    ask_save(chosen)


if __name__ == "__main__":
    main()
