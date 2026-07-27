# Live GNU Radio Signal Sources

Mapped GNU Radio challenges use the generated Python flowgraphs under
`radio/GNURadio/` as their only signal source.

Each runtime flowgraph:

1. Generates its payload and waveform continuously in GNU Radio.
2. Applies its channel model.
3. Sends post-channel-model CF32 samples through
   `radio/GNURadio/signal_forge_live_sink.py`.
4. Streams those samples to the server ingest endpoint at `127.0.0.1:9100`.

The flowgraphs must not read WAV, SigMF, IQ, or capture JSON files, and they must
not write File Sink or SigMF output. The server does not replay saved data and
does not synthesize a fallback for a missing mapped flowgraph.

Start the site with:

```powershell
python -m pip install -r requirements.txt
python server.py
```

GNU Radio itself must be installed through Radioconda/Conda or the operating
system package manager. Set `SIGNAL_FORGE_GNURADIO_PYTHON` if its Python runtime
is not discoverable. The site remains available without GNU Radio, but each
mapped challenge clearly reports that no live samples have arrived.

The old `generate_gnuradio_artifacts.py` utility and `captures/` directory are
retained only as reference material. They are not part of the runtime signal
path.
