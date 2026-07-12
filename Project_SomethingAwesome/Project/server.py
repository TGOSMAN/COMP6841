from __future__ import annotations

import json
import html
import hmac
import hashlib
import mimetypes
import os
import sqlite3
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "tolling.db"
CHALLENGES_PATH = DATA_DIR / "challenges.json"
CONFIG_PATH = ROOT / "config" / "range.json"
MODE = {"value": "attack"}
REPLAY_CACHE: set[str] = set()
OPERATOR_COMMENTS = [
    {
        "callsign": "WARTHOG-1",
        "route_note": "Decoded training frame looked normal.",
        "operator_comment": "Awaiting correlation with toll event.",
    }
]


def load_challenges() -> list[dict]:
    with CHALLENGES_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def public_task(task: dict) -> dict:
    return {key: value for key, value in task.items() if key != "flag"}


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS vehicles (
                vehicle_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                plate TEXT NOT NULL,
                account_state TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS toll_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id TEXT NOT NULL,
                booth_id TEXT NOT NULL,
                route_code TEXT NOT NULL,
                schedule_code TEXT NOT NULL,
                observed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schedules (
                schedule_code TEXT PRIMARY KEY,
                route_code TEXT NOT NULL,
                label TEXT NOT NULL,
                price_cents INTEGER NOT NULL,
                operator_only INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS api_notes (
                note_key TEXT PRIMARY KEY,
                note_value TEXT NOT NULL
            );

            DELETE FROM vehicles;
            DELETE FROM toll_events;
            DELETE FROM schedules;
            DELETE FROM api_notes;

            INSERT INTO vehicles VALUES
                ('VH-7A29', 'training-driver', 'RF-6841', 'active'),
                ('VH-1138', 'commuter-a', 'ETA-1138', 'active'),
                ('VH-9001', 'operator-test', 'OPS-9001', 'operator');

            INSERT INTO toll_events (vehicle_id, booth_id, route_code, schedule_code, observed_at) VALUES
                ('VH-7A29', 'EAST-17', 'BIRCH', 'STANDARD', '2026-07-12T06:41:03Z'),
                ('VH-7A29', 'EAST-17', 'BIRCH', 'STANDARD', '2026-07-12T06:41:13Z'),
                ('VH-1138', 'WEST-04', 'CEDAR', 'PEAK', '2026-07-12T06:41:21Z'),
                ('VH-9001', 'EAST-17', 'BIRCH', 'MAINT_FREE', '2026-07-12T06:41:31Z');

            INSERT INTO schedules VALUES
                ('STANDARD', 'BIRCH', 'Normal tolling window', 750, 0),
                ('PEAK', 'CEDAR', 'Peak congestion window', 1250, 0),
                ('NIGHT', 'BIRCH', 'Low demand window', 300, 0),
                ('MAINT_FREE', 'BIRCH', 'Maintenance vehicle bypass', 0, 1);

            INSERT INTO api_notes VALUES
                ('recon_flag', 'CTF{SCHEDULES_TABLE_FOUND}'),
                ('logic_flag', 'CTF{TOLL_PRICE_ZERO}');
            """
        )


def query_db(sql: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def read_json_body(handler: SimpleHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def telemetry_payload(data: dict) -> str:
    fields = [
        "vehicle_id",
        "pseudonym_id",
        "booth_id",
        "route_code",
        "schedule_code",
        "timestamp",
        "nonce",
    ]
    return "|".join(str(data.get(field, "")) for field in fields)


def telemetry_hmac(data: dict, config: dict | None = None) -> str:
    config = config or load_config()
    key = config["telemetry"]["hmac_key"].encode("utf-8")
    return hmac.new(key, telemetry_payload(data).encode("utf-8"), hashlib.sha256).hexdigest()


def example_secure_packet() -> dict:
    config = load_config()
    packet = {
        key: config["telemetry"][key]
        for key in [
            "vehicle_id",
            "pseudonym_id",
            "booth_id",
            "route_code",
            "schedule_code",
            "timestamp",
            "nonce",
        ]
    }
    packet["timestamp_unix"] = int(time.time())
    packet["hmac"] = telemetry_hmac(packet, config)
    return packet


def vehicle_is_operator(vehicle_id: str) -> bool:
    rows = query_db("SELECT account_state FROM vehicles WHERE vehicle_id = ?", (vehicle_id,))
    return bool(rows and rows[0]["account_state"] == "operator")


class CTFHandler(SimpleHTTPRequestHandler):
    server_version = "SignalForgeCTF/1.0"

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            self.write_json(load_config())
            return
        if parsed.path == "/api/mode":
            self.write_json({"mode": MODE["value"]})
            return
        if parsed.path == "/api/tasks":
            self.write_json({"tasks": [public_task(task) for task in load_challenges()]})
            return
        if parsed.path == "/api/toll/events":
            self.handle_vulnerable_events(parsed.query)
            return
        if parsed.path == "/api/toll/safe-events":
            self.handle_safe_events(parsed.query)
            return
        if parsed.path == "/api/toll/quote":
            self.handle_quote(parsed.query)
            return
        if parsed.path == "/api/telemetry/example":
            self.write_json(example_secure_packet())
            return
        if parsed.path == "/api/radio/intercept":
            self.write_json(radio_intercept())
            return
        if parsed.path == "/operator/events":
            self.handle_operator_events()
            return
        if parsed.path == "/api/research":
            self.write_json(research_notes())
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/mode":
            self.handle_mode()
            return
        if parsed.path == "/api/flag":
            self.handle_flag()
            return
        if parsed.path == "/api/toll/secure-quote":
            self.handle_secure_quote()
            return
        if parsed.path == "/api/telemetry/verify":
            self.handle_telemetry_verify()
            return
        if parsed.path == "/operator/comment":
            self.handle_operator_comment()
            return
        self.write_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean_path = unquote(parsed.path).lstrip("/")
        target = (ROOT / clean_path).resolve()
        if not str(target).startswith(str(ROOT)):
            return str(ROOT / "index.html")
        if target.is_dir():
            target = target / "index.html"
        return str(target)

    def write_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def handle_flag(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "message": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return

        task_id = body.get("taskId", "")
        submitted = str(body.get("flag", "")).strip().upper()
        task = next((item for item in load_challenges() if item["id"] == task_id), None)
        if not task:
            self.write_json({"ok": False, "message": "Unknown task."}, HTTPStatus.NOT_FOUND)
            return

        expected = task["flag"].upper()
        if submitted == expected:
            self.write_json({"ok": True, "message": "Correct. Task solved.", "points": task["points"]})
        else:
            self.write_json({"ok": False, "message": "Not quite. Re-check the signal evidence and hints."})

    def handle_mode(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        requested = str(body.get("mode", "")).lower()
        if requested not in {"attack", "secure"}:
            self.write_json({"error": "mode must be attack or secure"}, HTTPStatus.BAD_REQUEST)
            return
        MODE["value"] = requested
        if requested == "attack":
            REPLAY_CACHE.clear()
        self.write_json({"mode": MODE["value"]})

    def handle_vulnerable_events(self, query: str) -> None:
        if MODE["value"] == "secure":
            self.write_json(
                {
                    "mode": "secure",
                    "blocked": True,
                    "reason": "Secure Mode disables the intentionally vulnerable SQL endpoint. Use /api/toll/safe-events.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        params = parse_qs(query)
        vehicle_id = params.get("vehicle_id", [""])[0]
        sql = (
            "SELECT event_id, vehicle_id, booth_id, route_code, schedule_code "
            f"FROM toll_events WHERE vehicle_id = '{vehicle_id}'"
        )
        try:
            rows = query_db(sql)
            schema_found = any("schedules" in {str(value) for value in row.values()} for row in rows)
            self.write_json(
                {
                    "warning": "Intentionally vulnerable training endpoint. Do not copy this pattern.",
                    "query": sql,
                    "rows": rows,
                    "flag": "CTF{SCHEDULES_TABLE_FOUND}" if schema_found else None,
                }
            )
        except sqlite3.Error as exc:
            self.write_json(
                {
                    "warning": "SQL error intentionally exposed for the training task.",
                    "query": sql,
                    "error": str(exc),
                },
                HTTPStatus.BAD_REQUEST,
            )

    def handle_safe_events(self, query: str) -> None:
        params = parse_qs(query)
        vehicle_id = params.get("vehicle_id", [""])[0]
        rows = query_db(
            """
            SELECT event_id, vehicle_id, booth_id, route_code, schedule_code
            FROM toll_events
            WHERE vehicle_id = ?
            """,
            (vehicle_id,),
        )
        self.write_json(
            {
                "defence": "This endpoint uses a parameterized query, so SQL text and user data stay separate.",
                "rows": rows,
            }
        )

    def handle_quote(self, query: str) -> None:
        params = parse_qs(query)
        vehicle_id = params.get("vehicle_id", [""])[0]
        booth_id = params.get("booth_id", [""])[0]
        route_code = params.get("route_code", [""])[0]
        schedule_code = params.get("schedule_code", [""])[0]

        schedules = query_db(
            """
            SELECT schedule_code, route_code, label, price_cents, operator_only
            FROM schedules
            WHERE route_code = ? AND schedule_code = ?
            """,
            (route_code, schedule_code),
        )
        if not schedules:
            self.write_json({"error": "No matching schedule."}, HTTPStatus.NOT_FOUND)
            return

        schedule = schedules[0]
        if MODE["value"] == "secure" and schedule["operator_only"] and not vehicle_is_operator(vehicle_id):
            self.write_json(
                {
                    "mode": "secure",
                    "authorized_schedule": False,
                    "decision": "rejected",
                    "reason": "Secure Mode derives operator-only schedule entitlement server-side.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        result = {
            "vehicle_id": vehicle_id,
            "booth_id": booth_id,
            "route_code": route_code,
            "schedule_code": schedule_code,
            "price_cents": schedule["price_cents"],
            "logic_flaw": "The endpoint trusts schedule_code from telemetry instead of deriving entitlement server-side.",
        }
        if schedule["price_cents"] == 0:
            result["flag"] = "CTF{TOLL_PRICE_ZERO}"
        self.write_json(result)

    def handle_secure_quote(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        packet = body.get("packet", body)
        if not isinstance(packet, dict):
            self.write_json({"decision": "rejected", "reason": "packet must be a JSON object"}, HTTPStatus.BAD_REQUEST)
            return
        verification = verify_telemetry_packet(packet)
        if not verification["decision"] == "accepted":
            self.write_json(verification, HTTPStatus.FORBIDDEN)
            return

        schedules = query_db(
            """
            SELECT schedule_code, route_code, label, price_cents, operator_only
            FROM schedules
            WHERE route_code = ? AND schedule_code = ?
            """,
            (packet.get("route_code", ""), packet.get("schedule_code", "")),
        )
        if not schedules:
            self.write_json({"decision": "rejected", "reason": "No matching schedule."}, HTTPStatus.NOT_FOUND)
            return

        schedule = schedules[0]
        authorized = not schedule["operator_only"] or vehicle_is_operator(packet.get("vehicle_id", ""))
        if not authorized:
            self.write_json(
                {
                    "decision": "rejected",
                    "authorized_schedule": False,
                    "reason": "Operator-only schedule denied for this vehicle.",
                },
                HTTPStatus.FORBIDDEN,
            )
            return
        self.write_json(
            {
                "decision": "accepted",
                "authorized_schedule": True,
                "price_cents": schedule["price_cents"],
                "schedule_code": schedule["schedule_code"],
            }
        )

    def handle_telemetry_verify(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        packet = body.get("packet", body)
        if not isinstance(packet, dict):
            self.write_json({"decision": "rejected", "reason": "packet must be a JSON object"}, HTTPStatus.BAD_REQUEST)
            return
        result = verify_telemetry_packet(packet)
        status = HTTPStatus.OK if result["decision"] == "accepted" else HTTPStatus.FORBIDDEN
        self.write_json(result, status)

    def handle_operator_events(self) -> None:
        self.write_json(
            {
                "mode": MODE["value"],
                "events": OPERATOR_COMMENTS,
                "xss_training_flag": "CTF{CONSOLE_XSS_CHAIN}",
                "rendering_note": "Attack Mode intentionally renders comments as HTML in the browser. Secure Mode renders text only.",
            }
        )

    def handle_operator_comment(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON."}, HTTPStatus.BAD_REQUEST)
            return
        event = {
            "callsign": str(body.get("callsign", "UNKNOWN")),
            "route_note": str(body.get("route_note", "")),
            "operator_comment": str(body.get("operator_comment", "")),
        }
        if MODE["value"] == "secure":
            event = {key: html.escape(value) for key, value in event.items()}
        OPERATOR_COMMENTS.append(event)
        self.write_json({"ok": True, "mode": MODE["value"], "event": event})


def verify_telemetry_packet(packet: dict) -> dict:
    config = load_config()
    supplied = str(packet.get("hmac", ""))
    expected = telemetry_hmac(packet, config)
    hmac_valid = hmac.compare_digest(supplied, expected)

    timestamp_unix = int(packet.get("timestamp_unix", 0) or 0)
    now = int(time.time())
    window = int(config["security"]["freshness_window_seconds"])
    fresh_timestamp = timestamp_unix > 0 and abs(now - timestamp_unix) <= window

    nonce = str(packet.get("nonce", ""))
    replay_seen = nonce in REPLAY_CACHE

    accepted = hmac_valid and fresh_timestamp and not replay_seen
    if accepted:
        REPLAY_CACHE.add(nonce)

    return {
        "mode": MODE["value"],
        "hmac_valid": hmac_valid,
        "fresh_timestamp": fresh_timestamp,
        "replay_seen": replay_seen,
        "authorized_schedule": None,
        "decision": "accepted" if accepted else "rejected",
        "reason": "packet authenticated and fresh" if accepted else "packet failed HMAC, freshness, or replay checks",
        "expected_hmac_for_training": expected if MODE["value"] == "attack" else None,
    }


def radio_intercept() -> dict:
    config = load_config()
    telemetry = config["telemetry"]
    return {
        "frame_id": "RF-INT-2437-0007",
        "callsign": "WARTHOG-1",
        "channel_label": "TOLL-LPI-TRAINING-03",
        "center_hz": config["rf"]["center_hz"],
        "carrier_offset_hz": -320000,
        "estimated_doppler_hz": 42,
        "rssi_dbm": -67,
        "snr_db": 18.4,
        "modulation": "2-FSK training burst with FHSS-like channel plan",
        "preamble": "0xA7D5",
        "sync_word": "0xC35A",
        "vehicle_id": telemetry["vehicle_id"],
        "pseudonym_id": telemetry["pseudonym_id"],
        "booth_id": telemetry["booth_id"],
        "route_code": telemetry["route_code"],
        "schedule_code": telemetry["schedule_code"],
        "timestamp": telemetry["timestamp"],
        "nonce": telemetry["nonce"],
        "checksum": "0x5e",
        "operator_note": (
            "RF-origin operator_note field: schedule anomaly requires review. "
            "<button onclick=\"document.querySelector('#operator-flag').textContent='CTF{CONSOLE_XSS_CHAIN}'\">"
            "Render test</button>"
        ),
        "sink_warning": "This decoded note is untrusted RF-origin text. Attack Mode renders it as HTML; Secure Mode renders it as text.",
        "operator_action": "Correlate burst with toll event, then review trust boundary before posting to console.",
    }


def research_notes() -> dict:
    return {
        "rf": [
            "Waterfalls show power over frequency and time; repeated vertical marks indicate periodic bursts.",
            "ASK/OOK-style training signals are useful for teaching because amplitude changes are easy to inspect.",
            "Later stages should include multipath, Doppler, timing offset, burst collisions, adaptive coding, LPI/LPD tradeoffs, and direction-finding evidence.",
            "SigMF stores RF sample data with JSON metadata so captures remain reproducible without hardware."
        ],
        "cyber": [
            "A decoded radio field is still attacker-controlled input once it reaches a backend.",
            "SQL injection happens when applications concatenate untrusted input into query text.",
            "Prepared statements and allow-listed dynamic values are the intended defences for this CTF.",
            "Hard cyber stages should combine RE, memory corruption, fuzzing, protocol state-machine bugs, XSS sinks, authorization failures, and telemetry replay."
        ],
        "sota_security": [
            "Secure Mode demonstrates HMAC, freshness checks, replay rejection, server-side authorization, and safe SQL as the baseline, not the finish line.",
            "SOTA hard levels should require layered assurance: hardware root of trust, secure boot, signed firmware, key separation, remote attestation, and measured boot evidence.",
            "Radio SOTA should cover adaptive hopping, spread spectrum, interference classification, MIMO/beam/null steering concepts, propagation modelling, and jamming resilience.",
            "Cyber SOTA should include memory-safe parsers, fuzzing harnesses, binary hardening, SBOM/supply-chain checks, CSP/output encoding, and backend policy enforcement.",
            "Detection SOTA should fuse RF features, decoded protocol behaviour, backend logs, and anomaly models because valid packets can still be operationally suspicious."
        ],
        "hardware": [
            "Keep assessed transmit paths disabled, but model receiver front-end limits: saturation, dynamic range, adjacent-channel interference, clock drift, and oscillator error.",
            "Developer extensions can add signed firmware images, boot measurements, and simulated device attestation before the backend trusts a roadside unit.",
            "Hardware realism should also include antenna patterns, path loss, terrain/urban multipath assumptions, and calibration notes for every generated capture."
        ],
        "jamming": [
            "Beginner jamming captures can show obvious wideband noise; advanced captures should distinguish barrage, spot, sweep, follower, deceptive replay, and protocol-aware interference.",
            "Defence challenges should force tradeoffs between hopping, coding, power control, directional receive, redundancy, holdover logic, and backend fraud detection.",
            "The CTF should reward classification and mitigation planning, not over-the-air transmission."
        ],
        "gnu_radio": [
            "Use GNU Radio Companion in WSL/Ubuntu to generate flowgraphs.",
            "For this project, GNU Radio should generate artifacts rather than transmit over the air.",
            "A future bridge can publish FFT rows through ZeroMQ or a Python socket for the browser."
        ]
    }


def main() -> None:
    init_db()
    os.chdir(ROOT)
    port = int(os.environ.get("PORT", "8000"))
    mimetypes.add_type("application/json", ".sigmf-meta")
    server = ThreadingHTTPServer(("localhost", port), CTFHandler)
    print(f"Signal Forge CTF serving http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
