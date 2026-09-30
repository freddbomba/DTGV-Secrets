# Security, trust and limitations

## Trust model

| Role | Access |
|---|---|
| **Researcher** | Shared Nextcloud project folder. Own private key. Can encrypt and decrypt their own interviews. |
| **Supervisor** | Shared project folder + private masterfile. Holds the escrow private key that decrypts all interviews. |

Researchers are assumed honest but fallible. The supervisor's machine is
trusted. Nextcloud is trusted for storage/availability but **not**
confidentiality. The SD card is untrusted after use. The app does **not** defend
against endpoint compromise, key theft or coercion.

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

## Limitations

- **Drag-and-drop** needs `tkinterdnd2` *and* Tkinter; both are optional. The
  CLI is the supported path.
- **Windows** support is best-effort: paths, `os.replace`, eject, and Tkinter
  need testing. `age` and Python themselves are fine.
- **SD wipe** (`--wipe`) is a best-effort overwrite. On flash/CoW storage it is
  not a guaranteed erasure; treat used SD cards as sensitive.
- **Serial exhaustion** at `NNNN > 9999` aborts with a manual-intervention
  message, pending the open "add a zero" policy decision.
- **No re-encryption on key rotation.** The escrow key is the durable path.
