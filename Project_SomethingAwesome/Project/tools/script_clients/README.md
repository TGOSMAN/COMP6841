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

