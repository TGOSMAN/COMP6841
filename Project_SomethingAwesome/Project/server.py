from __future__ import annotations

import ast
import json
import html
import base64
import hmac
import hashlib
import math
import mimetypes
import os
import random
import re
import sqlite3
import socketserver
import struct
import threading
import time
import wave
from collections import deque
from contextlib import nullcontext
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from radio.live_signal_pipeline import generate_live_frame, live_signal_profile, raw_iq_bytes


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "tolling.db"
CHALLENGES_PATH = DATA_DIR / "challenges.json"
CONTEXTS_PATH = DATA_DIR / "contexts.json"
CONFIG_PATH = ROOT / "config" / "range.json"
VALIDATION_CONFIG_PATH = ROOT / "config" / "validation.json"
MODE = {"value": "attack"}
REPLAY_CACHE: set[str] = set()
AIR_WEATHER_SESSIONS: dict[str, dict] = {}
OPERATOR_COMMENTS = [
    {
        "callsign": "CIVIC-OPS-1",
        "route_note": "Decoded training frame looked normal.",
        "operator_comment": "Awaiting correlation with toll event.",
    }
]
RANGE_SECRET = os.urandom(32)
RF_TARGETS = {
    "tunnel-reading-signals": {"center_mhz": 915.0, "span_khz": 1200, "modulations": {"AUTO", "OOK", "ASK", "2-FSK"}, "label": "TUNNEL-SIGN-915"},
    "tunnel-tuning": {"center_mhz": 915.0, "span_khz": 1200, "modulations": {"AUTO", "OOK", "ASK", "2-FSK"}, "label": "TUNNEL-TUNE-915"},
    "tunnel-basic-dos": {"center_mhz": 915.0, "span_khz": 1200, "modulations": {"AUTO", "OOK", "ASK", "2-FSK"}, "label": "TUNNEL-DOS-915"},
    "tunnel-packet-injection": {"center_mhz": 915.0, "span_khz": 1200, "modulations": {"AUTO", "OOK", "ASK", "2-FSK"}, "label": "TUNNEL-INJECT-915"},
    "broadcast-reading-signals": {"center_mhz": 315.0, "span_khz": 500, "modulations": {"AUTO", "ASK", "MANCHESTER", "2-FSK"}, "label": "BROADCAST-META-315"},
    "broadcast-tuning": {"center_mhz": 315.0, "span_khz": 500, "modulations": {"AUTO", "ASK", "MANCHESTER", "2-FSK"}, "label": "BROADCAST-TUNE-315"},
    "broadcast-basic-dos": {"center_mhz": 315.0, "span_khz": 500, "modulations": {"AUTO", "ASK", "MANCHESTER", "2-FSK"}, "label": "BROADCAST-DOS-315"},
    "broadcast-packet-injection": {"center_mhz": 315.0, "span_khz": 500, "modulations": {"AUTO", "ASK", "MANCHESTER", "2-FSK"}, "label": "BROADCAST-INJECT-315"},
    "weather-boring-intercept": {"center_mhz": 169.65, "span_khz": 300, "modulations": {"AUTO", "AM", "QAM"}, "label": "WEATHER-HOP-169"},
    "weather-boring-obscured": {"center_mhz": 169.65, "span_khz": 300, "modulations": {"AUTO", "AM", "QAM"}, "label": "WEATHER-PRNG-169"},
    "weather-boring-active-re": {"center_mhz": 169.65, "span_khz": 300, "modulations": {"AUTO", "AM", "FSK"}, "label": "WEATHER-META-169"},
    "civilian-emergency-intercept": {"center_mhz": 169.65, "span_khz": 300, "modulations": {"AUTO", "AM"}, "label": "CIVIL-AUDIO-169"},
    "civilian-emergency-obscured": {"center_mhz": 169.65, "span_khz": 300, "modulations": {"AUTO", "AM"}, "label": "CIVIL-PRNG-169"},
    "civilian-emergency-active-re": {"center_mhz": 169.65, "span_khz": 300, "modulations": {"AUTO", "AM", "FSK"}, "label": "CIVIL-WARNING-169"},
    "bushfire-re-embedded": {"center_mhz": 433.92, "span_khz": 900, "modulations": {"AUTO", "FSK", "GFSK", "QAM"}, "label": "BUSHFIRE-RE-433"},
    "bushfire-hdl-flaw": {"center_mhz": 433.92, "span_khz": 900, "modulations": {"AUTO", "FSK", "GFSK", "QAM"}, "label": "BUSHFIRE-HDL-433"},
    "bushfire-rce": {"center_mhz": 433.92, "span_khz": 900, "modulations": {"AUTO", "FSK", "GFSK", "QAM"}, "label": "BUSHFIRE-RCE-433"},
    "bushfire-fuzz-spoof": {"center_mhz": 433.92, "span_khz": 900, "modulations": {"AUTO", "FSK", "GFSK", "QAM"}, "label": "BUSHFIRE-SPOOF-433"},
    "farm-gate-re-embedded": {"center_mhz": 902.3, "span_khz": 650, "modulations": {"AUTO", "4-FSK", "FSK"}, "label": "FARM-GATE-RE-902"},
    "farm-gate-hdl-flaw": {"center_mhz": 902.3, "span_khz": 650, "modulations": {"AUTO", "4-FSK", "FSK"}, "label": "FARM-GATE-HDL-902"},
    "farm-gate-rce": {"center_mhz": 902.3, "span_khz": 650, "modulations": {"AUTO", "4-FSK", "FSK"}, "label": "FARM-GATE-RCE-902"},
    "farm-gate-fuzz-spoof": {"center_mhz": 902.3, "span_khz": 650, "modulations": {"AUTO", "4-FSK", "FSK"}, "label": "FARM-GATE-SPOOF-902"},
}
TUNNEL_GNU_RADIO_CAPTURES = {
    "tunnel-reading-signals": {
        "stem": "ReadingSignals",
        "title": "Reading Signals",
        "path": "radio/GNURadio/Tunnel_Task/ReadingSignals.sigmf-data",
        "meta_path": "radio/GNURadio/Tunnel_Task/ReadingSignals.sigmf-meta",
        "grc_path": "radio/GNURadio/Tunnel_Task/ReadingSignals.grc",
        "python_path": "radio/GNURadio/Tunnel_Task/ReadingSignals.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 500,
        "flag": "FLAG{LIFE_IS_LIKE_A_BOX_OF_CHOCS}",
        "source_flag": "FLAG{LIFE_IS LIKE A BOX_OF_CHOCS}",
        "public_payload": True,
        "mission_note": "Already tuned tunnel sign packet.",
    },
    "tunnel-tuning": {
        "stem": "TuningSignals",
        "title": "Tuning Signals",
        "path": "radio/GNURadio/Tunnel_Task/TuningSignals.sigmf-data",
        "meta_path": "radio/GNURadio/Tunnel_Task/TuningSignals.sigmf-meta",
        "grc_path": "radio/GNURadio/Tunnel_Task/TuningSignals.grc",
        "python_path": "radio/GNURadio/Tunnel_Task/TuningSignals.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 500,
        "flag": "FLAG{HELLO_WORLD_I_DID_IT}",
        "source_flag": "FLAG{HELLO_WORLD_I_DID_IT}",
        "public_payload": True,
        "mission_note": "Same tunnel sign packet, but acquisition requires centre/span correction.",
    },
    "tunnel-basic-dos": {
        "stem": "DoSAttackMe",
        "title": "DoS Attack Me",
        "path": "radio/GNURadio/Tunnel_Task/DoSAttackMe.sigmf-data",
        "meta_path": "radio/GNURadio/Tunnel_Task/DoSAttackMe.sigmf-meta",
        "grc_path": "radio/GNURadio/Tunnel_Task/DoSAttackMe.grc",
        "python_path": "radio/GNURadio/Tunnel_Task/DoSAttackMe.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 500,
        "flag": "FLAG{OH_NO_YOU_DIDNT}",
        "source_flag": "FLAG{OH_NO_YOU_DIDNT}",
        "public_payload": False,
        "mission_note": "Tunnel sign packet used to show controlled local interference effects.",
    },
    "tunnel-packet-injection": {
        "stem": "InjectionTime",
        "title": "Injection Time",
        "path": "radio/GNURadio/Tunnel_Task/InjectionTime.sigmf-data",
        "meta_path": "radio/GNURadio/Tunnel_Task/InjectionTime.sigmf-meta",
        "grc_path": "radio/GNURadio/Tunnel_Task/InjectionTime.grc",
        "python_path": "radio/GNURadio/Tunnel_Task/InjectionTime.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 500,
        "flag": "FLAG{GET_VAXED_BABY}",
        "source_flag": "FLAG{GET_VAXED_BABY}",
        "public_payload": False,
        "mission_note": "Tunnel sign packet used as the local packet-injection target waveform.",
    },
}
SONG_META_GNU_RADIO_CAPTURES = {
    "broadcast-reading-signals": {
        "stem": "ReadingSignals",
        "title": "Song Metadata Reading Signals",
        "path": "radio/GNURadio/Song_Meta/ReadingSignals.sigmf-data",
        "meta_path": "radio/GNURadio/Song_Meta/ReadingSignals.sigmf-meta",
        "grc_path": "radio/GNURadio/Song_Meta/ReadingSignals.grc",
        "python_path": "radio/GNURadio/Song_Meta/ReadingSignals.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 50,
        "bits_per_symbol": 2,
        "bit_order": "msb",
        "modulation": "4-level ASK / 2-bit symbols",
        "flag": "FLAG{SOMEBODY_ONCE_TOLD_ME THE WORLD_IS}",
        "source_flag": "FLAG{SOMEBODY_ONCE_TOLD_ME THE WORLD_IS}",
        "public_payload": True,
        "mission_note": "Already tuned song metadata side-channel packet.",
    },
    "broadcast-tuning": {
        "stem": "TuningSignals",
        "title": "Song Metadata Tuning Signals",
        "path": "radio/GNURadio/Song_Meta/TuningSignals.sigmf-data",
        "meta_path": "radio/GNURadio/Song_Meta/TuningSignals.sigmf-meta",
        "grc_path": "radio/GNURadio/Song_Meta/TuningSignals.grc",
        "python_path": "radio/GNURadio/Song_Meta/TuningSignals.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 50,
        "bits_per_symbol": 2,
        "bit_order": "msb",
        "modulation": "4-level ASK / 2-bit symbols",
        "flag": "FLAG{FOR_THOSE_OF_YOU_WHO_JUST_TUNED_IN}",
        "source_flag": "FLAG{FOR_THOSE_OF_YOU_WHO_JUST_TUNED_IN}",
        "public_payload": True,
        "mission_note": "Song metadata side-channel packet that requires receiver centre/span correction.",
    },
    "broadcast-basic-dos": {
        "stem": "DoSAttackMe",
        "title": "Song Metadata DoS Attack Me",
        "path": "radio/GNURadio/Song_Meta/DoSAttackMe.sigmf-data",
        "meta_path": "radio/GNURadio/Song_Meta/DoSAttackMe.sigmf-meta",
        "grc_path": "radio/GNURadio/Song_Meta/DoSAttackMe.grc",
        "python_path": "radio/GNURadio/Song_Meta/DoSAttackMe.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 50,
        "bits_per_symbol": 2,
        "bit_order": "msb",
        "modulation": "4-level ASK / 2-bit symbols",
        "flag": "FLAG{HI_THERE_IM_DORY}",
        "source_flag": "",
        "public_payload": False,
        "mission_note": "Song metadata packet used as the reference receiver signal before controlled local interference.",
    },
    "broadcast-packet-injection": {
        "stem": "InjectionTime",
        "title": "Song Metadata Injection Time",
        "path": "radio/GNURadio/Song_Meta/InjectionTime.sigmf-data",
        "meta_path": "radio/GNURadio/Song_Meta/InjectionTime.sigmf-meta",
        "grc_path": "radio/GNURadio/Song_Meta/InjectionTime.grc",
        "python_path": "radio/GNURadio/Song_Meta/InjectionTime.py",
        "sample_rate": 44_200,
        "carrier_offset_hz": 10_000,
        "samples_per_symbol": 50,
        "bits_per_symbol": 2,
        "bit_order": "msb",
        "modulation": "4-level ASK / 2-bit symbols",
        "flag": "FLAG{THERES_NO_INJECTION_THAT_MAKES_YOU_SMARTER}",
        "source_flag": "FLAG{THERES_NO_INJECTION_THAT_MAKES_YOU_SMARTER}",
        "public_payload": False,
        "mission_note": "Song metadata packet used as the local packet-injection target waveform.",
    },
}
WEATHER_GNU_RADIO_CAPTURES = {
    "weather-boring-intercept": {
        "stem": "InterceptingReceiver",
        "title": "Weather Intercepting Receiver",
        "path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_Broadcast_Re.wav",
        "real_wav_path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_Broadcast_Re.wav",
        "imag_wav_path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_2_IM.wav",
        "grc_path": "radio/GNURadio/WeatherBroadcast/InterceptingReceiver.grc",
        "python_path": "radio/GNURadio/WeatherBroadcast/InterceptingReceiver.py",
        "sample_rate": 44_100,
        "carrier_offset_hz": 10_000,
        "carrier_offsets_hz": [10_000, 15_000],
        "hop_samples": 1_000,
        "samples_per_symbol": 1_000,
        "modulation": "patterned 10/15 kHz hopping complex weather audio",
        "source_mode": "weather_wav_pair",
        "lock_to_center": True,
        "public_payload": False,
        "mission_note": "Original weather report I/Q audio pair with a clear repeating hop pattern.",
    },
    "weather-boring-obscured": {
        "stem": "InterceptingReceiver_Task2",
        "title": "Obscured Weather Receiver",
        "path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_T2_RE.wav",
        "real_wav_path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_T2_RE.wav",
        "imag_wav_path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_T2_IM.wav",
        "grc_path": "radio/GNURadio/WeatherBroadcast/IThinkItsSecure.grc",
        "python_path": "radio/GNURadio/WeatherBroadcast/InterceptingReceiver_Task2.py",
        "sample_rate": 44_100,
        "carrier_offset_hz": -16_000,
        "carrier_offsets_hz": [-16_000, -10_000, -4_000, 3_000, 9_000, 15_000],
        "hop_samples": 4_410,
        "samples_per_symbol": 4_410,
        "modulation": "random frequency-hopping complex weather audio with RANDU QPSK phase symbols",
        "source_mode": "weather_wav_pair",
        "lock_to_center": True,
        "hop_mode": "keyed random",
        "hop_key": "weather-task-3.01-hop-v1",
        "phase_prng": "randu",
        "phase_seed": 1,
        "randu_samples_per_chip": 10,
        "public_payload": False,
        "mission_note": "Complex weather audio randomly hops among six RF channels every 100 ms. A separate fixed-seed RANDU sequence rotates only its QPSK phase symbols.",
    },
    "weather-boring-active-re": {
        "stem": "EmergencyWarningLight",
        "title": "Emergency Warning Light",
        "path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_T3_RE.wav",
        "real_wav_path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_T3_RE.wav",
        "imag_wav_path": "radio/GNURadio/WeatherBroadcast/WeatherRadio_T3_IM.wav",
        "grc_path": "radio/GNURadio/WeatherBroadcast/EmergencyWarningLight.grc",
        "python_path": "radio/GNURadio/WeatherBroadcast/EmergencyWarningLight.py",
        "sample_rate": 3_000_000,
        "carrier_offset_hz": 500_000,
        "carrier_offsets_hz": [500_000],
        "hop_samples": 1_000,
        "samples_per_symbol": 32,
        "modulation": "32-bit custom-interleaved alarm metadata with fixed-seed RANDU phase shifts",
        "source_mode": "weather_alarm_wav_pair",
        "lock_to_center": True,
        "randu_samples_per_chip": 10,
        "emergency": 0xB,
        "public_payload": False,
        "mission_note": "Third weather report pair carrying the custom alarm packet checked by the extracted C decoder.",
    },
}
GNU_RADIO_CAPTURE_GROUPS = (
    TUNNEL_GNU_RADIO_CAPTURES,
    SONG_META_GNU_RADIO_CAPTURES,
    WEATHER_GNU_RADIO_CAPTURES,
)
FLOWGRAPH_CONFIG_CACHE: dict[tuple[str, int], dict] = {}
SCRIPT_TERMINALS: dict[str, dict] = {}
EXTERNAL_FEED_LOCK = threading.Lock()
EXTERNAL_FEEDS: dict[str, dict] = {}
EXTERNAL_INGEST = {"host": "127.0.0.1", "port": 9100, "enabled": False, "error": ""}
EXTERNAL_INGEST_SERVER: SignalIngestTCPServer | None = None
MAX_EXTERNAL_LINE_BYTES = 2_000_000
MAX_EXTERNAL_IQ_SAMPLES = 131_072


def default_external_feed(challenge_id: str = "external") -> dict:
    target = RF_TARGETS.get(challenge_id, RF_TARGETS["tunnel-reading-signals"])
    center_hz = float(target["center_mhz"]) * 1_000_000
    span_hz = float(target["span_khz"]) * 1_000
    return {
        "challenge_id": challenge_id,
        "scheme_id": "EXTERNAL-SIGNAL-INGEST-V1",
        "center_hz": center_hz,
        "span_hz": span_hz,
        "sample_rate_hz": span_hz,
        "bins": 384,
        "frames": 1_000_000,
        "rows": deque(maxlen=240),
        "pending": deque(maxlen=512),
        "sequence": 0,
        "last_seen": 0.0,
        "client": "",
        "parser": {
            "stage": "raw_iq",
            "confidence": 0,
            "bit_buffer": "waiting for external frames",
            "fields": {"protocol": "Signal Forge external ingest v1"},
            "note": "Send JSON-lines FFT rows or cf32_le IQ blocks to the ingest port.",
        },
        "sources": [{"label": "External user signal", "kind": "external", "offset_hz": 0, "bandwidth_hz": max(1000, span_hz / 16)}],
        "annotations": [{"label": "external centre", "offset_hz": 0, "color": "#ff4ad2"}],
        "protocol_notes": {
            "modulation": "user supplied",
            "source": "External TCP JSON-lines ingest",
            "raw_path": "/api/rf/external/status",
        },
    }


def external_feed_for(challenge_id: str) -> dict:
    with EXTERNAL_FEED_LOCK:
        if challenge_id not in EXTERNAL_FEEDS:
            EXTERNAL_FEEDS[challenge_id] = default_external_feed(challenge_id)
        return EXTERNAL_FEEDS[challenge_id]

RECEIVE_FLAG_TASKS = {
    "tunnel-reading-signals",
    "tunnel-tuning",
    "broadcast-reading-signals",
    "weather-boring-intercept",
    "civilian-emergency-intercept",
}
DECODE_FLAG_TASKS = {
    "broadcast-tuning",
    "weather-boring-obscured",
    "civilian-emergency-obscured",
    "farm-gate-re-embedded",
}
INTERFERENCE_FLAG_TASKS = {"tunnel-basic-dos", "broadcast-basic-dos"}
TRANSMIT_FLAG_TASKS = {
    "tunnel-packet-injection",
    "broadcast-packet-injection",
    "bushfire-rce",
    "bushfire-fuzz-spoof",
    "farm-gate-rce",
}
SEND_FLAG_TASKS = {
    "weather-boring-active-re",
    "civilian-emergency-active-re",
    "bushfire-re-embedded",
    "bushfire-hdl-flaw",
    "farm-gate-hdl-flaw",
    "farm-gate-fuzz-spoof",
}


def session_id_from(handler: SimpleHTTPRequestHandler, body: dict | None = None) -> str:
    candidate = str((body or {}).get("session_id", "") or handler.headers.get("X-Signal-Session", "")).strip()
    if not candidate:
        return "anonymous"
    return "".join(character for character in candidate if character.isalnum() or character in "-_")[:80] or "anonymous"


def session_token(session_id: str, purpose: str, length: int = 16) -> str:
    digest = hmac.new(RANGE_SECRET, f"{session_id}:{purpose}".encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return digest[:length]


def flag_for(session_id: str, challenge_id: str) -> str:
    return f"CTF{{{session_token(session_id, f'flag:{challenge_id}')}}}"


def user_data_for(session_id: str) -> dict:
    token = session_token(session_id, "user-data", 20)
    return {
        "operator_id": f"OP-{token[:6]}",
        "callsign": f"FORGE-{token[6:10]}",
        "vehicle_id": f"VH-{token[10:14]}",
        "range_nonce": token[14:20],
    }


def load_challenges() -> list[dict]:
    with CHALLENGES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def public_static_artifact_paths() -> set[str]:
    """Return the local files explicitly published by challenge metadata."""
    allowed: set[str] = set()
    for task in load_challenges():
        for artifact in task.get("artifacts", []):
            request_path = unquote(urlparse(str(artifact.get("href", ""))).path)
            if not request_path or request_path.startswith("/api/"):
                continue
            normalized = f"/{request_path.lstrip('/')}"
            try:
                bounded_project_path(normalized.lstrip("/"))
            except ValueError:
                continue
            allowed.add(normalized)
    return allowed


def validate_public_static_artifacts() -> None:
    """Fail startup when a challenge advertises a missing local resource."""
    missing = [
        request_path
        for request_path in sorted(public_static_artifact_paths())
        if not bounded_project_path(request_path.lstrip("/")).is_file()
    ]
    if missing:
        raise RuntimeError(f"Missing public challenge artifacts: {', '.join(missing)}")


def load_contexts() -> list[dict]:
    with CONTEXTS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_validation_config() -> dict:
    with VALIDATION_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def configured_flags_for(challenge_id: str) -> list[str]:
    validation = load_validation_config()
    flags: list[str] = []
    primary = str(validation.get("flags", {}).get(challenge_id, "")).strip()
    if primary:
        flags.append(primary)
    for alias in validation.get("aliases", {}).get(challenge_id, []):
        alias_text = str(alias).strip()
        if alias_text:
            flags.append(alias_text)
    gnu_radio_capture = gnu_radio_capture_for(challenge_id)
    if gnu_radio_capture:
        for key in ("flag", "source_flag"):
            value = str(gnu_radio_capture.get(key, "")).strip()
            if value:
                flags.append(value)
    unique: list[str] = []
    seen: set[str] = set()
    for flag in flags:
        normalized = flag.upper()
        if normalized not in seen:
            unique.append(flag)
            seen.add(normalized)
    return unique


def expected_flag_for(session_id: str, challenge_id: str) -> str:
    static_flags = configured_flags_for(challenge_id)
    return static_flags[0] if static_flags else flag_for(session_id, challenge_id)


def is_valid_flag(session_id: str, challenge_id: str, submitted: str) -> bool:
    expected = {flag.upper() for flag in configured_flags_for(challenge_id)}
    expected.add(flag_for(session_id, challenge_id).upper())
    return submitted.strip().upper() in expected


def gnu_radio_capture_for(challenge_id: str | None) -> dict | None:
    if not challenge_id:
        return None
    for capture_group in GNU_RADIO_CAPTURE_GROUPS:
        capture = capture_group.get(challenge_id)
        if capture:
            return capture
    return None


def gnu_radio_settings(challenge_id: str | None) -> dict | None:
    capture = gnu_radio_capture_for(challenge_id)
    if not capture:
        return None
    target = RF_TARGETS.get(challenge_id, RF_TARGETS["tunnel-reading-signals"])
    return {
        "path": capture["path"],
        "datatype": "cf32_le",
        "sample_rate": capture["sample_rate"],
        "center_hz": float(target["center_mhz"]) * 1_000_000,
        "fft_bins": 512,
        "max_frames": 300,
        "samples_per_symbol": capture["samples_per_symbol"],
        "bits_per_symbol": capture.get("bits_per_symbol", 1),
        "decode_max_samples": 500_000,
        "source_mode": capture.get("source_mode", "generated_python_flowgraph"),
        "capture": capture,
    }


def tunnel_gnu_radio_settings(challenge_id: str) -> dict | None:
    return gnu_radio_settings(challenge_id)


def bounded_project_path(relative_path: str | Path) -> Path:
    path = Path(str(relative_path))
    target = path if path.is_absolute() else ROOT / path
    target = target.resolve()
    try:
        target.relative_to(ROOT)
    except ValueError as error:
        raise ValueError("Artifact path must remain inside the project") from error
    return target


def fft_in_place(values: list[complex]) -> None:
    """Dependency-free radix-2 FFT used for local GNU Radio capture previews."""
    size = len(values)
    target = 0
    for source in range(1, size):
        bit = size >> 1
        while target & bit:
            target ^= bit
            bit >>= 1
        target ^= bit
        if source < target:
            values[source], values[target] = values[target], values[source]

    length = 2
    while length <= size:
        angle = -2.0 * math.pi / length
        step = complex(math.cos(angle), math.sin(angle))
        half = length // 2
        for start in range(0, size, length):
            phase = 1.0 + 0.0j
            for index in range(start, start + half):
                even = values[index]
                odd = values[index + half] * phase
                values[index] = even + odd
                values[index + half] = even - odd
                phase *= step
        length <<= 1


def nearest_power_of_two(value: int) -> int:
    value = max(1, int(value))
    return 1 << (value.bit_length() - 1)


def resample_row(row: list[float], bins: int) -> list[float]:
    if not row:
        return [0.0] * bins
    if len(row) == bins:
        return [round(max(0.0, min(1.0, float(value))), 4) for value in row]
    return [
        round(max(0.0, min(1.0, float(row[round(index * (len(row) - 1) / max(1, bins - 1))]))), 4)
        for index in range(bins)
    ]


def fft_row_from_complex(samples: list[complex], requested_bins: int = 384) -> tuple[list[float], list[float], int]:
    fft_size = nearest_power_of_two(min(len(samples), max(64, min(2048, requested_bins))))
    if len(samples) < fft_size:
        raise ValueError(f"Need at least {fft_size} complete complex samples")
    window = [0.5 - 0.5 * math.cos(2.0 * math.pi * index / max(1, fft_size - 1)) for index in range(fft_size)]
    values = [samples[index] * window[index] for index in range(fft_size)]
    fft_in_place(values)
    shifted = values[fft_size // 2 :] + values[: fft_size // 2]
    power_db = [20.0 * math.log10(max(1e-12, abs(value))) for value in shifted]
    peak_db = max(power_db)
    floor_db = max(min(power_db), peak_db - 80)
    dynamic_range = max(1.0, peak_db - floor_db)
    row = [round(max(0.0, min(1.0, (value - floor_db) / dynamic_range)), 4) for value in power_db]
    time_peak = max(1e-9, max(abs(value.real) for value in samples[: min(len(samples), 256)]))
    time_samples = [
        round(max(-1.0, min(1.0, samples[round(index * (min(len(samples), 256) - 1) / 159)].real / time_peak)), 4)
        for index in range(160)
    ]
    return row, time_samples, fft_size


def public_external_feed_meta(feed: dict) -> dict:
    return {
        "challenge_id": feed["challenge_id"],
        "scheme_id": feed["scheme_id"],
        "center_hz": feed["center_hz"],
        "span_hz": feed["span_hz"],
        "sample_rate_hz": feed["sample_rate_hz"],
        "bins": feed["bins"],
        "frames": feed["frames"],
        "sources": feed["sources"],
        "annotations": feed["annotations"],
        "protocol_notes": feed["protocol_notes"],
        "parser": feed["parser"],
        "external_ingest": {
            "host": EXTERNAL_INGEST["host"],
            "port": EXTERNAL_INGEST["port"],
            "enabled": EXTERNAL_INGEST["enabled"],
            "error": EXTERNAL_INGEST["error"],
            "protocol": "json-lines+rawiq/v1",
        },
        "last_seen": feed["last_seen"],
        "pending_frames": len(feed["pending"]),
        "buffered_rows": len(feed["rows"]),
        "client": feed.get("client", ""),
        "description": "Live frames supplied by an external script, GNU Radio bridge, or C/C++ client over TCP JSON-lines or framed raw IQ.",
    }


def ingest_external_signal(payload: dict, client: str = "") -> dict:
    message_type = str(payload.get("type", "fft")).lower()
    challenge_id = str(payload.get("challenge_id") or payload.get("channel") or "external").strip()[:80] or "external"
    if message_type == "reset":
        with EXTERNAL_FEED_LOCK:
            EXTERNAL_FEEDS[challenge_id] = default_external_feed(challenge_id)
        return {"ok": True, "challenge_id": challenge_id, "message": "feed reset"}

    with EXTERNAL_FEED_LOCK:
        feed = EXTERNAL_FEEDS.setdefault(challenge_id, default_external_feed(challenge_id))
        if "center_hz" in payload:
            feed["center_hz"] = float(payload["center_hz"])
        if "span_hz" in payload:
            feed["span_hz"] = max(1.0, float(payload["span_hz"]))
        if "sample_rate_hz" in payload:
            feed["sample_rate_hz"] = max(1.0, float(payload["sample_rate_hz"]))
            feed["span_hz"] = float(payload.get("span_hz", feed["sample_rate_hz"]))
        if "scheme_id" in payload:
            feed["scheme_id"] = str(payload["scheme_id"])[:120]
        if "modulation" in payload:
            feed["protocol_notes"]["modulation"] = str(payload["modulation"])[:120]
        if "source_label" in payload:
            feed["sources"] = [{"label": str(payload["source_label"])[:80], "kind": "external", "offset_hz": 0, "bandwidth_hz": max(1000, feed["span_hz"] / 16)}]
        requested_bins = int(payload.get("bins", feed.get("bins", 384)))

    if message_type in {"meta", "hello"}:
        with EXTERNAL_FEED_LOCK:
            feed["last_seen"] = time.time()
            feed["client"] = client
            return {"ok": True, "challenge_id": challenge_id, "meta": public_external_feed_meta(feed)}

    parser = payload.get("parser") if isinstance(payload.get("parser"), dict) else None
    if message_type in {"fft", "row"}:
        row_values = payload.get("row")
        if not isinstance(row_values, list):
            raise ValueError("fft message requires row: [0.0..1.0]")
        bins = max(16, min(2048, requested_bins or len(row_values)))
        row = resample_row([float(value) for value in row_values], bins)
        samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
        samples = [round(max(-1.0, min(1.0, float(value))), 4) for value in samples[:512]]
    elif message_type == "iq":
        with EXTERNAL_FEED_LOCK:
            feed["protocol_notes"]["source"] = "External TCP framed raw IQ ingest"
        data = payload.get("data") or payload.get("iq_base64")
        if not isinstance(data, str):
            raise ValueError("iq message requires base64 cf32_le data")
        raw = base64.b64decode(data, validate=True)
        complete = len(raw) - len(raw) % 8
        if complete < 512:
            raise ValueError("iq message needs at least 64 cf32_le samples")
        samples_complex = [complex(real, imag) for real, imag in struct.iter_unpack("<ff", raw[:complete])]
        row, samples, bins = fft_row_from_complex(samples_complex, requested_bins=requested_bins)
    else:
        raise ValueError(f"Unsupported external signal message type: {message_type}")

    with EXTERNAL_FEED_LOCK:
        feed = EXTERNAL_FEEDS.setdefault(challenge_id, default_external_feed(challenge_id))
        feed["bins"] = len(row)
        feed["frames"] = max(feed["frames"], feed["sequence"] + 1)
        feed["last_seen"] = time.time()
        feed["client"] = client
        feed["parser"] = parser or {
            "stage": "fft" if message_type in {"fft", "row"} else "raw_iq",
            "confidence": float(payload.get("confidence", 0.7 if message_type in {"fft", "row"} else 0.76)),
            "bit_buffer": str(payload.get("bit_buffer", "external frame")),
            "fields": {
                "message_type": message_type,
                "sequence": feed["sequence"],
                "bins": len(row),
                "sample_count": len(samples),
            },
            "note": "Frame accepted from external signal ingest.",
        }
        frame = {
            "frame": feed["sequence"],
            "row": row,
            "samples": samples,
            "parser": feed["parser"],
            "external": True,
        }
        feed["rows"].append(row)
        feed["pending"].append(frame)
        feed["sequence"] += 1
        return {"ok": True, "challenge_id": challenge_id, "sequence": feed["sequence"] - 1, "bins": len(row)}


def external_feed_snapshot(challenge_id: str) -> dict:
    with EXTERNAL_FEED_LOCK:
        feed = EXTERNAL_FEEDS.get(challenge_id) or EXTERNAL_FEEDS.get("external")
        if feed is None:
            feed = EXTERNAL_FEEDS.setdefault(challenge_id, default_external_feed(challenge_id))
        return public_external_feed_meta(feed)


def external_feed_next_frame(challenge_id: str, last_sequence: int) -> dict | None:
    with EXTERNAL_FEED_LOCK:
        feed = EXTERNAL_FEEDS.get(challenge_id) or EXTERNAL_FEEDS.get("external")
        if feed is None:
            return None
        for frame in feed["pending"]:
            if int(frame.get("frame", -1)) > last_sequence:
                return dict(frame)
    return None


def parse_ingest_options(line: str) -> dict:
    options: dict[str, str] = {}
    for token in line.strip().split()[2:]:
        key, separator, value = token.partition("=")
        if separator and key:
            options[key.strip()] = value.strip()
    return options


def ingest_external_iq_bytes(options: dict, raw: bytes, client: str = "") -> dict:
    payload = dict(options)
    payload["type"] = "iq"
    payload["data"] = base64.b64encode(raw).decode("ascii")
    return ingest_external_signal(payload, client=client)


class SignalIngestTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class SignalIngestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        client = f"{self.client_address[0]}:{self.client_address[1]}"
        while True:
            raw_line = self.rfile.readline(MAX_EXTERNAL_LINE_BYTES + 1)
            if not raw_line:
                return
            if len(raw_line) > MAX_EXTERNAL_LINE_BYTES:
                self.write_ingest_response({"ok": False, "error": "ingest line too large"})
                return
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                upper = line.upper()
                if line.startswith("{"):
                    result = ingest_external_signal(json.loads(line), client=client)
                    self.write_ingest_response(result)
                elif upper.startswith("SFORGE IQCF32 "):
                    result = self.handle_single_iq_frame(line, client)
                    self.write_ingest_response(result)
                elif upper.startswith("SFORGE RAWIQ "):
                    self.handle_raw_iq_stream(line, client)
                    return
                else:
                    self.write_ingest_response(
                        {
                            "ok": False,
                            "error": "unknown ingest record; use JSON-lines, SFORGE IQCF32, or SFORGE RAWIQ",
                        }
                    )
            except (json.JSONDecodeError, ValueError, OSError, struct.error) as error:
                self.write_ingest_response({"ok": False, "error": str(error)})

    def handle_single_iq_frame(self, line: str, client: str) -> dict:
        options = parse_ingest_options(line)
        sample_count = int(options.get("samples", "0"))
        if sample_count <= 0 or sample_count > MAX_EXTERNAL_IQ_SAMPLES:
            raise ValueError(f"samples must be between 1 and {MAX_EXTERNAL_IQ_SAMPLES}")
        raw = self.rfile.read(sample_count * 8)
        if len(raw) != sample_count * 8:
            raise ValueError(f"expected {sample_count * 8} IQ bytes, received {len(raw)}")
        return ingest_external_iq_bytes(options, raw, client=client)

    def handle_raw_iq_stream(self, line: str, client: str) -> None:
        options = parse_ingest_options(line)
        block_samples = int(options.get("block_samples", options.get("samples", "2048")))
        if block_samples <= 0 or block_samples > MAX_EXTERNAL_IQ_SAMPLES:
            raise ValueError(f"block_samples must be between 1 and {MAX_EXTERNAL_IQ_SAMPLES}")
        options["samples"] = str(block_samples)
        self.write_ingest_response({"ok": True, "mode": "rawiq", "block_samples": block_samples})
        block_bytes = block_samples * 8
        while True:
            raw = self.rfile.read(block_bytes)
            if not raw:
                return
            if len(raw) < 512:
                return
            ingest_external_iq_bytes(options, raw, client=client)

    def write_ingest_response(self, payload: dict) -> None:
        try:
            self.wfile.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return


def start_external_ingest_server() -> None:
    global EXTERNAL_INGEST_SERVER
    host = os.environ.get("SIGNAL_INGEST_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("SIGNAL_INGEST_PORT", "9100"))
    except ValueError:
        port = 9100
    EXTERNAL_INGEST.update({"host": host, "port": port, "enabled": False, "error": ""})
    try:
        EXTERNAL_INGEST_SERVER = SignalIngestTCPServer((host, port), SignalIngestHandler)
        thread = threading.Thread(target=EXTERNAL_INGEST_SERVER.serve_forever, daemon=True, name="signal-ingest")
        thread.start()
        EXTERNAL_INGEST.update({"enabled": True, "error": ""})
        print(f"Signal ingest listening on {host}:{port} (Signal Forge ingest v1)")
    except OSError as error:
        EXTERNAL_INGEST_SERVER = None
        EXTERNAL_INGEST.update({"enabled": False, "error": str(error)})
        print(f"Signal ingest unavailable on {host}:{port}: {error}")


def configured_gnu_radio_path(settings: dict | None = None) -> tuple[Path, Path]:
    settings = settings or load_config().get("gnu_radio_capture", {})
    relative_path = Path(str(settings.get("path", "radio/GNURadio/ReadingSignals.sigmf-data")))
    capture_path = bounded_project_path(relative_path)
    return capture_path, relative_path


def parse_number_literal(value: str, fallback: float = 0.0) -> float:
    try:
        return float(value.replace("_", ""))
    except (AttributeError, ValueError):
        return fallback


def payload_bits_msb(payload: bytes) -> str:
    return "".join(f"{byte:08b}" for byte in payload)


def symbols_from_bits(bits: str, bits_per_symbol: int) -> list[int]:
    bits_per_symbol = max(1, bits_per_symbol)
    if bits_per_symbol == 1:
        return [1 if bit == "1" else 0 for bit in bits]
    return [
        int(bits[index : index + bits_per_symbol].ljust(bits_per_symbol, "0"), 2)
        for index in range(0, len(bits), bits_per_symbol)
    ]


def generated_flowgraph_config(settings: dict) -> dict:
    capture_info = settings.get("capture", {})
    relative = capture_info.get("python_path")
    if not relative:
        raise FileNotFoundError("No generated GNU Radio Python script is mapped for this challenge")
    script_path = bounded_project_path(relative)
    if not script_path.is_file():
        raise FileNotFoundError(f"Generated GNU Radio Python script not found: {relative}")
    cache_key = (str(script_path), script_path.stat().st_mtime_ns)
    cached = FLOWGRAPH_CONFIG_CACHE.get(cache_key)
    if cached:
        return cached

    source = script_path.read_text(encoding="utf-8", errors="replace")
    source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
    flowgraph_blocks = list(
        dict.fromkeys(
            re.findall(
                r"self\.[A-Za-z_][A-Za-z0-9_]*\s*=\s*"
                r"((?:[A-Za-z_][A-Za-z0-9_]*\.)+[A-Za-z_][A-Za-z0-9_]*)\s*\(",
                source,
            )
        )
    )
    payload_match = re.search(r"vector_source_b\(list\((b(?:\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*'))\)", source)
    if not payload_match:
        raise ValueError(f"Could not find vector_source_b byte payload in {relative}")
    payload = ast.literal_eval(payload_match.group(1))
    if not isinstance(payload, (bytes, bytearray)):
        raise ValueError(f"GNU Radio vector payload in {relative} is not a bytes literal")
    payload = bytes(payload)

    sample_rate_match = re.search(r"self\.samp_rate\s*=\s*samp_rate\s*=\s*([0-9_]+(?:\.[0-9_]+)?)", source)
    repeat_match = re.search(r"blocks\.repeat\(gr\.sizeof_char\*1,\s*([0-9_]+)\)", source)
    carrier_match = re.search(r"analog\.sig_source_c\([^,]+,\s*analog\.GR_COS_WAVE,\s*([0-9_]+(?:\.[0-9_]+)?)", source)
    noise_match = re.search(r"noise_voltage\s*=\s*([0-9_]+(?:\.[0-9_]+)?)", source)
    repack_match = re.search(r"repack_bits_bb\(\s*([0-9_]+)\s*,\s*([0-9_]+)", source)
    interleaved_match = re.search(
        r"interleaved_char_to_complex\(\s*(?:True|False)\s*,\s*"
        r"([0-9_]+(?:\.[0-9_]+)?)",
        source,
    )

    repeat = int(parse_number_literal(repeat_match.group(1), settings.get("samples_per_symbol", 500) * 2)) if repeat_match else int(settings.get("samples_per_symbol", 500)) * 2
    bits_per_symbol = int(parse_number_literal(repack_match.group(2), 1)) if repack_match else int(settings.get("bits_per_symbol", 1))
    bits = payload_bits_msb(payload)
    symbols = symbols_from_bits(bits, bits_per_symbol)
    samples_per_symbol = max(1, repeat // 2)
    script_hash_seed = int(source_sha256[:8], 16)
    config = {
        "source_mode": "generated_python_flowgraph",
        "source_script": str(relative).replace("\\", "/"),
        "script_size_bytes": script_path.stat().st_size,
        "source_sha256": source_sha256,
        "flowgraph_blocks": flowgraph_blocks,
        "flowgraph_block_count": len(flowgraph_blocks),
        "sample_rate": parse_number_literal(sample_rate_match.group(1), float(settings.get("sample_rate", 44_200))) if sample_rate_match else float(settings.get("sample_rate", 44_200)),
        "carrier_offset_hz": parse_number_literal(carrier_match.group(1), float(capture_info.get("carrier_offset_hz", 10_000))) if carrier_match else float(capture_info.get("carrier_offset_hz", 10_000)),
        "repeat": repeat,
        "samples_per_symbol": samples_per_symbol,
        "bits_per_symbol": bits_per_symbol,
        "bit_order": "msb" if "GR_MSB_FIRST" in source or str(settings.get("bit_order", "msb")).lower() == "msb" else "lsb",
        "payload": payload,
        "payload_text": payload.decode("latin-1", errors="replace"),
        "bits": bits,
        "symbols": symbols or [0],
        "period_samples": max(1, len(symbols) * samples_per_symbol),
        "noise_voltage": parse_number_literal(noise_match.group(1), 0.0) if noise_match else 0.0,
        "interleaved_char_to_complex": bool(interleaved_match),
        "interleaved_scale": parse_number_literal(interleaved_match.group(1), 1.0) if interleaved_match else 1.0,
        "seed": script_hash_seed,
        "has_repack_bits": bool(repack_match),
    }
    FLOWGRAPH_CONFIG_CACHE.clear()
    FLOWGRAPH_CONFIG_CACHE[cache_key] = config
    return config


def gnu_radio_runtime_settings(settings: dict) -> dict:
    runtime = dict(settings)
    source_mode = runtime.get("source_mode")
    if source_mode in {"weather_wav_pair", "weather_alarm_wav_pair"}:
        capture = runtime.get("capture", {})
        real_path = bounded_project_path(capture["real_wav_path"])
        imag_path = bounded_project_path(capture["imag_wav_path"])
        with wave.open(str(real_path), "rb") as real_wav, wave.open(str(imag_path), "rb") as imag_wav:
            source_frames = min(real_wav.getnframes(), imag_wav.getnframes())
        expansion = 32 if source_mode == "weather_alarm_wav_pair" else 1
        runtime["sample_count"] = max(1, source_frames * expansion)
        return runtime
    if source_mode != "generated_python_flowgraph":
        return runtime
    flowgraph = generated_flowgraph_config(runtime)
    runtime.update(
        {
            "flowgraph": flowgraph,
            "sample_rate": flowgraph["sample_rate"],
            "samples_per_symbol": flowgraph["samples_per_symbol"],
            "bits_per_symbol": flowgraph["bits_per_symbol"],
            "bit_order": flowgraph["bit_order"],
        }
    )
    capture = dict(runtime.get("capture", {}))
    capture["carrier_offset_hz"] = flowgraph["carrier_offset_hz"]
    capture["source_mode"] = flowgraph["source_mode"]
    runtime["capture"] = capture
    return runtime


def deterministic_noise(seed: int, value: int) -> float:
    mixed = (value ^ seed) & 0xFFFFFFFF
    mixed ^= (mixed << 13) & 0xFFFFFFFF
    mixed ^= mixed >> 17
    mixed ^= (mixed << 5) & 0xFFFFFFFF
    return (mixed & 0xFFFFFFFF) / 0xFFFFFFFF - 0.5


def read_wav_mono_samples(path: Path, start_frame: int, frame_count: int) -> list[float]:
    """Read one channel from a PCM WAV file, looping when a request crosses EOF."""
    if frame_count <= 0:
        return []
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        total_frames = source.getnframes()
        if total_frames <= 0:
            return [0.0] * frame_count
        if sample_width not in {1, 2, 3, 4}:
            raise ValueError(f"Unsupported WAV sample width {sample_width} in {path.name}")

        output: list[float] = []
        frame = start_frame % total_frames
        while len(output) < frame_count:
            source.setpos(frame)
            take = min(frame_count - len(output), total_frames - frame)
            raw = source.readframes(take)
            frame_bytes = channels * sample_width
            for offset in range(0, len(raw) - frame_bytes + 1, frame_bytes):
                sample = raw[offset : offset + sample_width]
                if sample_width == 1:
                    value = (sample[0] - 128) / 128.0
                else:
                    signed = int.from_bytes(sample, "little", signed=True)
                    value = signed / float(1 << (sample_width * 8 - 1))
                output.append(max(-1.0, min(1.0, value)))
            frame = 0
            if not raw:
                break
        if len(output) < frame_count:
            output.extend([0.0] * (frame_count - len(output)))
        return output


def alarm_encode_packet(data: int, emergency: int = 0xB) -> int:
    """Mirror the GNU Radio alarm encoder: data MSB-first, alarm LSB-first."""
    packet = 0
    packet_length = 0
    pair_count = 0
    emergency_index = 0
    data &= 0xFFFF
    emergency &= 0x0F
    for bit_index in range(15, -1, -1):
        data_bit = (data >> bit_index) & 1
        packet = (packet << 1) | data_bit
        packet_length += 1
        if data_bit:
            pair_count += 1
        if pair_count == 2 and emergency_index < 4:
            packet = (packet << 1) | ((emergency >> emergency_index) & 1)
            packet_length += 1
            emergency_index += 1
            pair_count = 0
    while emergency_index < 4:
        packet = (packet << 1) | ((emergency >> emergency_index) & 1)
        packet_length += 1
        emergency_index += 1
    return (packet << (32 - packet_length)) & 0xFFFFFFFF


def alarm_decode_packet(packet: int) -> int:
    """Mirror AlarmDecoder in MyEmbeddedAlarmSystem.c exactly."""
    packet &= 0xFFFFFFFF
    input_mask = 1 << 31
    output_mask = 1
    emergency = 0
    pair_count = 0
    recovered = 0
    for _ in range(16):
        if packet & input_mask:
            pair_count += 1
        input_mask >>= 1
        if pair_count == 2 and recovered < 4:
            if packet & input_mask:
                emergency |= output_mask
            output_mask <<= 1
            recovered += 1
            pair_count = 0
            input_mask >>= 1
    while recovered < 4:
        if packet & input_mask:
            emergency |= output_mask
        input_mask >>= 1
        output_mask <<= 1
        recovered += 1
    return emergency


def parse_u32_packet(value: object) -> int:
    text = str(value).strip().replace("_", "")
    if not text:
        raise ValueError("Enter one 32-bit packet as hexadecimal or decimal.")
    try:
        packet = int(text, 0)
    except ValueError as error:
        raise ValueError("Packet must be a number such as 0x1234ABCD.") from error
    if packet < 0 or packet > 0xFFFFFFFF:
        raise ValueError("Packet must fit in an unsigned 32-bit value.")
    return packet


def randu_state_at_chip(chip_index: int, seed: int = 1) -> int:
    state = (int(seed) & 0x7FFFFFFF) or 1
    if state % 2 == 0:
        state += 1
    return (state * pow(65_539, max(0, chip_index) + 1, 1 << 31)) & 0x7FFFFFFF


def weather_hop_offset(capture: dict, hop_index: int) -> float:
    offsets = [float(value) for value in capture.get("carrier_offsets_hz", [capture.get("carrier_offset_hz", 0)])]
    if not offsets:
        return 0.0
    if str(capture.get("hop_mode", "")).lower() == "keyed random":
        hop_key = str(capture.get("hop_key", "weather-hop"))
        digest = hashlib.sha256(f"{hop_key}:{max(0, hop_index)}".encode("utf-8")).digest()
        return offsets[int.from_bytes(digest[:4], "big") % len(offsets)]
    return offsets[hop_index % len(offsets)]


def weather_carrier_phase(capture: dict, sample_rate: float, sample_index: int, hop_samples: int) -> float:
    """Return a phase-continuous carrier position for arbitrary sample access."""
    sample_index = max(0, int(sample_index))
    complete_hops, partial_samples = divmod(sample_index, hop_samples)
    accumulated_cycles = sum(
        weather_hop_offset(capture, hop_index) * hop_samples
        for hop_index in range(complete_hops)
    )
    accumulated_cycles += weather_hop_offset(capture, complete_hops) * partial_samples
    return 2.0 * math.pi * accumulated_cycles / sample_rate


def weather_wav_iq_samples(settings: dict, start_sample: int, sample_count: int) -> list[complex]:
    capture = settings.get("capture", {})
    real_path = bounded_project_path(capture["real_wav_path"])
    imag_path = bounded_project_path(capture["imag_wav_path"])
    source_mode = settings.get("source_mode")
    alarm_mode = source_mode == "weather_alarm_wav_pair"
    expansion = 32 if alarm_mode else 1
    first_frame = start_sample // expansion
    last_sample = start_sample + max(0, sample_count - 1)
    required_frames = last_sample // expansion - first_frame + 1 if sample_count else 0
    real_values = read_wav_mono_samples(real_path, first_frame, required_frames)
    imag_values = read_wav_mono_samples(imag_path, first_frame, required_frames)
    sample_rate = max(1.0, float(settings.get("sample_rate", 44_100)))
    hop_samples = max(1, int(capture.get("hop_samples", 1_000)))
    randu_samples = int(capture.get("randu_samples_per_chip", 0))
    emergency = int(capture.get("emergency", 0xB))
    square_signal = bool(capture.get("square_signal", False))
    noise_scale = 0.008
    samples: list[complex] = []
    phase_table = (1.0 + 0.0j, 0.0 + 1.0j, -1.0 + 0.0j, 0.0 - 1.0j)
    current_chip_index = start_sample // randu_samples if randu_samples else -1
    randu_state = (
        randu_state_at_chip(current_chip_index, int(capture.get("phase_seed", 1)))
        if randu_samples
        else 0
    )
    current_hop_index = start_sample // hop_samples
    current_carrier_offset = weather_hop_offset(capture, current_hop_index)
    carrier_phase = weather_carrier_phase(capture, sample_rate, start_sample, hop_samples)

    packet_cache: dict[int, tuple[int, int]] = {}
    for local_index in range(sample_count):
        absolute_index = start_sample + local_index
        frame_index = absolute_index // expansion
        source_index = frame_index - first_frame
        if alarm_mode:
            cached = packet_cache.get(source_index)
            if cached is None:
                real_word = int(round(real_values[source_index] * 32767.0)) & 0xFFFF
                imag_word = int(round(imag_values[source_index] * 32767.0)) & 0xFFFF
                cached = (
                    alarm_encode_packet(real_word, emergency),
                    alarm_encode_packet(imag_word, emergency),
                )
                packet_cache[source_index] = cached
            bit_index = absolute_index % 32
            source_value = complex((cached[0] >> (31 - bit_index)) & 1, (cached[1] >> (31 - bit_index)) & 1)
        else:
            source_value = complex(real_values[source_index], imag_values[source_index])

        if randu_samples:
            chip_index = absolute_index // randu_samples
            while current_chip_index < chip_index:
                randu_state = (65_539 * randu_state) & 0x7FFFFFFF
                current_chip_index += 1
            shifted = source_value * phase_table[(randu_state >> 28) & 0x03]
            source_value = source_value * shifted if square_signal else shifted

        hop_index = absolute_index // hop_samples
        if hop_index != current_hop_index:
            current_hop_index = hop_index
            current_carrier_offset = weather_hop_offset(capture, current_hop_index)
        carrier = complex(math.cos(carrier_phase), math.sin(carrier_phase))
        carrier_phase += 2.0 * math.pi * current_carrier_offset / sample_rate
        if abs(carrier_phase) > math.pi * 4_096:
            carrier_phase = math.fmod(carrier_phase, 2.0 * math.pi)
        noise = complex(
            deterministic_noise(0x6841, absolute_index * 2),
            deterministic_noise(0x6841, absolute_index * 2 + 1),
        ) * noise_scale
        samples.append(source_value * carrier + noise)
    return samples


def generated_flowgraph_iq_samples(settings: dict, start_sample: int, sample_count: int) -> list[complex]:
    flowgraph = settings.get("flowgraph") or generated_flowgraph_config(settings)
    sample_rate = max(1.0, float(flowgraph["sample_rate"]))
    carrier_offset = float(flowgraph["carrier_offset_hz"])
    samples_per_symbol = max(1, int(flowgraph["samples_per_symbol"]))
    symbols = flowgraph["symbols"] or [0]
    phase_step = 2.0 * math.pi * carrier_offset / sample_rate
    carrier = complex(math.cos(phase_step * start_sample), math.sin(phase_step * start_sample))
    rotation = complex(math.cos(phase_step), math.sin(phase_step))
    noise_scale = max(0.0, float(flowgraph.get("noise_voltage", 0.0))) * 2.0
    interleaved_complex = bool(flowgraph.get("interleaved_char_to_complex", False))
    interleaved_scale = max(1e-9, float(flowgraph.get("interleaved_scale", 1.0)))
    seed = int(flowgraph.get("seed", 0))
    samples: list[complex] = []
    for offset in range(sample_count):
        sample_index = start_sample + offset
        symbol = symbols[(sample_index // samples_per_symbol) % len(symbols)]
        value = float(symbol) / interleaved_scale
        baseband = complex(value, value) if interleaved_complex else complex(value, 0.0)
        sample = carrier * baseband
        if noise_scale:
            sample += complex(
                deterministic_noise(seed, sample_index * 2) * noise_scale,
                deterministic_noise(seed, sample_index * 2 + 1) * noise_scale,
            )
        samples.append(sample)
        carrier *= rotation
    return samples


def gnu_radio_iq_samples(settings: dict, start_sample: int, sample_count: int) -> list[complex]:
    runtime = gnu_radio_runtime_settings(settings)
    if runtime.get("source_mode") == "generated_python_flowgraph":
        return generated_flowgraph_iq_samples(runtime, start_sample, sample_count)
    if runtime.get("source_mode") in {"weather_wav_pair", "weather_alarm_wav_pair"}:
        return weather_wav_iq_samples(runtime, start_sample, sample_count)
    capture_path, _ = configured_gnu_radio_path(runtime)
    if not capture_path.is_file():
        raise FileNotFoundError(f"GNU Radio capture not found: {capture_path.name}")
    with capture_path.open("rb") as handle:
        handle.seek(max(0, start_sample) * 8)
        raw = handle.read(max(0, sample_count) * 8)
    complete_bytes = len(raw) - len(raw) % 8
    return [complex(real, imag) for real, imag in struct.iter_unpack("<ff", raw[:complete_bytes])]


def gnu_radio_magnitudes(settings: dict, max_samples: int) -> list[float]:
    return [abs(sample) for sample in gnu_radio_iq_samples(settings, 0, max_samples)]


def pack_cf32_le(samples: list[complex]) -> bytes:
    data = bytearray(len(samples) * 8)
    for index, sample in enumerate(samples):
        struct.pack_into("<ff", data, index * 8, float(sample.real), float(sample.imag))
    return bytes(data)


def decode_bits_to_ascii(bits: str, bit_orders: tuple[str, ...] = ("msb", "lsb")) -> dict:
    best = {"text": "", "flag": "", "score": -1.0, "bit_offset": 0, "bit_order": "msb"}
    if len(bits) < 8:
        return best
    for bit_order in bit_orders:
        for bit_offset in range(8):
            values: list[int] = []
            for index in range(bit_offset, len(bits) - 7, 8):
                chunk = bits[index : index + 8]
                if bit_order == "lsb":
                    chunk = chunk[::-1]
                values.append(int(chunk, 2))
            if not values:
                continue
            printable = sum(1 for value in values if value in {9, 10, 13} or 32 <= value <= 126)
            text = bytes(values).decode("latin-1", errors="ignore")
            flag = extract_flag_from_text(text)
            score = printable / len(values)
            if flag:
                score += 4.0
            if "FLAG{" in text:
                score += 1.0
            if score > best["score"]:
                best = {
                    "text": text,
                    "flag": flag,
                    "score": score,
                    "bit_offset": bit_offset,
                    "bit_order": bit_order,
                }
    return best


def extract_flag_from_text(text: str) -> str:
    start = text.find("FLAG{")
    if start < 0:
        return ""
    end = text.find("}", start)
    if end < 0:
        return ""
    return text[start : end + 1]


def cluster_amplitude_levels(values: list[float], level_count: int = 4) -> tuple[list[int], list[float], float]:
    if not values:
        return [], [], 0.0
    ordered = sorted(values)
    centers = [
        ordered[min(len(ordered) - 1, max(0, round((index + 0.5) * (len(ordered) - 1) / level_count)))]
        for index in range(level_count)
    ]
    for _ in range(12):
        buckets = [[] for _ in range(level_count)]
        for value in values:
            bucket_index = min(range(level_count), key=lambda index: abs(value - centers[index]))
            buckets[bucket_index].append(value)
        next_centers = [
            sum(bucket) / len(bucket) if bucket else centers[index]
            for index, bucket in enumerate(buckets)
        ]
        if max(abs(next_centers[index] - centers[index]) for index in range(level_count)) < 1e-9:
            centers = next_centers
            break
        centers = next_centers
    ordered_centers = sorted(centers)
    symbols = [min(range(level_count), key=lambda index: abs(value - ordered_centers[index])) for value in values]
    separations = [
        ordered_centers[index + 1] - ordered_centers[index]
        for index in range(level_count - 1)
    ]
    contrast = min(separations) / max(1e-9, ordered_centers[-1] - ordered_centers[0]) if separations else 0.0
    return symbols, ordered_centers, max(0.0, min(1.0, contrast))


def decode_gnu_radio_ask2(settings: dict) -> dict:
    """Recover 2-bit ASK symbols from GNU Radio complex-float samples."""
    settings = gnu_radio_runtime_settings(settings)
    samples_per_symbol = max(8, int(settings.get("samples_per_symbol", 500)))
    max_samples = max(samples_per_symbol * 32, min(1_000_000, int(settings.get("decode_max_samples", 500000))))
    magnitudes = gnu_radio_magnitudes(settings, max_samples)
    if len(magnitudes) < samples_per_symbol * 16:
        return {"ok": False, "note": "Not enough IQ samples for 2-bit ASK symbol recovery."}

    prefix = [0.0]
    for magnitude in magnitudes:
        prefix.append(prefix[-1] + magnitude)

    best: dict = {"score": -1.0, "bits": "", "confidence": 0.0}
    phase_step = max(1, samples_per_symbol // 50)
    for phase in range(0, samples_per_symbol, phase_step):
        symbol_count = (len(magnitudes) - phase) // samples_per_symbol
        if symbol_count < 16:
            continue
        means = [
            (prefix[phase + (index + 1) * samples_per_symbol] - prefix[phase + index * samples_per_symbol]) / samples_per_symbol
            for index in range(symbol_count)
        ]
        symbols, centers, contrast = cluster_amplitude_levels(means, 4)
        if len(set(symbols[: min(len(symbols), 256)])) < 2:
            continue
        for level_map in ((0, 1, 2, 3), (3, 2, 1, 0)):
            bit_text = "".join(format(level_map[symbol], "02b") for symbol in symbols[:1024])
            bit_order = str(settings.get("bit_order", "msb")).lower()
            bit_orders = ("msb",) if bit_order == "msb" else ("lsb",) if bit_order == "lsb" else ("msb", "lsb")
            ascii_candidate = decode_bits_to_ascii(bit_text, bit_orders)
            score = contrast + max(0.0, float(ascii_candidate.get("score", 0.0)))
            if ascii_candidate.get("flag"):
                score += 4.0
            if score > best["score"]:
                best = {
                    "score": score,
                    "bits": bit_text,
                    "confidence": max(0.0, min(0.99, 0.45 + contrast * 0.54)),
                    "samples_per_symbol": samples_per_symbol,
                    "bits_per_symbol": 2,
                    "phase": phase,
                    "level_centers": [round(center, 6) for center in centers],
                    "decoded_text": ascii_candidate.get("text", ""),
                    "decoded_flag": ascii_candidate.get("flag", ""),
                    "byte_offset": ascii_candidate.get("bit_offset", 0),
                    "bit_order": ascii_candidate.get("bit_order", "msb"),
                    "symbol_encoding": "4-level ASK, MSB-first natural binary level order" if level_map[0] == 0 else "4-level ASK, MSB-first reversed level order",
                }
    return {"ok": bool(best["bits"]), **best, "note": "Recovered from four ASK amplitude levels; each symbol contributes two bits."}


def decode_gnu_radio_ook(settings: dict | None = None) -> dict:
    """Recover OOK bits from IQ amplitude without assuming byte or payload content."""
    settings = settings or load_config().get("gnu_radio_capture", {})
    settings = gnu_radio_runtime_settings(settings)
    if int(settings.get("bits_per_symbol", 1)) == 2:
        return decode_gnu_radio_ask2(settings)
    samples_per_symbol = max(8, int(settings.get("samples_per_symbol", 500)))
    max_samples = max(samples_per_symbol * 32, min(1_000_000, int(settings.get("decode_max_samples", 500000))))
    magnitudes = gnu_radio_magnitudes(settings, max_samples)
    if len(magnitudes) < samples_per_symbol * 16:
        return {"ok": False, "note": "Not enough IQ samples for symbol recovery."}

    prefix = [0.0]
    for magnitude in magnitudes:
        prefix.append(prefix[-1] + magnitude)

    best: dict = {"score": -1.0, "bits": "", "confidence": 0.0}
    phase_step = max(1, samples_per_symbol // 50)
    for phase in range(0, samples_per_symbol, phase_step):
        symbol_count = (len(magnitudes) - phase) // samples_per_symbol
        if symbol_count < 16:
            continue
        means = [
            (prefix[phase + (index + 1) * samples_per_symbol] - prefix[phase + index * samples_per_symbol]) / samples_per_symbol
            for index in range(symbol_count)
        ]
        ordered = sorted(means)
        low_seed = ordered[max(0, len(ordered) // 8)]
        high_seed = ordered[min(len(ordered) - 1, len(ordered) * 7 // 8)]
        threshold = (low_seed + high_seed) / 2.0
        low_values = [value for value in means if value < threshold]
        high_values = [value for value in means if value >= threshold]
        if not low_values or not high_values:
            continue
        low_mean = sum(low_values) / len(low_values)
        high_mean = sum(high_values) / len(high_values)
        low_variance = sum((value - low_mean) ** 2 for value in low_values) / len(low_values)
        high_variance = sum((value - high_mean) ** 2 for value in high_values) / len(high_values)
        contrast = (high_mean - low_mean) / max(1e-9, high_mean)
        spread = (math.sqrt(low_variance) + math.sqrt(high_variance)) / max(1e-9, high_mean - low_mean)
        score = contrast / max(0.02, spread)
        bits = [1 if value >= threshold else 0 for value in means]
        bit_text = "".join(str(bit) for bit in bits[:512])
        ascii_candidate = decode_bits_to_ascii(bit_text)
        combined_score = score + max(0.0, float(ascii_candidate.get("score", 0.0)))
        if combined_score > best["score"]:
            best = {
                "score": combined_score,
                "bits": bit_text,
                "confidence": max(0.0, min(0.99, contrast * (1.0 - min(0.8, spread)))),
                "samples_per_symbol": samples_per_symbol,
                "phase": phase,
                "threshold": threshold,
                "decoded_text": ascii_candidate.get("text", ""),
                "decoded_flag": ascii_candidate.get("flag", ""),
                "byte_offset": ascii_candidate.get("bit_offset", 0),
                "bit_order": ascii_candidate.get("bit_order", "msb"),
            }
    return {"ok": bool(best["bits"]), **best, "note": "Recovered from IQ amplitude without byte or payload assumptions."}


def gnu_radio_capture_preview(challenge_id: str | None = None, reveal_payload: bool = False) -> dict:
    """Convert a GNU Radio Python flowgraph stream or cf32 capture to web FFT rows."""
    settings = tunnel_gnu_radio_settings(challenge_id) or load_config().get("gnu_radio_capture", {})
    settings = gnu_radio_runtime_settings(settings)
    capture_info = settings.get("capture", {})
    generated_source = settings.get("source_mode") == "generated_python_flowgraph"
    virtual_source = settings.get("source_mode") in {
        "generated_python_flowgraph",
        "weather_wav_pair",
        "weather_alarm_wav_pair",
    }
    capture_path, relative_path = configured_gnu_radio_path(settings)
    flowgraph = settings.get("flowgraph", {})
    source_relative_path = Path(str(flowgraph.get("source_script") or relative_path.as_posix()))
    if not virtual_source and not capture_path.is_file():
        raise FileNotFoundError(f"GNU Radio capture not found: {relative_path.as_posix()}")

    datatype = str(settings.get("datatype", "cf32_le"))
    if datatype != "cf32_le":
        raise ValueError(f"Unsupported GNU Radio datatype: {datatype}; expected cf32_le")
    sample_rate = float(settings.get("sample_rate", 44200))
    center_hz = float(settings.get("center_hz", 915000000))
    carrier_offset_hz = float(capture_info.get("carrier_offset_hz", 0))
    fft_bins = int(settings.get("fft_bins", 512))
    max_frames = int(settings.get("max_frames", 120))
    if fft_bins < 64 or fft_bins > 2048 or fft_bins & (fft_bins - 1):
        raise ValueError("fft_bins must be a power of two between 64 and 2048")
    max_frames = max(1, min(512, max_frames))

    bytes_per_sample = 8
    sample_count = (
        int(flowgraph.get("period_samples", settings.get("sample_count", 0)))
        if virtual_source
        else capture_path.stat().st_size // bytes_per_sample
    )
    if sample_count < fft_bins:
        sample_count = fft_bins if virtual_source else sample_count
    if sample_count < fft_bins:
        raise ValueError(f"Capture needs at least {fft_bins} complete complex-float samples")
    weather_source = settings.get("source_mode") in {"weather_wav_pair", "weather_alarm_wav_pair"}
    audio_weather_source = settings.get("source_mode") == "weather_wav_pair"
    decoder = (
        {
            "ok": False,
            "bits": "",
            "confidence": 0.0,
            "note": "Audio capture: inspect hop timing and demodulate the tuned complex audio instead of amplitude-slicing it as OOK.",
        }
        if audio_weather_source
        else decode_gnu_radio_ook(settings)
    )
    symbol_phase = int(decoder.get("phase", 0))
    samples_per_symbol = int(decoder.get("samples_per_symbol", settings.get("samples_per_symbol", 500)))
    if audio_weather_source:
        hop_samples = max(fft_bins, int(capture_info.get("hop_samples", fft_bins)))
        frame_stride = max(fft_bins, hop_samples // 4)
        frame_count = max(1, min(max_frames, 1 + max(0, sample_count - fft_bins) // frame_stride))
        starts = [index * frame_stride for index in range(frame_count)]
    elif decoder.get("ok") and symbol_phase + fft_bins <= sample_count:
        available_frames = max_frames if virtual_source else 1 + max(0, (sample_count - symbol_phase - fft_bins) // samples_per_symbol)
        frame_count = max(1, min(max_frames, available_frames, max(1, len(str(decoder.get("bits", ""))))))
        starts = [symbol_phase + index * samples_per_symbol for index in range(frame_count)]
    else:
        frame_count = min(max_frames, max(1, sample_count // fft_bins))
        last_start = max(0, sample_count - fft_bins)
        starts = [round(index * last_start / max(1, frame_count - 1)) for index in range(frame_count)]
    window = [0.5 - 0.5 * math.cos(2.0 * math.pi * index / max(1, fft_bins - 1)) for index in range(fft_bins)]
    power_rows: list[list[float]] = []
    time_rows_raw: list[list[float]] = []
    iq_rows_raw: list[list[complex]] = []

    with capture_path.open("rb") if not virtual_source else nullcontext() as handle:
        for start in starts:
            if virtual_source:
                unwindowed = gnu_radio_iq_samples(settings, start, fft_bins)
            else:
                handle.seek(start * bytes_per_sample)
                raw = handle.read(fft_bins * bytes_per_sample)
                if len(raw) != fft_bins * bytes_per_sample:
                    continue
                unpacked = struct.iter_unpack("<ff", raw)
                unwindowed = [complex(real, imag) for real, imag in unpacked]
            iq_rows_raw.append(unwindowed[:256])
            time_rows_raw.append([unwindowed[round(index * (fft_bins - 1) / 159)].real for index in range(160)])
            samples = [value * window[index] for index, value in enumerate(unwindowed)]
            fft_in_place(samples)
            shifted = samples[fft_bins // 2 :] + samples[: fft_bins // 2]
            power_rows.append([20.0 * math.log10(max(1e-12, abs(value))) for value in shifted])

    if not power_rows:
        raise ValueError("Capture changed while it was being read; stop GNU Radio briefly and reload")
    floor_db = min(min(row) for row in power_rows)
    peak_db = max(max(row) for row in power_rows)
    display_floor = max(floor_db, peak_db - 80.0)
    dynamic_range = max(1.0, peak_db - display_floor)
    rows = [[max(0.0, min(1.0, (value - display_floor) / dynamic_range)) for value in row] for row in power_rows]
    time_peak = max(1e-9, max(abs(value) for row in time_rows_raw for value in row))
    time_rows = [[max(-1.0, min(1.0, value / time_peak)) for value in row] for row in time_rows_raw]
    iq_peak = max(1e-9, max(abs(value) for row in iq_rows_raw for value in row))
    iq_rows = [[[value.real / iq_peak, value.imag / iq_peak] for value in row] for row in iq_rows_raw]
    average_power = [sum(row[index] for row in power_rows) / len(power_rows) for index in range(fft_bins)]
    peak_bin = max(range(fft_bins), key=average_power.__getitem__)
    detected_frequency_hz = center_hz + (peak_bin - fft_bins / 2) * sample_rate / fft_bins
    recovered_bits = decoder.get("bits", "")
    decoded_text = str(decoder.get("decoded_text", ""))
    decoded_flag = str(decoder.get("decoded_flag", ""))
    public_payload = bool(capture_info.get("public_payload", True))
    payload_revealed = reveal_payload and public_payload
    expected_flag = str(capture_info.get("flag", "") or decoded_flag)
    payload_preview = decoded_text[:160] if payload_revealed else "withheld; use the radio receive workflow to recover payload ASCII"
    modulation_label = str(capture_info.get("modulation") or ("4-level ASK / 2-bit symbols" if int(decoder.get("bits_per_symbol", 1)) == 2 else "OOK/ASK amplitude"))
    parser = {
        "stage": "bit_slice",
        "confidence": decoder.get("confidence", 0.0),
        "bit_buffer": recovered_bits or "no stable symbols recovered",
        "fields": {
            "detected_frequency_hz": round(detected_frequency_hz, 3),
            "modulation": modulation_label,
            "samples_per_symbol": decoder.get("samples_per_symbol", settings.get("samples_per_symbol", 500)),
            "bits_per_symbol": decoder.get("bits_per_symbol", settings.get("bits_per_symbol", 1)),
            "recovered_bit_count": len(recovered_bits),
            "byte_offset": decoder.get("byte_offset", 0),
            "bit_order": decoder.get("bit_order", "msb"),
            "symbol_encoding": decoder.get("symbol_encoding", "binary amplitude"),
            "level_centers": decoder.get("level_centers", []),
            "integrity": "no CRC or framing field present in the GNU Radio generator",
        },
        "note": str(decoder.get("note") or "Binary symbols recovered from IQ amplitude; byte alignment is estimated from printable payload structure."),
    }
    if generated_source:
        parser["fields"].update(
            {
                "flowgraph_source": str(flowgraph.get("source_script", "")),
                "flowgraph_sha256": str(flowgraph.get("source_sha256", "")),
                "flowgraph_block_count": int(flowgraph.get("flowgraph_block_count", 0)),
                "flowgraph_blocks": flowgraph.get("flowgraph_blocks", []),
                "source_payload_bytes": len(flowgraph.get("payload", b"")),
                "source_period_samples": int(flowgraph.get("period_samples", 0)),
            }
        )
    if audio_weather_source:
        parser["stage"] = "energy_detect"
        parser["fields"].update(
            {
                "payload": "complex weather voice audio",
                "hop_mode": capture_info.get("hop_mode", "repeating pattern"),
                "hop_period_ms": round(float(capture_info.get("hop_samples", 1_000)) / sample_rate * 1_000, 3),
                "hop_offsets_hz": capture_info.get("carrier_offsets_hz", [carrier_offset_hz]),
                "phase_mode": capture_info.get("phase_prng", "none"),
                "phase_symbol_samples": capture_info.get("randu_samples_per_chip", 0),
            }
        )
    if payload_revealed:
        parser["fields"]["payload_ascii"] = payload_preview
        parser["fields"]["payload_state"] = "revealed_by_receiver"
    else:
        parser["fields"]["payload_state"] = "withheld_in_artifact_preview"
    source_files = {}
    for label, key in (
        ("grc", "grc_path"),
        ("python", "python_path"),
        ("raw_iq", "path"),
        ("file_meta", "meta_path"),
        ("real_wav", "real_wav_path"),
        ("imag_wav", "imag_wav_path"),
    ):
        relative = capture_info.get(key)
        if not relative:
            continue
        source_path = bounded_project_path(relative)
        source_files[label] = {
            "path": str(relative).replace("\\", "/"),
            "size_bytes": source_path.stat().st_size if source_path.exists() else 0,
        }
    if generated_source and flowgraph:
        source_files["generated_python"] = {
            "path": str(flowgraph.get("source_script", "")).replace("\\", "/"),
            "size_bytes": int(flowgraph.get("script_size_bytes", 0)),
            "sha256": str(flowgraph.get("source_sha256", "")),
        }
        source_files.pop("raw_iq", None)
        source_files.pop("file_meta", None)
    if settings.get("source_mode") in {"weather_wav_pair", "weather_alarm_wav_pair"}:
        source_mode_label = "paired weather-report WAV sources processed by the backend flowgraph model"
        source_files.pop("raw_iq", None)
    elif generated_source:
        source_mode_label = "generated GNU Radio Python flowgraph"
    else:
        source_mode_label = "raw GNU Radio cf32 File Sink capture"
    preview_sources = [
        {
            "label": capture_info.get("title", "GNU Radio tunnel capture"),
            "kind": (
                "weather_complex"
                if weather_source
                else "gnu_radio_cf32_ask2"
                if int(decoder.get("bits_per_symbol", 1)) == 2
                else "gnu_radio_cf32_ook"
            ),
            "offset_hz": round(detected_frequency_hz - center_hz, 3),
            "bandwidth_hz": min(sample_rate / 4, 50_000) if weather_source else 2_000,
        }
    ]
    if weather_source and capture_info.get("carrier_offsets_hz"):
        preview_sources = [
            {
                "label": f"Weather audio hop {index + 1}",
                "kind": "random_audio_hop" if capture_info.get("hop_mode") else "patterned_audio_hop",
                "offset_hz": float(offset),
                "bandwidth_hz": min(5_000, sample_rate / 10),
            }
            for index, offset in enumerate(capture_info["carrier_offsets_hz"])
        ]
    else:
        preview_sources.append(
            {
                "label": "Nominal GNU Radio tone",
                "kind": "carrier_reference",
                "offset_hz": carrier_offset_hz,
                "bandwidth_hz": 1_000,
            }
        )
    preview_annotations = [
        {
            "label": f"hop {index + 1}",
            "offset_hz": float(offset),
            "color": "#73f2a6" if index % 2 == 0 else "#ffc766",
        }
        for index, offset in enumerate(capture_info.get("carrier_offsets_hz", []))
    ] if weather_source else [
        {"label": "detected ASK carrier", "offset_hz": round(detected_frequency_hz - center_hz, 3), "color": "#73f2a6"},
        {"label": f"nominal {carrier_offset_hz / 1000:g} kHz tone", "offset_hz": carrier_offset_hz, "color": "#ffc766"},
    ]
    return {
        "challenge_id": challenge_id or "configured-gnu-radio-capture",
        "scheme_id": f"GNU-RADIO-{str(capture_info.get('stem', 'LOCAL-CAPTURE')).upper()}",
        "center_hz": center_hz,
        "span_hz": sample_rate,
        "sample_rate_hz": sample_rate,
        "bins": fft_bins,
        "frames": len(rows),
        "rows": rows,
        "time_rows": time_rows,
        "iq_rows": iq_rows,
        "symbol_bits": recovered_bits[:len(rows)],
        "symbol_phase_samples": symbol_phase,
        "time_component": "normalized real (I) samples aligned with each FFT frame",
        "detected_frequency_hz": detected_frequency_hz,
        "lock_frequency_hz": center_hz if capture_info.get("lock_to_center") else detected_frequency_hz,
        "parser": parser,
        "description": f"Waterfall generated live by the backend from {capture_info.get('title', 'a local GNU Radio')} using a {source_mode_label}.",
        "source_file": source_relative_path.as_posix(),
        "source_mode": settings.get("source_mode", "recorded_cf32"),
        "source_files": source_files,
        "sample_count": sample_count,
        "duration_seconds": sample_count / sample_rate,
        "decoded_text": decoded_text[:240] if payload_revealed else "",
        "expected_flag": expected_flag if payload_revealed else "",
        "sources": preview_sources,
        "protocol_notes": {
            "datatype": datatype,
            "modulation": f"{modulation_label} from the {source_mode_label}",
            "source": f"Python backend serves a looping cf32 stream from the {source_mode_label}; no pre-recorded SigMF file is required.",
            "raw_path": f"/api/rf/raw?challenge_id={challenge_id or 'tunnel-reading-signals'}&bytes=2097152",
            "metadata": "The challenge signal source is the editable generated Python flowgraph; recordings are optional developer snapshots.",
        },
        "annotations": preview_annotations,
    }


def gnu_radio_live_frame(preview: dict, frame: int) -> dict:
    rows = preview.get("rows") or []
    if not rows:
        return {"frame": frame, "row": [], "samples": [], "parser": preview.get("parser", {})}
    index = frame % len(rows)
    parser = dict(preview.get("parser", {}))
    bit_buffer = str(parser.get("bit_buffer", ""))
    if bit_buffer and set(bit_buffer) <= {"0", "1"}:
        visible_bits = max(16, min(len(bit_buffer), int((index + 1) / max(1, len(rows)) * len(bit_buffer))))
        parser["bit_buffer"] = bit_buffer[:visible_bits]
        parser["stage"] = "bit_slice" if visible_bits < len(bit_buffer) else "field_decode"
    return {
        "frame": frame,
        "row": rows[index],
        "samples": (preview.get("time_rows") or [[]])[index] if preview.get("time_rows") else [],
        "iq": (preview.get("iq_rows") or [[]])[index] if preview.get("iq_rows") else [],
        "parser": parser,
    }


def read_gnu_radio_raw_sample(challenge_id: str, byte_count: int = 2_097_152, byte_offset: int = 0) -> tuple[bytes, dict]:
    settings = tunnel_gnu_radio_settings(challenge_id)
    if not settings:
        raise FileNotFoundError(f"No GNU Radio capture is mapped for {challenge_id}")
    settings = gnu_radio_runtime_settings(settings)
    virtual_source = settings.get("source_mode") in {
        "generated_python_flowgraph",
        "weather_wav_pair",
        "weather_alarm_wav_pair",
    }
    byte_count = max(1024, min(8_388_608, byte_count))
    byte_offset = max(0, byte_offset)
    byte_offset -= byte_offset % 8
    if virtual_source:
        flowgraph = settings.get("flowgraph", {})
        sample_count = max(1, byte_count // 8)
        sample_offset = byte_offset // 8
        body = pack_cf32_le(gnu_radio_iq_samples(settings, sample_offset, sample_count))
        source_file = (
            str(flowgraph.get("source_script", "")).replace("\\", "/")
            or str(settings.get("capture", {}).get("grc_path", "")).replace("\\", "/")
        )
        source_size = int(flowgraph.get("period_samples", settings.get("sample_count", sample_count))) * 8
        return body, {
            "source_file": source_file,
            "source_size": source_size,
            "offset": byte_offset,
            "bytes": len(body),
            "stem": settings.get("capture", {}).get("stem", challenge_id),
            "source_mode": settings.get("source_mode"),
        }
    capture_path, relative_path = configured_gnu_radio_path(settings)
    if not capture_path.is_file():
        raise FileNotFoundError(f"GNU Radio capture not found: {relative_path.as_posix()}")
    file_size = capture_path.stat().st_size
    byte_offset = max(0, min(max(0, file_size - 1), byte_offset))
    byte_offset -= byte_offset % 8
    with capture_path.open("rb") as handle:
        handle.seek(byte_offset)
        data = handle.read(byte_count)
    return data, {
        "source_file": relative_path.as_posix(),
        "source_size": file_size,
        "offset": byte_offset,
        "bytes": len(data),
        "stem": settings.get("capture", {}).get("stem", challenge_id),
    }


def public_task(task: dict) -> dict:
    return {key: value for key, value in task.items() if key != "flag"}


def public_contexts() -> list[dict]:
    tasks_by_id = {task["id"]: public_task(task) for task in load_challenges()}
    contexts = []
    for context in load_contexts():
        subtasks = [tasks_by_id[task_id] for task_id in context.get("subtask_ids", []) if task_id in tasks_by_id]
        total_points = sum(int(task.get("points", 0)) for task in subtasks)
        contexts.append(
            {
                **context,
                "subtasks": subtasks,
                "subtask_count": len(subtasks),
                "total_points": total_points,
            }
        )
    return contexts


def default_receiver_for(challenge_id: str) -> dict:
    target = RF_TARGETS.get(challenge_id, next(iter(RF_TARGETS.values())))
    return {
        "center_mhz": target["center_mhz"],
        "span_khz": target["span_khz"],
        "gain_db": 32,
        "squelch_db": -90,
        "modulation": "AUTO",
    }


def transmitter_target_overlap(transmitter: dict | None, target: dict) -> tuple[bool, dict]:
    if transmitter is None:
        return True, {"provided": False, "note": "No TX state supplied; script terminal compatibility mode."}
    try:
        tx_center_hz = float(transmitter.get("center_hz"))
        tx_bandwidth_hz = max(1000.0, float(transmitter.get("bandwidth_khz", 1)) * 1000.0)
        tx_power_db = float(transmitter.get("power_db", -60))
    except (TypeError, ValueError):
        return False, {"provided": True, "reason": "transmitter center_hz, bandwidth_khz, and power_db must be numeric"}
    target_hz = float(target["center_mhz"]) * 1_000_000.0
    target_bandwidth_hz = 3200.0
    distance_hz = abs(tx_center_hz - target_hz)
    overlap_hz = max(0.0, tx_bandwidth_hz / 2.0 + target_bandwidth_hz / 2.0 - distance_hz)
    overlap_ratio = overlap_hz / max(1.0, target_bandwidth_hz)
    hits = overlap_ratio >= 0.35 and tx_power_db >= -45.0
    return hits, {
        "provided": True,
        "tx_center_hz": round(tx_center_hz, 3),
        "target_hz": round(target_hz, 3),
        "distance_hz": round(distance_hz, 3),
        "tx_bandwidth_hz": round(tx_bandwidth_hz, 3),
        "overlap_ratio": round(overlap_ratio, 3),
        "power_db": tx_power_db,
    }


def build_rf_command_response(session_id: str, challenge_id: str, action: str, arguments: str, receiver: dict, transmitter: dict | None = None) -> tuple[dict, HTTPStatus]:
    action = action.lower().strip()
    target = RF_TARGETS.get(challenge_id)
    if not target:
        return {"ok": False, "lines": ["No RF target is assigned to this subtask."]}, HTTPStatus.NOT_FOUND

    imported_capture = None
    if gnu_radio_capture_for(challenge_id):
        try:
            imported_capture = gnu_radio_capture_preview(challenge_id, reveal_payload=action == "receive")
            target = {
                **target,
                "center_mhz": float(imported_capture.get("lock_frequency_hz", imported_capture["detected_frequency_hz"])) / 1e6,
                "span_khz": float(imported_capture["sample_rate_hz"]) / 1e3,
                "modulations": set(target.get("modulations", {"AUTO"})) | {"AUTO"},
                "label": str(imported_capture["scheme_id"]),
            }
        except (FileNotFoundError, OSError, ValueError, struct.error):
            imported_capture = None

    try:
        center_mhz = float(receiver.get("center_mhz", target["center_mhz"]))
        span_khz = max(1.0, float(receiver.get("span_khz", target.get("span_khz", 500))))
        gain_db = float(receiver.get("gain_db", 0))
        squelch_db = float(receiver.get("squelch_db", -90))
    except (TypeError, ValueError):
        return {"ok": False, "lines": ["Receiver values must be numeric."]}, HTTPStatus.BAD_REQUEST

    modulation = str(receiver.get("modulation", "AUTO")).upper()
    offset_khz = abs(center_mhz - target["center_mhz"]) * 1000
    in_view = offset_khz <= span_khz / 2
    tuned = offset_khz <= (span_khz * 0.48 if imported_capture else max(8.0, min(40.0, span_khz / 16)))
    demod_ok = modulation in target["modulations"]
    level_db = -72 + min(28, gain_db * 0.7)
    above_squelch = level_db >= squelch_db
    locked = tuned and demod_ok and above_squelch

    base = {
        "ok": True,
        "action": action,
        "challenge_id": challenge_id,
        "locked": locked,
        "target": target["label"],
        "receiver": {
            "center_mhz": center_mhz,
            "span_khz": span_khz,
            "offset_khz": round(offset_khz, 3),
            "modulation": modulation,
            "gain_db": gain_db,
            "squelch_db": squelch_db,
        },
        "user_data": user_data_for(session_id),
    }
    if transmitter is not None:
        _, tx_report = transmitter_target_overlap(transmitter, target)
        base["transmitter"] = tx_report

    if action == "scan":
        base["lines"] = (
            [
                f"ENERGY  {target['label']}  {target['center_mhz']:.6f} MHz  level {level_db:.1f} dBFS",
                f"OFFSET  {offset_khz:.1f} kHz  candidate demodulations: {', '.join(sorted(target['modulations']))}",
            ]
            if in_view
            else ["No target energy inside the selected span.", "Adjust centre/span or inspect the subtask intelligence."]
        )
        return base, HTTPStatus.OK

    if action in {"status", "tune"}:
        base["lines"] = [
            f"RX {center_mhz:.6f} MHz / span {span_khz:.0f} kHz / {modulation} / gain {gain_db:.0f} dB",
            f"TARGET {'LOCKED' if locked else 'UNLOCKED'} / offset {offset_khz:.1f} kHz / squelch {'open' if above_squelch else 'closed'}",
        ]
        return base, HTTPStatus.OK

    if not locked:
        base["ok"] = False
        base["lines"] = [
            "Receiver not locked: no usable target output.",
            f"Check centre frequency, demodulation, gain, and squelch (offset {offset_khz:.1f} kHz).",
        ]
        return base, HTTPStatus.BAD_REQUEST

    if action == "receive":
        if imported_capture:
            parser = imported_capture.get("parser", {})
            bitstream = str(parser.get("bit_buffer", ""))
            decoded_text = str(imported_capture.get("decoded_text", "") or parser.get("fields", {}).get("payload_ascii", ""))
            base["parser"] = parser
            lines = [
                f"LOCK {target['label']} / measured carrier {target['center_mhz']:.6f} MHz",
                f"GNU Radio cf32 capture parsed / {parser.get('fields', {}).get('modulation', 'ASK amplitude')} clock recovered",
            ]
            if bitstream and set(bitstream) <= {"0", "1"}:
                base["bitstream"] = bitstream
                lines += [f"BITSTREAM RECOVERED / {len(bitstream)} bits", bitstream]
                if challenge_id in RECEIVE_FLAG_TASKS:
                    base["decoded_text"] = decoded_text
                    base["flag"] = expected_flag_for(session_id, challenge_id)
                    lines += [f"PLAINTEXT PAYLOAD {decoded_text or base['flag']}", f"FLAG {base['flag']}"]
                elif challenge_id in INTERFERENCE_FLAG_TASKS:
                    lines += ["EXPECTED SIGN PAYLOAD BUFFERED", "Apply a controlled interference action to produce the workbook failure condition."]
                elif challenge_id in TRANSMIT_FLAG_TASKS:
                    lines += ["TARGET WAVEFORM PROFILE BUFFERED", "Transmit a shaped local sign message to produce the workbook success condition."]
            else:
                base["ok"] = False
                lines.append("Carrier is locked, but no stable binary symbols were recovered from the IQ samples.")
            base["lines"] = lines
            return base, HTTPStatus.OK if base["ok"] else HTTPStatus.UNPROCESSABLE_ENTITY

        lines = [f"LOCK {target['label']} / sync acquired / CRC usable"]
        if challenge_id in RECEIVE_FLAG_TASKS:
            base["flag"] = expected_flag_for(session_id, challenge_id)
            lines += ["PLAINTEXT/CALLSIGN RECOVERED", f"FLAG {base['flag']}"]
        elif challenge_id in DECODE_FLAG_TASKS:
            lines += ["FRAME BUFFERED / additional reconstruction required", "Try `decode` with the recovered timing or PRNG state."]
        elif challenge_id in INTERFERENCE_FLAG_TASKS:
            lines += ["EXPECTED STRING buffered", "Apply a controlled `interfere` action to observe mismatch behaviour."]
        elif challenge_id in TRANSMIT_FLAG_TASKS:
            lines += ["TARGET READY / local TX chain armed", "Use `transmit` with the required payload pattern."]
        elif challenge_id in SEND_FLAG_TASKS:
            lines += ["TARGET READY / accepts structured `send` input", "Use the subtask evidence to craft the accepted message."]
        else:
            lines += ["TARGET DATA buffered for analysis."]
        base["lines"] = lines
        return base, HTTPStatus.OK

    lower_args = arguments.lower()
    if action == "decode" and challenge_id in DECODE_FLAG_TASKS and any(
        word in lower_args for word in {"", "weak", "prng", "admin", "metadata", "packet"}
    ):
        base["flag"] = expected_flag_for(session_id, challenge_id)
        base["lines"] = ["DECODE accepted / recovered hidden field", f"FLAG {base['flag']}"]
    elif action == "interfere" and MODE["value"] == "attack" and challenge_id in INTERFERENCE_FLAG_TASKS and any(
        word in lower_args for word in {"noise", "dos", "mismatch", "jam", "metadata"}
    ):
        tx_hits, tx_report = transmitter_target_overlap(transmitter, target)
        base["transmitter"] = tx_report
        if not tx_hits:
            base["ok"] = False
            base["lines"] = [
                "INTERFERENCE waveform transmitted locally, but it is not overlapping the target carrier enough to corrupt the sign decoder.",
                "Tune RX to lock the target, then retune TX centre/offset and bandwidth until the local energy collides with the detected carrier.",
            ]
            return base, HTTPStatus.BAD_REQUEST
        base["flag"] = expected_flag_for(session_id, challenge_id)
        base["lines"] = ["INTERFERENCE accepted / decoded string mismatch observed", f"DISPLAY OUTPUT {base['flag']}"]
    elif action == "transmit" and MODE["value"] == "attack" and challenge_id in TRANSMIT_FLAG_TASKS and any(
        word in lower_args for word in {"sign", "message", "metadata", "fibonacci", "tone", "gate", "null", "theta", "replay", "waveform"}
    ):
        tx_hits, tx_report = transmitter_target_overlap(transmitter, target)
        base["transmitter"] = tx_report
        if transmitter is not None and not tx_hits:
            base["ok"] = False
            base["lines"] = [
                "TX waveform was generated, but the receiver did not see it at the target carrier.",
                "Tune RX first, then set TX offset/bandwidth so the injected packet lands on the detected signal.",
            ]
            return base, HTTPStatus.BAD_REQUEST
        base["flag"] = expected_flag_for(session_id, challenge_id)
        base["lines"] = ["TX waveform accepted by local target", "TARGET EFFECT matched success condition", f"FLAG {base['flag']}"]
    elif action == "send" and challenge_id == "weather-boring-active-re":
        packet_text = arguments.strip()
        if packet_text.lower().startswith("packet "):
            packet_text = packet_text.split(maxsplit=1)[1]
        try:
            packet = parse_u32_packet(packet_text)
        except ValueError as error:
            base["ok"] = False
            base["lines"] = [str(error), "Send the forged receiver input as `send 0x........`."]
            return base, HTTPStatus.BAD_REQUEST
        emergency = alarm_decode_packet(packet)
        base["packet"] = f"0x{packet:08X}"
        base["decoded_emergency"] = f"0x{emergency:X}"
        base["alarm_active"] = emergency == 0xB and MODE["value"] == "attack"
        if not base["alarm_active"]:
            base["ok"] = False
            base["lines"] = [
                f"PACKET {base['packet']} decoded / emergency={base['decoded_emergency']}",
                "Warning light remained off: AlarmCheck did not accept an unauthenticated emergency value in the current mode.",
            ]
            return base, HTTPStatus.UNPROCESSABLE_ENTITY
        base["flag"] = expected_flag_for(session_id, challenge_id)
        base["lines"] = [
            f"PACKET {base['packet']} decoded / emergency={base['decoded_emergency']}",
            "FORGED ALARM accepted by the extracted receiver logic",
            "WARNING LIGHT ACTIVE",
            f"FLAG {base['flag']}",
        ]
    elif action == "send" and challenge_id == "bushfire-hdl-flaw":
        bin_match = re.search(r"\b(?:bin|azimuth)\s*[=:]?\s*(\d{1,2})\b", arguments, re.IGNORECASE)
        correlation_match = re.search(r"\b(?:correlation|corr|score)\s*[=:]?\s*(\d{1,3})\b", arguments, re.IGNORECASE)
        if not bin_match or not correlation_match:
            base["ok"] = False
            base["lines"] = [
                "Beam-gate input requires an arrival bin and correlation score.",
                "Use `send beam bin <0..31> correlation <0..255>` after mapping the recovered HDL response.",
            ]
            return base, HTTPStatus.BAD_REQUEST
        arrival_bin = int(bin_match.group(1))
        correlation = int(correlation_match.group(1))
        array_gain = 255 if arrival_bin in {2, 10, 18, 26} else 0
        hidden_lobe = arrival_bin in {10, 18, 26}
        base["beam_pattern"] = {
            "arrival_bin": arrival_bin,
            "correlation": correlation,
            "array_gain": array_gain,
            "hidden_lobe": hidden_lobe,
        }
        if not 0 <= arrival_bin <= 31 or not 0 <= correlation <= 255:
            base["ok"] = False
            base["lines"] = ["Beam input is outside the recovered hardware field widths."]
            return base, HTTPStatus.BAD_REQUEST
        if not hidden_lobe or correlation < 240 or array_gain < 240 or MODE["value"] != "attack":
            base["ok"] = False
            base["lines"] = [
                f"BEAM GATE rejected bin={arrival_bin} correlation={correlation} gain={array_gain}",
                "The main look direction is expected; demonstrate a separate off-axis lobe that aliases the trusted steering vector.",
            ]
            return base, HTTPStatus.UNPROCESSABLE_ENTITY
        base["flag"] = expected_flag_for(session_id, challenge_id)
        base["lines"] = [
            f"BEAM GATE accepted off-axis bin={arrival_bin} correlation={correlation} gain={array_gain}",
            "UNINTENDED LOBE aliases TRUST_VECTOR; relay data crossed the spatial gate",
            f"FLAG {base['flag']}",
        ]
    elif action == "send" and MODE["value"] == "attack" and challenge_id in SEND_FLAG_TASKS and any(
        word in lower_args
        for word in {"warning", "light", "auth", "evacuation", "anomaly", "testbench", "latch", "default", "bitstream", "superuser", "kill"}
    ):
        base["flag"] = expected_flag_for(session_id, challenge_id)
        base["lines"] = ["STRUCTURED INPUT accepted by local target", "SIMULATED EFFECT reached success condition", f"FLAG {base['flag']}"]
    else:
        base["ok"] = False
        base["lines"] = [
            "Command reached the target but did not trigger its success condition.",
            "Use the subtask's flag-location note, evidence, and script commands to shape the payload.",
        ]
        return base, HTTPStatus.BAD_REQUEST
    return base, HTTPStatus.OK


def script_interface_description() -> dict:
    return {
        "name": "Signal Forge Script Terminal",
        "base_url": f"http://localhost:{os.environ.get('PORT', '8000')}",
        "endpoints": {
            "GET /api/script/interface": "Describe this script-facing interface.",
            "POST /api/script/terminal": "Run one terminal command against a selected subtask.",
            "GET /api/contexts": "List situations and nested subtasks.",
            "GET /api/tasks": "List all subtasks.",
            "GET /api/rf/live": "Stream live SSE parser events. Mapped GNU Radio subtasks synthesize cf32 IQ from their generated Python flowgraph scripts.",
            "GET /api/rf/raw": "Download bounded generated cf32 IQ samples; use bytes and offset query params.",
            "GET /api/rf/gnu-radio-capture": "Analyse a selected generated GNU Radio Python flowgraph with challenge_id and return measured FFT, tuned IQ, and recovered bits.",
            "TCP signal ingest": f"Send JSON-lines or raw cf32_le framed IQ to {EXTERNAL_INGEST['host']}:{EXTERNAL_INGEST['port']}. Use SIGNAL_INGEST_HOST/SIGNAL_INGEST_PORT to change it.",
            "GNU Radio ZMQ bridge": "Run tools/script_clients/zmq_signal_bridge.py against a GNU Radio ZMQ PUSH/PUB Sink, then view it with External feed.",
            "GET /api/rf/external/status": "Describe the currently buffered external signal feed for a challenge.",
            "GET /api/rf/external/live": "Stream externally supplied frames into the same browser waterfall with Server-Sent Events.",
        },
        "terminal_payload": {
            "session_id": "stable id chosen by your script",
            "challenge_id": "subtask id, e.g. tunnel-tuning",
            "command": "scan | tune <MHz> | span <kHz> | demod <mode> | receive | decode | interfere <effect> | transmit <payload> | send <payload>",
        },
        "example": {
            "session_id": "dev-script-01",
            "challenge_id": "tunnel-tuning",
            "command": "tune 915.000",
        },
        "client": "/tools/script_clients/signal_terminal_client.py",
        "signal_client": "/tools/script_clients/external_signal_sender.py",
        "zmq_bridge": "/tools/script_clients/zmq_signal_bridge.py",
    }


def script_get_response(path: str, session_id: str) -> tuple[dict, HTTPStatus]:
    parsed = urlparse(path)
    if parsed.path == "/api/tasks":
        return {"tasks": [public_task(task) for task in load_challenges()]}, HTTPStatus.OK
    if parsed.path == "/api/contexts":
        return {"contexts": public_contexts()}, HTTPStatus.OK
    if parsed.path == "/api/radio/intercept":
        return radio_intercept(session_id), HTTPStatus.OK
    if parsed.path == "/api/script/interface":
        return script_interface_description(), HTTPStatus.OK
    return {"error": "script terminal request supports /api/tasks, /api/contexts, /api/radio/intercept, and /api/script/interface"}, HTTPStatus.NOT_FOUND


def run_script_terminal_command(session_id: str, body: dict) -> tuple[dict, HTTPStatus]:
    terminal = SCRIPT_TERMINALS.setdefault(
        session_id,
        {"challenge_id": "tunnel-reading-signals", "receivers": {}},
    )
    if body.get("challenge_id"):
        terminal["challenge_id"] = str(body["challenge_id"])
    challenge_id = terminal["challenge_id"]
    receiver = terminal["receivers"].setdefault(challenge_id, default_receiver_for(challenge_id))
    command_line = str(body.get("command", "")).strip()
    if not command_line:
        return {"ok": False, "lines": ["No command supplied."]}, HTTPStatus.BAD_REQUEST

    command, _, arguments = command_line.partition(" ")
    command = command.lower()
    arguments = arguments.strip()

    if command == "help":
        return {
            "ok": True,
            "session_id": session_id,
            "challenge_id": challenge_id,
            "receiver": receiver,
            "lines": [
                "Commands: challenge <id>, scan, tune <MHz>, span <kHz>, gain <dB>, squelch <dB>, demod <mode>, receive, decode, interfere, transmit, send, request <path>",
                "Use GET /api/contexts to discover situation and subtask ids.",
            ],
        }, HTTPStatus.OK

    if command == "challenge":
        if arguments not in RF_TARGETS:
            return {"ok": False, "lines": [f"Unknown subtask id: {arguments}"]}, HTTPStatus.NOT_FOUND
        terminal["challenge_id"] = arguments
        receiver = terminal["receivers"].setdefault(arguments, default_receiver_for(arguments))
        return {"ok": True, "session_id": session_id, "challenge_id": arguments, "receiver": receiver, "lines": [f"Active subtask set to {arguments}."]}, HTTPStatus.OK

    if command == "request":
        return script_get_response(arguments, session_id)

    numeric_controls = {
        "tune": ("center_mhz", "status"),
        "center": ("center_mhz", "status"),
        "span": ("span_khz", "status"),
        "gain": ("gain_db", "status"),
        "squelch": ("squelch_db", "status"),
    }
    if command in numeric_controls:
        field, action = numeric_controls[command]
        try:
            receiver[field] = float(arguments)
        except ValueError:
            return {"ok": False, "lines": [f"{command}: numeric value required."]}, HTTPStatus.BAD_REQUEST
        return build_rf_command_response(session_id, challenge_id, "tune" if command == "tune" else action, "", receiver)

    if command == "demod":
        receiver["modulation"] = arguments.upper()
        return build_rf_command_response(session_id, challenge_id, "status", "", receiver)

    if command in {"scan", "status", "receive", "decode", "interfere", "transmit", "send"}:
        return build_rf_command_response(session_id, challenge_id, command, arguments, receiver)

    return {"ok": False, "lines": [f"{command}: command not found. Try help."]}, HTTPStatus.BAD_REQUEST


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                vehicle_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                plate TEXT NOT NULL,
                account_state TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS toll_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id TEXT NOT NULL,
                booth_id TEXT NOT NULL,
                route_code TEXT NOT NULL,
                schedule_code TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schedules (
                schedule_code TEXT PRIMARY KEY,
                route_code TEXT NOT NULL,
                label TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                operator_only INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS api_notes (
                note_key TEXT PRIMARY KEY,
                note_value TEXT NOT NULL
            );

            DELETE FROM vehicles;
            DELETE FROM toll_events;
            DELETE FROM schedules;
            DELETE FROM api_notes;

            INSERT INTO vehicles VALUES
                ('VH-7A29', 'training-driver', 'RF-6841', 'active'),
                ('VH-1138', 'commuter-a', 'ETA-1138', 'active'),
                ('VH-9001', 'operator-test', 'OPS-9001', 'operator');

            INSERT INTO toll_events (vehicle_id, booth_id, route_code, schedule_code, observed_at) VALUES
                ('VH-7A29', 'EAST-17', 'BIRCH', 'STANDARD', '2026-07-12T06:41:03Z'),
                ('VH-7A29', 'EAST-17', 'BIRCH', 'STANDARD', '2026-07-12T06:41:13Z'),
                ('VH-1138', 'WEST-04', 'CEDAR', 'PEAK', '2026-07-12T06:41:21Z'),
                ('VH-9001', 'EAST-17', 'BIRCH', 'MAINT_FREE', '2026-07-12T06:41:31Z');

            INSERT INTO schedules VALUES
                ('STANDARD', 'BIRCH', 'Normal tolling window', 750, 0),
                ('PEAK', 'CEDAR', 'Peak congestion window', 1250, 0),
                ('NIGHT', 'BIRCH', 'Low demand window', 300, 0),
                ('MAINT_FREE', 'BIRCH', 'Maintenance vehicle bypass', 0, 1);

            INSERT INTO api_notes VALUES
                ('recon_flag', '__SESSION_RECON_FLAG__');
            """
        )


def query_db(sql: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def telemetry_payload(data: dict) -> str:
    fields = [
        "vehicle_id",
        "pseudonym_id",
        "booth_id",
        "route_code",
        "schedule_code",
        "timestamp",
        "nonce",
    ]
    return "|".join(str(data.get(field, "")) for field in fields)


def telemetry_hmac(data: dict, config: dict | None = None) -> str:
    config = config or load_config()
    key = config["telemetry"]["hmac_key"].encode("utf-8")
    return hmac.new(key, telemetry_payload(data).encode("utf-8"), hashlib.sha256).hexdigest()


def example_secure_packet() -> dict:
    config = load_config()
    packet = {
        key: config["telemetry"][key]
        for key in [
            "vehicle_id",
            "pseudonym_id",
            "booth_id",
            "route_code",
            "schedule_code",
            "timestamp",
            "nonce",
        ]
    }
    packet["timestamp_unix"] = int(time.time())
    packet["hmac"] = telemetry_hmac(packet, config)
    return packet


def vehicle_is_operator(vehicle_id: str) -> bool:
    rows = query_db("SELECT account_state FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    return bool(rows and rows[0]["account_state"] == "operator")


class CTFHandler(SimpleHTTPRequestHandler):
    server_version = "SignalForgeCTF/1.0"

    def handle(self) -> None:
        try:
            super().handle()
        except ConnectionAbortedError:
            return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def static_request_is_private(self, request_path: str) -> bool:
        if request_path in {"/data/challenges.json", "/data/contexts.json", "/data/tolling.db", "/config/range.json", "/server.py"}:
            return True
        if request_path.startswith("/."):
            return True
        return (
            request_path.startswith("/radio/GNURadio/")
            and request_path.endswith((".py", ".grc"))
            and request_path not in public_static_artifact_paths()
        )

    def do_HEAD(self) -> None:
        request_path = f"/{unquote(urlparse(self.path).path).lstrip('/')}"
        if self.static_request_is_private(request_path):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        super().do_HEAD()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        request_path = f"/{unquote(parsed.path).lstrip('/')}"
        if self.static_request_is_private(request_path):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if parsed.path.startswith("/context/"):
            context_id = parsed.path.removeprefix("/context/").strip("/")
            known_ids = {context["id"] for context in load_contexts()}
            if context_id not in known_ids:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown context")
                return
            self.path = "/context.html"
            super().do_GET()
            return
        if parsed.path.startswith("/challenge/"):
            challenge_id = parsed.path.removeprefix("/challenge/").strip("/")
            known_ids = {task["id"] for task in load_challenges()}
            if challenge_id not in known_ids:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown challenge")
                return
            self.path = "/challenge.html"
            super().do_GET()
            return
        if parsed.path == "/api/config":
            public_config = load_config()
            public_config["telemetry"].pop("hmac_key", None)
            self.write_json(public_config)
            return
        if parsed.path == "/api/mode":
            self.write_json({"mode": MODE["value"]})
            return
        if parsed.path == "/api/tasks":
            self.write_json({"tasks": [public_task(task) for task in load_challenges()]})
            return
        if parsed.path == "/config/validation.json":
            self.write_json({"error": "server-only configuration"}, HTTPStatus.NOT_FOUND)
            return
        if parsed.path == "/api/contexts":
            self.write_json({"contexts": public_contexts()})
            return
        if parsed.path == "/api/toll/events":
            self.handle_vulnerable_events(parsed.query)
            return
        if parsed.path == "/api/toll/safe-events":
            self.handle_safe_events(parsed.query)
            return
        if parsed.path == "/api/toll/quote":
            self.handle_quote(parsed.query)
            return
        if parsed.path == "/api/telemetry/example":
            self.write_json(example_secure_packet())
            return
        if parsed.path == "/api/radio/intercept":
            self.write_json(radio_intercept(session_id_from(self)))
            return
        if parsed.path == "/api/air/weather":
            session_id = session_id_from(self)
            intercept = generate_air_weather_intercept(session_id)
            AIR_WEATHER_SESSIONS[session_id] = intercept
            self.write_json({key: value for key, value in intercept.items() if key not in {"answer", "auth_code"}})
            return
        if parsed.path == "/api/rf/session":
            session_id = session_id_from(self)
            self.write_json({"session_id": session_id, "user_data": user_data_for(session_id), "fft_bins": 1024})
            return
        if parsed.path == "/api/rf/live":
            self.handle_rf_live(parsed.query)
            return
        if parsed.path == "/api/rf/external/live":
            self.handle_rf_external_live(parsed.query)
            return
        if parsed.path == "/api/rf/external/status":
            params = parse_qs(parsed.query)
            challenge_id = params.get("challenge_id", ["external"])[0]
            self.write_json(external_feed_snapshot(challenge_id))
            return
        if parsed.path == "/api/rf/raw":
            self.handle_rf_raw(parsed.query)
            return
        if parsed.path == "/api/rf/gnu-radio-capture":
            self.handle_gnu_radio_capture(parsed.query)
            return
        if parsed.path == "/api/script/interface":
            self.write_json(script_interface_description())
            return
        if parsed.path == "/api/rsu/maintenance":
            self.write_json(
                {
                    "target": "RSU maintenance TLV parser",
                    "method": "POST",
                    "path": "/api/rsu/maintenance/parse",
                    "content_type": "application/json",
                    "schema": {"type": "0x42", "declared_length": 111, "payload": "operator note"},
                    "operator_note": "Attack Mode models the native parser's trusted-length behaviour; Secure Mode requires exact length agreement.",
                }
            )
            return
        if parsed.path == "/operator/events":
            self.handle_operator_events()
            return
        if parsed.path == "/api/research":
            self.write_json(research_notes())
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/mode":
            self.handle_mode()
            return
        if parsed.path == "/api/flag":
            self.handle_flag()
            return
        if parsed.path == "/api/toll/secure-quote":
            self.handle_secure_quote()
            return
        if parsed.path == "/api/telemetry/verify":
            self.handle_telemetry_verify()
            return
        if parsed.path == "/operator/comment":
            self.handle_operator_comment()
            return
        if parsed.path == "/api/rsu/maintenance/parse":
            self.handle_maintenance_parser()
            return
        if parsed.path == "/api/rf/command":
            self.handle_rf_command()
            return
        if parsed.path == "/api/script/terminal":
            self.handle_script_terminal()
            return
        if parsed.path == "/api/air/inject":
            self.handle_air_voice_injection()
            return
        if parsed.path == "/api/weather/alarm":
            self.handle_weather_alarm()
            return
        self.write_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean_path = unquote(parsed.path).lstrip("/")
        target = (ROOT / clean_path).resolve()
        if target == VALIDATION_CONFIG_PATH.resolve():
            return str(ROOT / "__server_private__")
        try:
            target.relative_to(ROOT)
        except ValueError:
            return str(ROOT / "index.html")
        if target.is_dir():
            target = target / "index.html"
        return str(target)

    def write_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def handle_rf_live(self, query: str) -> None:
        params = parse_qs(query)
        challenge_id = params.get("challenge_id", ["tunnel-reading-signals"])[0]
        session_id = params.get("session_id", [session_id_from(self)])[0]
        target = RF_TARGETS.get(challenge_id, RF_TARGETS["tunnel-reading-signals"])
        try:
            bins = int(params.get("bins", ["384"])[0])
            rate = float(params.get("rate", ["18"])[0])
        except ValueError:
            bins = 384
            rate = 18.0
        rate = max(3.0, min(40.0, rate))
        gnu_radio_preview = None
        try:
            if gnu_radio_capture_for(challenge_id):
                gnu_radio_preview = gnu_radio_capture_preview(challenge_id)
                profile = {key: value for key, value in gnu_radio_preview.items() if key not in {"rows", "time_rows", "iq_rows"}}
            else:
                profile = live_signal_profile(challenge_id, target=target, bins=bins)
        except (FileNotFoundError, OSError, ValueError, struct.error) as error:
            profile = live_signal_profile(challenge_id, target=target, bins=bins)
            profile["protocol_notes"]["source"] = f"GNU Radio capture unavailable ({error}); using Python fallback profile."

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send_event(event_name: str, payload: dict) -> None:
            encoded = json.dumps(payload, separators=(",", ":"))
            self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
            self.wfile.write(f"data: {encoded}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            send_event("meta", profile)
            frame = 0
            frame_count = max(1, int(profile.get("frames", 720)))
            while True:
                looped_frame = frame % frame_count
                if gnu_radio_preview:
                    send_event("frame", gnu_radio_live_frame(gnu_radio_preview, looped_frame))
                else:
                    send_event("frame", generate_live_frame(profile, looped_frame, session_id=session_id))
                frame += 1
                time.sleep(1 / rate)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def handle_rf_external_live(self, query: str) -> None:
        params = parse_qs(query)
        challenge_id = params.get("challenge_id", ["external"])[0]
        try:
            last_sequence = int(params.get("last_sequence", ["-1"])[0])
        except ValueError:
            last_sequence = -1
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send_event(event_name: str, payload: dict) -> None:
            encoded = json.dumps(payload, separators=(",", ":"))
            self.wfile.write(f"event: {event_name}\n".encode("utf-8"))
            self.wfile.write(f"data: {encoded}\n\n".encode("utf-8"))
            self.wfile.flush()

        try:
            send_event("meta", external_feed_snapshot(challenge_id))
            last_status = 0.0
            while True:
                frame = external_feed_next_frame(challenge_id, last_sequence)
                if frame:
                    last_sequence = int(frame.get("frame", last_sequence))
                    send_event("frame", frame)
                elif time.time() - last_status > 2.0:
                    send_event("status", external_feed_snapshot(challenge_id))
                    last_status = time.time()
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def handle_rf_raw(self, query: str) -> None:
        params = parse_qs(query)
        challenge_id = params.get("challenge_id", ["tunnel-reading-signals"])[0]
        target = RF_TARGETS.get(challenge_id, RF_TARGETS["tunnel-reading-signals"])
        try:
            byte_count = int(params.get("bytes", ["2097152"])[0])
            byte_offset = int(params.get("offset", ["0"])[0])
        except ValueError:
            byte_count = 2_097_152
            byte_offset = 0
        if gnu_radio_capture_for(challenge_id):
            try:
                body, source = read_gnu_radio_raw_sample(challenge_id, byte_count=byte_count, byte_offset=byte_offset)
            except (FileNotFoundError, OSError, ValueError) as error:
                self.write_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
                return
            filename = f"{source['stem']}-sample-{source['offset']}.cf32"
        else:
            body = raw_iq_bytes(challenge_id, target=target, frame_count=96)
            source = None
            filename = f"{challenge_id}-complex16.iq"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        if source:
            self.send_header("X-Signal-Source", source["source_file"])
            self.send_header("X-Signal-Source-Size", str(source["source_size"]))
            self.send_header("X-Signal-Offset", str(source["offset"]))
        self.end_headers()
        self.wfile.write(body)

    def handle_gnu_radio_capture(self, query: str = "") -> None:
        params = parse_qs(query)
        challenge_id = params.get("challenge_id", ["tunnel-reading-signals"])[0]
        try:
            self.write_json(gnu_radio_capture_preview(challenge_id))
        except FileNotFoundError as error:
            self.write_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except (OSError, ValueError, struct.error) as error:
            self.write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def handle_weather_alarm(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "message": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        challenge_id = str(body.get("challenge_id", "weather-boring-active-re"))
        if challenge_id != "weather-boring-active-re":
            self.write_json({"ok": False, "message": "This packet input is only connected to the warning-light task."}, HTTPStatus.NOT_FOUND)
            return
        try:
            packet = parse_u32_packet(body.get("packet", ""))
        except ValueError as error:
            self.write_json({"ok": False, "message": str(error)}, HTTPStatus.BAD_REQUEST)
            return

        emergency = alarm_decode_packet(packet)
        alarm_pattern = emergency == 0xB
        accepted = alarm_pattern and MODE["value"] == "attack"
        response = {
            "ok": accepted,
            "packet": f"0x{packet:08X}",
            "decoded_emergency": f"0x{emergency:X}",
            "alarm_active": accepted,
            "message": (
                "Forged packet accepted by AlarmCheck(); the emergency warning light is active."
                if accepted
                else "Alarm bits matched, but Secure Mode rejected the unauthenticated packet."
                if alarm_pattern
                else "Packet decoded successfully, but its emergency nibble does not activate the light."
            ),
        }
        if accepted:
            session_id = session_id_from(self, body)
            response["flag"] = expected_flag_for(session_id, challenge_id)
            response["message"] += f" Flag: {response['flag']}"
            self.write_json(response)
            return
        self.write_json(response, HTTPStatus.FORBIDDEN if alarm_pattern else HTTPStatus.UNPROCESSABLE_ENTITY)

    def handle_flag(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "message": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return

        task_id = body.get("taskId", "")
        submitted = str(body.get("flag", "")).strip().upper()
        task = next((item for item in load_challenges() if item["id"] == task_id), None)
        if not task:
            self.write_json({"ok": False, "message": "Unknown task."}, HTTPStatus.NOT_FOUND)
            return

        session_id = session_id_from(self, body)
        if is_valid_flag(session_id, task_id, submitted):
            self.write_json({"ok": True, "message": "Correct. Task solved.", "points": task["points"]})
        else:
            self.write_json({"ok": False, "message": "Not quite. Re-check the signal evidence and hints."})

    def handle_air_voice_injection(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "message": "Invalid report payload."}, HTTPStatus.BAD_REQUEST)
            return

        session_id = session_id_from(self, body)
        challenge_id = str(body.get("challenge_id", ""))
        if challenge_id != "civilian-emergency-active-re":
            self.write_json(
                {"ok": False, "message": "The emergency rebroadcast input is connected only to the final civilian emergency task."},
                HTTPStatus.NOT_FOUND,
            )
            return
        intercept = AIR_WEATHER_SESSIONS.get(session_id)
        if not intercept or str(body.get("intercept_id", "")) != intercept["intercept_id"]:
            self.write_json({"ok": False, "message": "Generate a current intercept before filing the report."}, HTTPStatus.BAD_REQUEST)
            return

        message = " ".join(str(body.get("message", "")).strip().upper().split())
        zone = str(intercept.get("zone", intercept.get("sector", ""))).upper()
        required = {
            "target callsign": intercept["callsign"].upper() in message,
            "zone identifier": f"ZONE {zone}" in message,
            "alert reason": "ALERT " in message,
            "action instruction": "ACTION " in message,
            "authentication code": f"AUTH {intercept['auth_code']}" in message,
            "credible public-safety wording": any(word in message for word in {"WEATHER", "STORM", "FLOOD", "FIRE", "SMOKE", "CLOSURE", "EVACUATE", "SHELTER", "HAZARD"}),
        }
        missing = [label for label, present in required.items() if not present]
        if not missing:
            self.write_json({
                "ok": True,
                "message": "Protocol accepted. The synthetic public-warning message was rebroadcast on the training net.",
                "flag": expected_flag_for(session_id, challenge_id),
                "broadcast": message,
            })
            return
        self.write_json({
            "ok": False,
            "message": f"Injection rejected. Missing or incorrect: {', '.join(missing)}.",
            "accepted_fields": [label for label, present in required.items() if present],
        })

    def handle_mode(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        requested = str(body.get("mode", "")).lower()
        if requested not in {"attack", "secure"}:
            self.write_json({"error": "mode must be attack or secure"}, HTTPStatus.BAD_REQUEST)
            return
        MODE["value"] = requested
        if requested == "attack":
            REPLAY_CACHE.clear()
        self.write_json({"mode": MODE["value"]})

    def handle_vulnerable_events(self, query: str) -> None:
        if MODE["value"] == "secure":
            self.write_json(
                {
                    "mode": "secure",
                    "blocked": True,
                    "reason": "Secure Mode disables the intentionally vulnerable SQL endpoint. Use /api/toll/safe-events.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        params = parse_qs(query)
        vehicle_id = params.get("vehicle_id", [""])[0]
        sql = (
            "SELECT event_id, vehicle_id, booth_id, route_code, schedule_code "
            f"FROM toll_events WHERE vehicle_id = '{vehicle_id}'"
        )
        try:
            rows = query_db(sql)
            session_id = session_id_from(self)
            for row in rows:
                for key, value in row.items():
                    if value == "__SESSION_RECON_FLAG__":
                        row[key] = flag_for(session_id, "backend-recon")
            self.write_json(
                {
                    "warning": "Intentionally vulnerable training endpoint. Do not copy this pattern.",
                    "query": sql,
                    "rows": rows,
                }
            )
        except sqlite3.Error as exc:
            self.write_json(
                {
                    "warning": "SQL error intentionally exposed for the training task.",
                    "query": sql,
                    "error": str(exc),
                },
                HTTPStatus.BAD_REQUEST,
            )

    def handle_safe_events(self, query: str) -> None:
        params = parse_qs(query)
        vehicle_id = params.get("vehicle_id", [""])[0]
        rows = query_db(
            """
            SELECT event_id, vehicle_id, booth_id, route_code, schedule_code
            FROM toll_events
            WHERE vehicle_id = ?
            """,
            (vehicle_id,),
        )
        self.write_json(
            {
                "defence": "This endpoint uses a parameterized query, so SQL text and user data stay separate.",
                "rows": rows,
            }
        )

    def handle_quote(self, query: str) -> None:
        params = parse_qs(query)
        vehicle_id = params.get("vehicle_id", [""])[0]
        booth_id = params.get("booth_id", [""])[0]
        route_code = params.get("route_code", [""])[0]
        schedule_code = params.get("schedule_code", [""])[0]

        schedules = query_db(
            """
            SELECT schedule_code, route_code, label, price_cents, operator_only
            FROM schedules
            WHERE route_code = ? AND schedule_code = ?
            """,
            (route_code, schedule_code),
        )
        if not schedules:
            self.write_json({"error": "No matching schedule."}, HTTPStatus.NOT_FOUND)
            return

        schedule = schedules[0]
        if MODE["value"] == "secure" and schedule["operator_only"] and not vehicle_is_operator(vehicle_id):
            self.write_json(
                {
                    "mode": "secure",
                    "authorized_schedule": False,
                    "decision": "rejected",
                    "reason": "Secure Mode derives operator-only schedule entitlement server-side.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        result = {
            "vehicle_id": vehicle_id,
            "booth_id": booth_id,
            "route_code": route_code,
            "schedule_code": schedule_code,
            "price_cents": schedule["price_cents"],
            "logic_flaw": "The endpoint trusts schedule_code from telemetry instead of deriving entitlement server-side.",
        }
        if schedule["price_cents"] == 0:
            result["flag"] = flag_for(session_id_from(self), "free-trip-logic-flaw")
        self.write_json(result)

    def handle_secure_quote(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        packet = body.get("packet", body)
        if not isinstance(packet, dict):
            self.write_json({"decision": "rejected", "reason": "packet must be a JSON object"}, HTTPStatus.BAD_REQUEST)
            return
        verification = verify_telemetry_packet(packet)
        if not verification["decision"] == "accepted":
            self.write_json(verification, HTTPStatus.FORBIDDEN)
            return

        schedules = query_db(
            """
            SELECT schedule_code, route_code, label, price_cents, operator_only
            FROM schedules
            WHERE route_code = ? AND schedule_code = ?
            """,
            (packet.get("route_code", ""), packet.get("schedule_code", "")),
        )
        if not schedules:
            self.write_json({"decision": "rejected", "reason": "No matching schedule."}, HTTPStatus.NOT_FOUND)
            return

        schedule = schedules[0]
        authorized = not schedule["operator_only"] or vehicle_is_operator(packet.get("vehicle_id", ""))
        if not authorized:
            self.write_json(
                {
                    "decision": "rejected",
                    "authorized_schedule": False,
                    "reason": "Operator-only schedule denied for this vehicle.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        self.write_json(
            {
                "decision": "accepted",
                "authorized_schedule": True,
                "price_cents": schedule["price_cents"],
                "schedule_code": schedule["schedule_code"],
            }
        )

    def handle_telemetry_verify(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        packet = body.get("packet", body)
        if not isinstance(packet, dict):
            self.write_json({"decision": "rejected", "reason": "packet must be a JSON object"}, HTTPStatus.BAD_REQUEST)
            return
        result = verify_telemetry_packet(packet)
        status = HTTPStatus.OK if result["decision"] == "accepted" else HTTPStatus.FORBIDDEN
        self.write_json(result, status)

    def handle_operator_events(self) -> None:
        self.write_json(
            {
                "mode": MODE["value"],
                "events": OPERATOR_COMMENTS,
                "rendering_note": "Attack Mode intentionally renders comments as HTML in the browser. Secure Mode renders text only.",
            }
        )

    def handle_operator_comment(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        event = {
            "callsign": str(body.get("callsign", "UNKNOWN")),
            "route_note": str(body.get("route_note", "")),
            "operator_comment": str(body.get("operator_comment", "")),
        }
        if MODE["value"] == "secure":
            event = {key: html.escape(value) for key, value in event.items()}
        OPERATOR_COMMENTS.append(event)
        self.write_json({"ok": True, "mode": MODE["value"], "event": event})

    def handle_maintenance_parser(self) -> None:
        try:
            body = read_json_body(self)
            tlv_type = int(str(body.get("type", "0")), 0)
            declared_length = int(body.get("declared_length", 0))
            payload = str(body.get("payload", ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            self.write_json({"error": "type and declared_length must be valid integers"}, HTTPStatus.BAD_REQUEST)
            return

        actual_length = len(payload.encode("utf-8"))
        if tlv_type != 0x42:
            self.write_json({"decision": "rejected", "reason": "unsupported TLV type"}, HTTPStatus.BAD_REQUEST)
            return
        if MODE["value"] == "secure" and declared_length != actual_length:
            self.write_json(
                {
                    "mode": "secure",
                    "decision": "rejected",
                    "declared_length": declared_length,
                    "actual_length": actual_length,
                    "reason": "declared length does not equal available payload length",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        result = {
            "mode": MODE["value"],
            "decision": "parsed",
            "declared_length": declared_length,
            "actual_length": actual_length,
            "length_mismatch": declared_length != actual_length,
            "diagnostic_command_seen": "MAINT_DIAG_UNLOCK" in payload,
        }
        if MODE["value"] == "attack" and declared_length > actual_length and "MAINT_DIAG_UNLOCK" in payload:
            result["diagnostic_access"] = "granted"
            result["flag"] = flag_for(session_id_from(self, body), "length-field-chaos")
        self.write_json(result)

    def handle_rf_command(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "lines": ["Invalid command payload."]}, HTTPStatus.BAD_REQUEST)
            return

        session_id = session_id_from(self, body)
        challenge_id = str(body.get("challenge_id", ""))
        action = str(body.get("action", "")).lower().strip()
        arguments = str(body.get("arguments", "")).strip()
        receiver = body.get("receiver", {}) if isinstance(body.get("receiver", {}), dict) else {}
        transmitter = body.get("transmitter") if isinstance(body.get("transmitter"), dict) else None
        response, status = build_rf_command_response(session_id, challenge_id, action, arguments, receiver, transmitter)
        self.write_json(response, status)
        return
        target = RF_TARGETS.get(challenge_id)
        if not target:
            self.write_json({"ok": False, "lines": ["No RF target is assigned to this module."]}, HTTPStatus.NOT_FOUND)
            return

        try:
            center_mhz = float(receiver.get("center_mhz", 0))
            span_khz = max(1.0, float(receiver.get("span_khz", 1)))
            gain_db = float(receiver.get("gain_db", 0))
            squelch_db = float(receiver.get("squelch_db", -90))
        except (TypeError, ValueError):
            self.write_json({"ok": False, "lines": ["Receiver values must be numeric."]}, HTTPStatus.BAD_REQUEST)
            return

        modulation = str(receiver.get("modulation", "AUTO")).upper()
        offset_khz = abs(center_mhz - target["center_mhz"]) * 1000
        in_view = offset_khz <= span_khz / 2
        tuned = offset_khz <= max(8.0, min(40.0, span_khz / 16))
        demod_ok = modulation in target["modulations"]
        level_db = -72 + min(28, gain_db * 0.7)
        above_squelch = level_db >= squelch_db
        locked = tuned and demod_ok and above_squelch

        base = {
            "ok": True,
            "action": action,
            "locked": locked,
            "target": target["label"],
            "receiver": {"center_mhz": center_mhz, "offset_khz": round(offset_khz, 3), "modulation": modulation},
            "user_data": user_data_for(session_id),
        }

        if action == "scan":
            if in_view:
                base["lines"] = [
                    f"ENERGY  {target['label']}  {target['center_mhz']:.6f} MHz  level {level_db:.1f} dBFS",
                    f"OFFSET  {offset_khz:.1f} kHz  candidate demodulations: {', '.join(sorted(target['modulations']))}",
                ]
            else:
                base["lines"] = ["No target energy inside the selected span.", "Adjust centre/span or inspect the module's signal intelligence."]
            self.write_json(base)
            return

        if action in {"status", "tune"}:
            base["lines"] = [
                f"RX {center_mhz:.6f} MHz / span {span_khz:.0f} kHz / {modulation} / gain {gain_db:.0f} dB",
                f"TARGET {'LOCKED' if locked else 'UNLOCKED'} / offset {offset_khz:.1f} kHz / squelch {'open' if above_squelch else 'closed'}",
            ]
            self.write_json(base)
            return

        if not locked:
            base["ok"] = False
            base["lines"] = [
                "Receiver not locked: no usable target output.",
                f"Check centre frequency, demodulation, gain, and squelch (offset {offset_khz:.1f} kHz).",
            ]
            self.write_json(base, HTTPStatus.BAD_REQUEST)
            return

        if action == "receive":
            lines = [f"LOCK {target['label']} / sync acquired / CRC usable"]
            if challenge_id == "find-the-scheme":
                lines += ["BEACON vendor user_data decoded", f"FLAG {flag_for(session_id, challenge_id)}"]
                base["flag"] = flag_for(session_id, challenge_id)
            elif challenge_id == "reverse-the-decoder":
                lines += ["FRAME SFCTF1|VH-7A29|PX-41F0|EAST-17|BIRCH|STANDARD|...|5e", "Decoder input buffered. Try `decode`." ]
            elif challenge_id == "backend-recon":
                lines += ["UPLINK vehicle_id=VH-7A29 service=/api/toll/events", "The terminal can run same-origin requests with `request <path>`." ]
            elif challenge_id == "free-trip-logic-flaw":
                lines += ["TOLL FRAME schedule=STANDARD price=750", "Replay/interference controls can alter the observed maintenance schedule." ]
            elif challenge_id == "operator-console-xss":
                lines += ["AFSK operator_note decoded", "NOTE contains an active console control; use `forward console`." ]
            elif challenge_id == "weather-radio-watch":
                lines += ["AM voice carrier acquired on 169.650 MHz", "Open the council warning audio net, intercept the exchange, and recover its message fields."]
            else:
                lines += ["TLV type=0x42 declared=111 actual=47", "PAYLOAD MAINT_DIAG_UNLOCKAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]
            base["lines"] = lines
            self.write_json(base)
            return

        if action == "decode" and challenge_id == "reverse-the-decoder":
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["CHECKSUM expected=5e provided=5e valid=true", f"DECODER OUTPUT {base['flag']}"]
        elif action == "interfere" and MODE["value"] == "attack" and challenge_id == "free-trip-logic-flaw" and any(word in arguments.lower() for word in {"replay", "maint_free", "maintenance"}):
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["INTERFERENCE replay aligned / schedule=MAINT_FREE", "TOLL OUTPUT price=0", f"FLAG {base['flag']}"]
        elif action == "transmit":
            if MODE["value"] == "attack" and challenge_id == "free-trip-logic-flaw" and "replay" in arguments.lower():
                base["flag"] = flag_for(session_id, challenge_id)
                base["lines"] = ["TX replay waveform visible in receiver passband", "TARGET OUTPUT schedule=MAINT_FREE price=0", f"FLAG {base['flag']}"]
            else:
                base["lines"] = ["TX burst injected into local spectrum simulation.", "No target state change was observed for this waveform."]
        elif action == "forward" and MODE["value"] == "attack" and challenge_id == "operator-console-xss" and "console" in arguments.lower():
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["FORWARD operator_note -> console", "Console rendered RF-origin control in Attack Mode.", f"UI OUTPUT {base['flag']}"]
        elif action == "send" and MODE["value"] == "attack" and challenge_id == "length-field-chaos" and "maint_diag_unlock" in arguments.lower():
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["TX TLV accepted / length mismatch reached native parser", "DIAGNOSTIC ACCESS granted", f"TARGET OUTPUT {base['flag']}"]
        else:
            base["ok"] = False
            base["lines"] = ["Command reached the target but did not trigger its success condition.", "Use `receive` and the module intelligence to inspect the target output."]
        self.write_json(base, HTTPStatus.OK if base["ok"] else HTTPStatus.BAD_REQUEST)

    def handle_script_terminal(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "lines": ["Invalid script terminal payload."]}, HTTPStatus.BAD_REQUEST)
            return
        session_id = session_id_from(self, body)
        response, status = run_script_terminal_command(session_id, body)
        response.setdefault("session_id", session_id)
        self.write_json(response, status)


def verify_telemetry_packet(packet: dict) -> dict:
    config = load_config()
    supplied = str(packet.get("hmac", ""))
    expected = telemetry_hmac(packet, config)
    hmac_valid = hmac.compare_digest(supplied, expected)

    timestamp_unix = int(packet.get("timestamp_unix", 0) or 0)
    now = int(time.time())
    window = int(config["security"]["freshness_window_seconds"])
    fresh_timestamp = timestamp_unix > 0 and abs(now - timestamp_unix) <= window

    nonce = str(packet.get("nonce", ""))
    replay_seen = nonce in REPLAY_CACHE

    accepted = hmac_valid and fresh_timestamp and not replay_seen
    if accepted:
        REPLAY_CACHE.add(nonce)

    return {
        "mode": MODE["value"],
        "hmac_valid": hmac_valid,
        "fresh_timestamp": fresh_timestamp,
        "replay_seen": replay_seen,
        "authorized_schedule": None,
        "decision": "accepted" if accepted else "rejected",
        "reason": "packet authenticated and fresh" if accepted else "packet failed HMAC, freshness, or replay checks",
        "expected_hmac_for_training": expected if MODE["value"] == "attack" else None,
    }


def generate_air_weather_intercept(session_id: str) -> dict:
    rng = random.SystemRandom()
    callsign = f"{rng.choice(['LIBRARY', 'DEPOT', 'SHELTER', 'STATION', 'TUNNEL', 'CIVIC'])}-{rng.randint(1, 9)}"
    controller = rng.choice(["COUNCIL CONTROL", "CIVIC DISPATCH", "CITY WARNING", "RANGE CONTROL"])
    facility = rng.choice(["public library", "bus depot", "sports centre", "river pump station", "tunnel control room", "community shelter"])
    zone = rng.choice(["NORTH", "RIVER", "CBD", "EAST", "WEST", "HILLS"])
    wind_direction = rng.randrange(10, 360, 10)
    wind_speed = rng.randrange(12, 46)
    gust = wind_speed + rng.randrange(6, 21)
    visibility = rng.choice(["three", "five", "seven", "ten", "more than ten"])
    cloud = rng.choice(["heavy cloud over the ridge", "low cloud over the river", "clear air west of the city", "rain bands moving through the zone"])
    pressure = rng.randrange(995, 1028)
    auth_code = f"{rng.choice(['RIVER', 'ANCHOR', 'CIVIC', 'VECTOR', 'HARBOUR', 'SUMMIT'])}-{rng.randint(2, 9)}"
    hazard, advisory, action, readback = rng.choice([
        ("storm", "severe storm cells crossing low-lying roads", "SHELTER", "storm warning and shelter instruction"),
        ("flood", "river gauge rising above the local warning threshold", "EVACUATE", "flood warning and evacuation instruction"),
        ("smoke", "smoke reducing visibility near public roads", "CLOSE ROUTE", "smoke warning and route closure"),
        ("heat", "extreme heat affecting public transport shelters", "WELFARE CHECK", "heat warning and welfare checks"),
        ("wind", "damaging wind reported around exposed infrastructure", "SECURE SITE", "wind warning and site security"),
        ("closure", "building access restricted by local hazard reports", "HOLD POSITION", "closure warning and hold instruction"),
    ])
    request = rng.choice([
        "request current warning status and action",
        "say weather for the zone and public safety action",
        "request local hazard status and council instruction",
    ])
    acknowledgement = rng.choice(["copy all", "good readback", "affirm, that is correct", "confirmed"])
    intercept_id = session_token(session_id, f"council-weather:{time.time_ns()}:{rng.random()}", 12)
    lines = [
        {"speaker": callsign, "role": "site", "text": f"{controller}, {callsign}, {facility}, zone {zone}, {request}."},
        {"speaker": controller, "role": "controller", "text": f"{callsign}, {controller}. Zone {zone}: wind {wind_direction:03d} at {wind_speed}, gusting {gust}; visibility {visibility} kilometres; {cloud}; QNH {pressure}. Primary alert is {advisory}. Action {action}."},
        {"speaker": callsign, "role": "site", "text": f"{controller}, {callsign}, copy wind {wind_direction:03d} at {wind_speed}, QNH {pressure}, {readback}."},
        {"speaker": controller, "role": "controller", "text": f"{callsign}, {acknowledgement}. Report when action is complete for zone {zone}. Authentication for warning updates is {auth_code}."},
    ]
    return {
        "intercept_id": intercept_id,
        "channel": "169.650 MHz",
        "modulation": "AM",
        "callsign": callsign,
        "controller": controller,
        "sector": zone,
        "zone": zone,
        "lines": lines,
        "answer": hazard,
        "action": action,
        "auth_code": auth_code,
    }


def radio_intercept(session_id: str = "anonymous") -> dict:
    config = load_config()
    telemetry = config["telemetry"]
    return {
        "frame_id": "RF-INT-2437-0007",
        "callsign": "CIVIC-OPS-1",
        "channel_label": "TOLL-LPI-TRAINING-03",
        "center_hz": config["rf"]["center_hz"],
        "carrier_offset_hz": -320000,
        "estimated_doppler_hz": 42,
        "rssi_dbm": -67,
        "snr_db": 18.4,
        "modulation": "2-FSK training burst with FHSS-like channel plan",
        "preamble": "0xA7D5",
        "sync_word": "0xC35A",
        "vehicle_id": telemetry["vehicle_id"],
        "pseudonym_id": telemetry["pseudonym_id"],
        "booth_id": telemetry["booth_id"],
        "route_code": telemetry["route_code"],
        "schedule_code": telemetry["schedule_code"],
        "timestamp": telemetry["timestamp"],
        "nonce": telemetry["nonce"],
        "checksum": "0x5e",
        "operator_note": (
            "RF-origin operator_note field: schedule anomaly requires review. "
            f"<button onclick=\"document.querySelector('#operator-flag').textContent='{flag_for(session_id, 'operator-console-xss')}'\">"
            "Render test</button>"
        ),
        "sink_warning": "This decoded note is untrusted RF-origin text. Attack Mode renders it as HTML; Secure Mode renders it as text.",
        "operator_action": "Correlate burst with toll event, then review trust boundary before posting to console.",
    }


def research_notes() -> dict:
    return {
        "rf": [
            "Waterfalls show power over frequency and time; repeated vertical marks indicate periodic bursts.",
            "ASK/OOK-style training signals are useful for teaching because amplitude changes are easy to inspect.",
            "Later stages should include multipath, Doppler, timing offset, burst collisions, adaptive coding, LPI/LPD tradeoffs, and direction-finding evidence.",
            "SigMF stores RF sample data with JSON metadata so captures remain reproducible without hardware."
        ],
        "cyber": [
            "A decoded radio field is still attacker-controlled input once it reaches a backend.",
            "SQL injection happens when applications concatenate untrusted input into query text.",
            "Prepared statements and allow-listed dynamic values are the intended defences for this CTF.",
            "Hard cyber stages should combine RE, memory corruption, fuzzing, protocol state-machine bugs, XSS sinks, authorization failures, and telemetry replay."
        ],
        "sota_security": [
            "Secure Mode demonstrates HMAC, freshness checks, replay rejection, server-side authorization, and safe SQL as the baseline, not the finish line.",
            "SOTA hard levels should require layered assurance: hardware root of trust, secure boot, signed firmware, key separation, remote attestation, and measured boot evidence.",
            "Radio SOTA should cover adaptive hopping, spread spectrum, interference classification, MIMO/beam/null steering concepts, propagation modelling, and jamming resilience.",
            "Cyber SOTA should include memory-safe parsers, fuzzing harnesses, binary hardening, SBOM/supply-chain checks, CSP/output encoding, and backend policy enforcement.",
            "Detection SOTA should fuse RF features, decoded protocol behaviour, backend logs, and anomaly models because valid packets can still be operationally suspicious."
        ],
        "hardware": [
            "Keep assessed transmit paths disabled, but model receiver front-end limits: saturation, dynamic range, adjacent-channel interference, clock drift, and oscillator error.",
            "Developer extensions can add signed firmware images, boot measurements, and simulated device attestation before the backend trusts a roadside unit.",
            "Hardware realism should also include antenna patterns, path loss, terrain/urban multipath assumptions, and calibration notes for every generated capture."
        ],
        "jamming": [
            "Beginner jamming captures can show obvious wideband noise; advanced captures should distinguish barrage, spot, sweep, follower, deceptive replay, and protocol-aware interference.",
            "Defence challenges should force tradeoffs between hopping, coding, power control, directional receive, redundancy, holdover logic, and backend fraud detection.",
            "The CTF should reward classification and mitigation planning, not over-the-air transmission."
        ],
        "gnu_radio": [
            "Use GNU Radio Companion in WSL/Ubuntu to generate flowgraphs.",
            "For this project, GNU Radio should generate artifacts rather than transmit over the air.",
            "The live bridge accepts JSON-lines FFT rows or framed raw cf32_le IQ on the local Signal Forge ingest socket.",
            "A GNU Radio flowgraph can feed it through a Python block, a TCP/file sink plus bridge script, or a future ZeroMQ adapter."
        ]
    }


def main() -> None:
    validate_public_static_artifacts()
    init_db()
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", "8000"))
    mimetypes.add_type("application/json", ".sigmf-meta")
    start_external_ingest_server()
    server = ThreadingHTTPServer(("localhost", port), CTFHandler)
    print(f"Signal Forge CTF serving http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
