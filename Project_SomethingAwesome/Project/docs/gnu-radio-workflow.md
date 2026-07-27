# GNU Radio Development Workflow

This project is sim-first and requires no SDR hardware. Mapped RF challenges use
GNU Radio as a live DSP runtime and stream directly into the browser analyser.

## Recommended Setup on Windows

Use WSL with Ubuntu for the development path:

```bash
sudo apt update
sudo apt install gnuradio python3-numpy python3-scipy
gnuradio-companion
```

Keep transmit-capable workflows out of the assessed build. Generate and stream
complex baseband samples in-process rather than transmitting over the air.

## Source-of-Truth Contract

RF data for a mapped challenge must originate in its committed GNU Radio
generated Python file. The `.grc` and generated `.py` files are the editable and
runtime sources. Do not use WAV, SigMF, IQ, capture JSON, File Source, File Sink,
or SigMF sink blocks in the runtime graph.

## Flowgraph Pattern

For each RF challenge, create a flowgraph with:

- Vector Source, Signal Source, or Embedded Python Block for live payload data.
- Simple OOK/ASK or FSK modulation for teaching visibility.
- Noise Source and channel impairment blocks.
- QT GUI Frequency Sink for local validation.
- `SignalForgeLiveSink` connected after the channel model for live CF32 output.

## Live GNU Radio Stream

The mapped generated Python files instantiate
`radio/GNURadio/signal_forge_live_sink.py`. Start the site normally:

```powershell
python server.py
```

Opening a mapped challenge makes the server discover a GNU Radio-capable
Python runtime and launch the exact mapped generated Python file. The sink sends
post-channel-model complex64 blocks to
`127.0.0.1:9100`, and the normal **Live parser** view reads only those arriving
blocks. Set `SIGNAL_FORGE_GNURADIO_PYTHON` when GNU Radio is installed in a
non-standard environment. There is no recording or synthetic fallback. When a
flowgraph cannot start or does not send samples, the browser displays an
explicit no-live-data warning.

Receiver centre/span, demodulation, gain, and squelch are applied to the same
IQ frame used by both the tuned time-series and the audio monitor.

Flag verification is deliberately separate from signal processing. Set the
`flags.tunnel-reading-signals` value in the server-only
`config/validation.json` file to the answer the task should accept. Requests for
that file are blocked by the backend. The receiver API never returns this
value; it exposes only the recovered binary stream for the learner to interpret.

## Live Ingest Protocol

The live endpoint accepts raw GNU Radio `cf32_le` samples. The built-in sink
uses this protocol automatically. The default endpoint is:

```text
127.0.0.1:9100
```

For another direct GNU Radio integration, send this header once:

```text
SFORGE RAWIQ challenge_id=tunnel-basic-dos center_hz=915000000 sample_rate_hz=44200 span_hz=44200 bins=384 scheme_id=MY-GR-FLOWGRAPH block_samples=2048
```

Then write repeated `block_samples * 8` byte blocks of interleaved little-endian
float32 IQ. See `docs/external-signal-ingest.md` for the JSON-lines FFT variant
and the one-shot IQ frame format.

## GNU Radio ZMQ Bridge

For a more natural GNU Radio workflow, use a ZMQ sink in the flowgraph and let
`tools/script_clients/zmq_signal_bridge.py` forward the stream to Signal Forge.

Recommended GRC setup:

- Add a **ZMQ PUSH Sink** after the final complex baseband signal.
- Set the item type to complex.
- Set the address to `tcp://127.0.0.1:5555`.
- Set the GNU Radio block to bind.
- Disable tag passing for the training bridge.

Then run:

```powershell
python tools/script_clients/zmq_signal_bridge.py --challenge-id tunnel-packet-injection --endpoint tcp://127.0.0.1:5555 --pattern pull --dtype cf32 --center-hz 915000000 --sample-rate-hz 44200 --span-hz 44200
```

Use `--pattern sub` for a GNU Radio ZMQ PUB Sink when multiple receivers should
observe the same signal. Use `--dtype f32fft --bins 384` only when the flowgraph
already emits normalized or magnitude FFT rows.
