"""Command-line interface.

Subcommands:

* ``intake``  -- ingest an audio file (spec section 11)
* ``open``    -- list/decrypt an interview (spec section 12)
* ``config``  -- show/initialise researcher config (spec section 14)
* ``verify``  -- check registry + stored files
* ``keygen``  -- generate an age X25519 keypair
* ``setup``   -- first-run: create config and keys if missing
* ``registration`` -- show/export the registration request (public key)
* ``templates`` -- seed the shared project templates
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .config import (
    default_config_dir,
    default_config_path,
    key_path_for,
    load_config,
    save_config,
    validate_config,
    with_overrides,
)
from .crypto import (
    available_backends,
    generate_keypair,
    public_key_for_identity_file,
    write_identity_file,
)
from .errors import IntakeError, ValidationError
from .fs import ensure_private_dir, expand_path, wipe_file
from .id_grammar import validate_mnemonic, validate_researcher_id
from .intake import perform_intake, scan_audio_files
from .media import eject_path
from .models import Config
from .open_interview import list_interviews, open_interview
from .qr import QrUnavailableError, qr_available, render_ascii, write_qr
from .registration import RegistrationRequest, write_registration
from .templates import install_default_templates
from .verify import verify_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interview-intake",
        description="Ingest, encrypt and file interview audio under serial IDs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to config.json (default: ~/.config/interview-intake/config.json).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    intake = sub.add_parser("intake", help="Ingest an audio file.")
    intake.add_argument("source", nargs="?", help="Audio file or SD card directory.")
    intake.add_argument("-m", "--mnemonic", help="Three-letter mnemonic (BBB).")
    intake.add_argument("--project", help="Override project folder path.")
    intake.add_argument(
        "--backend", choices=["auto", "pyrage", "cli", "age-cli", "age"], default="auto"
    )
    intake.add_argument("-y", "--yes", action="store_true", help="Assume yes / non-interactive.")
    intake.add_argument("--wipe", action="store_true", help="Wipe the source file after success.")
    intake.add_argument("--eject", action="store_true", help="Eject the source volume after success.")
    intake.add_argument("--max-retries", type=int, default=5)
    intake.set_defaults(func=cmd_intake)

    open_cmd = sub.add_parser("open", help="List or decrypt an interview.")
    open_cmd.add_argument("interview_id", nargs="?", help="Interview ID to decrypt.")
    open_cmd.add_argument("--project", help="Override project folder path.")
    open_cmd.add_argument("-o", "--output", help="Output path (must be outside sync_root).")
    open_cmd.add_argument(
        "--backend", choices=["auto", "pyrage", "cli", "age-cli", "age"], default="auto"
    )
    open_cmd.add_argument("--no-open", action="store_true", help="Do not launch a player.")
    open_cmd.add_argument("--force", action="store_true", help="Overwrite an existing output.")
    open_cmd.add_argument("--list", action="store_true", help="Only list interviews.")
    open_cmd.set_defaults(func=cmd_open)

    config_cmd = sub.add_parser("config", help="Show or initialise config.")
    config_sub = config_cmd.add_subparsers(dest="config_command", required=True)
    config_cmd.set_defaults(func=cmd_config)
    config_show = config_sub.add_parser("show", help="Print the current config.")
    config_show.set_defaults(func=cmd_config)
    config_init = config_sub.add_parser("init", help="Write a new config.json.")
    config_init.add_argument("--researcher-id", required=True)
    config_init.add_argument("--project-path", required=True)
    config_init.add_argument("--sync-root", required=True)
    config_init.add_argument("--private-key-path")
    config_init.add_argument("--sync-wait-seconds", type=int, default=3)
    config_init.add_argument("--lock-stale-seconds", type=int, default=60)
    config_init.add_argument("--generate-key", action="store_true")
    config_init.add_argument("--install-templates", action="store_true")
    config_init.add_argument("--force", action="store_true")
    config_init.set_defaults(func=cmd_config)

    verify = sub.add_parser("verify", help="Verify registry + stored files.")
    verify.add_argument("--project", help="Override project folder path.")
    verify.set_defaults(func=cmd_verify)

    keygen = sub.add_parser("keygen", help="Generate an age X25519 keypair.")
    keygen.add_argument("--out", help="Directory for the identity file.")
    keygen.add_argument("--name", help="Key name (defaults to researcher ID).")
    keygen.add_argument("--force", action="store_true")
    keygen.set_defaults(func=cmd_keygen)

    setup = sub.add_parser(
        "setup", help="First run: create config and keys if they do not exist."
    )
    setup.add_argument("--researcher-id")
    setup.add_argument("--project-path")
    setup.add_argument("--sync-root")
    setup.add_argument("--private-key-path", help="Researcher identity file.")
    setup.add_argument("--keys-dir", help="Directory for generated keys.")
    setup.add_argument(
        "--create-escrow",
        action="store_true",
        help="Also create the supervisor/escrow key (supervisor machine only).",
    )
    setup.add_argument("--escrow-key-path", help="Path for the escrow identity file.")
    setup.add_argument("--sync-wait-seconds", type=int, default=3)
    setup.add_argument("--lock-stale-seconds", type=int, default=60)
    setup.add_argument("--install-templates", action="store_true")
    setup.add_argument(
        "--display-name",
        help="Display name for the registration request (default: Researcher <ID>).",
    )
    setup.add_argument(
        "--no-registration",
        action="store_true",
        help="Do not write the registration request file.",
    )
    setup.add_argument("--qr", action="store_true", help="Print the public key as a terminal QR.")
    setup.add_argument("-y", "--yes", action="store_true", help="Non-interactive.")
    setup.add_argument(
        "--force", action="store_true", help="Regenerate keys even if present."
    )
    setup.set_defaults(func=cmd_setup)

    registration = sub.add_parser(
        "registration", help="Show or export your registration request (public key)."
    )
    registration.add_argument("--out", help="Write registration.json to this path.")
    registration.add_argument("--display-name", help="Display name to embed in the request.")
    registration.add_argument("--qr", action="store_true", help="Print the public key as a terminal QR.")
    registration.add_argument("--qr-out", help="Write the public key QR to a file (.svg/.png/.txt).")
    registration.add_argument(
        "--format", dest="fmt", choices=["svg", "png", "txt"], help="QR file format."
    )
    registration.set_defaults(func=cmd_registration)

    templates = sub.add_parser("templates", help="Seed shared project templates.")
    templates.add_argument("--project", help="Override project folder path.")
    templates.add_argument("--overwrite", action="store_true")
    templates.set_defaults(func=cmd_templates)

    return parser


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _is_interactive() -> bool:
    return sys.stdin.isatty()


def _load_config(args) -> Config:
    config, _ = load_config(getattr(args, "config", None))
    return config


def _project_for(config: Config, override: Optional[str]) -> Config:
    if not override:
        return config
    return with_overrides(config, project_path=override)


def _prompt_mnemonic(initial: Optional[str]) -> str:
    value = initial
    while True:
        if value is None:
            value = input("Mnemonic (3 letters, BBB): ")
        try:
            return validate_mnemonic(value)
        except ValidationError as exc:
            print(f"error: {exc}", file=sys.stderr)
            if not _is_interactive():
                raise
            value = None


def _select_source(source: Optional[str], assume_yes: bool) -> Path:
    if source is None:
        if not _is_interactive():
            raise IntakeError("No source given and not running interactively.")
        source = input("Path to audio file or SD card directory: ").strip()
    candidates = scan_audio_files(source)
    if not candidates:
        raise IntakeError(f"No supported audio files found under {source!r}.")
    if len(candidates) == 1:
        return candidates[0]
    if assume_yes or not _is_interactive():
        raise IntakeError(
            "Multiple audio files found; pass an explicit file path. Candidates: "
            + ", ".join(str(c) for c in candidates)
        )
    print("Multiple audio files found:")
    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}. {candidate}")
    while True:
        choice = input(f"Select [1-{len(candidates)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            return candidates[int(choice) - 1]
        print("Invalid selection.")


def _select_interview(ids: list[str]) -> Optional[str]:
    """Prompt the user to pick an interview from a list (interactive only)."""
    print("Interviews:")
    for index, interview_id in enumerate(ids, start=1):
        print(f"  {index}. {interview_id}")
    while True:
        choice = input(f"Select [1-{len(ids)}] (Enter to cancel): ").strip()
        if not choice:
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(ids):
            return ids[int(choice) - 1]
        print("Invalid selection.")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    if not _is_interactive():
        raise IntakeError(f"Confirmation required: {prompt} (use --yes).")
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")


def _get_value(value, prompt: str, *, non_interactive: bool) -> str:
    """Return a supplied value, or prompt for it when interactive."""
    if value:
        return value
    if non_interactive or not _is_interactive():
        raise IntakeError(f"Missing required value: {prompt}")
    entered = input(f"{prompt}: ").strip()
    if not entered:
        raise IntakeError(f"Missing required value: {prompt}")
    return entered


def _ensure_key(key_path: Path, *, force: bool, label: str) -> tuple[bool, str]:
    """Create a key only if missing (or ``force``) and return its public key.

    Returns ``(created, public_key)``.  Existing keys are never overwritten
    unless ``force`` is set, so first-run setup is safe to re-run.
    """
    if key_path.exists() and not force:
        recipient = public_key_for_identity_file(key_path)
        print(f"Reusing existing {label}: {key_path}")
        print(f"Public key: {recipient}")
        return False, recipient
    identity, recipient = generate_keypair()
    ensure_private_dir(key_path.parent)
    write_identity_file(identity, key_path)
    print(f"Generated {label}: {key_path}")
    print(f"Public key: {recipient}")
    return True, recipient


def _registration_path_for(config: Config, config_path: Path) -> Path:
    """Registration request lives next to the config (not in the shared tree)."""
    return expand_path(config_path).parent / "registration" / f"{config.researcher_id}.pub.json"


def _display_name_for(config: Config, override: Optional[str] = None) -> str:
    """Human-readable name for the registration request."""
    if override and override.strip():
        return override.strip()
    return f"Researcher {config.researcher_id.upper()}"


def _print_terminal_qr(text: str) -> None:
    if not qr_available():
        raise QrUnavailableError(
            "QR rendering needs the optional 'qrcode' package. "
            "Install it with: pip install 'interview-intake[qr]'"
        )
    sys.stdout.write(render_ascii(text))


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_intake(args) -> int:
    config = _load_config(args)
    config = _project_for(config, args.project)
    source = _select_source(args.source, args.yes)
    mnemonic = _prompt_mnemonic(args.mnemonic)

    print(f"Researcher : {config.researcher_id}")
    print(f"Source     : {source}")
    print(f"Mnemonic   : {mnemonic}")
    print(f"Project    : {expand_path(config.project_path)}")
    if not _confirm("Proceed with intake?", args.yes):
        print("Aborted.")
        return 1

    result = perform_intake(
        expand_path(config.project_path),
        config,
        source,
        mnemonic,
        max_retries=args.max_retries,
        backend=None if args.backend == "auto" else _backend_from_name(args.backend),
    )

    print(f"\nCreated interview {result.interview_id}")
    print(f"  folder     : {result.interview_dir}")
    print(f"  audio      : {result.audio_path}")
    print(f"  meta       : {result.meta_path}")
    print(f"  transcript : {result.transcript_path}")
    print(f"  note       : {result.note_path}")
    if not result.registry_confirmed:
        print("WARNING: registry.json did not list the new interview; re-check sync.", file=sys.stderr)

    if args.wipe:
        if _confirm(f"Wipe source file {source}?", args.yes):
            wipe_file(source)
            print(f"Wiped {source}")
    if args.eject:
        try:
            print(eject_path(source))
        except IntakeError as exc:
            print(f"warning: {exc}", file=sys.stderr)
    return 0 if result.registry_confirmed else 1


def _backend_from_name(name: str):
    from .crypto import select_backend

    if name in ("cli", "age-cli", "age"):
        return select_backend("cli")
    return select_backend(name)


def cmd_open(args) -> int:
    config = _load_config(args)
    config = _project_for(config, args.project)
    project = expand_path(config.project_path)

    if args.list or not args.interview_id:
        ids = list_interviews(project)
        if not ids:
            print("No interviews found.")
            return 0
        print(f"Interviews in {project}:")
        for interview_id in ids:
            print(f"  {interview_id}")
        if args.list or not _is_interactive():
            return 0
        selected = _select_interview(ids)
        if selected is None:
            return 0
        args.interview_id = selected

    path = open_interview(
        project,
        config,
        args.interview_id,
        output=expand_path(args.output) if args.output else None,
        backend=None if args.backend == "auto" else _backend_from_name(args.backend),
        open_file=not args.no_open,
        force=args.force,
    )
    print(f"Decrypted to {path}")
    print("This decrypted file is outside Nextcloud. Delete it when done.")
    return 0


def cmd_config(args) -> int:
    sub = getattr(args, "config_command", None)
    if sub in (None, "show"):
        try:
            config, path = load_config(args.config)
        except IntakeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print(f"Config path would be: {default_config_path()}")
            print(f"Available age backends: {available_backends() or 'none'}")
            return 1
        print(f"# {path}")
        print(json.dumps(config.to_dict(), indent=2))
        return 0

    if sub == "init":
        return _config_init(args)
    print(f"Unknown config command: {sub}", file=sys.stderr)
    return 2


def _config_init(args) -> int:
    config_path = expand_path(args.config) if args.config else default_config_path()
    if config_path.exists() and not args.force:
        print(f"error: {config_path} already exists (use --force).", file=sys.stderr)
        return 1

    researcher_id = validate_researcher_id(args.researcher_id)
    key_path = (
        expand_path(args.private_key_path)
        if args.private_key_path
        else default_config_dir() / "keys" / f"{researcher_id}.key"
    )

    if args.generate_key:
        _ensure_key(key_path, force=args.force, label="researcher key")

    config = Config(
        researcher_id=researcher_id,
        private_key_path=str(key_path),
        project_path=str(expand_path(args.project_path)),
        sync_root=str(expand_path(args.sync_root)),
        sync_wait_seconds=args.sync_wait_seconds,
        lock_stale_seconds=args.lock_stale_seconds,
    )
    try:
        validate_config(config)
    except IntakeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    save_config(config, config_path)
    print(f"Wrote {config_path}")

    if args.install_templates:
        written = install_default_templates(expand_path(args.project_path))
        if written:
            print("Installed templates: " + ", ".join(str(p) for p in written))
        else:
            print("Templates already present.")
    return 0


def cmd_verify(args) -> int:
    config = _load_config(args)
    config = _project_for(config, args.project)
    report = verify_project(expand_path(config.project_path))
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    print(f"Checked {report.checked} issued interview(s): {'OK' if report.ok else 'FAILED'}")
    return 0 if report.ok else 1


def cmd_keygen(args) -> int:
    name = args.name
    if name is None:
        try:
            config, _ = load_config(args.config)
            name = config.researcher_id
        except IntakeError:
            name = "researcher"
    out_dir = expand_path(args.out) if args.out else default_config_dir() / "keys"
    ensure_private_dir(out_dir)
    key_path = out_dir / f"{name}.key"
    _ensure_key(key_path, force=args.force, label="key")
    print("Give the public key to the supervisor to add to registry.json.")
    return 0


def _registry_snippet(config: Config, researcher_pub: str, supervisor_pub: Optional[str]) -> str:
    snippet = {
        "schema_version": 1,
        "researchers": {
            config.researcher_id: {
                "display_name": f"Researcher {config.researcher_id.upper()}",
                "age_public_key": researcher_pub or "<researcher public key>",
                "active": True,
            }
        },
        "supervisor": {
            "age_public_key": supervisor_pub or "<supervisor public key>"
        },
        "last_serial": 0,
        "issued": [],
    }
    return json.dumps(snippet, indent=2)


def cmd_setup(args) -> int:
    """First-run bootstrap: config + keys if missing. Never writes registry.json."""
    config_path = expand_path(args.config) if args.config else default_config_path()
    non_interactive = args.yes or not _is_interactive()

    if config_path.exists():
        config, _ = load_config(config_path)
        print(f"Using existing config: {config_path}")
    else:
        researcher_id = validate_researcher_id(
            _get_value(args.researcher_id, "Researcher ID (3 letters)", non_interactive=non_interactive)
        )
        project_path = expand_path(
            _get_value(args.project_path, "Project folder path", non_interactive=non_interactive)
        )
        sync_root = expand_path(
            _get_value(args.sync_root, "Sync root (must contain the project)", non_interactive=non_interactive)
        )
        keys_dir = expand_path(args.keys_dir) if args.keys_dir else default_config_dir() / "keys"
        key_path = (
            expand_path(args.private_key_path)
            if args.private_key_path
            else keys_dir / f"{researcher_id}.key"
        )
        config = Config(
            researcher_id=researcher_id,
            private_key_path=str(key_path),
            project_path=str(project_path),
            sync_root=str(sync_root),
            sync_wait_seconds=args.sync_wait_seconds,
            lock_stale_seconds=args.lock_stale_seconds,
        )
        validate_config(config)
        save_config(config, config_path)
        print(f"Wrote {config_path}")

    researcher_key = expand_path(config.private_key_path)
    _, researcher_pub = _ensure_key(
        researcher_key, force=args.force, label="researcher key"
    )

    supervisor_pub: Optional[str] = None
    create_escrow = args.create_escrow
    if not create_escrow and not non_interactive:
        create_escrow = _confirm(
            "Create a supervisor/escrow key on this machine? (supervisor only)",
            assume_yes=False,
        )
    if create_escrow:
        escrow_path = (
            expand_path(args.escrow_key_path)
            if args.escrow_key_path
            else researcher_key.parent / "supervisor.key"
        )
        _, supervisor_pub = _ensure_key(
            escrow_path, force=args.force, label="supervisor/escrow key"
        )
        print("NOTE: the escrow key must live only on the supervisor's machine.")

    if args.install_templates:
        written = install_default_templates(expand_path(config.project_path))
        print(
            "Installed templates: " + ", ".join(str(p) for p in written)
            if written
            else "Templates already present."
        )

    registration_path: Optional[Path] = None
    if not getattr(args, "no_registration", False):
        registration_path = _registration_path_for(config, config_path)
        request = RegistrationRequest.create_from_public_key(
            config.researcher_id,
            _display_name_for(config, getattr(args, "display_name", None)),
            researcher_pub,
        )
        write_registration(registration_path, request)
        print(f"Registration request: {registration_path}")
        if args.qr:
            _print_terminal_qr(researcher_pub)

    print("\n== registry.json ==")
    print(_registry_snippet(config, researcher_pub, supervisor_pub))
    target = registration_path if registration_path else "<researcher>.pub.json"
    print(
        "\nThe app never creates or edits registry.json (spec section 15).\n"
        "Send your registration request to the supervisor, who registers it with:\n"
        f"  interview-supervisor researcher add --from {target}"
    )
    if supervisor_pub is None:
        print(
            "If you are not the supervisor, do not create the escrow key; the "
            "supervisor provisions registry.json."
        )
    return 0


def cmd_registration(args) -> int:
    config, _ = load_config(getattr(args, "config", None))
    key_path = key_path_for(config)
    public_key = public_key_for_identity_file(key_path)
    request = RegistrationRequest.create_from_public_key(
        config.researcher_id,
        _display_name_for(config, getattr(args, "display_name", None)),
        public_key,
    )
    if args.out:
        path = write_registration(expand_path(args.out), request)
        print(f"Wrote {path}")
    else:
        print(json.dumps(request.to_dict(), indent=2))
    if args.qr:
        _print_terminal_qr(public_key)
    if args.qr_out:
        path = write_qr(public_key, expand_path(args.qr_out), fmt=args.fmt)
        print(f"Wrote QR: {path}")
    return 0


def cmd_templates(args) -> int:
    project = None
    if args.project:
        project = expand_path(args.project)
    else:
        config = _load_config(args)
        project = expand_path(config.project_path)
    written = install_default_templates(project, overwrite=args.overwrite)
    if written:
        for path in written:
            print(f"Wrote {path}")
    else:
        print("Templates already present (use --overwrite to replace).")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    try:
        return func(args)
    except IntakeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
