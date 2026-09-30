# Installation

Requirements, install steps and first-run checks for the Interview Intake App.

## Requirements

- **Python 3.11 or newer** (3.12 / 3.13 also work).
- **One age backend**:
  - `pyrage` — recommended, ships prebuilt wheels (Apple Silicon/Intel, Linux),
    no compiler needed; **or**
  - the `age` / `age-keygen` CLI (`brew install age` on macOS,
    `sudo apt install age` on Debian/Ubuntu).
- **Tk** (only for the desktop apps): bundled on macOS, `sudo apt install
  python3-tk` on Linux.
- **Optional** extras: `mutagen` for duration of compressed audio, `qrcode` for
  QR codes.

## Quick install (pip + venv)

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e '.[pyrage,duration,qr]'
```

Notes:

- Use `pip install .` instead of `-e .` for a fixed (non-editable) install.
- Without `pyrage`, install the `age` CLI and use `pip install '.[duration,qr]'`.
- `pip install -e '.[dev]'` adds the test dependencies.

### Optional extras

| Extra | Purpose |
|---|---|
| `pyrage` | Preferred age binding (no CLI needed). |
| `duration` | `mutagen`, used to read duration from mp3/m4a/flac. WAV duration uses the stdlib. |
| `gui` | GUI shell. Tk ships with Python / the OS, so this installs nothing. |
| `gui-dnd` | `tkinterdnd2`, optional drag-and-drop for the GUIs. |
| `qr` | `qrcode`, for terminal/SVG/PNG QR codes (key exchange and backup). |
| `excel` | `openpyxl`, for the pro forma → Excel export. |
| `packaging` | `pyinstaller`, to build standalone desktop apps. |
| `dev` | `pytest`, `pyrage`, `mutagen`, `qrcode`, `openpyxl`, `pyyaml`. |

## Verify the install

```bash
interview-intake --version
interview-intake --help
interview-supervisor --help
interview-intake config show      # reports "Available age backends"
```

## Standalone desktop apps (no Python)

Prebuilt bundles need neither Python nor `pip`. Get them from the
[packaging instructions](packaging/README.md) (build locally), or from the
artifacts produced by the release workflow: `.dmg` on macOS,
`.AppImage` / `.deb` on Linux.

## macOS setup (Tahoe / macOS 26)

For macOS 26 "Tahoe" (including 26.6), on both Apple Silicon and Intel. The app
needs Python **3.11 or newer**; these steps install 3.11. Any 3.12/3.13 also
works.

### 1. Open Terminal

- Press `⌘ + Space`, type `Terminal`, and press Return, **or**
- open **Finder → Applications → Utilities → Terminal**.

### 2. Check for Python

```bash
python3 --version
```

If it prints `Python 3.11.x` or newer, skip to
[step 4](#4-create-the-app-environment). Do not rely on the bare system
`/usr/bin/python3` stub; install a real 3.11.

### 3. Install Python 3.11

#### Option A — Homebrew (recommended)

1. Install the Xcode command-line tools (needed by Homebrew):

   ```bash
   xcode-select --install
   ```

2. Install Homebrew (skip if `brew --version` already works):

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

   On Apple Silicon, add Homebrew to the current shell as the installer asks:

   ```bash
   eval "$(/opt/homebrew/bin/brew shellenv)"
   ```

3. Install Python 3.11 (and Tk for the GUI):

   ```bash
   brew install python@3.11
   brew install python-tk@3.11      # optional, for the GUI
   ```

4. Confirm the interpreter:

   ```bash
   "$(brew --prefix python@3.11)/bin/python3.11" --version
   ```

#### Option B — python.org installer (no Homebrew; bundles Tk)

1. In a browser, open <https://www.python.org/downloads/macos/> and download the
   latest **Python 3.11.x macOS 64-bit universal2 installer**.
2. Open the downloaded `.pkg`, click through the installer, and enter your
   password when prompted.
3. Confirm the interpreter:

   ```bash
   python3.11 --version
   ```

> If `python@3.11` is no longer offered by Homebrew, use `python@3.12` (or newer)
> instead — the app supports 3.11 and up.

### 4. Create the app environment

From the project folder (use `cd` to go wherever you cloned `DTGV-Secrets`):

```bash
# Homebrew (Option A) — explicit path works even if python3.11 is not on PATH:
PYTHON="$(brew --prefix python@3.11)/bin/python3.11"

# python.org (Option B):
# PYTHON=python3.11

"$PYTHON" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[pyrage,duration,qr]'
```

Then check it:

```bash
python --version
interview-intake --help
```

### 5. First run

```bash
interview-intake setup --researcher-id abc \
  --project-path ~/Nextcloud/project \
  --sync-root   ~/Nextcloud \
  --install-templates
```

See the [README quick start](README.md#quick-start-5-minutes) or the
[full usage guide](docs/usage.md) for the rest of the workflow.

### macOS notes

- **Backends.** `pyrage` installs as a prebuilt wheel on Apple Silicon and Intel,
  so no compiler is required. To use the `age` CLI instead: `brew install age`.
- **GUI / drag-and-drop.** Requires Tkinter (bundled by the python.org installer,
  or `python-tk@3.11` with Homebrew). Without it, the CLI works exactly as
  documented and is the supported path.
- **SD cards** mount under `/Volumes/<NAME>`. Quote the path if it contains
  spaces:

  ```bash
  interview-intake intake "/Volumes/NO NAME/REC_0042.wav" -m xyz
  ```

- **Gatekeeper.** Installing with `pip` needs no signing or notarization. Only a
  packaged `.app` would require a Developer ID and notarization.

## Linux notes

- Desktop apps need Tk: `sudo apt install python3-tk`.
- `age` CLI fallback: `sudo apt install age`.
- Standalone builds additionally need `binutils`; see
  [packaging/README.md](packaging/README.md).

## Where things live

| What | Path |
|---|---|
| Config | `~/.config/interview-intake/config.json` |
| Private key | `~/.config/interview-intake/keys/<researcher_id>.key` (`0600`) |
| Registration request | `~/.config/interview-intake/registration/<id>.pub.json` |
| Shared project | the path passed as `--project-path` |

Override the config location with `--config PATH` or the
`INTERVIEW_INTAKE_CONFIG` environment variable.

## Troubleshooting

- **`Cannot derive the public key: install pyrage or age-keygen`** — install one
  of the two backends (see Requirements).
- **`Config not found`** — run `interview-intake setup ...` (or `config init`).
- **The GUI does not open** — install Tk (`python3-tk` on Linux); otherwise use
  the CLI, which is always available.
- **`project_path ... must be inside sync_root`** — `sync_root` must be a prefix
  of `project_path`.
- **Private key is group/world-accessible** — `chmod 600 <key>`.
