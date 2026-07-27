#!/usr/bin/env python3
"""Generate Signal Forge RF artifacts from editable GNU Radio profiles.

The browser consumes compact waterfall JSON, but that JSON is a generated
artifact. Edit radio/profiles/training_signals.json, then run this script.

On WSL/Ubuntu with GNU Radio installed this file is the place to wire each
profile to a real GNU Radio Companion generated top_block. The deterministic
Python emitter remains available so the web project can be built and tested on
machines that do not have GNU Radio installed.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import struct
from pathlib import Path
from typing import Any

try:
    from gnuradio import gr  # type: ignore

    GNU_RADIO_AVAILABLE = True
except Exception:
    gr = None
    GNU_RADIO_AVAILABLE = False


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES = ROOT / "radio" / "profiles" / "training_signals.json"
GENERATOR_ID = "radio/generate_gnuradio_artifacts.py"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CTF RF artifacts from GNU Radio profiles.")
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--profile", default="all", help="profile_id to generate, or all")
    parser.add_argument("--write-iq", action="store_true", help="also emit small SigMF IQ sample files")
    parser.add_argument("--require-gnuradio", action="store_true", help="fail if GNU Radio is not importable")
    args = parser.parse_args()

    if args.require_gnuradio and not GNU_RADIO_AVAILABLE:
        raise SystemExit("GNU Radio is not importable. Run inside WSL/Ubuntu with gnuradio installed.")

    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    selected = [profile for profile in profiles if args.profile == "all" or profile["profile_id"] == args.profile]
    if not selected:
        raise SystemExit(f"No profile matched {args.profile!r}")

    for profile in selected:
        capture_path = ROOT / profile["output_json"]
        capture_path.parent.mkdir(parents=True, exist_ok=True)
        capture = web_capture_from_profile(profile)
        capture_path.write_text(json.dumps(capture, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {capture_path.relative_to(ROOT)}")

        if args.write_iq:
            write_sigmf_pair(profile)


def web_capture_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    passthrough_keys = [
        "scheme_id",
        "center_hz",
        "span_hz",
        "bins",
        "frames",
        "seed",
        "description",
        "protocol_notes",
        "access_point",
        "annotations",
        "sources",
    ]
    capture = {key: profile[key] for key in passthrough_keys if key in profile}
    capture["generated_by"] = GENERATOR_ID
    capture["source_profile"] = f"radio/profiles/training_signals.json#{profile['profile_id']}"
    capture["generator_mode"] = "gnu-radio-ready" if GNU_RADIO_AVAILABLE else "deterministic-python-fallback"
    capture["sample_rate_hz"] = int(profile.get("sample_rate_hz", profile.get("span_hz", 1)))
    capture["artifact_role"] = "browser waterfall preview generated from RF profile"
    return capture


def write_sigmf_pair(profile: dict[str, Any]) -> None:
    stem = ROOT / profile["output_sigmf_stem"]
    stem.parent.mkdir(parents=True, exist_ok=True)
    data_path = stem.with_suffix(".sigmf-data")
    meta_path = stem.with_suffix(".sigmf-meta")

    sample_rate = int(profile.get("sample_rate_hz", profile["span_hz"]))
    samples = synthesize_complex_samples(profile, sample_rate=sample_rate, seconds=0.04)
    with data_path.open("wb") as handle:
        for real, imag in samples:
          handle.write(struct.pack("<ff", real, imag))

    meta = {
        "global": {
            "core:datatype": "cf32_le",
            "core:sample_rate": sample_rate,
            "core:description": profile["description"],
            "core:version": "1.0.0",
            "core:author": "Signal Forge CTF GNU Radio profile generator"
        },
        "captures": [
            {
                "core:sample_start": 0,
                "core:frequency": profile["center_hz"]
            }
        ],
        "annotations": sigmf_annotations(profile),
        "signal_forge": {
            "generated_by": GENERATOR_ID,
            "source_profile": f"radio/profiles/training_signals.json#{profile['profile_id']}",
            "generator_mode": "gnu-radio-ready" if GNU_RADIO_AVAILABLE else "deterministic-python-fallback"
        }
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {data_path.relative_to(ROOT)}")
    print(f"wrote {meta_path.relative_to(ROOT)}")


def synthesize_complex_samples(profile: dict[str, Any], sample_rate: int, seconds: float) -> list[tuple[float, float]]:
    sample_count = max(2048, min(65536, int(sample_rate * seconds)))
    rng = random.Random(int(profile.get("seed", 6841)))
    phases = {source["label"]: rng.random() * math.tau for source in profile.get("sources", [])}
    samples: list[tuple[float, float]] = []
    frames = int(profile.get("frames", 120))

    for index in range(sample_count):
        t = index / sample_rate
        frame = int(index / max(1, sample_count - 1) * frames)
        real = (rng.random() - 0.5) * 0.025
        imag = (rng.random() - 0.5) * 0.025
        for source in profile.get("sources", []):
            amp = source_amplitude(source, frame)
            if amp <= 0:
                continue
            offset = source_offset_hz(source, frame)
            phase = phases[source["label"]] + math.tau * offset * t
            real += amp * math.cos(phase)
            imag += amp * math.sin(phase)
        scale = max(1.0, abs(real), abs(imag))
        samples.append((real / scale * 0.85, imag / scale * 0.85))
    return samples


def source_amplitude(source: dict[str, Any], frame: int) -> float:
    if source.get("kind") == "noise_band":
        return float(source.get("power", 0.3)) * 0.25
    period = max(1, int(source.get("period_frames", source.get("sweep_period_frames", 40))))
    duration = int(source.get("duration_frames", period))
    phase = int(source.get("phase_frames", 0))
    position = (frame + phase) % period
    if source.get("kind") == "sweep":
        return float(source.get("power", 0.7)) * 0.35
    if position >= duration:
        return 0.0
    edge = max(1.0, duration * 0.22)
    if position < edge:
        envelope = 0.5 - 0.5 * math.cos(math.pi * position / edge)
    elif position > duration - edge:
        envelope = 0.5 - 0.5 * math.cos(math.pi * (duration - position) / edge)
    else:
        envelope = 1.0
    return float(source.get("power", 0.8)) * envelope * 0.45


def source_offset_hz(source: dict[str, Any], frame: int) -> float:
    if source.get("kind") == "sweep":
        period = max(1, int(source.get("sweep_period_frames", 60)))
        start = float(source.get("sweep_start_hz", -100000))
        stop = float(source.get("sweep_stop_hz", 100000))
        return start + ((frame % period) / period) * (stop - start)
    hop_set = source.get("hop_offsets_hz")
    if hop_set:
        period = max(1, int(source.get("period_frames", 40)))
        cycle = frame // period
        return float(hop_set[cycle % len(hop_set)])
    return float(source.get("offset_hz", 0)) + float(source.get("drift_hz_per_frame", 0)) * frame


def sigmf_annotations(profile: dict[str, Any]) -> list[dict[str, Any]]:
    sample_rate = int(profile.get("sample_rate_hz", profile["span_hz"]))
    annotations = []
    for index, source in enumerate(profile.get("sources", [])):
        annotations.append(
            {
                "core:sample_start": 0,
                "core:sample_count": sample_rate // 50,
                "core:freq_lower_edge": profile["center_hz"] + int(source.get("offset_hz", 0)) - int(source.get("bandwidth_hz", 10000)) // 2,
                "core:freq_upper_edge": profile["center_hz"] + int(source.get("offset_hz", 0)) + int(source.get("bandwidth_hz", 10000)) // 2,
                "core:label": source.get("label", f"source-{index + 1}")
            }
        )
    return annotations


if __name__ == "__main__":
    main()
