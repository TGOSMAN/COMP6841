from __future__ import annotations

import json
import html
import hmac
import hashlib
import math
import mimetypes
import os
import random
import sqlite3
import struct
import time
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
SCRIPT_TERMINALS: dict[str, dict] = {}

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


def load_contexts() -> list[dict]:
    with CONTEXTS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_validation_config() -> dict:
    with VALIDATION_CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def configured_gnu_radio_path(settings: dict | None = None) -> tuple[Path, Path]:
    settings = settings or load_config().get("gnu_radio_capture", {})
    relative_path = Path(str(settings.get("path", "radio/GNURadio/ReadingSignals.sigmf-data")))
    capture_path = (ROOT / relative_path).resolve()
    try:
        capture_path.relative_to(ROOT)
    except ValueError as error:
        raise ValueError("GNU Radio capture path must remain inside the project") from error
    return capture_path, relative_path


def decode_gnu_radio_ook(settings: dict | None = None) -> dict:
    """Recover OOK bits from IQ amplitude without assuming byte or payload content."""
    settings = settings or load_config().get("gnu_radio_capture", {})
    capture_path, _ = configured_gnu_radio_path(settings)
    if not capture_path.is_file():
        raise FileNotFoundError(f"GNU Radio capture not found: {capture_path.name}")
    samples_per_symbol = max(8, int(settings.get("samples_per_symbol", 500)))
    max_samples = max(samples_per_symbol * 32, min(1_000_000, int(settings.get("decode_max_samples", 500000))))
    with capture_path.open("rb") as handle:
        raw = handle.read(max_samples * 8)
    complete_bytes = len(raw) - len(raw) % 8
    magnitudes = [math.hypot(real, imag) for real, imag in struct.iter_unpack("<ff", raw[:complete_bytes])]
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
        if score > best["score"]:
            best = {
                "score": score,
                "bits": "".join(str(bit) for bit in bits[:512]),
                "confidence": max(0.0, min(0.99, contrast * (1.0 - min(0.8, spread)))),
                "samples_per_symbol": samples_per_symbol,
                "phase": phase,
                "threshold": threshold,
            }
    return {"ok": bool(best["bits"]), **best, "note": "Recovered from IQ amplitude without byte or payload assumptions."}


def gnu_radio_capture_preview() -> dict:
    """Convert the configured raw GNU Radio complex-float capture to web FFT rows."""
    settings = load_config().get("gnu_radio_capture", {})
    capture_path, relative_path = configured_gnu_radio_path(settings)
    if not capture_path.is_file():
        raise FileNotFoundError(f"GNU Radio capture not found: {relative_path.as_posix()}")

    datatype = str(settings.get("datatype", "cf32_le"))
    if datatype != "cf32_le":
        raise ValueError(f"Unsupported GNU Radio datatype: {datatype}; expected cf32_le")
    sample_rate = float(settings.get("sample_rate", 44200))
    center_hz = float(settings.get("center_hz", 915000000))
    fft_bins = int(settings.get("fft_bins", 512))
    max_frames = int(settings.get("max_frames", 120))
    if fft_bins < 64 or fft_bins > 2048 or fft_bins & (fft_bins - 1):
        raise ValueError("fft_bins must be a power of two between 64 and 2048")
    max_frames = max(1, min(512, max_frames))

    bytes_per_sample = 8
    sample_count = capture_path.stat().st_size // bytes_per_sample
    if sample_count < fft_bins:
        raise ValueError(f"Capture needs at least {fft_bins} complete complex-float samples")
    decoder = decode_gnu_radio_ook(settings)
    symbol_phase = int(decoder.get("phase", 0))
    samples_per_symbol = int(decoder.get("samples_per_symbol", settings.get("samples_per_symbol", 500)))
    if decoder.get("ok") and symbol_phase + fft_bins <= sample_count:
        available_frames = 1 + max(0, (sample_count - symbol_phase - fft_bins) // samples_per_symbol)
        frame_count = min(max_frames, available_frames, len(str(decoder.get("bits", ""))))
        starts = [symbol_phase + index * samples_per_symbol for index in range(frame_count)]
    else:
        frame_count = min(max_frames, max(1, sample_count // fft_bins))
        last_start = max(0, sample_count - fft_bins)
        starts = [round(index * last_start / max(1, frame_count - 1)) for index in range(frame_count)]
    window = [0.5 - 0.5 * math.cos(2.0 * math.pi * index / max(1, fft_bins - 1)) for index in range(fft_bins)]
    power_rows: list[list[float]] = []
    time_rows_raw: list[list[float]] = []
    iq_rows_raw: list[list[complex]] = []

    with capture_path.open("rb") as handle:
        for start in starts:
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
    parser = {
        "stage": "bit_slice",
        "confidence": decoder.get("confidence", 0.0),
        "bit_buffer": recovered_bits or "no stable symbols recovered",
        "fields": {
            "detected_frequency_hz": round(detected_frequency_hz, 3),
            "modulation": "OOK/ASK amplitude",
            "samples_per_symbol": decoder.get("samples_per_symbol", settings.get("samples_per_symbol", 500)),
            "recovered_bit_count": len(recovered_bits),
            "integrity": "no CRC or framing field present in the GNU Radio generator",
        },
        "note": "Binary symbols recovered from IQ amplitude; byte/payload decoding is left to the learner.",
    }
    return {
        "scheme_id": "GNU-RADIO-LOCAL-CAPTURE",
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
        "parser": parser,
        "description": "Waterfall generated by the Signal Forge backend from a local GNU Radio cf32_le File Sink capture.",
        "source_file": relative_path.as_posix(),
        "sample_count": sample_count,
        "duration_seconds": sample_count / sample_rate,
        "protocol_notes": {
            "datatype": datatype,
            "metadata": "Configured server-side; GNU Radio File Meta Sink output is not required."
        },
        "annotations": [],
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


def build_rf_command_response(session_id: str, challenge_id: str, action: str, arguments: str, receiver: dict) -> tuple[dict, HTTPStatus]:
    action = action.lower().strip()
    target = RF_TARGETS.get(challenge_id)
    if not target:
        return {"ok": False, "lines": ["No RF target is assigned to this subtask."]}, HTTPStatus.NOT_FOUND

    imported_capture = None
    if challenge_id == "tunnel-reading-signals":
        try:
            imported_capture = gnu_radio_capture_preview()
            target = {
                **target,
                "center_mhz": float(imported_capture["detected_frequency_hz"]) / 1e6,
                "span_khz": float(imported_capture["sample_rate_hz"]) / 1e3,
                "modulations": {"AUTO", "OOK", "ASK"},
                "label": "GNU-RADIO-READING-SIGNALS",
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
            base["parser"] = parser
            lines = [
                f"LOCK {target['label']} / measured carrier {target['center_mhz']:.6f} MHz",
                "OOK amplitude clock recovered / no CRC or framing field present",
            ]
            if bitstream and set(bitstream) <= {"0", "1"}:
                base["bitstream"] = bitstream
                lines += [f"BITSTREAM RECOVERED / {len(bitstream)} bits", bitstream]
            else:
                base["ok"] = False
                lines.append("Carrier is locked, but no stable binary symbols were recovered from the IQ samples.")
            base["lines"] = lines
            return base, HTTPStatus.OK if base["ok"] else HTTPStatus.UNPROCESSABLE_ENTITY

        lines = [f"LOCK {target['label']} / sync acquired / CRC usable"]
        if challenge_id in RECEIVE_FLAG_TASKS:
            base["flag"] = flag_for(session_id, challenge_id)
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
        base["flag"] = flag_for(session_id, challenge_id)
        base["lines"] = ["DECODE accepted / recovered hidden field", f"FLAG {base['flag']}"]
    elif action == "interfere" and MODE["value"] == "attack" and challenge_id in INTERFERENCE_FLAG_TASKS and any(
        word in lower_args for word in {"noise", "dos", "mismatch", "jam", "metadata"}
    ):
        base["flag"] = flag_for(session_id, challenge_id)
        base["lines"] = ["INTERFERENCE accepted / decoded string mismatch observed", f"DISPLAY OUTPUT {base['flag']}"]
    elif action == "transmit" and MODE["value"] == "attack" and challenge_id in TRANSMIT_FLAG_TASKS and any(
        word in lower_args for word in {"sign", "message", "metadata", "fibonacci", "tone", "gate", "null", "theta"}
    ):
        base["flag"] = flag_for(session_id, challenge_id)
        base["lines"] = ["TX waveform accepted by local target", "TARGET EFFECT matched success condition", f"FLAG {base['flag']}"]
    elif action == "send" and MODE["value"] == "attack" and challenge_id in SEND_FLAG_TASKS and any(
        word in lower_args
        for word in {"warning", "light", "auth", "evacuation", "anomaly", "testbench", "latch", "default", "bitstream", "superuser", "kill"}
    ):
        base["flag"] = flag_for(session_id, challenge_id)
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
        "base_url": "http://localhost:8000",
        "endpoints": {
            "GET /api/script/interface": "Describe this script-facing interface.",
            "POST /api/script/terminal": "Run one terminal command against a selected subtask.",
            "GET /api/contexts": "List situations and nested subtasks.",
            "GET /api/tasks": "List all subtasks.",
            "GET /api/rf/live": "Stream live Python-generated FFT rows, time slices, and parser events.",
            "GET /api/rf/raw": "Download raw complex16 IQ samples generated from the same Python signal profile.",
            "GET /api/rf/gnu-radio-capture": "Analyse the configured local GNU Radio cf32_le capture and return measured FFT, tuned IQ, and recovered bits.",
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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/data/challenges.json", "/data/contexts.json", "/data/tolling.db", "/config/range.json", "/server.py"} or parsed.path.startswith("/."):
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
        if parsed.path == "/api/rf/raw":
            self.handle_rf_raw(parsed.query)
            return
        if parsed.path == "/api/rf/gnu-radio-capture":
            self.handle_gnu_radio_capture()
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
        self.write_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean_path = unquote(parsed.path).lstrip("/")
        target = (ROOT / clean_path).resolve()
        if target == VALIDATION_CONFIG_PATH.resolve():
            return str(ROOT / "__server_private__")
        if not str(target).startswith(str(ROOT)):
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
        profile = live_signal_profile(challenge_id, target=target, bins=bins)

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
            while frame < int(profile.get("frames", 720)):
                send_event("frame", generate_live_frame(profile, frame, session_id=session_id))
                frame += 1
                time.sleep(1 / rate)
            send_event("complete", {"ok": True, "message": "live profile ended; reconnect to replay"})
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def handle_rf_raw(self, query: str) -> None:
        params = parse_qs(query)
        challenge_id = params.get("challenge_id", ["tunnel-reading-signals"])[0]
        target = RF_TARGETS.get(challenge_id, RF_TARGETS["tunnel-reading-signals"])
        body = raw_iq_bytes(challenge_id, target=target, frame_count=96)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{challenge_id}-complex16.iq"')
        self.end_headers()
        self.wfile.write(body)

    def handle_gnu_radio_capture(self) -> None:
        try:
            self.write_json(gnu_radio_capture_preview())
        except FileNotFoundError as error:
            self.write_json({"error": str(error)}, HTTPStatus.NOT_FOUND)
        except (OSError, ValueError, struct.error) as error:
            self.write_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

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
        if task_id == "tunnel-reading-signals":
            expected = str(load_validation_config().get("flags", {}).get(task_id, "")).strip().upper()
        else:
            expected = flag_for(session_id, task_id).upper()
        if expected and submitted == expected:
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
                "flag": flag_for(session_id, "civilian-emergency-intercept"),
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
        response, status = build_rf_command_response(session_id, challenge_id, action, arguments, receiver)
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
            "A future bridge can publish FFT rows through ZeroMQ or a Python socket for the browser."
        ]
    }


def main() -> None:
    init_db()
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", "8000"))
    mimetypes.add_type("application/json", ".sigmf-meta")
    server = ThreadingHTTPServer(("localhost", port), CTFHandler)
    print(f"Signal Forge CTF serving http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
