"""Versioned, content-addressed transfer manifests shared by server and importer."""

import hashlib
import json
import re
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from external_apis.diki_api import resolve_lookup
from external_apis.diki_audio import (
    DISCOVERY_VERSION,
    _recording_url,
    discover_audio_urls,
    validate_audio_plan,
)
from external_apis.diki_page import inspect_page
from external_apis.diki_resources import normalize_word

PROTOCOL = 2
MAX_ITEMS = 10
MAX_TRANSFER_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 512 * 1024
LIMITS = {"html": 10 * 1024 * 1024, "audio": 5 * 1024 * 1024}
ID = re.compile(r"[a-f0-9]{32}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def html_source(word):
    return "https://www.diki.pl/slownik-angielskiego?" + urlencode({"q": word})


def validate_html(content):
    text = content.decode("utf-8", errors="strict")
    soup = BeautifulSoup(text, "html.parser")
    if not inspect_page(soup).recognized:
        raise ValueError("Not a recognized dictionary page")
    return text


def validate_artifact(artifact, content, word):
    if (
        len(content) != artifact["size"]
        or hashlib.sha256(content).hexdigest() != artifact["digest"]
    ):
        raise ValueError("Downloaded resource size/checksum does not match the manifest")
    if artifact["kind"] == "html":
        validate_html(content)
    elif not (
        content.startswith(b"ID3")
        or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    ):
        raise ValueError("Downloaded audio is not an MP3")


def validate_manifest(envelope):
    try:
        if len(canonical(envelope)) > MAX_MANIFEST_BYTES:
            raise ValueError("Transfer manifest exceeds the size limit")
        manifest = envelope["manifest"]
        if envelope["digest"] != digest(manifest) or not DIGEST.fullmatch(envelope["digest"]):
            raise ValueError("Invalid manifest checksum")
        if (
            type(manifest["protocol"]) is not int
            or manifest["protocol"] not in {1, PROTOCOL}
            or not ID.fullmatch(manifest["id"])
        ):
            raise ValueError("Unsupported transfer protocol or ID")
        items = manifest["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
            raise ValueError("Invalid transfer size")
        identifiers, words, total = set(), set(), 0
        for item in items:
            if not ID.fullmatch(item["id"]) or item["id"] in identifiers:
                raise ValueError("Invalid/duplicate item ID")
            if normalize_word(item["word"]) != item["word"] or item["word"] in words:
                raise ValueError("Invalid/duplicate word")
            identifiers.add(item["id"])
            words.add(item["word"])
            audio_only = "audioPlan" in item
            if audio_only:
                if manifest["protocol"] < 2:
                    raise ValueError("Audio-only transfers require protocol 2")
                validate_audio_plan(item["audioPlan"])
                if item.get("audioDiscoveryVersion") != item["audioPlan"]["discoveryVersion"]:
                    raise ValueError("Audio plan version mismatch")
            resources = item["resources"]
            if not isinstance(resources, list) or not 0 <= len(resources) <= 2:
                raise ValueError("Invalid resource count")
            kinds = set()
            for resource in resources:
                kind = resource["kind"]
                if kind not in LIMITS or kind in kinds or not DIGEST.fullmatch(resource["digest"]):
                    raise ValueError("Invalid resource kind/checksum")
                if type(resource["size"]) is not int or not 0 < resource["size"] <= LIMITS[kind]:
                    raise ValueError("Invalid resource size")
                if kind == "html":
                    if resource["status"] not in {200, 404} or resource["source"] != html_source(
                        item["word"]
                    ):
                        raise ValueError("Invalid HTML source/status")
                elif resource["status"] != 200 or not _recording_url(resource["source"]):
                    raise ValueError("Invalid audio source/status")
                if audio_only and (
                    kind != "audio" or resource["source"] not in item["audioPlan"]["urls"]
                ):
                    raise ValueError("Resource does not match the audio-only plan")
                kinds.add(kind)
                total += resource["size"]
            if audio_only:
                if item["audioState"] not in {"ready", "no_audio"}:
                    raise ValueError("Invalid audio-only state")
            elif "html" not in kinds or item["audioState"] not in {
                "ready",
                "no_audio",
                "not_required",
                "not_requested",
            }:
                raise ValueError("Invalid item state")
            if (item["audioState"] == "ready") != ("audio" in kinds):
                raise ValueError("Audio state does not match resources")
            if (
                item["audioState"] == "no_audio"
                and item.get("audioDiscoveryVersion") != DISCOVERY_VERSION
            ):
                raise ValueError(
                    "Audio discovery versions differ; update the client/server before importing negative results"
                )
        if total > MAX_TRANSFER_BYTES:
            raise ValueError("Transfer exceeds size limit")
        return manifest
    except (KeyError, TypeError, AttributeError, OverflowError):
        raise ValueError("Malformed transfer manifest") from None


def validate_item_content(item, contents):
    for artifact in item["resources"]:
        validate_artifact(artifact, contents[artifact["kind"]], item["word"])
    if "audioPlan" in item:
        plan = item["audioPlan"]
        html = contents.get("html")
        if html is None or hashlib.sha256(html).hexdigest() != plan["htmlDigest"]:
            raise ValueError(
                "Audio-only transfer requires the original local HTML; restore it before pulling"
            )
        if discover_audio_urls(validate_html(html), item["word"]) != plan["urls"]:
            raise ValueError("Audio-only transfer does not match locally discovered recordings")
    exact = bool(resolve_lookup(contents["html"].decode("utf-8"), item["word"]).meanings)
    if item["audioState"] == "not_required" and exact:
        raise ValueError("Exact word was incorrectly marked as not requiring audio")
    if item["audioState"] in {"ready", "no_audio"} and not exact:
        raise ValueError("Audio state requires an exact dictionary match")
