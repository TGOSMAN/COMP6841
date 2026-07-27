# Developer Extension Plan

This project is designed to give you room to push the CTF toward serious contested-spectrum training without making the default path unsafe or fragile.

## Where to Extend

- `config/range.json` controls RF, packet, and security settings.
- `data/challenges.json` controls public task intelligence and artifacts; `server.py` owns per-session flag derivation and target success conditions.
- `radio/profiles/training_signals.json` is the editable source of truth for RF artifact parameters.
- `radio/generate_gnuradio_artifacts.py` exports profile-derived capture JSON and optional SigMF IQ files.
- `captures/` stores generated RF-style artifacts consumed by the browser.
- `artifacts/` stores cyber challenge inputs.
- `tools/` stores source-backed local RE and parser challenges.

## Security Hardening Ideas

Current defensive examples use HMAC-SHA256, timestamp freshness, nonce replay rejection, parameterized SQL, server-side authorization, and safe output rendering.

Next useful upgrades:

- RF/protocol RE: add whitening, interleaving, forward-error correction, burst timing recovery, hop-set inference, and demodulator confidence scoring.
- Firmware RE: add a synthetic firmware image, memory map, command table, debug shell, key-slot metadata, signed image manifest, and attestation evidence.
- Binary exploitation: add stack overflow, format string, TLV length mismatch, integer overflow, parser state confusion, fuzzing corpus, and safe patched variants.
- Hardware trust: add secure boot, measured boot, signed firmware, protected keys, debug-lock state, and remote attestation before backend trust.
- RF resilience: add path-loss models, multipath, oscillator drift, Doppler, receiver saturation, adjacent-channel interference, and jamming/interference classes.
- Crypto/auth: replace HMAC with Ed25519 or ECDSA signatures, rotate pseudonymous IDs, and bind messages to nonce, timestamp, route, and device identity.
- Detection: add an audit/fraud scoring endpoint that fuses RF features, protocol state, backend logs, and operator activity.
- Browser/backend: add Content Security Policy reporting, output encoding tests, least-privilege DB access, and anomaly challenges where cryptography passes but behaviour is suspicious.

## C/C++ Extension Path

Good places for C or C++:

- packet encoder,
- telemetry decoder,
- local parser challenge,
- TLV parser challenge,
- firmware command-table stub,
- replay detector,
- GNU Radio custom block skeleton.

Keep C/C++ tools local-only. Include safe and unsafe variants when teaching exploitation so the defensive comparison is obvious.

## GNU Radio Extension Path

Use GNU Radio to generate or replay artifacts, not to transmit over the air by default.

Suggested flow:

1. Edit a profile in `radio/profiles/training_signals.json`.
2. Generate a synthetic OOK/ASK, FSK, AM, CSS-like, replay, or TLV burst.
3. Add controlled noise, hopping, drift, replay, or jamming effects.
4. Export SigMF data and metadata when IQ artifacts are needed.
5. Export a capture JSON preview for the browser workbench.

## Beyond Scope

Do not reproduce operational military waveforms, real tactical message formats, real restricted frequencies, or live interference procedures. Historical and contested-spectrum themes should remain synthetic, local, and educational.
