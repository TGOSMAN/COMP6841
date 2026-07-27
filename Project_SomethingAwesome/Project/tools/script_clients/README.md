# Signal Forge Script Clients

These clients talk to the local Signal Forge CTF server through the networked
terminal API.

Start the site first:

```powershell
$env:PORT='8002'
python server.py
```

Then run a command from another terminal:

```powershell
python tools/script_clients/signal_terminal_client.py tunnel-tuning "tune 915.000"
python tools/script_clients/signal_terminal_client.py tunnel-tuning receive
```

The API is local and synthetic. It does not transmit RF.

## External signal feed

The waterfall can also consume frames pushed from your own script or a GNU Radio
bridge over TCP. Start the site, click **External feed** in the RF workbench,
then send either normalized FFT rows or raw `cf32_le` IQ blocks:

```powershell
python tools/script_clients/external_signal_sender.py --challenge-id tunnel-basic-dos --mode fft
python tools/script_clients/external_signal_sender.py --challenge-id tunnel-basic-dos --mode iq --block-samples 2048
```

Mapped beginner tasks use their generated GNU Radio Python files directly:

```powershell
python radio/GNURadio/Tunnel_Task/DoSAttackMe.py
```

GNU Radio ZMQ live bridge:

```powershell
python tools/script_clients/zmq_signal_bridge.py --challenge-id tunnel-packet-injection --endpoint tcp://127.0.0.1:5555 --pattern pull --dtype cf32
```

The default ingest endpoint is `127.0.0.1:9100`. See
`docs/external-signal-ingest.md` for the protocol.
