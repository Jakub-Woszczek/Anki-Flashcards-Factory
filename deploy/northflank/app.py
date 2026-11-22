"""Authenticated API plus a single resident worker; run with python -m ...app."""

import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from deploy.northflank.config import Config
from deploy.northflank.service import DownloadService, PauseWork, QueueConflict
from external_apis.diki_audio import MAX_AUDIO_URLS
from external_apis.diki_transfer import PROTOCOL


class AudioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    htmlDigest: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")
    urls: list[StrictStr] = Field(min_length=1, max_length=MAX_AUDIO_URLS)
    discoveryVersion: StrictInt


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: StrictStr = Field(min_length=1, max_length=500)
    need_audio: StrictBool = True
    audio_plan: AudioPlan | None = None
    html: StrictStr | None = Field(default=None, max_length=700000)
    html_status: Literal[200, 404] = 200


class Submit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Job] = Field(min_length=1, max_length=200)
    redownload: StrictBool = False
    retry_failed: StrictBool = False


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: StrictStr = Field(pattern=r"^[a-f0-9]{64}$")


class Guard:
    """Authenticate before reading bodies; enforce a finite input size/time."""

    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["path"].startswith("/v1/") and not secrets.compare_digest(
            headers.get(b"authorization", b""), ("Bearer " + self.token).encode()
        ):
            return await JSONResponse({"detail": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
        if scope["method"] == "POST":
            body = bytearray()
            try:
                async with asyncio.timeout(15):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return None
                        body.extend(message.get("body", b""))
                        if len(body) > 2 * 1024 * 1024:
                            return await JSONResponse(
                                {"detail": "Request too large"}, status_code=413
                            )(scope, receive, send)
                        if not message.get("more_body"):
                            break
            except TimeoutError:
                return await JSONResponse({"detail": "Request body timeout"}, status_code=408)(
                    scope, receive, send
                )
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            return await self.app(scope, replay, send)
        return await self.app(scope, receive, send)


def create_app(service, *, run_worker=True):
    @asynccontextmanager
    async def lifespan(app):
        if run_worker:
            service.start()
        try:
            yield
        finally:
            service.close()

    app = FastAPI(
        title="Diki download worker",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(Guard, token=service.config.token)

    @app.exception_handler(QueueConflict)
    async def conflict(request, error):
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(PauseWork)
    async def full(request, error):
        return JSONResponse({"detail": str(error)}, status_code=507)

    @app.get("/health")
    def health():
        return {"service": "diki-download-worker", "protocol": PROTOCOL}

    @app.get("/v1/status")
    def status():
        return service.status()

    @app.post("/v1/jobs")
    def submit(body: Submit):
        try:
            return service.submit(
                [item.model_dump() for item in body.items],
                redownload=body.redownload,
                retry_failed=body.retry_failed,
            )
        except ValueError:
            raise HTTPException(422, "Invalid word, audio plan, or cached HTML seed") from None

    @app.get("/v1/transfers/next")
    def next_transfer():
        result = service.next_transfer()
        return (
            Response(status_code=204)
            if result is None
            else JSONResponse(result, headers={"Cache-Control": "no-store"})
        )

    @app.get("/v1/transfers/{batch_id}/files/{job_id}/{kind}")
    def blob(batch_id: str, job_id: str, kind: Literal["html", "audio"]):
        data = service.blob(batch_id, job_id, kind)
        return Response(
            data, media_type="application/octet-stream", headers={"Cache-Control": "no-store"}
        )

    @app.post("/v1/transfers/{batch_id}/ack")
    def acknowledge(batch_id: str, receipt: Receipt):
        return service.acknowledge(batch_id, receipt.digest)

    return app


def main():
    import uvicorn

    config = Config.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "posix" and os.geteuid() == 0:
        # Only the mounted data directory needs ownership. Drop root before serving.
        os.chown(config.data_dir, 10001, 10001)
        os.setgroups([])
        os.setgid(10001)
        os.setuid(10001)
    service = DownloadService(config)
    uvicorn.run(
        create_app(service),
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        workers=1,
        timeout_graceful_shutdown=30,
    )


if __name__ == "__main__":
    main()
