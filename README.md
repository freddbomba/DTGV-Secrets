# Interview Intake App

A small CLI + desktop tool for research interviews:

1. **Ingests** interview audio from an SD card.
2. **Encrypts it end-to-end** with [`age`](https://age-encryption.org).
3. **Files it** in a shared Nextcloud project folder under a globally unique,
   sequential interview ID (`2026-abc-xyz-0001`).
4. **Scaffolds** the `transcript.md` / `note.md` files you fill in later.

It does **not** transcribe, read the supervisor's masterfile, manage identity
mapping, or sync Nextcloud.

## The two roles

| Role | Responsible for | Key it holds |
|---|---|---|
| **Researcher** | Setting up their machine, ingesting audio, decrypting their own interviews. | Own private key. |
| **Supervisor** | Provisioning the project (`registry.json`), registering researchers, escrow backup. | Escrow key that can recover **every** interview. |

Every interview is encrypted to **both** the researcher and the supervisor.
The Researcher app never creates `registry.json`; only the Supervisor app does.

## Quick start (5 minutes)

Install first — see **[INSTALL.md](INSTALL.md)**. Short version:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[pyrage,duration,qr]'
```

Then, once per project:

```bash
# Supervisor — create the shared project, registry and escrow key
interview-supervisor init -p ~/Nextcloud/project

# Researcher — create config + key, then send the registration file to the supervisor
interview-intake setup --researcher-id abc \
  --project-path ~/Nextcloud/project --sync-root ~/Nextcloud
# -> ~/.config/interview-intake/registration/abc.pub.json

# Supervisor — register that researcher
interview-supervisor researcher add --from ~/Downloads/abc.pub.json
```

Every day:

```bash
# Researcher — ingest an interview (-m = 3-letter mnemonic you choose)
interview-intake intake /media/SDCARD/REC_0042.wav -m xyz

# Researcher — list and decrypt a stored interview
interview-intake open --list
interview-intake open 2026-abc-xyz-0001
```

> **Keys are created only if missing.** `setup` / `keygen` reuse an existing key
> instead of replacing it. Use `--force` only to deliberately rotate one — old
> interviews stay encrypted to the old key.

## Desktop apps (GUI)

The same workflows are available as Tk desktop apps, no terminal needed:

| Researcher app | Supervisor app |
|---|---|
| ![Researcher app](docs/images/gui-researcher-setup.png) | ![Supervisor app](docs/images/gui-supervisor-init.png) |

```bash
interview-intake-gui        # researcher app
interview-supervisor-gui    # supervisor app
```

See **[docs/gui.md](docs/gui.md)** for a screenshot of every tab and a
step-by-step walkthrough. Want to run it without installing Python? Use the
standalone apps in **[packaging/README.md](packaging/README.md)**.

## Command reference

| Task | Command |
|---|---|
| Researcher first-run setup | `interview-intake setup --researcher-id abc --project-path P --sync-root S` |
| Ingest audio | `interview-intake intake <file-or-dir> -m <bbb>` |
| List / decrypt interviews | `interview-intake open --list` · `interview-intake open <id>` |
| Integrity check | `interview-intake verify` |
| Supervisor: create project | `interview-supervisor init -p <project>` |
| Supervisor: researchers | `interview-supervisor researcher add --from <file>` · `interview-supervisor researcher list` |
| Supervisor: escrow backup | `interview-supervisor escrow backup --out <dir>` |
| Registration request / QR | `interview-intake registration [--qr] [--qr-out FILE]` |
| Generate a key | `interview-intake keygen --out <dir> --name <id>` |
| Seed templates | `interview-intake templates --overwrite` |
| Show config / backends | `interview-intake config show` |

## Documentation

| Doc | Contents |
|---|---|
| [INSTALL.md](INSTALL.md) | Requirements, pip/venv, macOS step-by-step, extras, troubleshooting. |
| [docs/usage.md](docs/usage.md) | Full CLI walkthrough, supervisor/registry, file layout, config schema, ID grammar. |
| [docs/gui.md](docs/gui.md) | Desktop apps: every tab, screenshots, step-by-step. |
| [docs/security.md](docs/security.md) | Trust model, crypto/integrity guarantees, Whisper notes, limitations. |
| [docs/reference.md](docs/reference.md) | Spec conformance decisions, pro forma / Excel export. |
| [docs/development.md](docs/development.md) | Dev setup, tests, source layout, packaging/releases. |
| [docs/implementation-plan.md](docs/implementation-plan.md) | Roadmap and delivered phases (Italian). |

## Trust in one paragraph

Nextcloud is trusted for availability but **not** confidentiality; the SD card
is untrusted after use. No plaintext is written during intake, decryption into
the sync folder is refused, and every interview is recoverable with the
supervisor's escrow key — old interviews are never re-encrypted. Full details in
[docs/security.md](docs/security.md).

## License

MIT — see [LICENSE](LICENSE).
