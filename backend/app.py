from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.schemas import (
    CommitRequest,
    CustomCardRequest,
    CurrentPatchRequest,
    DeckContextRequest,
    GeminiRequest,
    GeminiReviewRequest,
    LookupRequest,
    ModelSchemaRequest,
    QueueDiffRequest,
    QueueEditRequest,
    ReviewItemCommitRequest,
    ReviewItemExistingNoteRequest,
    ReviewItemLookupRequest,
    ReviewItemPreviewRequest,
    ReviewSnapshotRequest,
    SessionCreateRequest,
    SessionPatchRequest,
)
from backend.services import FactoryService, ServiceError
from backend.settings import ROOT_DIR, configured_words_to_add_path
from external_APIs.diki_lists import coverage


load_dotenv(ROOT_DIR / ".env")
service = FactoryService()


@asynccontextmanager
async def lifespan(application: FastAPI):
    yield
    if not getattr(application.state, "shutdown_sync_flushed", False):
        service.flush_sync()


app = FastAPI(title="Anki Flashcards Factory", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, error: ServiceError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


@app.get("/backend/status")
def status():
    return service.status()


@app.get("/backend/offline-coverage")
def offline_coverage():
    return coverage(service.diki.resources)


@app.post("/backend/shutdown")
def shutdown_app(
    background_tasks: BackgroundTasks,
    x_anki_factory_shutdown: str | None = Header(default=None),
):
    # A non-simple header prevents another website from issuing this local shutdown request.
    if x_anki_factory_shutdown != "true":
        raise HTTPException(status_code=403, detail="Shutdown requests must come from the Factory UI")
    result = service.flush_sync()
    app.state.shutdown_sync_flushed = True
    server = getattr(app.state, "uvicorn_server", None)
    if server is None:
        raise HTTPException(status_code=409, detail="This server cannot be stopped from the browser")
    background_tasks.add_task(setattr, server, "should_exit", True)
    return result


@app.get("/backend/sessions")
def list_sessions():
    return service.list_sessions()


@app.post("/backend/sessions")
def create_session(request: SessionCreateRequest):
    return service.create_add_session(request.words, "import", request.name)


@app.post("/backend/sessions/from-words-to-add")
def create_words_to_add_session():
    path = configured_words_to_add_path()
    if not path.exists():
        raise ServiceError(f"The source file does not exist: {path.name}", 404)
    words = path.read_text(encoding="utf-8").splitlines()
    return service.create_add_session(words, "words_to_add.txt", "words_to_add.txt")


@app.get("/backend/sessions/{session_id}")
def get_session(session_id: str):
    return service.session(session_id)


@app.delete("/backend/sessions/{session_id}")
def delete_session(session_id: str):
    service.delete_add_session(session_id)
    return {"id": session_id}


@app.patch("/backend/sessions/{session_id}")
def patch_session(session_id: str, request: SessionPatchRequest):
    return service.update_session(
        session_id,
        deck_name=request.deckName,
        model_name=request.modelName,
        field_mapping=request.fieldMapping,
    )


@app.patch("/backend/sessions/{session_id}/queue")
def patch_queue(session_id: str, request: QueueEditRequest):
    return service.replace_add_queue(session_id, request.words)


@app.post("/backend/sessions/{session_id}/queue/diff")
def diff_queue(session_id: str, request: QueueDiffRequest):
    return service.queue_diff(session_id, request.words)


@app.post("/backend/sessions/{session_id}/current/lookup")
def lookup_current(session_id: str, request: LookupRequest):
    return service.lookup_current(session_id, request.word)


@app.patch("/backend/sessions/{session_id}/current")
def patch_current(session_id: str, request: CurrentPatchRequest):
    return service.update_current_draft(session_id, request.draft)


@app.post("/backend/sessions/{session_id}/current/preview")
def preview_current(session_id: str):
    return service.preview_current(session_id)


@app.get("/backend/sessions/{session_id}/current/existing-note")
def existing_note(session_id: str):
    return service.existing_note(session_id)


@app.post("/backend/sessions/{session_id}/current/duplicate/suspend")
def suspend_duplicate_note(session_id: str):
    return service.suspend_duplicate_note(session_id)


@app.delete("/backend/sessions/{session_id}/current/duplicate")
def delete_duplicate_note(session_id: str):
    return service.delete_duplicate_note(session_id)


@app.post("/backend/sessions/{session_id}/current/commit")
def commit_current(session_id: str, request: CommitRequest):
    return service.commit_current(session_id, request.action, request.removeTags, request.flag)


@app.post("/backend/sessions/{session_id}/current/skip")
def skip_current(session_id: str):
    return service.skip_current(session_id)


@app.post("/backend/sessions/{session_id}/current/custom-card")
def create_custom_card(session_id: str, request: CustomCardRequest):
    return service.create_custom_card(session_id, request.deckName, request.modelName, request.fields)


@app.post("/backend/gemini/translate")
def gemini_translate(request: GeminiRequest):
    return service.gemini_translation(request.word, request.dikiTranslations)


@app.post("/backend/gemini/review-translations")
def gemini_review(request: GeminiReviewRequest):
    return service.gemini_review(request.word, request.currentTranslation, request.proposedTranslations)


@app.get("/backend/review/inventory")
def review_inventory(deckName: str | None = None):
    return service.review_inventory(deckName)


@app.post("/backend/review/snapshot")
def review_snapshot(request: ReviewSnapshotRequest):
    return service.review_snapshot(request.kind, request.value, request.deckName)


@app.post("/backend/review/item/lookup")
def review_item_lookup(request: ReviewItemLookupRequest):
    return service.review_item_lookup(request.word, request.fieldMapping)


@app.post("/backend/review/item/existing-note")
def review_item_existing_note(request: ReviewItemExistingNoteRequest):
    return service.review_item_existing_note(request.noteId, request.draft, request.fieldMapping)


@app.post("/backend/review/item/preview")
def review_item_preview(request: ReviewItemPreviewRequest):
    return service.review_item_preview(request.draft, request.deckName, request.modelName, request.fieldMapping)


@app.post("/backend/review/item/commit")
def review_item_commit(request: ReviewItemCommitRequest):
    return service.review_item_commit(
        request.noteId,
        request.cardId,
        request.draft,
        request.action,
        request.removeTags,
        request.flag,
        request.deckName,
        request.modelName,
        request.fieldMapping,
    )


@app.get("/backend/decks")
def decks():
    return service.decks()


@app.get("/backend/deck-tree")
def deck_tree():
    return service.deck_tree()


@app.post("/backend/deck-context")
def deck_context(request: DeckContextRequest):
    return service.deck_context(request.deckName)


@app.get("/backend/models")
def models():
    return service.models()


@app.post("/backend/model-schema")
def model_schema(request: ModelSchemaRequest):
    return service.model_schema(request.modelName)


DIST_DIR = ROOT_DIR / "frontend" / "dist"
if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("backend/"):
            raise HTTPException(status_code=404, detail="Backend route was not found")
        candidate = DIST_DIR / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html", headers={"Cache-Control": "no-store"})
