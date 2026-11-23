"""On-demand transfer client: stage -> validate -> durable cache -> ACK -> delete."""

import hashlib
import ipaddress
import json
import os
import tempfile
from contextlib import suppress
from urllib.parse import urlsplit

import requests

from external_apis.diki_api import resolve_lookup
from external_apis.diki_audio import DISCOVERY_VERSION, discover_audio_urls, validate_audio_plan
from external_apis.diki_resources import file_lock, normalize_word
from external_apis.diki_transfer import (
    ID,
    MAX_MANIFEST_BYTES,
    canonical,
    validate_artifact,
    validate_html,
    validate_item_content,
    validate_manifest,
)


class RemoteError(Exception):
    pass


class RemoteStopped(RemoteError):
    pass


def server_url(value):
    try:
        parsed = urlsplit(value)
        local = parsed.hostname == "localhost"
        with suppress(ValueError):
            local = local or ipaddress.ip_address(parsed.hostname).is_loopback
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or "\\" in value
            or any(ord(c) <= 32 for c in value)
            or not (parsed.scheme == "https" or (parsed.scheme == "http" and local))
        ):
            raise ValueError
        _ = parsed.port  # Access validates the port, including malformed numeric values.
    except (ValueError, TypeError):
        raise RemoteError(
            "DIKI_REMOTE_URL must be an HTTPS origin (HTTP is allowed only for loopback testing)"
        ) from None
    return value.rstrip("/")


def atomic_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".pull-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RemoteDownloads:
    def __init__(self, url, token, *, session=None, stop=None, preserve_existing=False):
        self.url = server_url(url)
        if not 32 <= len(token) <= 256 or any(not 33 <= ord(c) <= 126 for c in token):
            raise RemoteError(
                "Set DIKI_REMOTE_TOKEN to the server's 32–256 character printable ASCII API token"
            )
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.session.headers["Authorization"] = "Bearer " + token
        self.stop = stop
        self.preserve_existing = preserve_existing

    def _check_stop(self):
        if self.stop is not None and self.stop.is_set():
            raise RemoteStopped("Remote preparation stopped; transfers resume next launch")

    def close(self):
        self.session.close()

    def _request(self, method, path, **kwargs):
        self._check_stop()
        try:
            response = self.session.request(
                method,
                self.url + path,
                timeout=kwargs.pop("timeout", (5, 30)),
                allow_redirects=False,
                stream=True,
                **kwargs,
            )
        except requests.RequestException as error:
            raise RemoteError(
                f"Remote server connection failed ({type(error).__name__}); rerun to resume"
            ) from None
        if response.status_code not in {200, 204}:
            response.close()
            raise RemoteError(
                f"Remote server returned HTTP {response.status_code}; no transfer was acknowledged"
            )
        return response

    def _json(self, method, path, **kwargs):
        with self._request(method, path, **kwargs) as response:
            if response.status_code == 204:
                return None
            body = bytearray()
            try:
                for chunk in response.iter_content(65536):
                    self._check_stop()
                    body.extend(chunk)
                    if len(body) > MAX_MANIFEST_BYTES:
                        raise RemoteError("Remote JSON response exceeded the size limit")
                return json.loads(body)
            except (requests.RequestException, ValueError):
                raise RemoteError(
                    "Remote JSON response was incomplete/invalid; no transfer was acknowledged"
                ) from None

    def status(self, *, timeout=None):
        options = {"timeout": timeout} if timeout is not None else {}
        return self._json("GET", "/v1/status", **options)

    def require_scheduling(self):
        status = self.status()
        if not isinstance(status, dict) or status.get("schedulingVersion") != 1:
            raise RemoteError(
                "Update the remote worker to enable automatic scheduling; manual commands remain available"
            )
        return status

    def submit(
        self,
        words,
        resources,
        *,
        redownload=False,
        retry_failed=False,
        html_only=False,
        priority=None,
        remember=False,
    ):
        if priority not in {None, "buffer", "coverage"} or (
            priority == "coverage" and not html_only
        ):
            raise ValueError("Coverage priority is for HTML-only preparation")
        if remember:
            with resources.db() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS remote_submissions (
                    origin TEXT NOT NULL, goal TEXT NOT NULL, PRIMARY KEY(origin,goal))""")
        queued = known = skipped = audio_only = no_audio = 0
        remembered = 0
        records = []
        for word in dict.fromkeys(normalize_word(word) for word in words):
            self._check_stop()
            html = resources._cached(word, "html")
            if html is None:
                html = resources._reuse_legacy(word, "html")
            if html_only:
                if html is not None:
                    skipped += 1
                    continue
                records.append(
                    {"word": word, "need_audio": False, "priority": priority or "coverage"}
                )
                continue
            audio = resources._cached(word, "audio")
            if audio is None:
                audio = resources._reuse_legacy(word, "audio")
            exact = (
                bool(resolve_lookup(html.decode("utf-8"), word).meanings)
                if html is not None
                else False
            )
            if html is not None and audio is not None and not resources._audio_matches(word):
                audio = None
            audio_row = resources.metadata(word, "audio") or {}
            if html is not None and (
                not exact or audio is not None or audio_row.get("state") == "no_audio"
            ):
                skipped += 1
                continue
            record = {"word": word, "need_audio": audio is None}
            if priority is not None:
                record["priority"] = priority
            if html is not None:
                plan = resources._audio_plan(word, html)
                urls = json.loads(plan["urls"])
                if not urls:
                    self._record_no_audio(word, html, resources)
                    skipped += 1
                    no_audio += 1
                    continue
                record["audio_plan"] = validate_audio_plan(
                    {
                        "htmlDigest": plan["html_digest"],
                        "urls": urls,
                        "discoveryVersion": DISCOVERY_VERSION,
                    }
                )
                audio_only += 1
            records.append(record)
        # Only compact instructions, never cached HTML, are uploaded.
        origin = hashlib.sha256(self.url.encode()).hexdigest()
        if remember:
            with resources.db() as db:
                accepted = {
                    row[0]
                    for row in db.execute(
                        "SELECT goal FROM remote_submissions WHERE origin=?", (origin,)
                    )
                }
            fresh = [
                record
                for record in records
                if hashlib.sha256(canonical(record)).hexdigest() not in accepted
            ]
            remembered = len(records) - len(fresh)
            records = fresh

        def accept(batch):
            if remember:
                with resources.db() as db:
                    db.executemany(
                        "INSERT OR IGNORE INTO remote_submissions VALUES (?,?)",
                        [
                            (origin, hashlib.sha256(canonical(record)).hexdigest())
                            for record in batch
                        ],
                    )

        batch = []
        for record in records:
            candidate = {
                "items": batch + [record],
                "redownload": redownload,
                "retry_failed": retry_failed,
            }
            if batch and (len(batch) >= 100 or len(canonical(candidate)) > 1500000):
                result = self._json(
                    "POST",
                    "/v1/jobs",
                    json={"items": batch, "redownload": redownload, "retry_failed": retry_failed},
                )
                if result is None:
                    raise RemoteError("Remote server did not confirm submission")
                queued += result["queued"]
                known += result["alreadyKnown"]
                accept(batch)
                batch = []
            batch.append(record)
        if batch:
            result = self._json(
                "POST",
                "/v1/jobs",
                json={"items": batch, "redownload": redownload, "retry_failed": retry_failed},
            )
            if result is None:
                raise RemoteError("Remote server did not confirm submission")
            queued += result["queued"]
            known += result["alreadyKnown"]
            accept(batch)
        result = {
            "queued": queued,
            "alreadyKnown": known,
            "alreadyCached": skipped,
            "audioOnly": audio_only,
            "noAudioLocal": no_audio,
        }
        if remember:
            result["alreadySubmitted"] = remembered
        return result

    def _record_no_audio(self, word, html, resources):
        plan = resources._audio_plan(word, html)
        with file_lock(resources.root / "cache.lock"):
            current = resources._read_cached(word, "html")
            if current != html:
                raise RemoteError(
                    "Local HTML changed while recording no-audio; rerun to use the current page"
                )
            if resources._read_cached(word, "audio") is not None:
                return  # Preserve audio another local process may have imported.
            with resources.db() as db:
                db.execute(
                    "INSERT OR IGNORE INTO resources(word,kind,state) VALUES (?,'audio','no_audio')",
                    (word,),
                )
                db.execute(
                    """UPDATE resources SET state='no_audio',digest=NULL,size=NULL,status=NULL,source=NULL,
                    downloaded_at=NULL WHERE word=? AND kind='audio'""",
                    (word,),
                )
                result = db.execute(
                    "UPDATE audio_discovery SET exhausted=1 WHERE word=? AND html_digest=? AND version=?",
                    (word, plan["html_digest"], DISCOVERY_VERSION),
                )
                if result.rowcount != 1:
                    raise RemoteError("Local audio discovery changed; rerun to resume")
                db.execute("DELETE FROM resource_failures WHERE word=? AND kind='audio'", (word,))

    def _local_context(self, item, contents, resources):
        if "audioPlan" in item:
            contents["html"] = resources._cached(item["word"], "html")
            # Check before transferring MP3 bytes, not only after importing them.
            html = contents["html"]
            if html is None or hashlib.sha256(html).hexdigest() != item["audioPlan"]["htmlDigest"]:
                raise RemoteError(
                    "Audio-only transfer requires the original local HTML; restore it before pulling"
                )
            if discover_audio_urls(validate_html(html), item["word"]) != item["audioPlan"]["urls"]:
                raise RemoteError(
                    "Audio-only transfer does not match locally discovered recordings"
                )
        return contents

    def _contents(self, item, artifact, journal, resources, transfer_id):
        local = resources._cached(item["word"], artifact["kind"])
        if local is not None and hashlib.sha256(local).hexdigest() == artifact["digest"]:
            validate_artifact(artifact, local, item["word"])
            return local
        target = journal / f"{item['id']}.{artifact['kind']}"
        if target.is_symlink():
            raise RemoteError("Refusing a symlink in the local transfer journal")
        if target.exists():
            content = target.read_bytes()
            try:
                validate_artifact(artifact, content, item["word"])
                return content
            except ValueError:
                target.unlink()
        path = f"/v1/transfers/{transfer_id}/files/{item['id']}/{artifact['kind']}"
        with self._request("GET", path) as response:
            content = bytearray()
            try:
                for chunk in response.iter_content(65536):
                    self._check_stop()
                    content.extend(chunk)
                    if len(content) > artifact["size"]:
                        raise RemoteError("Remote resource exceeded its declared size")
            except requests.RequestException:
                raise RemoteError("Resource transfer interrupted; rerun pull to resume") from None
        content = bytes(content)
        validate_artifact(artifact, content, item["word"])
        atomic_file(target, content)
        return content

    def _import(self, item, contents, resources):
        word = item["word"]
        if self.preserve_existing:
            self._merge_existing(item, contents, resources)
            return
        for artifact in item["resources"]:
            resources._save(
                word,
                artifact["kind"],
                contents[artifact["kind"]],
                artifact["status"],
                artifact["source"],
                bool(resolve_lookup(contents["html"].decode(), word).meanings)
                if artifact["kind"] == "html"
                else False,
            )
        if item["audioState"] == "no_audio" and resources._cached(word, "audio") is None:
            self._record_no_audio(word, contents["html"], resources)
        text = contents["html"].decode("utf-8")
        result = resolve_lookup(text, word)
        if result.word and result.meanings:
            resources.retain_headword(word, result.word, text)

    def _merge_existing(self, item, contents, resources):
        word = item["word"]
        with file_lock(resources.root / "cache.lock"):
            for artifact in item["resources"]:
                kind = artifact["kind"]
                current = resources._read_cached(word, kind)
                html = resources._read_cached(word, "html") or contents["html"]
                urls = discover_audio_urls(html.decode("utf-8"), word)
                source = (resources.metadata(word, kind) or {}).get("source")
                if current is not None and (kind == "html" or source in urls):
                    continue
                if kind == "audio" and artifact["source"] not in urls:
                    continue
                resources._save_locked(
                    word,
                    kind,
                    contents[kind],
                    artifact["status"],
                    artifact["source"],
                    bool(resolve_lookup(contents["html"].decode(), word).meanings)
                    if kind == "html"
                    else False,
                )
        html = resources._cached(word, "html")
        if (
            html == contents["html"]
            and item["audioState"] == "no_audio"
            and resources._cached(word, "audio") is None
        ):
            self._record_no_audio(word, html, resources)
        if html is not None:
            result = resolve_lookup(html.decode(), word)
            if result.word and result.meanings:
                resources.retain_headword(word, result.word, html.decode())

    def _verify_reconciled(self, manifest, all_contents, journal, resources):
        outcomes = []
        for item, original in zip(manifest["items"], all_contents, strict=True):
            word = item["word"]
            with file_lock(resources.root / "cache.lock"):
                html = resources._read_cached(word, "html")
                if html is None:
                    raise RemoteError("Imported HTML is not durably available")
                validate_html(html)
                urls = discover_audio_urls(html.decode(), word)
                if "audioPlan" in item and (
                    hashlib.sha256(html).hexdigest() != item["audioPlan"]["htmlDigest"]
                    or urls != item["audioPlan"]["urls"]
                ):
                    raise RemoteError(
                        "Audio-only transfer requires the original local HTML; restore it before pulling"
                    )
                audio = resources._read_cached(word, "audio")
                row = resources.metadata(word, "audio") or {}
                valid_audio = audio is not None and row.get("source") in urls
                if valid_audio:
                    validate_artifact(row, audio, word)
                if item["audioState"] == "ready" and not valid_audio:
                    offered = next(
                        artifact["source"]
                        for artifact in item["resources"]
                        if artifact["kind"] == "audio"
                    )
                    if offered in urls:
                        raise RemoteError("Imported recording is not durably available")
                if (
                    item["audioState"] == "no_audio"
                    and html == original["html"]
                    and not valid_audio
                    and row.get("state") != "no_audio"
                ):
                    raise RemoteError("Imported no-audio result is not durably available")
                outcomes.append(
                    {
                        "word": word,
                        "htmlDigest": hashlib.sha256(html).hexdigest(),
                        "audioDigest": hashlib.sha256(audio).hexdigest()
                        if valid_audio and audio is not None
                        else None,
                    }
                )
        # Original manifest bytes remain staged until ACK. Record the retained
        # cache outcome rather than pretending different source digests are equal.
        atomic_file(journal / "reconciled.json", canonical(outcomes))

    def _transfer(self, envelope, journal, resources):
        self._check_stop()
        if journal.is_symlink():
            raise RemoteError("Refusing a symlink in the local transfer journal")
        manifest = validate_manifest(envelope)
        atomic_file(journal / "manifest.json", canonical(envelope))
        # Validate the whole transfer before changing local cache or acknowledging.
        all_contents = []
        for item in manifest["items"]:
            contents = self._local_context(item, {}, resources)
            contents.update(
                {
                    artifact["kind"]: self._contents(
                        item, artifact, journal, resources, manifest["id"]
                    )
                    for artifact in item["resources"]
                }
            )
            validate_item_content(item, contents)
            if self.preserve_existing:
                for artifact in item["resources"]:
                    atomic_file(
                        journal / f"{item['id']}.{artifact['kind']}", contents[artifact["kind"]]
                    )
            all_contents.append(contents)
        self._check_stop()
        for item, contents in zip(manifest["items"], all_contents, strict=True):
            self._import(item, contents, resources)
        # Re-read the committed cache; a failed write must never lead to ACK.
        for item in [] if self.preserve_existing else manifest["items"]:
            contents = self._local_context(item, {}, resources)
            for artifact in item["resources"]:
                content = resources._cached(item["word"], artifact["kind"])
                if content is None:
                    raise RemoteError(
                        "Imported resource is not durably available in the local cache"
                    )
                validate_artifact(artifact, content, item["word"])
                contents[artifact["kind"]] = content
            validate_item_content(item, contents)
            if item["audioState"] == "no_audio":
                row = resources.metadata(item["word"], "audio") or {}
                if (
                    row.get("state") != "no_audio"
                    and resources._cached(item["word"], "audio") is None
                ):
                    raise RemoteError(
                        "Imported no-audio result is not durably available in the local cache"
                    )
        if self.preserve_existing:
            self._verify_reconciled(manifest, all_contents, journal, resources)
        self._check_stop()
        receipt = self._json(
            "POST", f"/v1/transfers/{manifest['id']}/ack", json={"digest": envelope["digest"]}
        )
        if not isinstance(receipt, dict) or receipt.get("acknowledged") is not True:
            raise RemoteError("Server did not confirm acknowledgment; rerun pull to resume")
        for item in manifest["items"]:
            for artifact in item["resources"]:
                (journal / f"{item['id']}.{artifact['kind']}").unlink(missing_ok=True)
        (journal / "manifest.json").unlink(missing_ok=True)
        (journal / "reconciled.json").unlink(missing_ok=True)
        # Do not remove unfamiliar files in a journal directory.
        with suppress(OSError):
            journal.rmdir()
        return len(manifest["items"]), receipt.get("cleanupPending", 0)

    def pull(self, resources, *, max_batches=100, startup=False):
        if startup:
            self.require_scheduling()
            max_batches = 20000
        if not 1 <= max_batches <= (20000 if startup else 1000):
            raise RemoteError("max_batches must be between 1 and 1000")
        imports = (
            resources.root / "remote-imports" / hashlib.sha256(self.url.encode()).hexdigest()[:16]
        )
        imports.mkdir(parents=True, exist_ok=True)
        count = words = cleanup = 0
        seen = set()
        try:
            with file_lock(resources.root / "remote-pull.lock", blocking=False):
                # Resolve an ACK lost in transit before requesting another transfer.
                for journal in sorted(imports.iterdir()):
                    self._check_stop()
                    if not ID.fullmatch(journal.name) or not (journal / "manifest.json").is_file():
                        continue
                    if journal.is_symlink() or (journal / "manifest.json").is_symlink():
                        raise RemoteError("Refusing a symlink in the local transfer journal")
                    if (journal / "manifest.json").stat().st_size > MAX_MANIFEST_BYTES:
                        raise RemoteError("Local transfer manifest exceeds the size limit")
                    if count >= max_batches:
                        break
                    envelope = json.loads((journal / "manifest.json").read_text())
                    if validate_manifest(envelope)["id"] != journal.name:
                        raise RemoteError("Local transfer journal ID mismatch")
                    imported, pending = self._transfer(envelope, journal, resources)
                    count, words, cleanup = count + 1, words + imported, cleanup + pending
                    seen.add(journal.name)
                drain_id = None
                if startup:
                    snapshot = self._json("POST", "/v1/transfers/drain")
                    if (
                        not isinstance(snapshot, dict)
                        or not isinstance(snapshot.get("id"), str)
                        or not ID.fullmatch(snapshot["id"])
                    ):
                        raise RemoteError("Invalid startup drain snapshot")
                    drain_id = snapshot["id"]
                while count < max_batches:
                    self._check_stop()
                    path = "/v1/transfers/next" + (f"?drain_id={drain_id}" if drain_id else "")
                    envelope = self._json("GET", path)
                    if envelope is None:
                        break
                    manifest = validate_manifest(envelope)
                    if manifest["id"] in seen:
                        raise RemoteError("Server returned an already-acknowledged transfer")
                    imported, pending = self._transfer(
                        envelope, imports / manifest["id"], resources
                    )
                    count, words, cleanup = count + 1, words + imported, cleanup + pending
                    seen.add(manifest["id"])
        except BlockingIOError:
            raise RemoteError("Another pull is running for this local cache") from None
        except (OSError, ValueError) as error:
            raise RemoteError(
                f"Pull stopped before completion: {error}; server retains unacknowledged downloads"
            ) from None
        return {
            "transfersAcknowledged": count,
            "wordsImported": words,
            "serverCleanupPending": cleanup,
        }
