# Interview Intake App

A small utility that ingests interview audio from an SD card, encrypts it
client-side with [`age`](https://age-encryption.org), and files it in a shared
Nextcloud project folder under a globally unique, sequentially numbered
interview ID. It also scaffolds the `transcript.md` / `note.md` files the
researcher fills in later.

**It does not** transcribe, read the supervisor's masterfile, manage identity
mapping, or sync Nextcloud.

This is an implementation of the "Interview Intake App" specification v0.1.
The contracts in spec sections 4 (filename grammar), 5 (`registry.json`),
7 (`meta.json`), 9 (encryption) and 10 (allocation) are implemented verbatim.
See [Spec conformance decisions](#spec-conformance-decisions) for the few
places where the spec left an ambiguity.

---

## Contents

- [User instructions (step by step)](#user-instructions-step-by-step)
- [Install](#install)
- [Trust model](#trust-model)
- [Folder layout](#folder-layout)
- [Supervisor setup](#supervisor-setup-one-time)
- [Researcher setup](#researcher-setup-once-per-machine)
- [Daily use: intake](#daily-use-intake)
- [Opening and decrypting](#opening-and-decrypting)
- [Verifying a project](#verifying-a-project)
- [Key generation](#key-generation)
- [Templates](#templates)
- [Security properties](#security-properties)
- [Whisper safety notes](#whisper-safety-notes)
- [Spec conformance decisions](#spec-conformance-decisions)
- [Limitations](#limitations)
- [Development](#development)

---

## Install

Requires Python 3.11+.

Preferred (Rust-backed `pyrage`):

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[pyrage,duration]'
```

Fallback (uses the `age` CLI instead of `pyrage`):

```bash
pip install .
# plus: apt install age   /   brew install age
```

Optional extras:

| Extra | Purpose |
|---|---|
| `pyrage` | Preferred age binding (no CLI needed). |
| `duration` | `mutagen`, used to read duration from mp3/m4a/flac. WAV duration uses the stdlib. |
| `gui` | `tkinterdnd2`, enables drag-and-drop. |
| `dev` | `pytest`, `pyrage`, `mutagen`. |

Check which backend is available:

```bash
interview-intake --help
interview-intake config show   # prints "Available age backends"
```

---

## User instructions (step by step)

This is the practical walkthrough for the two roles. The sections after it are
the detailed reference.

### A. Supervisor — set up the project once

1. **Create the shared folder** in Nextcloud, e.g. `~/Nextcloud/project`.

2. **Create the escrow key** on the supervisor's machine (keep it off researcher
   machines — it can decrypt every interview):

   ```bash
   interview-intake keygen --out ~/.config/interview-intake/keys --name supervisor
   ```

   (Alternatively `interview-intake setup --create-escrow` creates it alongside a
   config.) Copy the printed `Public key` (`age1...`).

3. **Create `registry.json`** in the shared folder. The app **never creates or
   edits this file** (spec section 15). Start from
   [`examples/registry.example.json`](examples/registry.example.json) and put the
   escrow public key in `supervisor`:

   ```json
   {
     "schema_version": 1,
     "researchers": {},
     "supervisor": { "age_public_key": "age1...<escrow>" },
     "last_serial": 0,
     "issued": []
   }
   ```

4. **Register each researcher.** When a researcher sends you their public key,
   add an entry under `researchers`:

   ```json
   "abc": { "display_name": "Researcher ABC", "age_public_key": "age1...<theirs>", "active": true }
   ```

5. **Back up the escrow key** (paper copy + offline encrypted copy). It is the
   durable access path if a researcher leaves.

### B. Researcher — set up this machine once

1. **Install** the app (see [Install](#install)).

2. **First run** — `setup` creates the config and a private key *if missing* and
   never overwrites an existing key:

   ```bash
   interview-intake setup \
     --researcher-id abc \
     --project-path ~/Nextcloud/project \
     --sync-root   ~/Nextcloud \
     --install-templates
   ```

   It prints your **public key**. Send it to the supervisor.

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

### Quick command reference

| Task | Command |
|---|---|
| First-run setup (researcher) | `interview-intake setup --researcher-id abc --project-path P --sync-root S` |
| Add escrow key (supervisor) | `interview-intake setup --create-escrow` (or `keygen --name supervisor`) |
| Show config / backends | `interview-intake config show` |
| Ingest audio | `interview-intake intake <file-or-dir> -m <bbb>` |
| List interviews | `interview-intake open --list` |
| Decrypt one | `interview-intake open <id> [-o path] [--no-open]` |
| Check integrity | `interview-intake verify` |
| Seed templates | `interview-intake templates --overwrite` |

> **Keys are created only if missing.** Re-running `setup` or `keygen` prints the
> existing public key instead of replacing it. Use `--force` only to deliberately
> rotate a key — old interviews stay encrypted to the old key.

---

## Trust model

| Role | Access |
|---|---|
| **Researcher** | Shared Nextcloud project folder. Own private key. Can encrypt and decrypt their own interviews. |
| **Supervisor** | Shared project folder + private masterfile. Holds the escrow private key that decrypts all interviews. |

Researchers are assumed honest but fallible. The supervisor's machine is
trusted. Nextcloud is trusted for storage/availability but **not**
confidentiality. The SD card is untrusted after use. The app does **not** defend
against endpoint compromise, key theft or coercion.

---

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
└── keys/<researcher_id>.key      # chmod 600
```

Interview ID grammar (`^[0-9]{4}-[a-z]{3}-[a-z]{3}-[0-9]{4}$`):

| Field | Rule |
|---|---|
| `YYYY` | Interview year, from the system clock at intake. |
| `AAA` | Researcher ID, 3 lowercase letters, from `config.json`. |
| `BBB` | Mnemonic, 3 lowercase letters, entered at intake. |
| `NNNN` | Global serial, 4 digits, allocated by the app. |

Everything is lowercased; uppercase input is normalised. Reserved mnemonics
(`key`, `tmp`, `new`, `old`, `aux`, `con`, `prn`, `nul`) are rejected.

---

## Supervisor setup (one time)

1. **Create the shared folder** and a `registry.json` with the strict schema
   from spec section 5:

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

   See [`examples/registry.example.json`](examples/registry.example.json).
   The placeholder keys in the example must be replaced with real ones from
   `keygen` / `age-keygen`.

   The app **never creates or repairs** `registry.json`. It only re-reads and
   appends to it. A missing or malformed registry is a hard error.

2. **Add each researcher's age public key** to `researchers`. The supervisor's
   escrow public key goes in `supervisor`. Every interview is encrypted to both
   the researcher and the supervisor.

3. Keep the supervisor private key off researcher machines. It is the durable
   access path if a researcher leaves (old interviews are **not** re-encrypted).

---

## Researcher setup (once per machine)

`setup` is the first-run command. It creates whatever is missing (config and
keys), never overwrites an existing key, and prints the public key to send to the
supervisor:

```bash
interview-intake setup \
  --researcher-id abc \
  --project-path ~/Nextcloud/project \
  --sync-root   ~/Nextcloud \
  --install-templates
```

It writes `~/.config/interview-intake/config.json` and
`~/.config/interview-intake/keys/abc.key` (mode `0600`), seeds the shared
templates, and prints a ready-to-paste `registry.json` snippet. **It never
creates `registry.json`** — the supervisor provisions that (spec section 15).

On the **supervisor's** machine only, add `--create-escrow` to also generate the
escrow key (default `~/.config/interview-intake/keys/supervisor.key`):

```bash
interview-intake setup --create-escrow
```

Re-running `setup` is safe: existing keys are reused and their public keys are
re-derived, not regenerated. Pass `--force` to deliberately rotate a key
(dangerous — old interviews stay encrypted to the old key).

The lower-level `config init --generate-key` still works and is now also
idempotent.

`sync_root` must be a prefix of `project_path`; this is enforced. It is used to
refuse decryption into the synced tree.

Config schema (spec section 14):

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
(or set `INTERVIEW_INTAKE_CONFIG`).

---

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

Drag-and-drop is optional. Without `tkinterdnd2` (or without Tkinter at all),
use the CLI:

```bash
interview-intake intake /media/SDCARD/REC_0042.wav -m xyz
```

---

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

---

## Verifying a project

```bash
interview-intake verify
```

Without decrypting, this checks the registry, every issued interview folder,
`meta.json`, and that each `audio.age` matches the size and SHA-256 recorded in
`meta.json`. It also reports folder/registry mismatches and `FAILED` markers.

---

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
3. Supervisor runs `setup --create-escrow` (their machine) and/or pastes both
   public keys into `registry.json`.

Only the supervisor's machine should ever hold the escrow identity.

---

## Templates

The shared templates live in `<project>/templates/`. If absent, bundled defaults
are used. Re-seed with:

```bash
interview-intake templates --overwrite
```

Templates use `{{interview_id}}`, `{{date}}`, `{{researcher_id}}`,
`{{mnemonic}}` placeholders. Unknown placeholders are an error.

---

## Security properties

- **No plaintext on disk during intake.** The `pyrage` backend reads the file
  into a `bytearray`, zeroes it after use, and writes only ciphertext (via a
  same-directory temp + `os.replace`). The `age` CLI backend pipes the source
  through stdin in a single pass, hashing as it streams.
- **Two recipients.** Each interview is encrypted to the researcher *and* the
  supervisor, read from `registry.json`, never hardcoded.
- **Integrity before commit.** The encrypted file on disk is re-hashed and must
  match the value captured while writing before `meta.json` is recorded.
- **Sync-root refusal.** Decryption into `sync_root` is refused, comparing
  resolved paths so symlinks cannot bypass the check.
- **Private key perms.** The config validator refuses a group/world-accessible
  private key.

> Note: the exact plaintext size can be inferred from the age container, but
> contents are confidential. Metadata (`meta.json`) contains no PII.

---

## Whisper safety notes

Transcription is researcher-driven, so the app cannot enforce these. They are
also embedded in the transcript template's `SAFETY REMINDERS` block.

- **TMPDIR.** Set `TMPDIR` to a directory outside the Nextcloud sync root before
  running Whisper, and wipe that directory afterwards:
  ```bash
  export TMPDIR=~/tmp/whisper-$$
  mkdir -p "$TMPDIR" && chmod 700 "$TMPDIR"
  whisper ... ; rm -rf "$TMPDIR"
  ```
- **Known issue.** Whisper's Python `transcribe()` can write temp audio files to
  the system temp dir and does not always clean them up on failure. Verify with
  `ls -la "$TMPDIR"` after every run.
- **Model cache.** Whisper caches model weights in `~/.cache/whisper`
  (Linux/macOS) or `%USERPROFILE%\.cache\whisper` (Windows). This is model data,
  not interview data, and can be left in place.
- **Output location.** Write the transcript directly into
  `project/interviews/<interview_id>/transcript.md`. Do not write it elsewhere
  and move it later.
- **Never decrypt into the synced folder.** Decrypt to `~/tmp/`, transcribe,
  then delete the plaintext audio.

---

## Spec conformance decisions

Ambiguities in the spec and how this implementation resolves them:

1. **`meta.json` `size_bytes`** (spec section 7) is the size of the stored
   encrypted `audio.age`, so `verify` can check it against the on-disk file.
   `original_*` fields describe the source.
2. **Registry commit vs. encryption order.** The reserve-then-commit algorithm
   (section 10) commits `last_serial` and `issued` *before* encryption, because
   that is the order in section 11. A failed encryption therefore consumes a
   serial; this "phantom serial" is left with a `FAILED` marker for the
   supervisor. The integrity check in section 7 runs before `meta.json` is
   written.
3. **Decryption output extension** is taken from `meta.json`'s
   `audio.format`, defaulting to `.wav` (spec section 12 shows `.wav`).
4. **Interview folder permissions** respect the umask rather than forcing
   `0700`, so the shared Nextcloud folder keeps working.
5. **`age` CLI fallback for decryption** refuses to overwrite existing output;
   pass `--force` to replace.
6. **Stale lock** older than `lock_stale_seconds` is removed at the start of
   each allocation attempt, as suggested in section 10.

---

## Limitations

- **Drag-and-drop** needs `tkinterdnd2` *and* Tkinter; both are optional. The
  CLI is the supported path.
- **Windows** support is best-effort: paths, `os.replace`, eject, and Tkinter
  need testing. `age` and Python themselves are fine.
- **SD wipe** (`--wipe`) is a best-effort overwrite. On flash/CoW storage it is
  not a guaranteed erasure; treat used SD cards as sensitive.
- **Serial exhaustion** at `NNNN > 9999` aborts with a manual-intervention
  message, pending the open "add a zero" policy decision.
- **No re-encryption on key rotation.** Documented above; escrow key is the
  durable path.

---

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

Layout:

```
src/interview_intake/
├── cli.py            # argparse entry points
├── config.py         # ~/.config/interview-intake/config.json
├── models.py         # registry/meta/config dataclasses + validation
├── id_grammar.py     # section 4 grammar
├── allocation.py     # section 10 reserve-then-commit
├── registry.py       # section 5 load/save
├── crypto.py         # section 9 pyrage + age CLI backends
├── intake.py         # section 11 workflow
├── open_interview.py # section 12 decryption helper
├── templates.py      # section 8 markdown templates
├── verify.py         # integrity checks
├── fs.py             # atomic writes, hashing, containment
├── media.py          # eject / mount detection
└── gui.py            # optional drag-and-drop
tests/                # unit + integration tests (fake age backend)
```

The test suite uses a deterministic fake backend, so it runs without `pyrage`
or the `age` CLI.
