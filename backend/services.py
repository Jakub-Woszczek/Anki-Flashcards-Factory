import html
import re
import threading
import time
from collections import Counter
from difflib import SequenceMatcher
from typing import Any

from allNotesDb import NotesDatabase
from backend.storage import SessionStore
from external_APIs.ankiConnect import AnkiConnect
from external_APIs.dikiApi import DikiApi
from external_APIs.diki_resources import ResourceError
from external_APIs.geminiAPI import GeminiBot


SYNC_COOLDOWN_SECONDS = 10


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class FactoryService:
    def __init__(self):
        self.sessions = SessionStore()
        self.notes = NotesDatabase()
        self.diki = DikiApi()
        self.anki = AnkiConnect()
        self.gemini = GeminiBot()
        self._sync_lock = threading.Lock()
        self._sync_dirty = False
        self._last_sync_at: float | None = None
        self._sync_error: str | None = None

    def _ensure_sync_state(self):
        # Some focused tests construct the service without __init__.
        if not hasattr(self, "_sync_lock"):
            self._sync_lock = threading.Lock()
            self._sync_dirty = False
            self._last_sync_at = None
            self._sync_error = None

    def _sync_now(self) -> float:
        clock = getattr(self, "_sync_clock", time.monotonic)
        return clock()

    def _sync_locked(self) -> dict[str, Any]:
        synced = self.anki.sync()
        self._last_sync_at = self._sync_now()
        if synced:
            self._sync_dirty = False
            self._sync_error = None
            return {"synced": True, "syncPending": False}

        self._sync_error = self.anki.last_error or "Anki could not synchronize with AnkiWeb"
        return {"synced": False, "syncPending": True, "syncWarning": self._sync_error}

    def _sync_after_mutation(self) -> dict[str, Any]:
        """Sync at most once per cooldown window after successful Anki changes."""
        self._ensure_sync_state()
        with self._sync_lock:
            self._sync_dirty = True
            if self._last_sync_at is not None and self._sync_now() - self._last_sync_at < SYNC_COOLDOWN_SECONDS:
                result: dict[str, Any] = {"synced": False, "syncPending": True}
                if self._sync_error:
                    result["syncWarning"] = self._sync_error
                return result
            return self._sync_locked()

    def flush_sync(self) -> dict[str, Any]:
        """Synchronize pending changes immediately, including during shutdown."""
        self._ensure_sync_state()
        with self._sync_lock:
            if not self._sync_dirty:
                return {"synced": False, "syncPending": False}
            return self._sync_locked()

    @staticmethod
    def _translation_groups(translations: list[list[str]]) -> list[list[dict[str, Any]]]:
        groups = []
        for group in translations:
            items = [
                {"original": translation, "value": translation, "selected": False}
                for translation in group
            ]
            items.append({"original": "<br>", "value": "<br>", "selected": False, "isBreak": True})
            groups.append(items)
        return groups

    @staticmethod
    def _normalize_word(word: str) -> str:
        return NotesDatabase.normalize_word(word)

    @staticmethod
    def _normalize_anki_field_value(value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html.unescape(value))
        return " ".join(text.replace("\xa0", " ").split()).lower()

    @staticmethod
    def _draft_word(draft: dict[str, Any], current: dict[str, Any]) -> str:
        word = draft.get("word") or current.get("word")
        if not isinstance(word, str) or not word.strip():
            raise ServiceError("The current word is missing")
        return " ".join(word.split()).lower()

    @staticmethod
    def _selected_translation_groups(draft: dict[str, Any]) -> list[list[str]]:
        groups = draft.get("groups", [])
        if not isinstance(groups, list):
            raise ServiceError("Translation groups must be a list")

        selected = []
        for group in groups:
            if not isinstance(group, list):
                continue
            values = []
            for translation in group:
                if not isinstance(translation, dict) or not translation.get("selected"):
                    continue
                value = translation.get("value")
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
            if values:
                selected.append(values)
        return selected

    @staticmethod
    def translation_html(selected_groups: list[list[str]]) -> str:
        output = ""
        previous_wants_break = False
        for group in selected_groups:
            wants_break = "<br>" in group
            values = [value for value in group if value != "<br>"]
            if not values:
                continue
            if output:
                output += "<br>\n" if previous_wants_break else ", "
            output += ", ".join(html.escape(value) for value in values)
            previous_wants_break = wants_break
        return output

    @staticmethod
    def _audio_filename(word: str) -> str:
        safe_word = re.sub(r'[<>:"/\\|?*\0]', "", word)
        return f"{safe_word}.mp3"

    def create_add_session(self, words: list[str], source: str, name: str | None = None):
        if not any(word.strip() for word in words):
            raise ServiceError("Import at least one non-empty word")
        return self.sessions.create_add_session(words, source, name)

    def _find_existing_note_id(self, word: str, session: dict[str, Any]) -> int | None:
        indexed_note_id = self.notes.get_note_id(word)
        if indexed_note_id:
            note = self.anki.get_note(indexed_note_id)
            if note:
                return indexed_note_id
            if self.anki.last_error:
                # Keep an index hit usable when Anki is temporarily unavailable.
                return indexed_note_id

        mapping = session.get("fieldMapping", {})
        english_field = mapping.get("englishField")
        if not isinstance(english_field, str) or not english_field:
            return None

        candidate_ids = self.anki.find_notes_by_field(english_field, word)
        if self.anki.last_error:
            return None
        normalized_word = self._normalize_word(word)
        for note in self.anki.notes_info(candidate_ids):
            field = note.get("fields", {}).get(english_field, {})
            if self._normalize_anki_field_value(field.get("value", "")) != normalized_word:
                continue
            note_id = note.get("noteId")
            if isinstance(note_id, int) and not self.notes.is_in_db(word):
                self.notes.add_word(note_id, word)
            return note_id if isinstance(note_id, int) else None
        return None

    def session(self, session_id: str):
        try:
            return self.sessions.get_session(session_id)
        except KeyError as error:
            raise ServiceError("Session was not found", 404) from error

    def list_sessions(self):
        return self.sessions.list_sessions()

    def delete_add_session(self, session_id: str):
        session = self.session(session_id)
        if session["mode"] != "add":
            raise ServiceError("Only add-word queues can be deleted", 409)
        try:
            self.sessions.delete_session(session_id)
        except KeyError as error:
            raise ServiceError("Session was not found", 404) from error

    @staticmethod
    def _duplicate_note_id(session: dict[str, Any]) -> int:
        current = session["current"]
        draft = session["draft"] or {}
        note_id = current.get("noteId") or draft.get("existingNoteId")
        if not isinstance(note_id, int):
            raise ServiceError("No duplicate Anki note is associated with this word", 404)
        return note_id

    def suspend_duplicate_note(self, session_id: str):
        session = self.session(session_id)
        if session["mode"] != "add" or not session["current"]:
            raise ServiceError("This queue item is not available", 409)
        note_id = self._duplicate_note_id(session)
        self.anki.suspend_note_cards(note_id)
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)
        result = {
            "action": "suspended duplicate",
            "noteId": note_id,
            "session": self.sessions.complete_current(session_id),
        }
        result.update(self._sync_after_mutation())
        return result

    def delete_duplicate_note(self, session_id: str):
        session = self.session(session_id)
        if session["mode"] != "add" or not session["current"]:
            raise ServiceError("This queue item is not available", 409)
        note_id = self._duplicate_note_id(session)
        self.anki.delete_note(note_id)
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)

        current_word = session["current"].get("word") or (session["draft"] or {}).get("word")
        if isinstance(current_word, str) and self.notes.get_note_id(current_word) == note_id:
            self.notes.delete_word(current_word)
        draft = {**(session["draft"] or {}), "existingNoteId": None}
        result = {
            "action": "deleted duplicate",
            "noteId": note_id,
            "session": self.sessions.replace_current_draft(session_id, draft),
        }
        result.update(self._sync_after_mutation())
        return result

    def update_session(self, session_id: str, **values):
        try:
            return self.sessions.update_session(session_id, **values)
        except KeyError as error:
            raise ServiceError("Session was not found", 404) from error

    def replace_add_queue(self, session_id: str, words: list[str]):
        try:
            return self.sessions.replace_add_queue(session_id, words)
        except KeyError as error:
            raise ServiceError("Session was not found", 404) from error
        except ValueError as error:
            raise ServiceError(str(error), 409) from error

    def queue_diff(self, session_id: str, words: list[str]):
        session = self.session(session_id)
        if session["mode"] != "add":
            raise ServiceError("Only add-word queues can be edited", 409)

        saved_words = [item["word"] for item in session["queue"] if item["word"]]
        proposed_words = [word.strip() for word in words if word.strip()]
        matcher = SequenceMatcher(None, saved_words, proposed_words, autojunk=False)
        hunks = []
        for group in matcher.get_grouped_opcodes(n=0):
            saved_start = group[0][1]
            saved_end = group[-1][2]
            proposed_start = group[0][3]
            proposed_end = group[-1][4]
            lines = []
            for tag, old_start, old_end, new_start, new_end in group:
                if tag == "equal":
                    lines.extend(
                        {"kind": "context", "saved": word, "proposed": word}
                        for word in saved_words[old_start:old_end]
                    )
                elif tag == "delete":
                    lines.extend(
                        {"kind": "remove", "saved": word, "proposed": None}
                        for word in saved_words[old_start:old_end]
                    )
                elif tag == "insert":
                    lines.extend(
                        {"kind": "add", "saved": None, "proposed": word}
                        for word in proposed_words[new_start:new_end]
                    )
                else:
                    old_words = saved_words[old_start:old_end]
                    new_words = proposed_words[new_start:new_end]
                    lines.extend(
                        {
                            "kind": "change",
                            "saved": old_words[index] if index < len(old_words) else None,
                            "proposed": new_words[index] if index < len(new_words) else None,
                        }
                        for index in range(max(len(old_words), len(new_words)))
                    )
            hunks.append(
                {
                    "id": f"{saved_start}:{saved_end}:{proposed_start}:{proposed_end}",
                    "savedStart": saved_start,
                    "savedEnd": saved_end,
                    "proposedStart": proposed_start,
                    "proposedEnd": proposed_end,
                    "lines": lines,
                }
            )
        return {"savedWords": saved_words, "proposedWords": proposed_words, "hunks": hunks}

    def lookup_current(self, session_id: str, requested_word: str | None = None):
        session = self.session(session_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)
        if session["mode"] != "add" and not requested_word:
            return self.existing_note(session_id)

        raw_word = current.get("word") or requested_word
        if not raw_word:
            raise ServiceError("Provide the English word to refresh Diki translations")
        word = self._normalize_word(requested_word or raw_word)
        existing_note_id = current.get("noteId") or self._find_existing_note_id(word, session)
        try:
            translations, suggestions = self.diki.lookup(word)
        except ResourceError as error:
            raise ServiceError(str(error), 503) from error
        draft = {
            "sourceWord": raw_word,
            "word": word,
            "groups": self._translation_groups(translations),
            "tags": [],
            "existingNoteId": existing_note_id,
        }
        self.sessions.replace_current_draft(session_id, draft)
        return {
            "word": word,
            "exactMatch": bool(translations),
            "groups": draft["groups"],
            "suggestions": suggestions,
            "existingNoteId": existing_note_id,
        }

    def update_current_draft(self, session_id: str, draft: dict[str, Any]):
        session = self.session(session_id)
        if not session["current"]:
            raise ServiceError("This session is complete", 409)
        self._draft_word(draft, session["current"])
        return self.sessions.replace_current_draft(session_id, draft)

    @staticmethod
    def _card_target(session: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
        override = draft.get("targetOverride")
        if not isinstance(override, dict):
            override = {}
        override_mapping = override.get("fieldMapping")
        return {
            "deckName": override.get("deckName") or session["deckName"],
            "modelName": override.get("modelName") or session["modelName"],
            "fieldMapping": override_mapping if isinstance(override_mapping, dict) else session["fieldMapping"],
            "isOverride": bool(override.get("deckName") or override.get("modelName")),
        }

    def _field_payload(
        self,
        session: dict[str, Any],
        draft: dict[str, Any],
        *,
        include_audio: bool = True,
    ) -> tuple[dict[str, str], str, list[str]]:
        mapping = self._card_target(session, draft)["fieldMapping"]
        english_field = mapping.get("englishField")
        translation_field = mapping.get("translationField")
        audio_field = mapping.get("audioField")
        if not english_field or not translation_field:
            raise ServiceError("Configure the English and translation fields before previewing")

        word = self._draft_word(draft, session["current"])
        selected_groups = self._selected_translation_groups(draft)
        translation_html = self.translation_html(selected_groups)
        fields = {english_field: word, translation_field: translation_html}
        additional_fields = mapping.get("additionalFields", {})
        if isinstance(additional_fields, dict):
            fields.update({key: str(value) for key, value in additional_fields.items() if value is not None})
        if audio_field:
            fields[audio_field] = f"[sound:{self._audio_filename(word)}]" if include_audio else ""
        return fields, translation_html, selected_groups

    def _validate_schema(self, target: dict[str, Any], fields: dict[str, str]):
        if not target["deckName"] or not target["modelName"]:
            raise ServiceError("Choose an Anki deck and note type before saving")
        schema = self.anki.model_schema(target["modelName"])
        if schema is None:
            raise ServiceError(self.anki.last_error or "Anki note type could not be read", 503)
        unknown_fields = set(fields) - set(schema["fields"])
        if unknown_fields:
            raise ServiceError(f"Configured fields are not in model {target['modelName']}: {', '.join(sorted(unknown_fields))}")

    def preview_current(self, session_id: str):
        session = self.session(session_id)
        if not session["current"]:
            raise ServiceError("This session is complete", 409)
        draft = session["draft"]
        if not draft:
            raise ServiceError("Look up or load the current card before previewing")
        fields, translation_html, selected_groups = self._field_payload(session, draft)
        target = self._card_target(session, draft)
        return {
            "word": self._draft_word(draft, session["current"]),
            "translationHtml": translation_html,
            "selectedGroups": selected_groups,
            "fields": fields,
            "tags": draft.get("tags", []),
            "audioFile": self._audio_filename(self._draft_word(draft, session["current"])),
            "target": target,
        }

    def _note_details(self, note_id: int):
        note = self.anki.get_note(note_id)
        if not note:
            raise ServiceError(self.anki.last_error or "The indexed Anki note no longer exists", 404)
        cards = self.anki.get_note_cards(note_id)
        return {"note": note, "cards": cards}

    def existing_note(self, session_id: str):
        session = self.session(session_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)

        note_id = current.get("noteId")
        if not note_id:
            note_id = (session["draft"] or {}).get("existingNoteId")
        if not note_id and current.get("word"):
            note_id = self.notes.get_note_id(current["word"])
        if not note_id:
            raise ServiceError("No existing note is associated with this word", 404)

        details = self._note_details(note_id)
        note = details["note"]
        fields = {name: value["value"] for name, value in note.get("fields", {}).items()}
        response = {
            "noteId": note_id,
            "modelName": note.get("modelName"),
            "fields": fields,
            "tags": note.get("tags", []),
            "cards": details["cards"],
        }
        if session["draft"] and session["fieldMapping"]:
            try:
                proposed, _, _ = self._field_payload(session, session["draft"])
                response["proposedFields"] = proposed
                response["fieldDiff"] = [
                    {"field": name, "existing": fields.get(name, ""), "proposed": value, "changed": fields.get(name, "") != value}
                    for name, value in proposed.items()
                ]
            except ServiceError:
                pass
        return response

    def _write_audio(self, word: str) -> bool:
        self.diki.last_error = None
        try:
            content = self.diki.fetch_audio(word)
            result = self.anki.store_media_file(self._audio_filename(word), content)
            if result is None:
                self.diki.last_error = self.anki.last_error or "Anki could not store the downloaded audio"
                return False
            return True
        except (ResourceError, AssertionError, OSError) as error:
            self.diki.last_error = f"Could not prepare Diki audio: {error}"
            return False

    def _perform_commit(
        self,
        target: dict[str, Any],
        fields: dict[str, str],
        tags: list[str],
        remove_tags: list[str],
        action: str,
        existing_note_id: int | None,
        word: str,
        flag: int | None,
        card_id: int | None,
    ) -> dict[str, Any]:
        audio_downloaded = self._write_audio(word)
        audio_field = target["fieldMapping"].get("audioField")
        if not audio_downloaded:
            if audio_field:
                fields[audio_field] = ""
            if "noAudio" not in tags:
                tags.append("noAudio")
        else:
            tags = [tag for tag in tags if tag != "noAudio"]
            remove_tags = [*remove_tags, "noAudio"]

        if action == "create":
            if existing_note_id:
                raise ServiceError("This word already has an indexed note. Review and update it instead.", 409)
            note_id = self.anki.add_note(target["deckName"], target["modelName"], fields, tags)
            if note_id is None:
                raise ServiceError(self.anki.last_error or "Anki rejected the new note", 409)
            self.notes.add_word(note_id, word)
            result = {"action": "created", "noteId": note_id, "audioDownloaded": audio_downloaded}
        else:
            if not existing_note_id:
                raise ServiceError("There is no existing note to update", 404)
            existing = self._note_details(existing_note_id)["note"]
            if existing.get("modelName") != target["modelName"]:
                raise ServiceError("Select the existing note type before updating this learned card", 409)
            if not audio_downloaded and audio_field:
                previous_audio = existing.get("fields", {}).get(audio_field, {}).get("value", "")
                if previous_audio:
                    fields.pop(audio_field, None)
                    tags = [tag for tag in tags if tag != "noAudio"]
                    remove_tags = [tag for tag in remove_tags if tag != "noAudio"]
            english_field = target["fieldMapping"].get("englishField")
            update_fields = {name: value for name, value in fields.items() if name != english_field}
            self.anki.update_note_fields(existing_note_id, update_fields)
            if self.anki.last_error:
                raise ServiceError(self.anki.last_error, 503)
            existing_tags = set(existing.get("tags", []))
            for tag in sorted(set(tags) - existing_tags):
                self.anki.add_tag_to_note(existing_note_id, tag)
                if self.anki.last_error:
                    raise ServiceError(self.anki.last_error, 503)
            for tag in sorted(set(remove_tags) & existing_tags):
                self.anki.remove_tag_from_note(existing_note_id, tag)
                if self.anki.last_error:
                    raise ServiceError(self.anki.last_error, 503)
            self.anki.change_note_deck(existing_note_id, target["deckName"])
            if self.anki.last_error:
                raise ServiceError(self.anki.last_error, 503)
            if not self.notes.is_in_db(word):
                self.notes.add_word(existing_note_id, word)
            result = {"action": "updated", "noteId": existing_note_id, "audioDownloaded": audio_downloaded}

        if flag is not None and action == "create" and not card_id:
            self.anki.set_note_cards_flag(note_id, flag)
            if self.anki.last_error:
                result["flagWarning"] = self.anki.last_error
        elif flag is not None and card_id:
            self.anki.set_card_flag(card_id, flag)
            if self.anki.last_error:
                result["flagWarning"] = self.anki.last_error

        if not audio_downloaded:
            result["audioError"] = self.diki.last_error or "Diki audio could not be downloaded"
        result.update(self._sync_after_mutation())
        return result

    def commit_current(self, session_id: str, action: str, remove_tags: list[str], flag: int | None):
        session = self.session(session_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)
        draft = session["draft"]
        if not draft:
            raise ServiceError("Load and configure the current card before saving")

        target = self._card_target(session, draft)
        fields, _, _ = self._field_payload(session, draft)
        self._validate_schema(target, fields)
        word = self._draft_word(draft, current)
        tags = [tag.strip() for tag in draft.get("tags", []) if isinstance(tag, str) and tag.strip()]
        existing_note_id = current.get("noteId") or draft.get("existingNoteId") or self.notes.get_note_id(word)

        result = self._perform_commit(
            target, fields, tags, remove_tags, action, existing_note_id, word, flag, current.get("cardId")
        )
        result["session"] = self.sessions.complete_current(session_id)
        return result

    def skip_current(self, session_id: str):
        return self.sessions.complete_current(session_id)

    def create_custom_card(
        self,
        session_id: str,
        deck_name: str,
        model_name: str,
        fields: dict[str, str],
    ):
        session = self.session(session_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)
        if session["mode"] != "add":
            raise ServiceError("Custom cards can only be created from an add queue", 409)

        schema = self.anki.model_schema(model_name)
        if schema is None:
            raise ServiceError(self.anki.last_error or "Anki note type could not be read", 503)
        unknown_fields = set(fields) - set(schema["fields"])
        if unknown_fields:
            raise ServiceError(f"Fields are not in model {model_name}: {', '.join(sorted(unknown_fields))}")
        note_fields = {field: str(fields.get(field, "")) for field in schema["fields"]}
        note_id = self.anki.add_note(deck_name, model_name, note_fields)
        if note_id is None:
            raise ServiceError(self.anki.last_error or "Anki rejected the custom note", 409)

        queue_word = current.get("word") or (session["draft"] or {}).get("word")
        if isinstance(queue_word, str) and queue_word.strip() and not self.notes.is_in_db(queue_word):
            self.notes.add_word(note_id, queue_word)
        result = {
            "action": "created custom card",
            "noteId": note_id,
            "session": self.sessions.complete_current(session_id),
        }
        result.update(self._sync_after_mutation())
        return result

    def status(self):
        self._ensure_sync_state()
        return {
            "ankiAvailable": self.anki.is_available(),
            "ankiError": self.anki.last_error,
            "geminiConfigured": bool(self.gemini.client),
            "databasePath": str(self.notes.db_path),
            "syncPending": self._sync_dirty,
            "syncError": self._sync_error,
        }

    def decks(self):
        decks = self.anki.deck_names()
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)
        return decks

    def deck_context(self, deck_name: str):
        model_counts = self.anki.deck_model_counts(deck_name)
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)
        return {
            "deckName": deck_name,
            "models": [item["name"] for item in model_counts],
            "modelCounts": model_counts,
        }

    def deck_tree(self):
        deck_names = self.anki.deck_names()
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)

        roots: list[dict[str, Any]] = []
        children_by_path: dict[str, list[dict[str, Any]]] = {"": roots}
        for deck_name in sorted(deck_names):
            path = ""
            for part in deck_name.split("::"):
                path = f"{path}::{part}" if path else part
                if path not in children_by_path:
                    node = {"name": part, "fullName": path, "children": []}
                    children_by_path.setdefault(path.rsplit("::", 1)[0] if "::" in path else "", []).append(node)
                    children_by_path[path] = node["children"]
        return roots

    def models(self):
        models = self.anki.model_names()
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)
        return models

    def model_schema(self, model_name: str):
        schema = self.anki.model_schema(model_name)
        if schema is None:
            raise ServiceError(self.anki.last_error or "Unable to load the note type", 503)
        return schema

    def gemini_translation(self, word: str, diki_translations: list[list[str]]):
        return {"text": self.gemini.get_word_translation(word, diki_translations)}

    def gemini_review(self, word: str, current_translation: str, proposed_translations: list[list[str]]):
        proposed = "; ".join(", ".join(group) for group in proposed_translations if group
        )
        question = (
            "Dla angielskiego slowa ponizej porownaj polskie tlumaczenia. "
            "Krotko wyjasnij, ktore sa najlepsze i czy cos jest bledne. "
            f"Slowo: {word}\nObecna fiszka: {current_translation}\nPropozycje: {proposed}"
        )
        return {"text": self.gemini.get_answer(question)}

    @staticmethod
    def _deck_query(deck_name: str | None) -> str:
        return f'deck:"{deck_name}"' if deck_name else ""

    def review_inventory(self, deck_name: str | None):
        query = self._deck_query(deck_name)
        card_ids = self.anki.invoke("findCards", query=query) or []
        cards = self.anki.cards_info(card_ids)
        note_ids = sorted({card.get("note") for card in cards if card.get("note")})
        notes = self.anki.notes_info(note_ids)
        tags = Counter(tag for note in notes for tag in note.get("tags", []))
        flags = []
        for flag in range(1, 8):
            flag_query = f"{query} flag:{flag}".strip()
            count = len(self.anki.invoke("findCards", query=flag_query) or [])
            if count:
                flags.append({"value": flag, "count": count})
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)
        return {
            "tags": [{"value": tag, "count": count} for tag, count in sorted(tags.items())],
            "flags": flags,
        }

    def review_snapshot(self, kind: str, value: str | int, deck_name: str | None):
        """A one-off, unsaved list of notes/cards matching a tag or flag filter.

        Unlike an add queue, this is never persisted: it's a live snapshot of
        current Anki state, walked entirely in the browser.
        """
        query = self._deck_query(deck_name)
        if kind == "tag":
            tag = str(value)
            query = f'{query} tag:"{tag}"'.strip()
            note_ids = self.anki.invoke("findNotes", query=query) or []
            items = [{"noteId": note_id, "cardId": None} for note_id in note_ids]
        else:
            flag = int(value)
            query = f"{query} flag:{flag}".strip()
            card_ids = self.anki.invoke("findCards", query=query) or []
            cards = self.anki.cards_info(card_ids)
            items = [
                {"noteId": card.get("note"), "cardId": card.get("cardId")}
                for card in cards
                if card.get("note") and card.get("cardId")
            ]
        if self.anki.last_error:
            raise ServiceError(self.anki.last_error, 503)
        if not items:
            raise ServiceError("No Anki cards matched this review filter", 404)
        return {"items": items, "filter": {"kind": kind, "value": value, "deckName": deck_name}}

    def review_item_lookup(self, word: str, field_mapping: dict[str, Any]):
        normalized = self._normalize_word(word)
        pseudo_session = {"fieldMapping": field_mapping}
        existing_note_id = self._find_existing_note_id(normalized, pseudo_session)
        try:
            translations, suggestions = self.diki.lookup(normalized)
        except ResourceError as error:
            raise ServiceError(str(error), 503) from error
        return {
            "word": normalized,
            "exactMatch": bool(translations),
            "groups": self._translation_groups(translations),
            "suggestions": suggestions,
            "existingNoteId": existing_note_id,
        }

    def review_item_existing_note(
        self, note_id: int, draft: dict[str, Any] | None, field_mapping: dict[str, Any] | None
    ):
        details = self._note_details(note_id)
        note = details["note"]
        fields = {name: value["value"] for name, value in note.get("fields", {}).items()}
        response = {
            "noteId": note_id,
            "modelName": note.get("modelName"),
            "fields": fields,
            "tags": note.get("tags", []),
            "cards": details["cards"],
        }
        if draft and field_mapping:
            pseudo_session = {"deckName": None, "modelName": None, "fieldMapping": field_mapping, "current": {}}
            try:
                proposed, _, _ = self._field_payload(pseudo_session, draft)
                response["proposedFields"] = proposed
                response["fieldDiff"] = [
                    {"field": name, "existing": fields.get(name, ""), "proposed": value, "changed": fields.get(name, "") != value}
                    for name, value in proposed.items()
                ]
            except ServiceError:
                pass
        return response

    def review_item_preview(
        self, draft: dict[str, Any], deck_name: str | None, model_name: str | None, field_mapping: dict[str, Any]
    ):
        pseudo_session = {"deckName": deck_name, "modelName": model_name, "fieldMapping": field_mapping, "current": {}}
        fields, translation_html, selected_groups = self._field_payload(pseudo_session, draft)
        target = self._card_target(pseudo_session, draft)
        word = self._draft_word(draft, pseudo_session["current"])
        return {
            "word": word,
            "translationHtml": translation_html,
            "selectedGroups": selected_groups,
            "fields": fields,
            "tags": draft.get("tags", []),
            "audioFile": self._audio_filename(word),
            "target": target,
        }

    def review_item_commit(
        self,
        note_id: int | None,
        card_id: int | None,
        draft: dict[str, Any],
        action: str,
        remove_tags: list[str],
        flag: int | None,
        deck_name: str | None,
        model_name: str | None,
        field_mapping: dict[str, Any],
    ):
        pseudo_session = {"deckName": deck_name, "modelName": model_name, "fieldMapping": field_mapping, "current": {}}
        target = self._card_target(pseudo_session, draft)
        fields, _, _ = self._field_payload(pseudo_session, draft)
        self._validate_schema(target, fields)
        word = self._draft_word(draft, pseudo_session["current"])
        tags = [tag.strip() for tag in draft.get("tags", []) if isinstance(tag, str) and tag.strip()]
        existing_note_id = note_id or draft.get("existingNoteId") or self.notes.get_note_id(word)
        return self._perform_commit(target, fields, tags, remove_tags, action, existing_note_id, word, flag, card_id)
