# Signal Forge CTF

Signal Forge is a sim-first contested-spectrum CTF about a smart tolling and ETA system. It combines RF signal analysis with several concrete cyber-security skill tracks:

1. Passive spectrum observation.
2. Scheme identification from RF artifacts.
3. Simplified telemetry decoding.
4. SQL injection against a local toll API.
5. Toll quote business logic abuse.
6. RF waveform/protocol reverse engineering.
7. Reverse engineering of a synthetic telemetry decoder.
8. Firmware reverse engineering and hardware trust analysis.
9. Local parser memory-safety analysis with vulnerable and safe C sources.
10. TLV length-field binary exploitation.
11. Operator-console XSS as an RF-to-web trust-boundary lesson.
12. Propagation, replay, and jamming analysis.
13. SOTA layered assurance across RF, hardware, cyber, and detection.
14. Defensive design across RF, backend, browser, and parser controls.

The CTF is designed to run without SDR hardware. GNU Radio is documented as the artifact generation path, not as a required live dependency.

## Run Locally

Use the Python backend rather than a static file server:

```powershell
python server.py
```

Then open:

```text
http://localhost:8000
```

The server initializes `data/tolling.db` on startup and serves both the webpage and JSON APIs.

## Project Structure

- `index.html`, `styles.css`, `app.js` - browser CTF interface.
- `server.py` - dependency-free Python HTTP API and static server.
- `config/range.json` - editable RF, telemetry, and security settings.
- `data/challenges.json` - editable challenge definitions and flags.
- `captures/` - RF artifacts, SigMF metadata, decoded packet notes, and waterfall JSON.
- `artifacts/` - cyber challenge inputs such as telemetry frames.
- `tools/` - local RE and parser challenge sources/harnesses.
- `docs/gnu-radio-workflow.md` - GNU Radio development path.

## API Examples

Normal event lookup:

```text
/api/toll/events?vehicle_id=VH-7A29
```

Trigger the intentionally vulnerable SQL endpoint:

```text
/api/toll/events?vehicle_id=VH-7A29'
```

Enumerate schema in the training endpoint:

```text
/api/toll/events?vehicle_id=' UNION SELECT name,type,sql,'x','x' FROM sqlite_master--
```

Safe parameterized comparison:

```text
/api/toll/safe-events?vehicle_id=VH-7A29
```

Business logic flaw quote:

```text
/api/toll/quote?vehicle_id=VH-7A29&booth_id=EAST-17&route_code=BIRCH&schedule_code=MAINT_FREE
```

Mode control:

```text
GET /api/mode
POST /api/mode {"mode":"attack"}
POST /api/mode {"mode":"secure"}
```

Secure telemetry example:

```text
GET /api/telemetry/example
POST /api/telemetry/verify
POST /api/toll/secure-quote
```

Operator-console XSS training:

```text
GET /operator/events
POST /operator/comment
GET /api/radio/intercept
```

Attack Mode intentionally renders operator comments as HTML in the browser. Secure Mode renders them as text.

## Cyber Tools

Reverse engineering challenge:

```powershell
python tools\telemetry_decoder\telemetry_decoder.py artifacts\telemetry-frame.txt
```

Roadside parser challenge sources:

```text
tools/rsu_parser/rsu_parser_vuln.c
tools/rsu_parser/rsu_parser_safe.c
tools/rsu_parser/sample_overflow_frame.txt
```

Firmware and additional binary exploitation tracks:

```text
tools/firmware_re/
tools/tlv_parser/
artifacts/waveform-re-notes.json
```

These are synthetic local training artifacts. They do not target real software or systems.

## Developing More Challenges

Add or edit challenges in `data/challenges.json`. Each challenge supports:

- `id`, `title`, `track`, `difficulty`, `points`
- `scenario`, `objective`, `concepts`
- ordered `steps`
- downloadable `artifacts`
- hint ladder
- expected `flag`

For new RF tasks, add captures under `captures/` and link them from the challenge JSON.

For new cyber tasks, add local-only artifacts under `artifacts/` or `tools/`, then link them from the challenge JSON.

## GNU Radio Direction

Recommended workflow on Windows is WSL/Ubuntu:

```bash
sudo apt update
sudo apt install gnuradio python3-numpy python3-scipy
gnuradio-companion
```

Use GNU Radio Companion to generate local IQ files, then describe them with SigMF metadata. Do not require live transmission for the assessed build.

See `docs/gnu-radio-workflow.md` for the detailed path.

## Security Notes

The `/api/toll/events` endpoint is intentionally vulnerable so players can learn SQL injection safely in a local training environment. The `/api/toll/safe-events` endpoint demonstrates the defensive version using parameterized queries.

Do not copy the vulnerable query pattern into production code.

Secure Mode demonstrates several state-of-practice controls at training scale:

- HMAC over telemetry fields.
- Timestamp freshness.
- Nonce replay rejection.
- Parameterized SQL.
- Server-side schedule authorization.
- Output encoding / safe DOM rendering for operator comments.
- Bounded parser design in the safe C source.
- Firmware signing, measured boot, protected key storage, and attestation as advanced design requirements.
- RF/cyber detection fusion for jamming, replay, and suspicious-but-valid telemetry.
