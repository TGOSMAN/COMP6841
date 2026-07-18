# Signal Artifact Generation

Signal capture JSON in `captures/` is a generated browser preview, not the
source of truth. Edit `radio/profiles/training_signals.json`, then regenerate.

```bash
python radio/generate_gnuradio_artifacts.py --profile all
python radio/generate_gnuradio_artifacts.py --profile council_weather_audio --write-iq
```

On WSL/Ubuntu, install GNU Radio and use `--require-gnuradio` when you want the
script to fail if the GNU Radio runtime is unavailable.

```bash
sudo apt update
sudo apt install gnuradio python3-numpy python3-scipy
python radio/generate_gnuradio_artifacts.py --require-gnuradio --profile all --write-iq
```

The generated files are:

- `captures/*.json`: compact artifact metadata for the browser waterfall.
- `captures/*.sigmf-meta`: SigMF metadata when `--write-iq` is used.
- `captures/*.sigmf-data`: deterministic complex float IQ preview when
  `--write-iq` is used.

For a deeper GNU Radio implementation, keep the profile schema stable and map
each profile to a GNU Radio Companion top block:

1. Read `center_hz`, `sample_rate_hz`, `sources`, and payload metadata.
2. Generate the waveform with GNU Radio blocks or custom C++/Python blocks.
3. Write SigMF IQ data.
4. Run the same profile through this exporter to produce the web preview JSON.
