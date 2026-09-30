# Usage guide (CLI)

The complete command-line workflow. For installation see
[../INSTALL.md](../INSTALL.md); for the desktop apps see [gui.md](gui.md).

- [Step by step](#step-by-step)
  - [A. Supervisor — set up the project once](#a-supervisor--set-up-the-project-once)
  - [B. Researcher — set up this machine once](#b-researcher--set-up-this-machine-once)
  - [C. Researcher — ingest an interview](#c-researcher--ingest-an-interview)
  - [D. Researcher — open (decrypt) an interview](#d-researcher--open-decrypt-an-interview)
- [Supervisor App (registry & escrow)](#supervisor-app-registry--escrow)
- [Manual registry setup (legacy)](#manual-registry-setup-legacy)
- [Daily use: intake](#daily-use-intake)
- [Opening and decrypting](#opening-and-decrypting)
- [Verifying a project](#verifying-a-project)
- [Key generation](#key-generation)
- [Templates](#templates)
- [Folder layout](#folder-layout)
- [Interview ID grammar](#interview-id-grammar)
- [Config schema](#config-schema)
- [Quick command reference](#quick-command-reference)

## Step by step

This is the practical walkthrough for the two roles.

### A. Supervisor — set up the project once

1. **Create the shared folder** in Nextcloud, e.g. `~/Nextcloud/project`.

2. **Initialise it with the Supervisor App** (creates `interviews/`, `templates/`,
   a valid `registry.json` and the escrow key):

   ```bash
   interview-supervisor init -p ~/Nextcloud/project \
     --escrow-key ~/.config/interview-intake/keys/supervisor.key
   ```

   The command is idempotent: an existing registry is kept. Use `--force` only to
   deliberately regenerate the escrow key and rewrite the registry (destructive).

3. **Register each researcher** once they send you their public key or
   `registration.json`:

   ```bash
   interview-supervisor researcher add --from ~/Downloads/abc.pub.json
   # or: interview-supervisor researcher add abc --name "Researcher ABC" --key age1...
   ```

4. **Back up the escrow key** (paper copy + offline encrypted copy). It is the
   durable access path if a researcher leaves.

> The manual alternative — hand-editing `registry.json` — still works; see
> [Manual registry setup](#manual-registry-setup-legacy).

### B. Researcher — set up this machine once

1. **Install** the app (see [../INSTALL.md](../INSTALL.md)).

2. **First run** — `setup` creates the config and a private key *if missing* and
   never overwrites an existing key:

   ```bash
   interview-intake setup \
     --researcher-id abc \
     --project-path ~/Nextcloud/project \
     --sync-root   ~/Nextcloud \
     --install-templates
   ```

   It writes `~/.config/interview-intake/config.json` and a **registration
   request** at `~/.config/interview-intake/registration/<id>.pub.json`,
   containing your public key. Send that file (or the printed public key) to the
   supervisor.

3. **Wait until the supervisor confirms** your key is in `registry.json`.

4. **Check the wiring:**

   ```bash
   interview-intake config show
   interview-intake open --list
   ```

### C. Researcher — ingest an interview

1. Plug in the SD card.
2. Run intake:

   ```bash
   interview-intake intake /media/SDCARD/REC_0042.wav -m xyz
   ```

   - `-m xyz` is a 3-letter mnemonic you choose (reserved words are rejected).
   - Add `--yes` for a non-interactive run.
   - Add `--wipe --eject` to erase the source and eject the card afterwards.
3. The app prints the new interview ID, e.g. `2026-abc-xyz-0001`, and writes
   `audio.age`, `meta.json`, `transcript.md`, `note.md` into the shared folder.
4. After transcribing, edit `transcript.md` / `note.md` in Nextcloud.

### D. Researcher — open (decrypt) an interview

1. List interviews: `interview-intake open --list`
2. Decrypt and play:

   ```bash
   interview-intake open 2026-abc-xyz-0001
   ```

   or write it somewhere specific without launching a player:

   ```bash
   interview-intake open 2026-abc-xyz-0001 -o ~/tmp/iv.wav --no-open
   ```

3. **Delete the decrypted file when done.** The app refuses to decrypt into the
   Nextcloud sync folder.

## Supervisor App (registry & escrow)

The `interview-supervisor` command provisions and maintains the shared project,
including `registry.json`. Per the 2026-09 role split, the **Supervisor App owns
`registry.json`** (creates and manages it); the **Researcher App never creates
it** — it only reads it and appends allocation records.

Register a researcher without hand-editing JSON:

```bash
# from a pasted public key
interview-supervisor researcher add abc --name "Researcher ABC" --key age1...

# or from the researcher's registration.json
interview-supervisor researcher add --from ~/Downloads/abc.pub.json

interview-supervisor researcher list
interview-supervisor researcher deactivate abc   # keep history, block new use
interview-supervisor researcher remove abc       # refused if interviews exist
```

Escrow key backup, with QR codes for offline/paper storage:

```bash
interview-supervisor escrow show --qr
interview-supervisor escrow backup --out ~/escrow-backup
# writes escrow-*.key (0600), escrow-public-*.svg, escrow-secret-*.svg (0600), README
```

`verify` additionally reports registry-level issues (duplicate public keys,
inactive researchers with issued interviews, interviews for unknown
researchers):

```bash
interview-supervisor verify -p ~/Nextcloud/project
```

> QR output needs the optional `qrcode` package: `pip install -e '.[qr]'`.

## Manual registry setup (legacy)

Instead of `interview-supervisor init`, you can create the shared folder and a
`registry.json` by hand, using the strict schema from spec section 5:

```json
{
  "schema_version": 1,
  "researchers": {
    "abc": {
      "display_name": "Researcher ABC",
      "age_public_key": "age1...",
      "active": true
    }
  },
  "supervisor": { "age_public_key": "age1..." },
  "last_serial": 0,
  "issued": []
}
```

See [`examples/registry.example.json`](../examples/registry.example.json). The
placeholder keys must be replaced with real ones from `keygen` / `age-keygen`.

Every interview is encrypted to both the researcher and the supervisor, read
from `registry.json`. Keep the supervisor private key off researcher machines
(old interviews are **not** re-encrypted when a researcher leaves).

## Daily use: intake

```bash
# One file, non-interactive:
interview-intake intake /media/SDCARD/REC_0042.wav -m xyz --yes

# A whole SD card; the app scans for *.wav/*.mp3/*.m4a/*.flac and prompts:
interview-intake intake /media/SDCARD -m xyz

# Then wipe the source and eject the card:
interview-intake intake /media/SDCARD/REC_0042.wav -m xyz --yes --wipe --eject
```

Workflow (spec section 11): validate config and recipients → scan/select audio
→ validate mnemonic → allocate serial → create folder → encrypt (streaming, no
plaintext to disk) → verify ciphertext on disk → write `meta.json` → render
`transcript.md` / `note.md` → re-read the registry to confirm the ID.

If encryption/meta/template writing fails, the partial `audio.age` is deleted
and a `FAILED` marker is left in the interview folder. The serial is already
committed (by design), so it becomes a **phantom serial** that the supervisor
reconciles with `interview-intake verify`.

## Opening and decrypting

```bash
interview-intake open --list
interview-intake open 2026-abc-xyz-0001                  # decrypt to ~/tmp/ + open player
interview-intake open 2026-abc-xyz-0001 -o ~/tmp/iv.wav --no-open
```

The default output is `~/tmp/<interview_id>.<format>` in a `0700` directory,
written `0600`. The app **refuses** any output path inside `sync_root`. It warns
if the destination directory is world-readable. Existing outputs are not
overwritten unless `--force`.

After transcription, delete the decrypted plaintext.

## Verifying a project

```bash
interview-intake verify
```

Without decrypting, this checks the registry, every issued interview folder,
`meta.json`, and that each `audio.age` matches the size and SHA-256 recorded in
`meta.json`. It also reports folder/registry mismatches and `FAILED` markers.

## Key generation

```bash
interview-intake keygen --out ~/.config/interview-intake/keys --name abc
interview-intake keygen --out ~/.config/interview-intake/keys --name supervisor
```

Generates an age X25519 keypair (or reuses the existing one and prints its
public key) and writes the identity (`0600`). Give the public key to the
supervisor to add to `registry.json`. The app never edits the registry for you.

The full first-run flow is:

1. Researcher runs `setup` → gets a public key.
2. Researcher sends that public key to the supervisor.
3. Supervisor runs `init` (or `setup --create-escrow`) and/or adds the public keys
   to `registry.json`.

Only the supervisor's machine should ever hold the escrow identity.

## Templates

The shared templates live in `<project>/templates/`. If absent, bundled defaults
are used. Re-seed with:

```bash
interview-intake templates --overwrite
```

Templates use `{{interview_id}}`, `{{date}}`, `{{researcher_id}}`,
`{{mnemonic}}` placeholders. Unknown placeholders are an error.

## Folder layout

Shared project folder (Nextcloud):

```
project/
├── registry.json
├── registry.lock                 # transient
├── templates/
│   ├── transcript_template.md
│   └── note_template.md
└── interviews/
    └── 2026-abc-xyz-0001/
        ├── audio.age
        ├── transcript.md
        ├── note.md
        └── meta.json
```

Supervisor-only (never on researcher machines):

```
supervisor/
├── master.json                   # encrypted at rest, e.g. git-crypt
├── supervisor_key.age            # private key
└── backups/
```

Researcher local (never synced):

```
~/.config/interview-intake/
├── config.json
├── keys/<researcher_id>.key      # chmod 600
└── registration/<id>.pub.json    # share with the supervisor
```

## Interview ID grammar

`^[0-9]{4}-[a-z]{3}-[a-z]{3}-[0-9]{4}$`

| Field | Rule |
|---|---|
| `YYYY` | Interview year, from the system clock at intake. |
| `AAA` | Researcher ID, 3 lowercase letters, from `config.json`. |
| `BBB` | Mnemonic, 3 lowercase letters, entered at intake. |
| `NNNN` | Global serial, 4 digits, allocated by the app. |

Everything is lowercased; uppercase input is normalised. Reserved mnemonics
(`key`, `tmp`, `new`, `old`, `aux`, `con`, `prn`, `nul`) are rejected.

## Config schema

Spec section 14:

```json
{
  "schema_version": 1,
  "researcher_id": "abc",
  "private_key_path": "~/.config/interview-intake/keys/abc.key",
  "project_path": "~/Nextcloud/project",
  "sync_root": "~/Nextcloud",
  "sync_wait_seconds": 3,
  "lock_stale_seconds": 60
}
```

`config show` prints the current config; `--config PATH` overrides the location
(or set `INTERVIEW_INTAKE_CONFIG`). `sync_root` must be a prefix of
`project_path`; this is enforced (it is used to refuse decryption into the
synced tree).

## Quick command reference

| Task | Command |
|---|---|
| First-run setup (researcher) | `interview-intake setup --researcher-id abc --project-path P --sync-root S` |
| Show/export registration request | `interview-intake registration [--out FILE] [--qr] [--qr-out FILE]` |
| Initialise project (supervisor) | `interview-supervisor init -p P [--escrow-key K]` |
| Manage researchers | `interview-supervisor researcher add/list/activate/deactivate/remove` |
| Escrow | `interview-supervisor escrow show [--qr]` · `escrow backup --out DIR` |
| Show config / backends | `interview-intake config show` |
| Ingest audio | `interview-intake intake <file-or-dir> -m <bbb>` |
| List interviews | `interview-intake open --list` |
| Decrypt one | `interview-intake open <id> [-o path] [--no-open]` |
| Check integrity | `interview-intake verify` |
| Generate a key | `interview-intake keygen --out DIR --name ID` |
| Seed templates | `interview-intake templates --overwrite` |

> **Keys are created only if missing.** Re-running `setup` or `keygen` prints the
> existing public key instead of replacing it. Use `--force` only to deliberately
> rotate a key — old interviews stay encrypted to the old key.
