from __future__ import annotations

import json
import html
import hmac
import hashlib
import mimetypes
import os
import random
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
AIR_WEATHER_SESSIONS: dict[str, dict] = {}
OPERATOR_COMMENTS = [
    {
        "callsign": "WARTHOG-1",
        "route_note": "Decoded training frame looked normal.",
        "operator_comment": "Awaiting correlation with toll event.",
    }
]
RANGE_SECRET = os.urandom(32)
RF_TARGETS = {
    "find-the-scheme": {"center_mhz": 915.0, "span_khz": 1200, "modulations": {"AUTO", "2-FSK"}, "label": "RSU-MAINT-915"},
    "reverse-the-decoder": {"center_mhz": 315.0, "span_khz": 500, "modulations": {"AUTO", "ASK", "MANCHESTER"}, "label": "RSU-FRAME-315"},
    "backend-recon": {"center_mhz": 868.3, "span_khz": 700, "modulations": {"AUTO", "CSS", "LORA"}, "label": "RSU-UPLINK-868"},
    "free-trip-logic-flaw": {"center_mhz": 2437.0, "span_khz": 1000, "modulations": {"AUTO", "GFSK"}, "label": "TOLL-REPLAY-2437"},
    "operator-console-xss": {"center_mhz": 144.39, "span_khz": 260, "modulations": {"AUTO", "AFSK"}, "label": "OPS-NOTE-144"},
    "length-field-chaos": {"center_mhz": 902.3, "span_khz": 650, "modulations": {"AUTO", "4-FSK"}, "label": "RSU-TLV-902"},
    "weather-radio-watch": {"center_mhz": 251.75, "span_khz": 300, "modulations": {"AUTO", "AM"}, "label": "FORGE-WEATHER-251"},
}


def session_id_from(handler: SimpleHTTPRequestHandler, body: dict | None = None) -> str:
    candidate = str((body or {}).get("session_id", "") or handler.headers.get("X-Signal-Session", "")).strip()
    if not candidate:
        return "anonymous"
    return "".join(character for character in candidate if character.isalnum() or character in "-_")[:80] or "anonymous"


def session_token(session_id: str, purpose: str, length: int = 16) -> str:
    digest = hmac.new(RANGE_SECRET, f"{session_id}:{purpose}".encode("utf-8"), hashlib.sha256).hexdigest().upper()
    return digest[:length]


def flag_for(session_id: str, challenge_id: str) -> str:
    return f"CTF{{{session_token(session_id, f'flag:{challenge_id}')}}}"


def user_data_for(session_id: str) -> dict:
    token = session_token(session_id, "user-data", 20)
    return {
        "operator_id": f"OP-{token[:6]}",
        "callsign": f"FORGE-{token[6:10]}",
        "vehicle_id": f"VH-{token[10:14]}",
        "range_nonce": token[14:20],
    }


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
                ('recon_flag', '__SESSION_RECON_FLAG__');
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
        if parsed.path in {"/data/challenges.json", "/data/tolling.db", "/config/range.json", "/server.py"} or parsed.path.startswith("/."):
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        if parsed.path.startswith("/challenge/"):
            challenge_id = parsed.path.removeprefix("/challenge/").strip("/")
            known_ids = {task["id"] for task in load_challenges()}
            if challenge_id not in known_ids:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown challenge")
                return
            self.path = "/challenge.html"
            super().do_GET()
            return
        if parsed.path == "/api/config":
            public_config = load_config()
            public_config["telemetry"].pop("hmac_key", None)
            self.write_json(public_config)
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
            self.write_json(radio_intercept(session_id_from(self)))
            return
        if parsed.path == "/api/air/weather":
            session_id = session_id_from(self)
            intercept = generate_air_weather_intercept(session_id)
            AIR_WEATHER_SESSIONS[session_id] = intercept
            self.write_json({key: value for key, value in intercept.items() if key not in {"answer", "auth_code"}})
            return
        if parsed.path == "/api/rf/session":
            session_id = session_id_from(self)
            self.write_json({"session_id": session_id, "user_data": user_data_for(session_id), "fft_bins": 1024})
            return
        if parsed.path == "/api/rsu/maintenance":
            self.write_json(
                {
                    "target": "RSU maintenance TLV parser",
                    "method": "POST",
                    "path": "/api/rsu/maintenance/parse",
                    "content_type": "application/json",
                    "schema": {"type": "0x42", "declared_length": 111, "payload": "operator note"},
                    "operator_note": "Attack Mode models the native parser's trusted-length behaviour; Secure Mode requires exact length agreement.",
                }
            )
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
        if parsed.path == "/api/rsu/maintenance/parse":
            self.handle_maintenance_parser()
            return
        if parsed.path == "/api/rf/command":
            self.handle_rf_command()
            return
        if parsed.path == "/api/air/inject":
            self.handle_air_voice_injection()
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

        session_id = session_id_from(self, body)
        expected = flag_for(session_id, task_id).upper()
        if submitted == expected:
            self.write_json({"ok": True, "message": "Correct. Task solved.", "points": task["points"]})
        else:
            self.write_json({"ok": False, "message": "Not quite. Re-check the signal evidence and hints."})

    def handle_air_voice_injection(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "message": "Invalid report payload."}, HTTPStatus.BAD_REQUEST)
            return

        session_id = session_id_from(self, body)
        intercept = AIR_WEATHER_SESSIONS.get(session_id)
        if not intercept or str(body.get("intercept_id", "")) != intercept["intercept_id"]:
            self.write_json({"ok": False, "message": "Generate a current intercept before filing the report."}, HTTPStatus.BAD_REQUEST)
            return

        message = " ".join(str(body.get("message", "")).strip().upper().split())
        required = {
            "target callsign": intercept["callsign"].upper() in message,
            "sector identifier": f"SECTOR {intercept['sector']}" in message,
            "diversion command": "DIVERT " in message,
            "authentication code": f"AUTH {intercept['auth_code']}" in message,
            "credible decoy reason": any(word in message for word in {"WEATHER", "STORM", "TRAFFIC", "RADAR", "EMERGENCY", "HAZARD", "RUNWAY"}),
        }
        missing = [label for label, present in required.items() if not present]
        if not missing:
            self.write_json({
                "ok": True,
                "message": "Protocol accepted. The synthetic diversion was rebroadcast on the training net.",
                "flag": flag_for(session_id, "weather-radio-watch"),
                "broadcast": message,
            })
            return
        self.write_json({
            "ok": False,
            "message": f"Injection rejected. Missing or incorrect: {', '.join(missing)}.",
            "accepted_fields": [label for label, present in required.items() if present],
        })

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
            session_id = session_id_from(self)
            for row in rows:
                for key, value in row.items():
                    if value == "__SESSION_RECON_FLAG__":
                        row[key] = flag_for(session_id, "backend-recon")
            self.write_json(
                {
                    "warning": "Intentionally vulnerable training endpoint. Do not copy this pattern.",
                    "query": sql,
                    "rows": rows,
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
            result["flag"] = flag_for(session_id_from(self), "free-trip-logic-flaw")
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

    def handle_maintenance_parser(self) -> None:
        try:
            body = read_json_body(self)
            tlv_type = int(str(body.get("type", "0")), 0)
            declared_length = int(body.get("declared_length", 0))
            payload = str(body.get("payload", ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            self.write_json({"error": "type and declared_length must be valid integers"}, HTTPStatus.BAD_REQUEST)
            return

        actual_length = len(payload.encode("utf-8"))
        if tlv_type != 0x42:
            self.write_json({"decision": "rejected", "reason": "unsupported TLV type"}, HTTPStatus.BAD_REQUEST)
            return
        if MODE["value"] == "secure" and declared_length != actual_length:
            self.write_json(
                {
                    "mode": "secure",
                    "decision": "rejected",
                    "declared_length": declared_length,
                    "actual_length": actual_length,
                    "reason": "declared length does not equal available payload length",
                },
                HTTPStatus.BAD_REQUEST,
            )
            return

        result = {
            "mode": MODE["value"],
            "decision": "parsed",
            "declared_length": declared_length,
            "actual_length": actual_length,
            "length_mismatch": declared_length != actual_length,
            "diagnostic_command_seen": "MAINT_DIAG_UNLOCK" in payload,
        }
        if MODE["value"] == "attack" and declared_length > actual_length and "MAINT_DIAG_UNLOCK" in payload:
            result["diagnostic_access"] = "granted"
            result["flag"] = flag_for(session_id_from(self, body), "length-field-chaos")
        self.write_json(result)

    def handle_rf_command(self) -> None:
        try:
            body = read_json_body(self)
        except json.JSONDecodeError:
            self.write_json({"ok": False, "lines": ["Invalid command payload."]}, HTTPStatus.BAD_REQUEST)
            return

        session_id = session_id_from(self, body)
        challenge_id = str(body.get("challenge_id", ""))
        action = str(body.get("action", "")).lower().strip()
        arguments = str(body.get("arguments", "")).strip()
        receiver = body.get("receiver", {}) if isinstance(body.get("receiver", {}), dict) else {}
        target = RF_TARGETS.get(challenge_id)
        if not target:
            self.write_json({"ok": False, "lines": ["No RF target is assigned to this module."]}, HTTPStatus.NOT_FOUND)
            return

        try:
            center_mhz = float(receiver.get("center_mhz", 0))
            span_khz = max(1.0, float(receiver.get("span_khz", 1)))
            gain_db = float(receiver.get("gain_db", 0))
            squelch_db = float(receiver.get("squelch_db", -90))
        except (TypeError, ValueError):
            self.write_json({"ok": False, "lines": ["Receiver values must be numeric."]}, HTTPStatus.BAD_REQUEST)
            return

        modulation = str(receiver.get("modulation", "AUTO")).upper()
        offset_khz = abs(center_mhz - target["center_mhz"]) * 1000
        in_view = offset_khz <= span_khz / 2
        tuned = offset_khz <= max(8.0, min(40.0, span_khz / 16))
        demod_ok = modulation in target["modulations"]
        level_db = -72 + min(28, gain_db * 0.7)
        above_squelch = level_db >= squelch_db
        locked = tuned and demod_ok and above_squelch

        base = {
            "ok": True,
            "action": action,
            "locked": locked,
            "target": target["label"],
            "receiver": {"center_mhz": center_mhz, "offset_khz": round(offset_khz, 3), "modulation": modulation},
            "user_data": user_data_for(session_id),
        }

        if action == "scan":
            if in_view:
                base["lines"] = [
                    f"ENERGY  {target['label']}  {target['center_mhz']:.6f} MHz  level {level_db:.1f} dBFS",
                    f"OFFSET  {offset_khz:.1f} kHz  candidate demodulations: {', '.join(sorted(target['modulations']))}",
                ]
            else:
                base["lines"] = ["No target energy inside the selected span.", "Adjust centre/span or inspect the module's signal intelligence."]
            self.write_json(base)
            return

        if action in {"status", "tune"}:
            base["lines"] = [
                f"RX {center_mhz:.6f} MHz / span {span_khz:.0f} kHz / {modulation} / gain {gain_db:.0f} dB",
                f"TARGET {'LOCKED' if locked else 'UNLOCKED'} / offset {offset_khz:.1f} kHz / squelch {'open' if above_squelch else 'closed'}",
            ]
            self.write_json(base)
            return

        if not locked:
            base["ok"] = False
            base["lines"] = [
                "Receiver not locked: no usable target output.",
                f"Check centre frequency, demodulation, gain, and squelch (offset {offset_khz:.1f} kHz).",
            ]
            self.write_json(base, HTTPStatus.BAD_REQUEST)
            return

        if action == "receive":
            lines = [f"LOCK {target['label']} / sync acquired / CRC usable"]
            if challenge_id == "find-the-scheme":
                lines += ["BEACON vendor user_data decoded", f"FLAG {flag_for(session_id, challenge_id)}"]
                base["flag"] = flag_for(session_id, challenge_id)
            elif challenge_id == "reverse-the-decoder":
                lines += ["FRAME SFCTF1|VH-7A29|PX-41F0|EAST-17|BIRCH|STANDARD|...|5e", "Decoder input buffered. Try `decode`." ]
            elif challenge_id == "backend-recon":
                lines += ["UPLINK vehicle_id=VH-7A29 service=/api/toll/events", "The terminal can run same-origin requests with `request <path>`." ]
            elif challenge_id == "free-trip-logic-flaw":
                lines += ["TOLL FRAME schedule=STANDARD price=750", "Replay/interference controls can alter the observed maintenance schedule." ]
            elif challenge_id == "operator-console-xss":
                lines += ["AFSK operator_note decoded", "NOTE contains an active console control; use `forward console`." ]
            elif challenge_id == "weather-radio-watch":
                lines += ["AM voice carrier acquired on 251.750 MHz", "Open the UHF protocol injection net, intercept the exchange, and recover its message fields."]
            else:
                lines += ["TLV type=0x42 declared=111 actual=47", "PAYLOAD MAINT_DIAG_UNLOCKAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]
            base["lines"] = lines
            self.write_json(base)
            return

        if action == "decode" and challenge_id == "reverse-the-decoder":
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["CHECKSUM expected=5e provided=5e valid=true", f"DECODER OUTPUT {base['flag']}"]
        elif action == "interfere" and MODE["value"] == "attack" and challenge_id == "free-trip-logic-flaw" and any(word in arguments.lower() for word in {"replay", "maint_free", "maintenance"}):
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["INTERFERENCE replay aligned / schedule=MAINT_FREE", "TOLL OUTPUT price=0", f"FLAG {base['flag']}"]
        elif action == "transmit":
            if MODE["value"] == "attack" and challenge_id == "free-trip-logic-flaw" and "replay" in arguments.lower():
                base["flag"] = flag_for(session_id, challenge_id)
                base["lines"] = ["TX replay waveform visible in receiver passband", "TARGET OUTPUT schedule=MAINT_FREE price=0", f"FLAG {base['flag']}"]
            else:
                base["lines"] = ["TX burst injected into local spectrum simulation.", "No target state change was observed for this waveform."]
        elif action == "forward" and MODE["value"] == "attack" and challenge_id == "operator-console-xss" and "console" in arguments.lower():
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["FORWARD operator_note -> console", "Console rendered RF-origin control in Attack Mode.", f"UI OUTPUT {base['flag']}"]
        elif action == "send" and MODE["value"] == "attack" and challenge_id == "length-field-chaos" and "maint_diag_unlock" in arguments.lower():
            base["flag"] = flag_for(session_id, challenge_id)
            base["lines"] = ["TX TLV accepted / length mismatch reached native parser", "DIAGNOSTIC ACCESS granted", f"TARGET OUTPUT {base['flag']}"]
        else:
            base["ok"] = False
            base["lines"] = ["Command reached the target but did not trigger its success condition.", "Use `receive` and the module intelligence to inspect the target output."]
        self.write_json(base, HTTPStatus.OK if base["ok"] else HTTPStatus.BAD_REQUEST)


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


def generate_air_weather_intercept(session_id: str) -> dict:
    rng = random.SystemRandom()
    callsign = f"{rng.choice(['VIPER', 'RAZOR', 'TALON', 'HAVOC', 'SABRE', 'RAVEN', 'COBRA'])} {rng.randint(1, 9)}-{rng.randint(1, 4)}"
    controller = rng.choice(["FORGE CONTROL", "NOMAD CONTROL", "OVERLORD", "SENTRY", "ATLAS CONTROL"])
    aircraft = rng.choice(["two F-35s", "a C-130", "two Super Hornets", "a P-8", "three Hawks", "a KC-30"])
    sector = rng.choice(["BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF"])
    altitude = rng.choice(["flight level one eight zero", "flight level two one zero", "flight level two six zero", "flight level three one zero", "one two thousand feet"])
    direction = rng.choice(["northbound", "southbound", "eastbound", "westbound"])
    wind_direction = rng.randrange(10, 360, 10)
    wind_speed = rng.randrange(12, 46)
    gust = wind_speed + rng.randrange(6, 21)
    visibility = rng.choice(["three", "five", "seven", "ten", "more than ten"])
    cloud = rng.choice(["broken cloud at four thousand", "overcast at two thousand five hundred", "scattered cloud at six thousand", "broken cloud at eight thousand"])
    pressure = rng.randrange(995, 1028)
    auth_code = f"{rng.choice(['ORBIT', 'LANCER', 'CITADEL', 'NOMAD', 'VECTOR', 'ANCHOR'])}-{rng.randint(2, 9)}"
    hazard, advisory, readback = rng.choice([
        ("thunderstorms", "embedded thunderstorms with tops above flight level three five zero", "thunderstorms and deviation east"),
        ("severe turbulence", "severe turbulence reported between flight levels two zero zero and two eight zero", "severe turbulence, maintaining below two zero zero"),
        ("airframe icing", "moderate to severe airframe icing in cloud above six thousand", "airframe icing, remaining clear of cloud"),
        ("wind shear", "significant wind shear on the western approach below three thousand", "wind shear, western approach not available"),
        ("volcanic ash", "volcanic ash reported across the northern half of the sector", "volcanic ash, routing south"),
        ("heavy precipitation", "heavy precipitation reducing radar and visual contact", "heavy precipitation, requesting vectors"),
    ])
    request = rng.choice([
        "request updated weather and routing recommendation",
        "say weather for the sector and any significant hazards",
        "request conditions along track and hazard status",
    ])
    acknowledgement = rng.choice(["copy all", "roger weather", "good readback", "affirm, that is correct"])
    intercept_id = session_token(session_id, f"air-weather:{time.time_ns()}:{rng.random()}", 12)
    lines = [
        {"speaker": callsign, "role": "aircraft", "text": f"{controller}, {callsign}, {aircraft}, {direction} {altitude}, approaching sector {sector}, {request}."},
        {"speaker": controller, "role": "controller", "text": f"{callsign}, {controller}. Sector {sector}: wind {wind_direction:03d} at {wind_speed}, gusting {gust}; visibility {visibility} miles; {cloud}; QNH {pressure}. Primary hazard is {advisory}. Recommend deviation {rng.choice(['east', 'west', 'south'])} by {rng.choice(['ten', 'fifteen', 'twenty'])} miles."},
        {"speaker": callsign, "role": "aircraft", "text": f"{controller}, {callsign}, copy wind {wind_direction:03d} at {wind_speed}, QNH {pressure}, {readback}."},
        {"speaker": controller, "role": "controller", "text": f"{callsign}, {acknowledgement}. Report clear of sector {sector}. Authentication for further routing is {auth_code}."},
    ]
    return {
        "intercept_id": intercept_id,
        "channel": "251.750 MHz",
        "modulation": "AM",
        "callsign": callsign,
        "controller": controller,
        "sector": sector,
        "lines": lines,
        "answer": hazard,
        "auth_code": auth_code,
    }


def radio_intercept(session_id: str = "anonymous") -> dict:
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
            f"<button onclick=\"document.querySelector('#operator-flag').textContent='{flag_for(session_id, 'operator-console-xss')}'\">"
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
