from __future__ import annotations

import hashlib
import math
import struct
from typing import Any


DEFAULT_BINS = 384
DEFAULT_FRAMES = 720


PROFILE_FAMILIES = {
    "tunnel": {
        "scheme_id": "SFC-TUNNEL-OOK-SIGN-LIVE",
        "family": "ook",
        "modulation": "OOK / NRZ",
        "description": "Fixed-carrier OOK tunnel sign packets. This is intentionally not hopping.",
        "bitstream": "101101001110010111000100101011110011",
        "fields": {
            "preamble": "0xB4E5",
            "message": "SIGN:LANE_OPEN",
            "checksum": "xor8=0x5A",
        },
        "annotations": [
            {"label": "OOK carrier", "offset_hz": 0, "color": "#73f2a6"},
            {"label": "symbol sideband", "offset_hz": 28_000, "color": "#ffc766"},
        ],
    },
    "broadcast": {
        "scheme_id": "SFC-BROADCAST-MANCHESTER-ASK-LIVE",
        "family": "manchester_ask",
        "modulation": "ASK / Manchester",
        "description": "Low-rate broadcast metadata side-channel with clock-rich Manchester transitions.",
        "bitstream": "11001010010111010011101000101101",
        "fields": {
            "sync": "0xA53C",
            "service": "NOW_PLAYING",
            "text": "FIELD-NET-METADATA",
        },
        "annotations": [
            {"label": "metadata carrier", "offset_hz": -42_000, "color": "#59d7e8"},
            {"label": "clock component", "offset_hz": 42_000, "color": "#ffc766"},
        ],
    },
    "clear_hop": {
        "scheme_id": "SFC-WEATHER-CLEAR-HOP-LIVE",
        "family": "clear_hop",
        "modulation": "AM voice bursts over clear hopping schedule",
        "description": "Predictable voice burst allocation. Hop transitions are smoothed to avoid impossible discontinuities.",
        "bitstream": "01110100101100100110111001011001",
        "fields": {
            "hop_plan": "[-90,-30,+60,+120] kHz",
            "voice_call": "COUNCIL-AUX",
            "auth": "spoken",
        },
        "annotations": [
            {"label": "hop slot A", "offset_hz": -90_000, "color": "#73f2a6"},
            {"label": "hop slot B", "offset_hz": -30_000, "color": "#59d7e8"},
            {"label": "hop slot C", "offset_hz": 60_000, "color": "#ffc766"},
            {"label": "hop slot D", "offset_hz": 120_000, "color": "#ff8a5b"},
        ],
    },
    "weak_prng": {
        "scheme_id": "SFC-WEAK-PRNG-HOP-LIVE",
        "family": "weak_prng",
        "modulation": "Weak PRNG hopped AM/QAM bursts",
        "description": "Hopping channel selected by a small LCG state. Learners can recover state from observed slots.",
        "bitstream": "10011100101101000110101110010010",
        "fields": {
            "generator": "x=(5x+1) mod 16",
            "state_hint": "small LCG",
            "slot_set": "7 offsets",
        },
        "annotations": [
            {"label": "PRNG slot -3", "offset_hz": -126_000, "color": "#73f2a6"},
            {"label": "PRNG slot 0", "offset_hz": 0, "color": "#59d7e8"},
            {"label": "PRNG slot +3", "offset_hz": 126_000, "color": "#ffc766"},
        ],
    },
    "emergency_meta": {
        "scheme_id": "SFC-EMERGENCY-AUDIO-METADATA-LIVE",
        "family": "emergency_meta",
        "modulation": "AM voice plus digital metadata subcarrier",
        "description": "Voice traffic carries a side metadata channel that drives a warning light policy.",
        "bitstream": "11100010100101101110000100110110",
        "fields": {
            "voice": "public warning net",
            "metadata": "ZONE|ACTION|AUTH",
            "integrity": "crc16-lite",
        },
        "annotations": [
            {"label": "voice carrier", "offset_hz": 0, "color": "#59d7e8"},
            {"label": "metadata subcarrier", "offset_hz": 38_000, "color": "#ff4ad2"},
        ],
    },
    "bushfire": {
        "scheme_id": "SFC-BUSHFIRE-PRNG-LEVEL-C2-LIVE",
        "family": "bushfire",
        "modulation": "GFSK command burst with PRNG-level whitening",
        "description": "Advanced bushfire relay traffic with propagation fade, whitening, anomaly scoring, and parser state.",
        "bitstream": "10101111000111001000101101111010",
        "fields": {
            "node": "BRAVO-17",
            "whitener": "xorshift-lite",
            "anomaly_score": "live",
        },
        "annotations": [
            {"label": "command burst", "offset_hz": -115_000, "color": "#73f2a6"},
            {"label": "relay echo", "offset_hz": 84_000, "color": "#ffc766"},
            {"label": "sweep jammer", "offset_hz": 0, "color": "#ff5c7c"},
        ],
    },
    "farm": {
        "scheme_id": "SFC-FARM-GATE-4FSK-TLV-LIVE",
        "family": "farm",
        "modulation": "4-FSK TLV maintenance frames",
        "description": "Long-range gate maintenance traffic with TLV parsing and unsafe native-parser comparison.",
        "bitstream": "00110110100111100010110101100011",
        "fields": {
            "tlv_type": "0x42",
            "length": "declared vs actual",
            "admin_path": "diagnostic",
        },
        "annotations": [
            {"label": "4-FSK -3", "offset_hz": -36_000, "color": "#73f2a6"},
            {"label": "4-FSK -1", "offset_hz": -12_000, "color": "#59d7e8"},
            {"label": "4-FSK +1", "offset_hz": 12_000, "color": "#ffc766"},
            {"label": "4-FSK +3", "offset_hz": 36_000, "color": "#ff8a5b"},
        ],
    },
}


def live_signal_profile(challenge_id: str, target: dict[str, Any] | None = None, bins: int = DEFAULT_BINS) -> dict[str, Any]:
    family_key = _family_for_challenge(challenge_id)
    family = PROFILE_FAMILIES[family_key]
    center_hz = float((target or {}).get("center_mhz", 915.0)) * 1_000_000
    span_hz = float((target or {}).get("span_khz", 800.0)) * 1_000
    seed = _stable_seed(challenge_id, family["scheme_id"])
    task_suffix = challenge_id.upper().replace("-", "_")
    return {
        "challenge_id": challenge_id,
        "scheme_id": f"{family['scheme_id']}-{task_suffix}",
        "family": family["family"],
        "description": family["description"],
        "center_hz": center_hz,
        "span_hz": span_hz,
        "bins": int(max(96, min(1024, bins))),
        "frames": DEFAULT_FRAMES,
        "seed": seed,
        "sources": _sources_for_family(family_key),
        "annotations": family["annotations"],
        "protocol_notes": {
            "modulation": family["modulation"],
            "source": "Python live parser. Replace the sample source with GNU Radio complex64 over file, socket, or ZeroMQ.",
            "raw_path": f"/api/rf/raw?challenge_id={challenge_id}",
        },
        "parser_fields": family["fields"],
    }


def generate_live_frame(profile: dict[str, Any], frame: int, session_id: str = "anonymous") -> dict[str, Any]:
    family = str(profile["family"])
    bins = int(profile["bins"])
    span_hz = float(profile["span_hz"])
    seed = int(profile["seed"])
    row: list[float] = []
    for bin_index in range(bins):
        offset_hz = -span_hz / 2 + bin_index / max(1, bins - 1) * span_hz
        power = _background_power(bin_index, frame, seed)
        power = max(power, _family_power(family, offset_hz, frame, seed))
        row.append(round(min(1.0, power), 4))
    return {
        "frame": frame,
        "row": row,
        "samples": _time_samples(family, frame, seed),
        "parser": _parser_event(profile, frame, session_id),
    }


def raw_iq_bytes(challenge_id: str, target: dict[str, Any] | None = None, frame_count: int = 64) -> bytes:
    profile = live_signal_profile(challenge_id, target=target, bins=128)
    output = bytearray()
    for frame in range(max(1, min(256, frame_count))):
        samples = _time_samples(str(profile["family"]), frame, int(profile["seed"]), count=48)
        for index, sample in enumerate(samples):
            phase = math.sin(index * 0.31 + frame * 0.07)
            i_value = int(max(-1.0, min(1.0, sample)) * 30_000)
            q_value = int(max(-1.0, min(1.0, sample * phase)) * 30_000)
            output += struct.pack("<hh", i_value, q_value)
    return bytes(output)


def _family_for_challenge(challenge_id: str) -> str:
    if challenge_id.startswith("tunnel-"):
        return "tunnel"
    if challenge_id.startswith("broadcast-"):
        return "broadcast"
    if challenge_id in {"weather-boring-obscured", "civilian-emergency-obscured"}:
        return "weak_prng"
    if challenge_id == "weather-boring-intercept":
        return "clear_hop"
    if challenge_id.startswith("weather-boring-") or challenge_id.startswith("civilian-emergency-"):
        return "emergency_meta"
    if challenge_id.startswith("bushfire-"):
        return "bushfire"
    if challenge_id.startswith("farm-gate-"):
        return "farm"
    return "tunnel"


def _sources_for_family(family_key: str) -> list[dict[str, Any]]:
    if family_key == "tunnel":
        return [{"label": "Live OOK sign carrier", "kind": "ook", "offset_hz": 0, "bandwidth_hz": 22_000}]
    if family_key == "broadcast":
        return [{"label": "Manchester metadata", "kind": "manchester_ask", "offset_hz": -42_000, "bandwidth_hz": 34_000}]
    if family_key == "clear_hop":
        return [{"label": "Clear hop voice burst", "kind": "clear_hop", "hop_offsets_hz": [-90_000, -30_000, 60_000, 120_000], "bandwidth_hz": 26_000}]
    if family_key == "weak_prng":
        return [{"label": "Weak PRNG hopped voice", "kind": "weak_prng", "bandwidth_hz": 24_000}]
    if family_key == "emergency_meta":
        return [{"label": "Voice carrier", "kind": "am_voice", "offset_hz": 0, "bandwidth_hz": 18_000}, {"label": "Metadata side-channel", "kind": "metadata", "offset_hz": 38_000, "bandwidth_hz": 10_000}]
    if family_key == "bushfire":
        return [{"label": "Bushfire command burst", "kind": "gfsk", "offset_hz": -115_000, "bandwidth_hz": 28_000}, {"label": "Relay echo", "kind": "echo", "offset_hz": 84_000, "bandwidth_hz": 20_000}]
    return [{"label": "4-FSK TLV symbols", "kind": "4fsk", "offset_hz": 0, "bandwidth_hz": 80_000}]


def _family_power(family: str, offset_hz: float, frame: int, seed: int) -> float:
    if family == "ook":
        gate = _raised_gate((frame + 3) % 42, 30, 6)
        symbol = _symbol_bit("101101001110010111000100101011110011", frame // 3)
        return _gaussian(offset_hz, 0, 15_000) * (0.18 + 0.78 * gate * symbol)
    if family == "manchester_ask":
        gate = _raised_gate((frame + 8) % 36, 28, 5)
        bit = _symbol_bit("11001010010111010011101000101101", frame // 2)
        clock = 0.45 + 0.35 * math.sin(frame * math.pi)
        return max(
            _gaussian(offset_hz, -42_000, 18_000) * (0.25 + 0.64 * gate * bit),
            _gaussian(offset_hz, 42_000, 8_000) * gate * (0.28 + abs(clock)),
        )
    if family == "clear_hop":
        offset = _smoothed_offset([-90_000, -30_000, 60_000, 120_000], frame, 34)
        gate = _raised_gate(frame % 34, 27, 5)
        return _gaussian(offset_hz, offset, 18_000) * (0.82 * gate + 0.08)
    if family == "weak_prng":
        offsets = [-126_000, -84_000, -42_000, 0, 42_000, 84_000, 126_000]
        slot = _lcg_slot(frame // 30, seed, len(offsets))
        next_slot = _lcg_slot(frame // 30 + 1, seed, len(offsets))
        offset = _blend_hop(offsets[slot], offsets[next_slot], frame % 30, 30)
        gate = _raised_gate(frame % 30, 24, 5)
        return _gaussian(offset_hz, offset, 16_000) * (0.76 * gate + 0.1)
    if family == "emergency_meta":
        voice = _gaussian(offset_hz, 0, 22_000) * (0.45 + 0.12 * math.sin(frame * 0.17))
        meta_gate = _raised_gate((frame + 5) % 28, 16, 4)
        metadata = _gaussian(offset_hz, 38_000, 7_000) * (0.72 * meta_gate)
        return max(voice, metadata)
    if family == "bushfire":
        fade = 0.76 + 0.18 * math.sin(frame * 0.071) + 0.08 * math.sin(frame * 0.019 + 1.7)
        command = _gaussian(offset_hz, -115_000 + math.sin(frame * 0.19) * 9_000, 18_000) * fade
        echo = _gaussian(offset_hz, 84_000 + math.sin(frame * 0.11) * 5_000, 13_000) * 0.42
        jammer_offset = -180_000 + (frame % 150) / 149 * 360_000
        jammer = _gaussian(offset_hz, jammer_offset, 24_000) * 0.36
        return max(command, echo, jammer)
    if family == "farm":
        symbols = [-36_000, -12_000, 12_000, 36_000]
        symbol_index = (frame // 5 + seed) % len(symbols)
        gate = _raised_gate(frame % 24, 20, 4)
        return _gaussian(offset_hz, symbols[symbol_index], 8_000) * (0.78 * gate)
    return 0.0


def _parser_event(profile: dict[str, Any], frame: int, session_id: str) -> dict[str, Any]:
    stages = [
        ("raw_iq", "reading complex samples"),
        ("fft", "estimating power bins"),
        ("energy_detect", "finding candidate channel"),
        ("symbol_clock", "recovering symbol timing"),
        ("bit_slice", "slicing bits"),
        ("frame_sync", "checking preamble"),
        ("field_decode", "parsing fields"),
        ("policy_check", "checking operational effect"),
    ]
    stage, label = stages[(frame // 12) % len(stages)]
    bitstream = PROFILE_FAMILIES[_family_for_challenge(str(profile["challenge_id"]))]["bitstream"]
    cursor = (frame // 2) % len(bitstream)
    bit_window = (bitstream + bitstream)[cursor:cursor + 24]
    family = str(profile["family"])
    fields = dict(profile.get("parser_fields", {}))
    if family == "weak_prng":
        fields["observed_slot"] = str(_lcg_slot(frame // 30, int(profile["seed"]), 7))
    if family == "bushfire":
        fields["anomaly_score"] = f"{0.22 + 0.34 * abs(math.sin(frame * 0.041)):.2f}"
    if family == "farm":
        fields["symbol"] = str((frame // 5) % 4)
    return {
        "stage": stage,
        "label": label,
        "bit_buffer": bit_window,
        "fields": fields,
        "confidence": round(0.52 + 0.45 * abs(math.sin(frame * 0.037 + len(session_id))), 3),
        "note": _parser_note(family, stage),
    }


def _parser_note(family: str, stage: str) -> str:
    if stage == "field_decode":
        if family == "ook":
            return "Plain sign text is visible after symbol slicing."
        if family == "weak_prng":
            return "Hop slots are generated by a small predictable state."
        if family == "bushfire":
            return "Whitening and anomaly checks now influence acceptance."
        if family == "farm":
            return "TLV length and command fields are entering the parser."
    if stage == "policy_check":
        return "The RF decode is now treated as untrusted input to a local cyber target."
    return "Live parser state is updating from raw sample slices."


def _time_samples(family: str, frame: int, seed: int, count: int = 160) -> list[float]:
    values: list[float] = []
    bitstream = PROFILE_FAMILIES[_family_for_runtime(family)]["bitstream"]
    for index in range(count):
        bit = _symbol_bit(bitstream, frame // 2 + index // 12)
        carrier = math.sin(index * 0.42 + frame * 0.09)
        if family == "ook":
            value = carrier * (0.12 + 0.8 * bit * _raised_gate((frame + 3) % 42, 30, 6))
        elif family in {"clear_hop", "weak_prng", "emergency_meta"}:
            value = math.sin(index * 0.17 + frame * 0.13) * 0.35 + math.sin(index * 0.63) * 0.12
        elif family == "farm":
            symbol = [-0.8, -0.28, 0.28, 0.8][(frame // 5 + index // 32) % 4]
            value = math.sin(index * (0.27 + symbol * 0.05) + frame * 0.1) * 0.65
        elif family == "bushfire":
            value = (math.sin(index * 0.31 + frame * 0.19) + math.sin(index * 0.057 + seed)) * 0.28
        else:
            value = carrier * (0.25 + 0.45 * bit)
        values.append(round(max(-1.0, min(1.0, value)), 4))
    return values


def _family_for_runtime(family: str) -> str:
    for key, profile in PROFILE_FAMILIES.items():
        if profile["family"] == family:
            return key
    return "tunnel"


def _raised_gate(phase: int, duration: int, ramp: int) -> float:
    if phase >= duration:
        return 0.0
    if ramp <= 0:
        return 1.0
    if phase < ramp:
        return 0.5 - 0.5 * math.cos(math.pi * phase / ramp)
    if duration - phase < ramp:
        return 0.5 - 0.5 * math.cos(math.pi * (duration - phase) / ramp)
    return 1.0


def _blend_hop(current: float, next_value: float, phase: int, period: int) -> float:
    transition = 5
    if phase < period - transition:
        return current
    amount = (phase - (period - transition)) / transition
    smooth = amount * amount * (3 - 2 * amount)
    return current + (next_value - current) * smooth


def _smoothed_offset(offsets: list[int], frame: int, period: int) -> float:
    index = frame // period % len(offsets)
    next_index = (index + 1) % len(offsets)
    return _blend_hop(offsets[index], offsets[next_index], frame % period, period)


def _lcg_slot(step: int, seed: int, modulus: int) -> int:
    state = (seed % 16) or 7
    for _ in range(step + 1):
        state = (5 * state + 1) % 16
    return state % modulus


def _symbol_bit(bitstream: str, index: int) -> int:
    return 1 if bitstream[index % len(bitstream)] == "1" else 0


def _gaussian(x: float, mean: float, width: float) -> float:
    return math.exp(-((x - mean) / max(1.0, width)) ** 2)


def _background_power(bin_index: int, frame: int, seed: int) -> float:
    slow = 0.045 + 0.015 * math.sin(bin_index * 0.021 + frame * 0.031 + seed)
    ripple = 0.018 * math.sin(bin_index * 0.13 + frame * 0.017)
    fine = 0.012 * _noise(bin_index // 3, frame // 3, seed)
    return max(0.01, slow + ripple + fine)


def _noise(x: int, y: int, seed: int) -> float:
    value = math.sin(x * 12.9898 + y * 78.233 + seed * 37.719) * 43_758.5453
    return value - math.floor(value)


def _stable_seed(*parts: str) -> int:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)
