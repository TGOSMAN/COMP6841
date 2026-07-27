# External Signal Ingest

Signal Forge can show live signals supplied by your own program. Start the CTF
server, open a challenge, click **External feed** in the RF workbench, then send
frames to the ingest socket.

Default endpoint:

```text
127.0.0.1:9100
```

The server binds to localhost by default. To accept feeds from another machine
on a lab network, start the site with explicit values:

```powershell
$env:SIGNAL_INGEST_HOST='0.0.0.0'
$env:SIGNAL_INGEST_PORT='9100'
$env:PORT='8002'
python server.py
```

Keep this on a trusted training network. The ingest protocol is for local CTF
instrumentation, not an internet-facing service.

## Browser View

The browser consumes the feed through Server-Sent Events:

```text
GET /api/rf/external/live?challenge_id=tunnel-basic-dos
GET /api/rf/external/status?challenge_id=tunnel-basic-dos
```

The challenge page does not need to know whether a frame came from GNU Radio,
C/C++, Python, or another DSP tool. Every accepted frame becomes one waterfall
row plus optional time-domain samples and parser state.

## Protocol 1: JSON-Lines FFT

Send one JSON object per line. This is the quickest route for Python or C++
clients that already computed FFT magnitudes.

Metadata:

```json
{"type":"meta","challenge_id":"tunnel-basic-dos","center_hz":915000000,"span_hz":44200,"sample_rate_hz":44200,"bins":384,"scheme_id":"MY-GNU-RADIO-FEED","modulation":"2-FSK"}
```

Frame:

```json
{"type":"fft","challenge_id":"tunnel-basic-dos","row":[0.01,0.04,0.92,0.31],"samples":[0.0,0.2,-0.1],"parser":{"stage":"external_fft","confidence":0.82,"bit_buffer":"101100","fields":{"source":"my-bridge"},"note":"External FFT row accepted."}}
```

The `row` values should be normalized from `0.0` to `1.0`. If the row length is
different from `bins`, the backend resamples it for display.

## Protocol 2: One-Shot Raw IQ Frame

Use this when your bridge has raw complex float32 samples and wants the Signal
Forge backend to compute the FFT row.

Send an ASCII header line:

```text
SFORGE IQCF32 challenge_id=tunnel-basic-dos center_hz=915000000 sample_rate_hz=44200 span_hz=44200 bins=384 scheme_id=MY-CF32-FEED samples=2048
```

Then immediately send `samples * 8` bytes of interleaved little-endian float32:

```text
I0 float32, Q0 float32, I1 float32, Q1 float32, ...
```

The server replies with a JSON acknowledgement line after the frame is parsed.

## Protocol 3: Continuous Raw IQ Stream

Use this for a GNU Radio file/socket bridge. Send one header, then stream fixed
size `cf32_le` blocks.

```text
SFORGE RAWIQ challenge_id=tunnel-basic-dos center_hz=915000000 sample_rate_hz=44200 span_hz=44200 bins=384 scheme_id=MY-GR-FILE-SINK block_samples=2048
```

After the header, send repeated blocks of `block_samples * 8` bytes. The server
does not need a JSON object for each block.

## Included Sender

Quick synthetic FFT feed:

```powershell
python tools/script_clients/external_signal_sender.py --challenge-id tunnel-basic-dos --mode fft
```

Synthetic raw IQ feed:

```powershell
python tools/script_clients/external_signal_sender.py --challenge-id tunnel-basic-dos --mode iq --block-samples 2048
```

Run the mapped GNU Radio-generated Python flowgraph:

```powershell
python radio/GNURadio/Tunnel_Task/DoSAttackMe.py
```

GNU Radio ZMQ live bridge:

```powershell
python tools/script_clients/zmq_signal_bridge.py --challenge-id tunnel-packet-injection --endpoint tcp://127.0.0.1:5555 --pattern pull --dtype cf32
```

The ZMQ bridge requires `pyzmq` in the environment where the bridge runs:

```bash
sudo apt install python3-zmq
```

or:

```bash
python -m pip install pyzmq
```

## GNU Radio Pattern

For the mapped beginner tasks, run the generated Python file and leave the
workbench on **Live parser**. The included `SignalForgeLiveSink` is connected
after the channel model, opens the TCP ingest socket, sends the `SFORGE RAWIQ`
header, and forwards complex64 blocks as GNU Radio produces them.

## GNU Radio ZMQ Pattern

For live GNU Radio work, prefer the included ZMQ bridge:

```text
GNU Radio flowgraph -> ZMQ PUSH Sink -> zmq_signal_bridge.py -> Signal Forge ingest -> browser
```

Recommended GNU Radio Companion block:

```text
Block: ZMQ PUSH Sink
Input type: Complex
Address: tcp://127.0.0.1:5555
Bind: Yes
Pass Tags: No
Timeout: 100 ms
High-water mark: small value such as 8 or 16
```

Then run the bridge:

```powershell
python tools/script_clients/zmq_signal_bridge.py --challenge-id tunnel-packet-injection --endpoint tcp://127.0.0.1:5555 --pattern pull --dtype cf32 --center-hz 915000000 --sample-rate-hz 44200 --span-hz 44200
```

The bridge defaults to connecting to GNU Radio. If you want the bridge to bind
and GNU Radio to connect, add `--bind` and turn off binding in the GNU Radio ZMQ
block.

For a PUB/SUB flowgraph, use GNU Radio's ZMQ PUB Sink and run:

```powershell
python tools/script_clients/zmq_signal_bridge.py --challenge-id tunnel-packet-injection --endpoint tcp://127.0.0.1:5555 --pattern sub --dtype cf32
```

Leave the PUB/SUB topic blank unless you deliberately need one. If you do use a
topic, pass the same value with `--topic`.

If GNU Radio computes the FFT or magnitude vector itself, set the bridge dtype
to `f32fft` and make each ZMQ message contain one or more rows of `bins`
little-endian float32 values:

```powershell
python tools/script_clients/zmq_signal_bridge.py --challenge-id tunnel-packet-injection --endpoint tcp://127.0.0.1:5555 --pattern pull --dtype f32fft --bins 384
```

For most challenge development, `cf32` is better: it keeps the browser path
close to real receiver data and lets the backend produce a consistent waterfall.
