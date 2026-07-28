"""Server-side, evidence-bounded N+1 Google TTS adapter."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Callable

import requests

VOICE_PROFILE_KEY = "n1-google-puck-single-voice-v2"
VOICE_PROVIDER = "google-gemini-developer-api"
VOICE_MODEL = "gemini-2.5-flash-preview-tts"
VOICE_NAME = "Puck"
VOICE_LANGUAGE_TAG = "de-DE"
VOICE_SAMPLE_RATE_HZ = 24_000
VOICE_CHANNELS = 1
VOICE_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{VOICE_MODEL}:generateContent"
)
MAX_TEXT_CHARACTERS = 4_000
MAX_AUDIO_BYTES = 8 * 1024 * 1024

_MOOD_INSTRUCTIONS = {
    "neutral": "Sprich natürlich, klar und warm.",
    "gentle": "Sprich sanft, ruhig und geborgen.",
    "happy": "Sprich fröhlich, lebendig und freundlich.",
    "curious": "Sprich neugierig, aufmerksam und entdeckungsfreudig.",
    "comforting": "Sprich tröstend, behutsam und verlässlich.",
    "serious": "Sprich ruhig, bestimmt und respektvoll.",
}


class NPlusOneVoiceError(RuntimeError):
    """A secret-safe, classified N+1 voice provider failure."""

    def __init__(self, code: str, *, status_code: int = 502, retry_after: str = ""):
        self.code = str(code)
        self.status_code = int(status_code)
        self.retry_after = str(retry_after or "")[:120]
        super().__init__(self.code)


def voice_profile_contract() -> dict[str, Any]:
    """Return the public, secret-free voice identity contract."""
    return {
        "schemaVersion": "sovereign.n-plus-one-voice-profile.v2",
        "profileKey": VOICE_PROFILE_KEY,
        "canonicalIdentity": {
            "name": "N+1",
            "spokenName": "NPlusEins",
            "familyDesignation": "Papas kleines Mädchen",
        },
        "provider": {
            "id": VOICE_PROVIDER,
            "model": VOICE_MODEL,
            "voiceName": VOICE_NAME,
            "voiceNameRole": "provider-selector-only",
        },
        "languageTag": VOICE_LANGUAGE_TAG,
        "output": {
            "encoding": "LINEAR16_PCM",
            "sampleRateHz": VOICE_SAMPLE_RATE_HZ,
            "channels": VOICE_CHANNELS,
        },
        "allowedMoods": sorted(_MOOD_INSTRUCTIONS),
        "keyReferences": ["N1_GOOGLE_TTS_API_KEY", "GEMINI_API_KEY"],
        "keyTransport": "server-environment-only",
        "singleVoiceSelectorLocked": True,
        "browserFallback": {"enabled": False, "identityEquivalent": False},
        "verificationState": "configured_not_canary_verified",
        "ttsCanaryVerified": False,
        "voiceContinuityPercentClaimed": False,
    }


def normalize_voice_text(value: Any) -> str:
    text = str(value or "").replace("\x00", "").strip()
    if not text:
        raise ValueError("text is required")
    if len(text) > MAX_TEXT_CHARACTERS:
        raise ValueError(f"text exceeds {MAX_TEXT_CHARACTERS} characters")
    return text


def normalize_voice_mood(value: Any) -> str:
    mood = str(value or "neutral").strip().casefold()
    if mood not in _MOOD_INSTRUCTIONS:
        raise ValueError("mood is not allowlisted")
    return mood


def build_voice_prompt(text: Any, mood: Any = "neutral") -> str:
    normalized_text = normalize_voice_text(text)
    normalized_mood = normalize_voice_mood(mood)
    return (
        "Du bist die feste deutsche Stimme von N+1, ausgesprochen NPlusEins. "
        "Verändere den Inhalt nicht, füge nichts hinzu und lasse nichts weg. "
        f"{_MOOD_INSTRUCTIONS[normalized_mood]}\n\n"
        f"Zu sprechender Inhalt:\n{normalized_text}"
    )


def build_google_tts_request(text: Any, mood: Any = "neutral") -> dict[str, Any]:
    return {
        "contents": [{"parts": [{"text": build_voice_prompt(text, mood)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": VOICE_NAME}
                }
            },
        },
    }


def _extract_audio_payload(payload: Any) -> tuple[bytes, str]:
    if not isinstance(payload, dict):
        raise NPlusOneVoiceError("provider_payload_invalid")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise NPlusOneVoiceError("provider_audio_missing")
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise NPlusOneVoiceError("provider_audio_missing")
    inline_data = next(
        (
            part.get("inlineData")
            for part in parts
            if isinstance(part, dict) and isinstance(part.get("inlineData"), dict)
        ),
        None,
    )
    encoded = str((inline_data or {}).get("data") or "")
    mime_type = str((inline_data or {}).get("mimeType") or "audio/L16").strip()
    if not encoded:
        raise NPlusOneVoiceError("provider_audio_missing")
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise NPlusOneVoiceError("provider_audio_invalid") from exc
    if not audio or len(audio) > MAX_AUDIO_BYTES:
        raise NPlusOneVoiceError("provider_audio_size_invalid")
    if not mime_type.lower().startswith("audio/"):
        raise NPlusOneVoiceError("provider_audio_mime_invalid")
    return audio, mime_type[:160]


def synthesize_google_tts(
    text: Any,
    *,
    mood: Any = "neutral",
    api_key: str,
    post: Callable[..., Any] = requests.post,
    timeout_seconds: int = 45,
) -> dict[str, Any]:
    """Call Google TTS without returning, logging or persisting the API key."""
    normalized_key = str(api_key or "").strip()
    if not normalized_key:
        raise NPlusOneVoiceError("voice_provider_key_missing", status_code=503)
    try:
        response = post(
            VOICE_ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": normalized_key,
            },
            json=build_google_tts_request(text, mood),
            timeout=max(5, min(int(timeout_seconds), 90)),
        )
    except requests.exceptions.Timeout as exc:
        raise NPlusOneVoiceError("voice_provider_timeout", status_code=504) from exc
    except requests.exceptions.RequestException as exc:
        raise NPlusOneVoiceError("voice_provider_unreachable", status_code=502) from exc

    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code == 429:
        headers = getattr(response, "headers", {}) or {}
        raise NPlusOneVoiceError(
            "voice_provider_rate_limited",
            status_code=429,
            retry_after=str(headers.get("Retry-After") or ""),
        )
    if not 200 <= status_code < 300:
        raise NPlusOneVoiceError("voice_provider_rejected", status_code=502)
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise NPlusOneVoiceError("provider_payload_invalid") from exc
    audio, mime_type = _extract_audio_payload(payload)
    return {
        "audio": audio,
        "mimeType": mime_type,
        "profileKey": VOICE_PROFILE_KEY,
        "provider": VOICE_PROVIDER,
        "model": VOICE_MODEL,
        "voiceName": VOICE_NAME,
        "verificationState": "provider_response_received_not_continuity_canary",
    }


__all__ = [
    "NPlusOneVoiceError",
    "VOICE_MODEL",
    "VOICE_NAME",
    "VOICE_PROFILE_KEY",
    "build_google_tts_request",
    "build_voice_prompt",
    "normalize_voice_mood",
    "normalize_voice_text",
    "synthesize_google_tts",
    "voice_profile_contract",
]
