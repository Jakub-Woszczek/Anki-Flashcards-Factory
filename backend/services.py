import hashlib
import html
import json
import re
import sqlite3
import threading
import time
from collections import Counter
from functools import wraps
from typing import TYPE_CHECKING, Any

from backend.note_index import NotesDatabase
from backend.storage import SessionStore, SourceChanged
from backend.word_completion import VerificationError, WordCompletion
from external_apis.anki_connect import AnkiConnect
from external_apis.diki_api import DikiApi
from external_apis.diki_entries import MatchingHeadword
from external_apis.diki_resources import ResourceError
from external_apis.gemini_api import GeminiBot

if TYPE_CHECKING:
    from backend.remote_preparation import RemotePreparation

SYNC_COOLDOWN_SECONDS = 10


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def source_action(method):
    @wraps(method)
    def guarded(self, session_id, *args, entry_id=None, **kwargs):
        try:
            with self.sessions.lock():
                self.sessions.require_current(session_id, entry_id)
                return method(self, session_id, *args, entry_id=entry_id, **kwargs)
        except KeyError as error:
            raise ServiceError("Source workspace was not found", 404) from error
        except SourceChanged as error:
            raise ServiceError(str(error), 409) from error
        except (OSError, UnicodeError, sqlite3.Error) as error:
            raise ServiceError(
                f"Source operation failed; reload before continuing. {error}", 503
            ) from error

    return guarded


class FactoryService:
    def __init__(self):
        self.sessions = SessionStore()
        self.notes = NotesDatabase()
        self.completions = WordCompletion()
        self.diki = DikiApi()
        self.anki = AnkiConnect()
        self.gemini = GeminiBot()
        self._sync_lock = threading.Lock()
        self._sync_dirty = False
        self._last_sync_at: float | None = None
        self._sync_error: str | None = None
        self.remote_preparation: RemotePreparation | None = None

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
            if (
                self._last_sync_at is not None
                and self._sync_now() - self._last_sync_at < SYNC_COOLDOWN_SECONDS
            ):
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
        return " ".join(text.replace("\xa0", " ").split())

    @staticmethod
    def _draft_word(draft: dict[str, Any], current: dict[str, Any]) -> str:
        word = draft.get("resolvedWord") or draft.get("word") or current.get("word")
        if not isinstance(word, str) or not word.strip():
            raise ServiceError("The current word is missing")
        return " ".join(word.split())

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
        # Anki media on the owner's Mac can be case-insensitive (Polish/polish).
        if word != word.lower():
            safe_word += "-" + hashlib.sha256(word.encode()).hexdigest()[:12]
        return f"{safe_word}.mp3"

    def _find_existing_note_id(
        self,
        word: str,
        session: dict[str, Any],
        *,
        case_sensitive: bool = False,
        matching_headwords=None,
    ) -> int | None:
        if matching_headwords:
            for headword in matching_headwords:
                note_id = self._find_existing_note_id(
                    headword["word"], session, case_sensitive=headword["caseSensitive"]
                )
                if self.anki.last_error:
                    raise ServiceError(
                        f"Could not check existing Anki notes: {self.anki.last_error}", 503
                    )
                if note_id is not None:
                    return note_id
            return None
        indexed_note_id = self.notes.get_note_id(word)
        mapping = session.get("fieldMapping", {})
        english_field = mapping.get("englishField")
        if not isinstance(english_field, str) or not english_field:
            return None

        candidate_ids = self.anki.find_notes_by_field(english_field, word)
        if self.anki.last_error:
            return None
        normalized_word = self._normalize_word(word)
        if isinstance(indexed_note_id, int) and indexed_note_id not in candidate_ids:
            candidate_ids = [*candidate_ids, indexed_note_id]
        matches = []
        for note in self.anki.notes_info(candidate_ids):
            field = note.get("fields", {}).get(english_field, {})
            value = self._normalize_anki_field_value(field.get("value", ""))
            if self._normalize_word(value) != normalized_word:
                continue
            matches.append((value, note))
        if self.anki.last_error:
            return None
        exact = [note for value, note in matches if value == word]
        candidates = exact or (
            [note for _, note in matches]
            if not case_sensitive and len({value for value, _ in matches}) == 1
            else []
        )
        if not candidates:
            return None
        note_id = candidates[0].get("noteId")
        stored_word = self._normalize_anki_field_value(
            candidates[0].get("fields", {}).get(english_field, {}).get("value", "")
        )
        if isinstance(note_id, int) and not self.notes.is_in_db(stored_word):
            self.notes.add_word(note_id, stored_word)
        return note_id if isinstance(note_id, int) else None

    def session(self, session_id: str):
        try:
            session = self.sessions.get_session(session_id)
            if getattr(self, "completions", None) and session.get("current"):
                save = self.completions.completed_for_entry(session_id, session["current"]["id"])
                if save:
                    session["pendingRemoval"] = self._source_save_result(save)
            return session
        except KeyError as error:
            raise ServiceError("Session was not found", 404) from error
        except SourceChanged as error:
            raise ServiceError(str(error), 409) from error
        except (OSError, UnicodeError) as error:
            raise ServiceError(f"Could not read source file: {error}", 503) from error

    def list_sessions(self):
        return self.sessions.list_sessions()

    def update_session(self, session_id: str, **values):
        try:
            return self.sessions.update_session(session_id, **values)
        except KeyError as error:
            raise ServiceError("Session was not found", 404) from error
        except SourceChanged as error:
            raise ServiceError(str(error), 409) from error
        except (OSError, UnicodeError) as error:
            raise ServiceError(f"Could not read source file: {error}", 503) from error

    @source_action
    def lookup_current(
        self,
        session_id: str,
        requested_word: str | None = None,
        *,
        entry_id: str | None = None,
        headword: str | None = None,
        preserve_draft: bool = False,
    ):
        session = self.sessions.require_current(session_id, entry_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)
        if session["mode"] != "add" and not requested_word:
            return self.existing_note(session_id)

        raw_word = current.get("word") or requested_word
        if not raw_word:
            raise ServiceError("Provide the English word to refresh Diki translations")
        query = " ".join((requested_word or raw_word).split())
        previous = session.get("draft") or {}
        if preserve_draft and previous.get("resolvedWord"):
            query = previous.get("lookupQuery") or previous["resolvedWord"]
            headword = previous["resolvedWord"]
        try:
            result = (
                self.diki.lookup(query, headword=headword)
                if headword is not None
                else self.diki.lookup(query)
            )
        except ResourceError as error:
            raise ServiceError(str(error), 503) from error
        word = result.word or query
        existing_note_id = current.get("noteId") or (
            self._find_existing_note_id(
                word,
                self._card_target(session, previous) if preserve_draft else session,
                case_sensitive=result.case_sensitive,
                matching_headwords=result.matching_headwords,
            )
            if result.word
            else None
        )
        draft = {
            **(previous if preserve_draft else {}),
            "entryId": current["id"],
            "sourceWord": raw_word,
            "word": word,
            "resolvedWord": result.word,
            "lookupQuery": query,
            "caseSensitive": result.case_sensitive,
            "matchingHeadwords": result.matching_headwords,
            "groups": previous.get("groups", [])
            if preserve_draft
            else self._translation_groups(result.translations),
            "tags": previous.get("tags", []) if preserve_draft else [],
            "existingNoteId": existing_note_id,
        }
        self.sessions.replace_current_draft(session_id, draft, current["id"])
        return {
            "entryId": current["id"],
            "sourceWord": raw_word,
            "word": word,
            "resolvedWord": result.word,
            "caseSensitive": result.case_sensitive,
            "exactMatch": bool(result.meanings),
            "groups": draft["groups"],
            "suggestions": result.suggestions,
            **self._lookup_classification(result, query),
            "existingNoteId": existing_note_id,
            "draft": draft if preserve_draft else None,
        }

    @staticmethod
    def _lookup_classification(result, query):
        return {
            "lookupQuery": query,
            "pageKind": result.page.kind if result.page else None,
            "entryChoices": result.entry_choices,
            "relatedEntries": result.related_entries,
            "matchingHeadwords": result.matching_headwords,
        }

    @source_action
    def update_current_draft(
        self, session_id: str, draft: dict[str, Any], *, entry_id: str | None = None
    ):
        session = self.sessions.require_current(session_id, entry_id)
        if not session["current"]:
            raise ServiceError("This session is complete", 409)
        self._draft_word(draft, session["current"])
        draft = {
            **draft,
            "entryId": session["current"]["id"],
            "sourceWord": session["current"]["word"],
        }
        previous = session.get("draft") or {}
        if previous.get("resolvedWord"):
            for key in (
                "word",
                "resolvedWord",
                "lookupQuery",
                "caseSensitive",
                "matchingHeadwords",
                "existingNoteId",
            ):
                draft[key] = previous.get(key)
        return self.sessions.replace_current_draft(session_id, draft, session["current"]["id"])

    @staticmethod
    def _card_target(session: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
        override = draft.get("targetOverride")
        if not isinstance(override, dict):
            override = {}
        override_mapping = override.get("fieldMapping")
        return {
            "deckName": override.get("deckName") or session["deckName"],
            "modelName": override.get("modelName") or session["modelName"],
            "fieldMapping": override_mapping
            if isinstance(override_mapping, dict)
            else session["fieldMapping"],
            "isOverride": bool(override.get("deckName") or override.get("modelName")),
        }

    def _field_payload(
        self,
        session: dict[str, Any],
        draft: dict[str, Any],
        *,
        include_audio: bool = True,
    ) -> tuple[dict[str, str], str, list[list[str]]]:
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
            fields.update(
                {key: str(value) for key, value in additional_fields.items() if value is not None}
            )
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
            raise ServiceError(
                f"Configured fields are not in model {target['modelName']}: {', '.join(sorted(unknown_fields))}"
            )

    @source_action
    def preview_current(self, session_id: str, *, entry_id: str | None = None):
        session = self.sessions.require_current(session_id, entry_id)
        if not session["current"]:
            raise ServiceError("This session is complete", 409)
        draft = session["draft"]
        if not draft:
            raise ServiceError("Look up or load the current card before previewing")
        fields, translation_html, selected_groups = self._field_payload(session, draft)
        target = self._card_target(session, draft)
        self._lock_preview_english(
            fields, target, session["current"].get("noteId") or draft.get("existingNoteId")
        )
        return {
            "word": self._draft_word(draft, session["current"]),
            "translationHtml": translation_html,
            "selectedGroups": selected_groups,
            "fields": fields,
            "tags": draft.get("tags", []),
            "audioFile": self._audio_filename(self._draft_word(draft, session["current"])),
            "target": target,
        }

    def _lock_preview_english(self, fields, target, note_id):
        if note_id:
            note = self.anki.get_note(note_id)
            if not note:
                raise ServiceError(
                    self.anki.last_error or "The existing note could not be read", 503
                )
            english_field = target["fieldMapping"].get("englishField")
            if english_field:
                fields[english_field] = (
                    note.get("fields", {}).get(english_field, {}).get("value", "")
                )

    def _note_details(self, note_id: int):
        note = self.anki.get_note(note_id)
        if not note:
            raise ServiceError(
                self.anki.last_error or "The indexed Anki note no longer exists", 404
            )
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
                english_field = self._card_target(session, session["draft"])["fieldMapping"].get(
                    "englishField"
                )
                if english_field:
                    proposed[english_field] = fields.get(english_field, "")
                response["proposedFields"] = proposed
                response["fieldDiff"] = [
                    {
                        "field": name,
                        "existing": fields.get(name, ""),
                        "proposed": value,
                        "changed": fields.get(name, "") != value,
                    }
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
                self.diki.last_error = (
                    self.anki.last_error or "Anki could not store the downloaded audio"
                )
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
        source_entry: dict[str, Any] | None = None,
        case_sensitive: bool = False,
        matching_headwords: list[MatchingHeadword] | None = None,
    ) -> dict[str, Any]:
        english_field = target["fieldMapping"].get("englishField")
        if (
            english_field
            and self._normalize_anki_field_value(fields.get(english_field, "")) != word
        ):
            raise ServiceError(
                "The submitted English field does not match the word; word retained", 409
            )
        intent = {
            "target": target,
            "fields": fields,
            "tags": sorted(tags),
            "removeTags": sorted(remove_tags),
            "action": action,
        }
        if matching_headwords:
            intent["matchingHeadwords"] = matching_headwords
            intent["existingNoteId"] = existing_note_id
        if source_entry is not None:
            intent["sourceEntry"] = source_entry
        try:
            with self.completions.lock():
                self._validate_source_entry(source_entry)
                profile = self.completions.profile(self.anki)
                save, resumed = self.completions.prepare(profile, word, intent, action)
                if resumed:
                    self.completions.recover(self.anki, save)
                    saved = self.completions.get(save["id"])
                    expected = json.loads(saved["expected_json"])
                    result = {
                        "saveId": save["id"],
                        "action": "created" if action == "create" else "updated",
                        "noteId": saved["note_id"],
                        "audioDownloaded": bool(
                            expected.get("fields", {}).get(target["fieldMapping"].get("audioField"))
                        ),
                        "resumed": True,
                    }
                    result.update(self.completions.finish(self.anki, save["id"]))
                    self.notes.load_db()
                    result.update(self._sync_after_mutation())
                    return result
                return self._commit_and_verify(
                    save["id"],
                    target,
                    fields,
                    tags,
                    remove_tags,
                    action,
                    existing_note_id,
                    word,
                    flag,
                    card_id,
                    source_entry,
                    case_sensitive,
                    matching_headwords,
                )
        except (VerificationError, OSError, sqlite3.Error) as error:
            raise ServiceError(f"Save not confirmed; word retained. {error}", 503) from error

    def _validate_source_entry(self, source_entry):
        if source_entry is not None:
            self.sessions.require_current(source_entry["sessionId"], source_entry["entryId"])

    def _verified_matching_headwords(self, draft) -> list[MatchingHeadword] | None:
        if not draft.get("matchingHeadwords"):
            return None
        word = self._draft_word(draft, {})
        query = draft.get("lookupQuery") or word
        try:
            # Reparse retained source: client-supplied alternatives cannot authorize an update.
            result = self.diki.lookup(query, headword=word)
        except ResourceError as error:
            raise ServiceError(f"Could not verify Diki entry identity: {error}", 503) from error
        if result.word != word or not result.meanings:
            raise ServiceError("The selected Diki entry could not be verified; word retained", 409)
        return result.matching_headwords

    def _commit_and_verify(
        self,
        save_id,
        target,
        fields,
        tags,
        remove_tags,
        action,
        existing_note_id,
        word,
        flag,
        card_id,
        source_entry,
        case_sensitive=False,
        matching_headwords=None,
    ):
        audio_downloaded = self._write_audio(word)
        english_field = target["fieldMapping"].get("englishField")
        audio_field = target["fieldMapping"].get("audioField")
        if not audio_downloaded:
            if audio_field:
                fields[audio_field] = ""
            if "noAudio" not in tags:
                tags.append("noAudio")
        else:
            tags = [tag for tag in tags if tag != "noAudio"]
            remove_tags = [*remove_tags, "noAudio"]

        self._validate_source_entry(source_entry)
        if action == "create":
            if matching_headwords:
                existing_note_id = (
                    self._find_existing_note_id(word, target, matching_headwords=matching_headwords)
                    or existing_note_id
                )
            if existing_note_id:
                raise ServiceError(
                    "This word already has an indexed note. Review and update it instead.", 409
                )
            expected = {
                "deckName": target["deckName"],
                "modelName": target["modelName"],
                "englishField": english_field,
                "fields": fields,
                "tags": tags,
                "sourceEntry": source_entry,
            }
            self.completions.expect(save_id, expected)
            note_id = self.anki.add_note(target["deckName"], target["modelName"], fields, tags)
            if type(note_id) is not int or note_id <= 0:
                raise ServiceError(self.anki.last_error or "Anki rejected the new note", 409)
            self.completions.submitted(save_id, note_id, expected, acknowledged=True)
            result = {"action": "created", "noteId": note_id, "audioDownloaded": audio_downloaded}
        else:
            if not existing_note_id:
                raise ServiceError("There is no existing note to update", 404)
            details = self._note_details(existing_note_id)
            existing = details["note"]
            if self.anki.last_error:
                raise VerificationError(self.anki.last_error)
            # Refresh content in place; the queue target only controls new notes.
            card_decks = self.completions.card_decks(details["cards"])
            if existing.get("modelName") != target["modelName"]:
                raise ServiceError(
                    "Select the existing note type before updating this learned card", 409
                )
            if not audio_downloaded and audio_field:
                previous_audio = existing.get("fields", {}).get(audio_field, {}).get("value", "")
                if previous_audio:
                    fields.pop(audio_field, None)
                    tags = [tag for tag in tags if tag != "noAudio"]
                    remove_tags = [tag for tag in remove_tags if tag != "noAudio"]
            english_field = target["fieldMapping"].get("englishField")
            update_fields = {name: value for name, value in fields.items() if name != english_field}
            expected_fields = {
                name: value["value"] for name, value in existing.get("fields", {}).items()
            }
            expected_fields.update(update_fields)
            existing_word = self._normalize_anki_field_value(expected_fields.get(english_field, ""))
            matches_word = (
                existing_word == word
                if case_sensitive
                else self._normalize_word(existing_word) == self._normalize_word(word)
            )
            if matching_headwords:
                matches_word = any(
                    existing_word == headword["word"]
                    or (
                        not headword["caseSensitive"]
                        and self._normalize_word(existing_word)
                        == self._normalize_word(headword["word"])
                    )
                    for headword in matching_headwords
                )
            if english_field and not matches_word:
                raise ServiceError(
                    "The existing note contains a different English word; word retained", 409
                )
            expected = {
                "cardDecks": card_decks,
                "modelName": target["modelName"],
                "englishField": english_field,
                "fields": expected_fields,
                "tags": tags,
                "removeTags": sorted(set(remove_tags) - set(tags)),
                "sourceEntry": source_entry,
            }
            self.completions.submitted(save_id, existing_note_id, expected)
            self._validate_source_entry(source_entry)
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
            result = {
                "action": "updated",
                "noteId": existing_note_id,
                "audioDownloaded": audio_downloaded,
            }

        result["saveId"] = save_id
        result.update(self.completions.finish(self.anki, save_id))
        self.notes.load_db()
        if flag is not None and action == "create" and not card_id:
            self.anki.set_note_cards_flag(result["noteId"], flag)
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

    def _complete_source(self, session, result):
        try:
            result["session"] = self.sessions.complete_current(
                session["id"],
                session["current"]["id"],
                reason=result["action"],
                save_id=result.get("saveId"),
            )
            result["removedLines"] = 1
            result["cleanupPending"] = False
            self._notify_remote_preparation()
        except (OSError, UnicodeError, sqlite3.Error, SourceChanged) as error:
            result.update(
                cleanupPending=True,
                cleanupWarning=(
                    f"Note {result['noteId']} was {'updated' if result['action'] == 'updated' else 'created'} "
                    f"in Anki, but its queue entry could not be removed: {error}. "
                    "Use Retry queue removal to finish."
                ),
            )
            # Keep the existing entry/draft for retry. Do not refresh/rebind it here.
            result["session"] = {
                **session,
                "pendingRemoval": {key: value for key, value in result.items() if key != "session"},
            }
        return result

    @staticmethod
    def _source_save_result(save):
        return {
            "saveId": save["id"],
            "noteId": save["note_id"],
            "action": {"create": "created", "custom": "created custom card", "update": "updated"}[
                save["reason"]
            ],
            "verified": save["state"] == "verified",
            "confirmationWarning": save["confirmation_warning"],
            "cleanupPending": True,
        }

    @source_action
    def retry_source_removal(self, session_id: str, *, entry_id: str | None = None):
        session = self.sessions.require_current(session_id, entry_id)
        save = self.completions.completed_for_entry(session_id, session["current"]["id"])
        if not save:
            raise ServiceError("There is no completed save for this source entry", 409)
        # Local-only retry: never create, read back, flag, or sync an Anki note.
        return self._complete_source(session, self._source_save_result(save))

    @source_action
    def commit_current(
        self,
        session_id: str,
        action: str,
        remove_tags: list[str],
        flag: int | None,
        *,
        entry_id: str | None = None,
    ):
        session = self.sessions.require_current(session_id, entry_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)
        if self.completions.completed_for_entry(session_id, current["id"]):
            return self.retry_source_removal(session_id, entry_id=current["id"])
        draft = session["draft"]
        if not draft:
            raise ServiceError("Load and configure the current card before saving")

        target = self._card_target(session, draft)
        fields, _, _ = self._field_payload(session, draft)
        self._validate_schema(target, fields)
        word = self._draft_word(draft, current)
        tags = [
            tag.strip() for tag in draft.get("tags", []) if isinstance(tag, str) and tag.strip()
        ]
        existing_note_id = current.get("noteId") or draft.get("existingNoteId")
        matching_headwords = self._verified_matching_headwords(draft)

        result = self._perform_commit(
            target,
            fields,
            tags,
            remove_tags,
            action,
            existing_note_id,
            word,
            flag,
            current.get("cardId"),
            {"sessionId": session_id, "entryId": current["id"], "source": session["source"]},
            bool(draft.get("caseSensitive")),
            matching_headwords,
        )
        return self._complete_source(session, result)

    @source_action
    def discard_current(self, session_id: str, *, entry_id: str | None = None):
        session = self.sessions.require_current(session_id, entry_id)
        result = self.sessions.complete_current(session_id, session["current"]["id"])
        self._notify_remote_preparation()
        return result

    def _notify_remote_preparation(self):
        preparation = getattr(self, "remote_preparation", None)
        if preparation is not None:
            preparation.notify()

    @source_action
    def create_custom_card(
        self,
        session_id: str,
        deck_name: str,
        model_name: str,
        fields: dict[str, str],
        *,
        entry_id: str | None = None,
    ):
        session = self.sessions.require_current(session_id, entry_id)
        current = session["current"]
        if not current:
            raise ServiceError("This session is complete", 409)
        if session["mode"] != "add":
            raise ServiceError("Custom cards can only be created from an add queue", 409)
        if self.completions.completed_for_entry(session_id, current["id"]):
            return self.retry_source_removal(session_id, entry_id=current["id"])

        schema = self.anki.model_schema(model_name)
        if schema is None:
            raise ServiceError(self.anki.last_error or "Anki note type could not be read", 503)
        unknown_fields = set(fields) - set(schema["fields"])
        if unknown_fields:
            raise ServiceError(
                f"Fields are not in model {model_name}: {', '.join(sorted(unknown_fields))}"
            )
        note_fields = {field: str(fields.get(field, "")) for field in schema["fields"]}
        queue_word = current.get("word") or (session["draft"] or {}).get("word")
        if not isinstance(queue_word, str) or not queue_word.strip():
            raise ServiceError("The queue word is missing")
        expected = {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": note_fields,
            "sourceEntry": {
                "sessionId": session_id,
                "entryId": current["id"],
                "source": session["source"],
            },
        }
        try:
            with self.completions.lock():
                profile = self.completions.profile(self.anki)
                save, resumed = self.completions.prepare(
                    profile,
                    queue_word,
                    {
                        **expected,
                        "sourceEntry": {
                            "sessionId": session_id,
                            "entryId": current["id"],
                            "source": session["source"],
                        },
                    },
                    "custom",
                    expected=expected,
                )
                if resumed:
                    self.completions.recover(self.anki, save)
                    note_id = self.completions.get(save["id"])["note_id"]
                else:
                    self.sessions.require_current(session_id, current["id"])
                    note_id = self.anki.add_note(deck_name, model_name, note_fields)
                    if type(note_id) is not int or note_id <= 0:
                        raise ServiceError(
                            self.anki.last_error or "Anki rejected the custom note", 409
                        )
                    self.completions.submitted(save["id"], note_id, expected, acknowledged=True)
                result = {"action": "created custom card", "noteId": note_id, "saveId": save["id"]}
                result.update(self.completions.finish(self.anki, save["id"]))
                self.notes.load_db()
        except (VerificationError, OSError, sqlite3.Error) as error:
            raise ServiceError(f"Save not confirmed; word retained. {error}", 503) from error
        result = self._complete_source(session, result)
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
                    children_by_path.setdefault(
                        path.rsplit("::", 1)[0] if "::" in path else "", []
                    ).append(node)
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

    def gemini_review(
        self, word: str, current_translation: str, proposed_translations: list[list[str]]
    ):
        proposed = "; ".join(", ".join(group) for group in proposed_translations if group)
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

    def review_item_lookup(
        self, word: str, field_mapping: dict[str, Any], *, headword: str | None = None
    ):
        query = " ".join(word.split())
        pseudo_session = {"fieldMapping": field_mapping}
        try:
            result = (
                self.diki.lookup(query, headword=headword)
                if headword is not None
                else self.diki.lookup(query)
            )
        except ResourceError as error:
            raise ServiceError(str(error), 503) from error
        existing_note_id = (
            self._find_existing_note_id(
                result.word,
                pseudo_session,
                case_sensitive=result.case_sensitive,
                matching_headwords=result.matching_headwords,
            )
            if result.word
            else None
        )
        return {
            "word": result.word or query,
            "resolvedWord": result.word,
            "caseSensitive": result.case_sensitive,
            "exactMatch": bool(result.meanings),
            "groups": self._translation_groups(result.translations),
            "suggestions": result.suggestions,
            **self._lookup_classification(result, query),
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
            pseudo_session = {
                "deckName": None,
                "modelName": None,
                "fieldMapping": field_mapping,
                "current": {},
            }
            try:
                proposed, _, _ = self._field_payload(pseudo_session, draft)
                english_field = self._card_target(pseudo_session, draft)["fieldMapping"].get(
                    "englishField"
                )
                if english_field:
                    proposed[english_field] = fields.get(english_field, "")
                response["proposedFields"] = proposed
                response["fieldDiff"] = [
                    {
                        "field": name,
                        "existing": fields.get(name, ""),
                        "proposed": value,
                        "changed": fields.get(name, "") != value,
                    }
                    for name, value in proposed.items()
                ]
            except ServiceError:
                pass
        return response

    def review_item_preview(
        self,
        draft: dict[str, Any],
        deck_name: str | None,
        model_name: str | None,
        field_mapping: dict[str, Any],
    ):
        pseudo_session = {
            "deckName": deck_name,
            "modelName": model_name,
            "fieldMapping": field_mapping,
            "current": {},
        }
        fields, translation_html, selected_groups = self._field_payload(pseudo_session, draft)
        target = self._card_target(pseudo_session, draft)
        word = self._draft_word(draft, pseudo_session["current"])
        self._lock_preview_english(fields, target, draft.get("existingNoteId"))
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
        pseudo_session = {
            "deckName": deck_name,
            "modelName": model_name,
            "fieldMapping": field_mapping,
            "current": {},
        }
        target = self._card_target(pseudo_session, draft)
        fields, _, _ = self._field_payload(pseudo_session, draft)
        self._validate_schema(target, fields)
        word = self._draft_word(draft, pseudo_session["current"])
        tags = [
            tag.strip() for tag in draft.get("tags", []) if isinstance(tag, str) and tag.strip()
        ]
        existing_note_id = note_id or draft.get("existingNoteId")
        return self._perform_commit(
            target,
            fields,
            tags,
            remove_tags,
            action,
            existing_note_id,
            word,
            flag,
            card_id,
            case_sensitive=bool(draft.get("caseSensitive")),
            matching_headwords=self._verified_matching_headwords(draft),
        )
