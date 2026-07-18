from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class SignalTerminalClient:
    base_url: str = "http://localhost:8002"
    session_id: str = "script-dev"

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def command(self, challenge_id: str, command: str) -> dict:
        payload = json.dumps(
            {
                "session_id": self.session_id,
                "challenge_id": challenge_id,
                "command": command,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/script/terminal",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Signal Forge script-terminal command.")
    parser.add_argument("challenge_id", help="Subtask id, e.g. tunnel-tuning")
    parser.add_argument("command", nargs="+", help="Terminal command, e.g. tune 915.000")
    parser.add_argument("--base-url", default="http://localhost:8002")
    parser.add_argument("--session-id", default="script-dev")
    args = parser.parse_args()

    client = SignalTerminalClient(base_url=args.base_url.rstrip("/"), session_id=args.session_id)
    result = client.command(args.challenge_id, " ".join(args.command))
    for line in result.get("lines", []):
        print(line)
    if result.get("flag"):
        print(result["flag"])
    if not result.get("ok", True):
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

