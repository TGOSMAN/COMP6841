# Networked Script Terminal

The browser terminal and external scripts can both talk to the local range.

Local API:

- `GET /api/script/interface` describes the interface.
- `POST /api/script/terminal` runs one command against a selected subtask.
- `GET /api/contexts` lists situations and nested subtasks.
- `GET /api/tasks` lists all subtasks.

Example payload:

```json
{
  "session_id": "my-script",
  "challenge_id": "tunnel-tuning",
  "command": "tune 915.000"
}
```

Supported commands:

- `help`
- `challenge <subtask-id>`
- `scan`
- `tune <MHz>`
- `span <kHz>`
- `gain <dB>`
- `squelch <dB>`
- `demod <mode>`
- `receive`
- `decode <notes>`
- `interfere <effect>`
- `transmit <payload>`
- `send <payload>`
- `request <path>`

Use `tools/script_clients/signal_terminal_client.py` as the generated Python
client. It uses only the Python standard library.

