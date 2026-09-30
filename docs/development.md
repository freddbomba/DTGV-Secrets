# Development

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

The test suite uses a deterministic fake age backend, so it runs without
`pyrage` or the `age` CLI. CI (`.github/workflows/release.yml`) runs it on
Python 3.11.

## Source layout

```
src/interview_intake/
├── cli.py            # researcher CLI entry points
├── supervisor_cli.py # supervisor CLI entry points (interview-supervisor)
├── supervisor.py     # supervisor core: registry provisioning + escrow + QR backup
├── registration.py   # registration.json public-key exchange document
├── qr.py             # QR rendering (terminal/SVG/PNG), optional qrcode
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
├── proforma.py       # pro forma data + Excel export
├── gui_common.py     # pure, headless-testable GUI helpers
├── gui.py            # researcher Tk app (optional drag-and-drop)
└── supervisor_gui.py # supervisor Tk app
tests/                # unit + integration tests (fake age backend)
tests/data/           # 15-record pro forma sample (fictional)
scripts/              # standalone utilities (pro forma -> xlsx, GUI screenshots)
packaging/            # PyInstaller specs + macOS/Linux build scripts
.github/workflows/    # release.yml (build matrix + artifact upload)
docs/                 # this documentation set
```

## Documentation map

| Doc | Contents |
|---|---|
| [../README.md](../README.md) | Overview + quick start. |
| [../INSTALL.md](../INSTALL.md) | Installation and macOS setup. |
| [usage.md](usage.md) | Full CLI workflows and reference. |
| [gui.md](gui.md) | Desktop apps and screenshots. |
| [security.md](security.md) | Trust model, security properties, limitations. |
| [reference.md](reference.md) | Spec conformance, pro forma export. |
| [implementation-plan.md](implementation-plan.md) | Roadmap and delivered phases (Italian). |

## Packaging and releases

Build the standalone desktop apps with the recipes in
[../packaging/README.md](../packaging/README.md):

```bash
pip install -e '.[pyrage,qr,packaging]'
packaging/build_macos.sh                  # .app + .dmg
packaging/build_linux.sh --all            # onedir + .AppImage + .deb
```

The `release.yml` workflow builds both platforms on a `v*` tag (or via **Run
workflow**) and uploads the artifacts.
