# Existing Local Adapter

Configuration is outside the skill at
`%LOCALAPPDATA%/Codex/communication-skills/profiles.json`. Read only the selected
`wechat` profile. It contains paths, not a raw key. The profile's `python` and
`runtime_paths` reuse the existing Python and dependency installation.

PowerShell example (replace the values with the actual requested scope):

```powershell
$cfg = Get-Content -LiteralPath "$env:LOCALAPPDATA/Codex/communication-skills/profiles.json" -Encoding UTF8 | ConvertFrom-Json
$py = $cfg.wechat.default.python
$reader = "$env:USERPROFILE/.codex/skills/wechat-local-reader/scripts/read_chat.py"
& $py $reader contacts --profile default --contains '<contact-or-group-fragment>'
& $py $reader read --profile default --chat '<exact-name-or-selected-id>' --since '<YYYY-MM-DD>' --before '<YYYY-MM-DD>'
```

`--before` is exclusive; omitted it uses the current time. Dates use the profile's
UTC offset; explicit ISO datetimes must include an offset. `--kind group|private`
can disambiguate names. Output uses a new private run directory each time. The CLI
prints its path/count, not the full message content; read the resulting JSON/text.

The profile needs `source_root` (the account's db_storage), `key_path` (existing
DPAPI file), `work_root`, and `timezone_offset`; `runtime_paths` is optional.
Do not infer that the account-folder suffix is the user's message sender ID.

The wrapper reuses the existing decryption/decoding helpers. It applies only valid
committed WAL frames, decrypts copies, checks integrity and searches message shards.
The per-shard snapshots are individually consistent, not a globally simultaneous
backup of the whole application. Do not claim otherwise.

No automatic dependency installation or credential recovery is performed. If the
profile or dependency path is missing on another machine, ask for configuration
rather than searching unrelated projects for secrets.
