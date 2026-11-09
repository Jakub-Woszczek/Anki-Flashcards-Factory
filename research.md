# Offline Diki research

## Original flow before offline caching

`backend/services.py:317` calls `DikiApi.get_translations`, then
`possible_spellings` on an empty result. Both methods independently request the
same HTML (`external_APIs/dikiApi.py:31,184`). Pure BeautifulSoup parsing already
exists in `parse_meanings` and `parse_translations` and can be reused unchanged.
Diki's 404 responses can contain valid spelling suggestions.

`DikiApi.diki_audio_harness` guesses six pronunciation URLs and writes directly
to an Anki media directory, ignoring existing files. `FactoryService._write_audio`
then reads that file and sends it to AnkiConnect's active collection. Failed audio
currently clears the mapped sound field even on updates.

Word-list imports use one fixed file (`backend/settings.py:34`); other text files
are manually imported in the browser. Session queues delete completed rows and
are therefore unsuitable as the source for original-list download coverage.
SQLite is already used for local application data; `data/` is gitignored.

```text
Original: UI -> FactoryService -> DikiApi -> requests -> parser
Implemented: UI / CLI -> DikiApi -> shared disk resources -> paced requests
                                     |
                         HTML + MP3 + SQLite metadata
```

## Integration and verification

Keep parsing independent of storage. Use a separate cache database, independent
of Anki and session initialization. Discover original text files for coverage,
deduplicating normalized words without editing lists. All HTTP requests must use
the same cross-process pacing lock, including audio fallback attempts.

Existing parser regression fixtures are safe offline. Some legacy Diki tests use
live HTTP, and AnkiConnect tests can mutate real notes, so verification must use
explicit mock-backed test selections. Frontend validation is `npm run build`.

Offline means internet-independent Diki lookup/export with local Anki running;
Gemini and AnkiWeb sync still require internet.

## Live transport investigation (2026-11-08)

Reproduced the old GET from `git show HEAD:external_APIs/dikiApi.py`, including
the original Mozilla User-Agent, outside the app with isolated temporary output.
It also times out before receiving HTTP headers. Restoring the header is correct
compatibility behavior, but it does not by itself fix this live failure.

Controlled requests were spaced 15–25 seconds apart with the launch agent paused.
Findings:

- DNS and TLS work; an unrelated HTTPS control request returned 200 in 0.15s.
- Ordinary requests and curl (HTTP/1.1 and HTTP/2) stall on dictionary pages.
- The homepage and direct `take.mp3` returned 200 in some probes; the MP3 was
  10,820 bytes. Other homepage attempts stalled too.
- Two isolated Chrome probes obtained real `take` HTML with 28 exact meanings,
  but later Chrome probes stalled as well. Browser impersonation and retaining
  a temporary browser profile did not produce a reliable fix. No browser client
  or dependency was retained in the application.
- Crucially, normal requests with the ORIGINAL headers and a 130-second read
  timeout received HTTP **524** after approximately **125 seconds** for both
  `take` and `bind`. This identifies a Cloudflare-to-Diki origin timeout; it is
  not an exception caused by BeautifulSoup, SQLite, disk writes or launchd.
  The underlying reason for Diki's origin not responding is not established.

Separate implementation defects found and corrected:

1. Restore the original User-Agent instead of changing transport identity while
   adding caching.
2. A real dictionary page includes `challenge-platform` JS detection markup.
   That script alone must not cause valid dictionary HTML to be classified as
   an anti-bot challenge.
3. Retain the actual request exception in error metadata and reports.
4. Do not end an entire batch on one word's read timeout/server error. Continue
   to other words, with a circuit breaker after three consecutive failures.
5. Persist in-progress attempt/HTML counts before waiting on audio.

The origin errors blocked live verification during this investigation. Later,
after Diki recovered, ordinary requests returned real dictionary HTML in 0.48s
and the scheduled job populated the cache. By November 9 it had downloaded 85
HTML pages and 70 MP3s, with 70 words fully available offline. A later anti-bot
challenge triggered the expected cooldown. No browser transport was needed.
