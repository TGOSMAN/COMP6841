# GNU Radio Development Workflow

This project is sim-first: the CTF can be solved without SDR hardware. GNU Radio is used to generate reproducible RF artifacts and to demonstrate how the waterfall could be driven by real DSP later.

## Recommended Setup on Windows

Use WSL with Ubuntu for the development path:

```bash
sudo apt update
sudo apt install gnuradio python3-numpy python3-scipy
gnuradio-companion
```

Keep transmit-capable workflows out of the assessed build. Generate files locally rather than transmitting over the air.

## Source-of-Truth Contract

RF data should stem from the GNU Radio generation path, not from hand-edited
browser JSON. The editable source is:

- `radio/profiles/training_signals.json` for challenge signal parameters.
- `radio/generate_gnuradio_artifacts.py` for generation/export.

The browser still consumes `captures/*.json`, but those files are derived
artifacts. Regenerate them after profile changes:

```bash
python radio/generate_gnuradio_artifacts.py --profile all
python radio/generate_gnuradio_artifacts.py --profile council_weather_audio --write-iq
```

Use `--require-gnuradio` in WSL/Ubuntu when you want to ensure GNU Radio is
installed for a development run.

## Flowgraph Pattern

For each RF challenge, create a flowgraph with:

- Vector Source or Embedded Python Block for payload bits.
- Simple OOK/ASK or FSK modulation for teaching visibility.
- Noise Source and channel impairment blocks.
- QT GUI Frequency Sink for local validation.
- File Sink for IQ output.

Export generated samples as SigMF:

- `captures/<name>.sigmf-data` for interleaved IQ samples.
- `captures/<name>.sigmf-meta` for JSON metadata.

The browser can consume:

- generated waterfall/capture JSON from `captures/*.json`, or
- a local GNU Radio `cf32_le` File Sink capture through the backend importer.

## Local GNU Radio Capture Import

The Reading Signals task is configured to read this File Sink output directly:

```text
radio/GNURadio/ReadingSignals.sigmf-data
```

Connect the final complex output of the GNU Radio flowgraph to a normal **File
Sink** using that filename. GNU Radio's **File Meta Sink** is not required; its
binary metadata format is intentionally ignored. Signal Forge reads the capture
settings from `config/range.json`, computes FFT rows on the backend, and loads
them through `GET /api/rf/gnu-radio-capture`.

The default capture settings are 44,200 samples/second, complex float little
endian (`cf32_le`), and a notional centre frequency of 915 MHz. Change the
`gnu_radio_capture` section of `config/range.json` when the flowgraph settings
change, then reload the challenge page.

The importer never receives the Vector Source text. It measures the carrier
from the recorded spectrum and recovers an OOK binary stream from IQ amplitude.
The UI deliberately stops at bit slicing; turning those bits into bytes and
recovering the flag remains part of the learner task. `samples_per_symbol`
describes the current Repeat/interleaving result (500 complex samples per bit),
so update it if the GNU Radio symbol timing changes.

Receiver centre/span, demodulation, gain, and squelch are applied to the same
IQ frame used by both the tuned time-series and the audio monitor.

Flag verification is deliberately separate from signal processing. Set the
`flags.tunnel-reading-signals` value in the server-only
`config/validation.json` file to the answer the task should accept. Requests for
that file are blocked by the backend. The receiver API never returns this
value; it exposes only the recovered binary stream for the learner to interpret.

## Optional Live Bridge

Later, add a GNU Radio ZeroMQ sink or file/socket sink that emits FFT rows. A small Python bridge can normalize those rows and publish:

```json
{
  "center_hz": 2437000000,
  "span_hz": 2000000,
  "timestamp": 1783857600.25,
  "bins": [0.05, 0.08, 0.15, 0.91]
}
```

The front end already has a waterfall renderer and can be extended to read these frames with WebSocket or Server-Sent Events.
