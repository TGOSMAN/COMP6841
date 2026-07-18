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
- live FFT rows from a future Python bridge.

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
