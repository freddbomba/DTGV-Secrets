# Piano di implementazione — App self-contained Researcher / Supervisor

Data: 2026-09
Stato: proposta, in attesa di go su Phase 1

## 1. Decisioni prese

- **(a)** Il provisioning di `registry.json` è di proprietà della **Supervisor App**.
  La **Researcher App non crea mai** `registry.json` (continua a leggerlo e ad
  appendervi l'allocazione). La spec §11/§15 va emendata per nominare la
  Supervisor App come provisioner legittimo.
- **Piattaforme target: macOS + Linux** (Windows fuori scope).
- **QR code** confermati: usati per lo scambio della chiave pubblica e per il
  backup delle chiavi (pubblica + privata). Dipendenza opzionale `qrcode`
  (`pip install '.[qr]'`), output terminale + SVG (stdlib) + PNG (con Pillow).
- **Due deliverable autonomi**, uno per ruolo, senza repo, `pip` o `venv`
  visibili all'utente finale.

## 2. Architettura target

```
                 interview_intake/  (core engine, invariato)
                 ├── models.py  registry.py  allocation.py  crypto.py
                 ├── intake.py  open_interview.py  verify.py  templates.py
                 └── ...
                        │
        ┌───────────────┴───────────────┐
        │                               │
  RESEARCHER APP                  SUPERVISOR APP
  interview-intake                interview-supervisor
  (setup, intake, open, verify)   (init, researcher, escrow, master, export)
  registry: READ + APPEND         registry: CREATE + MANAGE
```

- Il core resta l'unico motore di cifratura/formato/grammatica.
- Due entry point distinct (`pyproject.toml` → `[project.scripts]`).
- Un modulo condiviso di onboarding/scambio chiavi (`registration.py`).
- La UI (GUI o CLI guidata) è un layer sottile sopra il core.

## 3. Supervisor App — nuovo modulo `supervisor.py`

Entry point: `interview-supervisor` (nuovo in `[project.scripts]`).

| Comando | Effetto |
|---|---|
| `supervisor init --project PATH [--sync-root S] [--create-escrow] [--install-templates]` | Crea `project/`, `interviews/`, `templates/`, genera escrow key, **crea `registry.json` valido**. Idempotente. |
| `supervisor researcher add <id> --name "N" (--key age1... \| --from FILE \| --key-file PATH)` | Aggiunge/aggiorna un ricercatore nel registry. |
| `supervisor researcher deactivate <id>` / `activate <id>` | Imposta `active` senza cancellare (le interviste restano leggibili). |
| `supervisor researcher remove <id>` | Rimozione, rifiutata se esistono `issued` per quell'ID. |
| `supervisor researcher list` | Tabella: id, nome, attivo, chiave (troncata), n. interviste. |
| `supervisor escrow show` / `escrow backup` | Mostra chiave pubblica / istruzioni e copia di backup. |
| `supervisor verify` | Riutilizza `verify.py` + controlli registry (chiavi duplicate, issued orfani, inattivi con interviste). |
| `supervisor master init` / `master set <id> ...` / `master show` | Gestione del masterfile identità (oggi fuori banda). |
| `supervisor export --format xlsx --out F` | Export pro forma generato da registry + `meta.json` reali, non dal sample. |

Regole di sicurezza del registry:
- Scritture atomiche (riusa `fs.write_json_atomic` + `registry.lock`).
- Validazione via `models.Registry.from_dict/to_dict`, nessun campo extra.
- Backup automatico `registry.json.bak.<timestamp>` prima di ogni modifica.

## 4. Scambio chiavi ricercatore → supervisore

Oggi: copia/incolla manuale. Proposta: **file di registrazione**.

`registration.json` (prodotto dalla Researcher App, importato dalla Supervisor App):

```json
{
  "schema_version": 1,
  "researcher_id": "abc",
  "display_name": "Researcher ABC",
  "age_public_key": "age1...",
  "created_at": "2026-09-01T10:00:00Z"
}
```

- Researcher: `setup` lo scrive in `~/.config/interview-intake/registration/abc.pub.json`
  (e lo mostra/QR). Inviabile via email/chat.
- Supervisor: `supervisor researcher add abc --from abc.pub.json`.

Questo rende il flusso offline-friendly e senza errori di trascrizione.

## 5. Researcher App — semplificazione UX

- **`setup` → wizard unico**: prompt guidati per researcher id, project path,
  sync root; rileva cartelle Nextcloud; genera chiave; scrive config +
  registration file; stampa/QR la chiave. Nessun flag obbligatorio.
- **`intake` guidato**: rileva volumi rimovibili montati (`media.py`), li elenca,
  fa scegliere file; mnemonic suggerita; conferma riepilogo.
- **`open` guidato**: lista interviste, scelta, decrypt, cleanup.
- **GUI con Tk stdlib**: file picker e folder picker nativi (`tkinter.filedialog`).
  **Si elimina la dipendenza da `tkinterdnd2`** (drag&drop diventa opzionale, non
  richiesto). La GUI diventa veramente self-contained.
- La CLI resta completa come percorso avanzato.

## 6. Packaging self-contained

Nessun `pip`/`venv` per l'utente finale.

**macOS**
- PyInstaller `--windowed` → `Interview Intake.app` / `Interview Supervisor.app`.
- `create-dmg` / `hdiutil` → `.dmg`. Firma/notarizzazione opzionale (Developer ID).
- `pyrage` ha wheel precompilate (arm64 + x86_64) → bundling ok.

**Linux**
- PyInstaller onefile → AppImage (via `linuxdeploy`/`appimagetool`), alternativa `.deb`.
- `pyrage` wheel manylinux → bundling ok.

**CI**
- `.github/workflows/release.yml` con matrice `macos-latest` + `ubuntu-latest`.
- Build scripts in `packaging/` (`.spec` PyInstaller, ricetta AppImage, DMG).

Config e chiavi restano in `~/.config/interview-intake/` (XDG) su entrambe le
piattaforme — nessuna modifica necessaria.

## 7. Impatto su spec / schema

- `registry.json`: **schema invariato** (nessuna migrazione).
- `registration.json`: nuovo schema piccolo.
- `master.json`: schema di esempio già presente → formalizzato in `models.py`
  (o `master.py`) con validazione.
- Emenda spec §11/§15: il divieto di creare `registry.json` si applica alla sola
  Researcher App.

## 8. Test

- `tests/test_supervisor.py` — init, add/deactivate/remove researcher, backup.
- `tests/test_registration.py` — roundtrip file di registrazione.
- `tests/test_master.py` — masterfile set/show/export.
- **Test invariante**: `setup` della Researcher App non crea mai `registry.json`
  (anche con registry assente → errore).
- E2E CLI in modalità non interattiva.
- Smoke test dei binari impacchettati in CI.

## 9. File previsti

Nuovi:
- `src/interview_intake/supervisor.py`
- `src/interview_intake/supervisor_cli.py`
- `src/interview_intake/registration.py`
- `src/interview_intake/master.py`
- `src/interview_intake/wizard.py`
- `docs/implementation-plan.md` (questo file)
- `packaging/` + `.github/workflows/release.yml`

Modificati:
- `pyproject.toml` (entry point `interview-supervisor`, dipendenze)
- `src/interview_intake/cli.py` (wizard, output registration file)
- `src/interview_intake/gui.py` (Tk stdlib, file picker)
- `src/interview_intake/models.py` (master schema, se non separato)
- `README.md`, `examples/` (esempi aggiornati)

## 10. Fasi e stima

| Fase | Contenuto | Stima | Stato |
|---|---|---|---|
| 0 | Emenda spec, conferme | 0.5 gg | ✅ decisioni prese |
| 1 | Supervisor core + CLI (init, researcher, escrow) + QR | 2–3 gg | ✅ fatto |
| 2 | File di registrazione + wizard researcher | 1–2 gg | da fare |
| 3 | Masterfile + export Excel | 1–2 gg | da fare |
| 4 | GUI Tk stdlib per entrambi i ruoli | 2–3 gg | da fare |
| 5 | Packaging macOS/Linux + CI release | 3–5 gg | da fare |
| 6 | Docs, test hardening | 1–2 gg | in corso |
| | **Totale** | **~11–18 gg** | |

### Phase 1 — consegnato

- `supervisor.py`: `init_project`, `add_researcher`, `add/deactivate/activate/remove/list`,
  `ensure_escrow_key`, `escrow_info`, `backup_escrow` (key + QR pubblica/segreta),
  `verify_supervisor`; backup automatico `registry.json.bak.<ts>`.
- `supervisor_cli.py`: entry point `interview-supervisor` (`init`, `researcher`,
  `escrow show/backup`, `registry show`, `verify`).
- `registration.py`: documento di scambio `registration.json` (usato da
  `researcher add --from`).
- `qr.py`: QR ascii/SVG/PNG con fallback pulito se `qrcode` manca.
- `crypto.py`: `validate_recipient`, `read_identity`.
- Test: `test_qr.py`, `test_registration.py`, `test_supervisor.py`,
  `test_supervisor_cli.py` (26 nuovi test, suite totale 147).

## 11. Rischi / punti aperti

- **Firma/notarizzazione macOS**: senza Developer ID l'utente deve bypassare
  Gatekeeper al primo avvio. Da decidere se notarizzare.
- **QR code**: richiede dipendenza extra (`qrcode`); opzionale, non bloccante.
- **AppImage vs .deb**: AppImage è più self-contained; `.deb` più integrato.
- **Backward compat**: i registry creati a mano restano validi; nessuna rottura.
