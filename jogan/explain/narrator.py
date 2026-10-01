"""Gemini rewords the template explanation; it never decides and never adds facts.

Input and output are structured JSON (D-002 #10). The prompt holds the recommendation's
evidence and its template text, nothing a user typed. The answer is accepted only if it is
valid JSON, not too long, written in the requested script, and every number in it already
appears in the template (Bangla digits and digit grouping are normalised first); the
template's stock-out chance must be kept. Anything else, and any error, gives the template
back with the reason.

The primary model is tried first; on HTTP 429 (rate limit) or a 5xx error the fallback model
is tried. Calls are limited per minute per API instance, and results are cached in memory.
Endpoint and fields: ``models.generateContent`` (https://ai.google.dev/api/generate-content),
JSON output with ``responseMimeType`` and ``responseSchema``
(https://ai.google.dev/gemini-api/docs/structured-output), checked on 2026-10-02.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx2 as httpx

from jogan.explain.config import Narrator as NarratorConfig

log = logging.getLogger(__name__)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
LANGUAGE = {"en": "English", "bn": "Bangla (Bengali script, Bangla digits)"}
SYSTEM = """You reword a short decision-support note for an operations analyst at a mobile \
financial services company in Bangladesh. The input JSON holds the structured evidence behind \
one recommended runner visit and a template note written from that evidence.

Rewrite the template note in {language} so it reads naturally, in at most 5 sentences.
Rules:
- Use only facts that are in the input. Do not add advice, causes, names or dates.
- Copy every number exactly as the template writes it. Do not round, convert or add numbers.
- Keep the stock-out chance and say it is a prediction.
- Keep the recommendation and any manual-review reasons; do not soften or strengthen them.
Answer as JSON: {{"text": "<the reworded note>"}}."""

SCHEMA = {"type": "OBJECT", "properties": {"text": {"type": "STRING"}}, "required": ["text"]}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_BENGALI = re.compile(r"[ঀ-৿]")
_LETTER = re.compile(r"[^\W\d_]")


@dataclasses.dataclass(frozen=True)
class Narration:
    text: str
    source: str  # "gemini" or "template"
    model: str | None = None
    note: str | None = None  # why the template was used


def numbers(text: str) -> set[float]:
    """Every number in ``text``, with Bangla digits and digit grouping normalised."""
    found = _NUMBER.findall(text.translate(_TO_ASCII))
    return {float(n.replace(",", "").rstrip(".")) for n in found if n.replace(",", "")}


def check(text: str, template: str, lang: str, required: set[float], max_chars: int) -> str:
    """Why ``text`` is refused, or ``""`` when it may be shown."""
    if not text.strip():
        return "empty answer"
    if len(text) > max_chars:
        return "answer too long"
    extra = numbers(text) - numbers(template)
    if extra:
        return "number not in the evidence: " + ", ".join(f"{x:g}" for x in sorted(extra))
    if not required <= numbers(text):
        return "the stock-out chance is missing"
    letters = _LETTER.findall(text)
    bengali = sum(bool(_BENGALI.match(c)) for c in letters) / max(len(letters), 1)
    if (lang == "bn" and bengali < 0.5) or (lang == "en" and bengali > 0.05):
        return "wrong language"
    return ""


def answer_text(body: dict) -> str:
    """The JSON answer's ``text``; raises ``ValueError`` when the response has none."""
    try:
        parts = body["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("no candidate in the response") from e
    raw = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("answer is not JSON") from e
    if not isinstance(data, dict) or not isinstance(data.get("text"), str):
        raise ValueError("answer has no text")
    return data["text"].strip()


class Narrator:
    def __init__(
        self,
        cfg: NarratorConfig,
        api_key: str | None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cfg, self.api_key, self.clock = cfg, api_key, clock
        self.http = httpx.Client(base_url=BASE_URL, timeout=cfg.timeout_s, transport=transport)
        self.cache: collections.OrderedDict[Any, Narration] = collections.OrderedDict()
        self.calls: collections.deque[float] = collections.deque()
        self.lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _allow_call(self) -> bool:
        now = self.clock()
        with self.lock:
            while self.calls and now - self.calls[0] >= 60.0:
                self.calls.popleft()
            if len(self.calls) >= self.cfg.per_minute:
                return False
            self.calls.append(now)
            return True

    def _remember(self, key: Any, result: Narration) -> Narration:
        with self.lock:
            self.cache[key] = result
            self.cache.move_to_end(key)
            while len(self.cache) > self.cfg.cache_size:
                self.cache.popitem(last=False)
        return result

    def _request(self, model: str, payload: dict, lang: str) -> httpx.Response:
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM.format(language=LANGUAGE[lang])}]},
            "contents": [
                {"role": "user", "parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}
            ],
            "generationConfig": {
                "temperature": self.cfg.temperature,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        headers = {"x-goog-api-key": self.api_key or ""}
        return self.http.post(f"/models/{model}:generateContent", json=body, headers=headers)

    def narrate(
        self, key: Any, template: str, evidence: dict, lang: str, required: set[float]
    ) -> Narration:
        """Gemini's rewording of ``template`` if it passes :func:`check`, else the template."""
        if not self.enabled:
            return Narration(template, "template", note="narrator is off (no API key)")
        with self.lock:
            if key in self.cache:
                return self.cache[key]
        if not self._allow_call():
            return Narration(template, "template", note="narrator rate limit reached")
        payload = {"language": lang, "evidence": evidence, "template": template}
        note = ""
        for model in (self.cfg.primary, self.cfg.fallback):
            try:
                r = self._request(model, payload, lang)
            except httpx.HTTPError as e:
                note = f"{model}: {type(e).__name__}"
                continue
            if r.status_code == 429 or r.status_code >= 500:
                note = f"{model}: HTTP {r.status_code}"
                continue
            if not r.is_success:
                note = f"{model}: HTTP {r.status_code}"
                break
            try:
                text = answer_text(r.json())
            except ValueError as e:
                return self._remember(key, Narration(template, "template", model, str(e)))
            problem = check(text, template, lang, required, self.cfg.max_chars)
            if problem:
                log.info("narration refused (%s): %s", model, problem)
                return self._remember(key, Narration(template, "template", model, problem))
            return self._remember(key, Narration(text, "gemini", model))
        log.warning("narrator unavailable: %s", note)
        return Narration(template, "template", note=note)
