from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionPatchRequest(BaseModel):
    deckName: str | None = None
    modelName: str | None = None
    fieldMapping: dict[str, Any] | None = None


class SourceEntryRequest(BaseModel):
    entryId: str


class CurrentPatchRequest(SourceEntryRequest):
    draft: dict[str, Any]


class LookupRequest(SourceEntryRequest):
    word: str | None = None


class CommitRequest(SourceEntryRequest):
    action: Literal["create", "update"]
    removeTags: list[str] = Field(default_factory=list)
    flag: int | None = None


class CustomCardRequest(SourceEntryRequest):
    deckName: str
    modelName: str
    fields: dict[str, str]


class ReviewSnapshotRequest(BaseModel):
    kind: Literal["tag", "flag"]
    value: str | int
    deckName: str | None = None


class ReviewItemLookupRequest(BaseModel):
    word: str
    fieldMapping: dict[str, Any] = Field(default_factory=dict)


class ReviewItemExistingNoteRequest(BaseModel):
    noteId: int
    draft: dict[str, Any] | None = None
    fieldMapping: dict[str, Any] | None = None


class ReviewItemPreviewRequest(BaseModel):
    draft: dict[str, Any]
    deckName: str | None = None
    modelName: str | None = None
    fieldMapping: dict[str, Any] = Field(default_factory=dict)


class ReviewItemCommitRequest(BaseModel):
    noteId: int | None = None
    cardId: int | None = None
    draft: dict[str, Any]
    action: Literal["create", "update"]
    removeTags: list[str] = Field(default_factory=list)
    flag: int | None = None
    deckName: str | None = None
    modelName: str | None = None
    fieldMapping: dict[str, Any] = Field(default_factory=dict)


class DeckContextRequest(BaseModel):
    deckName: str


class ModelSchemaRequest(BaseModel):
    modelName: str


class GeminiRequest(BaseModel):
    word: str
    dikiTranslations: list[list[str]] = Field(default_factory=list)


class GeminiReviewRequest(BaseModel):
    word: str
    currentTranslation: str
    proposedTranslations: list[list[str]]
