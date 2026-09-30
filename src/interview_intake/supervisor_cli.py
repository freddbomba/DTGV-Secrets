"""Command-line interface for the Supervisor App.

Entry point: ``interview-supervisor``.  The Supervisor App owns ``registry.json``
(create + manage); this CLI is a thin layer over :mod:`interview_intake.supervisor`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .crypto import public_key_for_identity_file, validate_recipient
from .errors import IntakeError, ValidationError
from .fs import expand_path
from .qr import QrUnavailableError, qr_available, render_ascii, write_qr
from .registration import read_registration
from .supervisor import (
    add_researcher,
    add_researcher_from_registration,
    backup_escrow,
    default_escrow_key_path,
    escrow_info,
    init_project,
    list_researchers,
    remove_researcher,
    researcher_public_key,
    set_researcher_active,
    verify_supervisor,
)


def _common(parent: Optional[list] = None) -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, parents=parent or [])
    common.add_argument(
        "--project",
        "-p",
        metavar="PATH",
        help="Shared project folder containing registry.json.",
    )
    return common


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="interview-supervisor",
        description="Provision and manage an interview-intake project (supervisor).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # init --------------------------------------------------------------------
    init = sub.add_parser(
        "init",
        help="Create project layout, escrow key, registry.json.",
        parents=[_common()],
    )
    init.add_argument("--escrow-key", help="Path for the escrow identity file.")
    init.add_argument("--no-escrow", action="store_true", help="Do not create an escrow key.")
    init.add_argument("--no-templates", action="store_true", help="Do not seed templates.")
    init.add_argument(
        "--force",
        action="store_true",
        help="Regenerate the escrow key and rewrite registry.json (DESTRUCTIVE).",
    )
    init.set_defaults(func=cmd_init)

    # researcher --------------------------------------------------------------
    researcher = sub.add_parser("researcher", help="Manage registered researchers.")
    rsub = researcher.add_subparsers(dest="researcher_command", required=True)

    add = rsub.add_parser("add", help="Register a researcher.", parents=[_common()])
    add.add_argument("researcher_id", nargs="?", help="3-letter researcher ID.")
    add.add_argument("--name", help="Display name.")
    key_group = add.add_mutually_exclusive_group()
    key_group.add_argument("--key", help="Age public key (age1...).")
    key_group.add_argument("--key-file", help="Identity file to derive the public key from.")
    key_group.add_argument("--from", dest="from_file", help="registration.json to import.")
    add.set_defaults(func=cmd_researcher_add)

    deactivate = rsub.add_parser("deactivate", help="Mark a researcher inactive.", parents=[_common()])
    deactivate.add_argument("researcher_id")
    deactivate.set_defaults(func=lambda a: _set_active(a, False))

    activate = rsub.add_parser("activate", help="Mark a researcher active.", parents=[_common()])
    activate.add_argument("researcher_id")
    activate.set_defaults(func=lambda a: _set_active(a, True))

    remove = rsub.add_parser("remove", help="Remove a researcher.", parents=[_common()])
    remove.add_argument("researcher_id")
    remove.add_argument("--force", action="store_true", help="Allow removal with issued interviews.")
    remove.set_defaults(func=cmd_researcher_remove)

    listing = rsub.add_parser("list", help="List registered researchers.", parents=[_common()])
    listing.set_defaults(func=cmd_researcher_list)

    qr = rsub.add_parser("qr", help="Show a researcher public key as a QR code.", parents=[_common()])
    qr.add_argument("researcher_id")
    qr.add_argument("--out", help="Write the QR to a file (.svg/.png/.txt) instead of stdout.")
    qr.add_argument("--format", dest="fmt", choices=["svg", "png", "txt"], help="QR output format.")
    qr.set_defaults(func=cmd_researcher_qr)

    # escrow ------------------------------------------------------------------
    escrow = sub.add_parser("escrow", help="Manage the supervisor/escrow key.")
    esub = escrow.add_subparsers(dest="escrow_command", required=True)

    show = esub.add_parser("show", help="Show the escrow public key.")
    show.add_argument("--escrow-key", help="Escrow identity file (default ~/.config/...).")
    show.add_argument("--qr", action="store_true", help="Also print the public key as a terminal QR.")
    show.set_defaults(func=cmd_escrow_show)

    backup = esub.add_parser("backup", help="Write a portable backup (key + QR).")
    backup.add_argument("--escrow-key", help="Escrow identity file.")
    backup.add_argument("--out", help="Output directory (default: alongside the key, in backup/).")
    backup.add_argument("--no-secret-qr", action="store_true", help="Skip the SECRET key QR.")
    backup.add_argument("--format", dest="fmt", choices=["svg", "png"], default="svg")
    backup.set_defaults(func=cmd_escrow_backup)

    # registry + verify -------------------------------------------------------
    show_reg = sub.add_parser("registry", help="Registry utilities.")
    regsub = show_reg.add_subparsers(dest="registry_command", required=True)
    reg_show = regsub.add_parser("show", help="Print registry.json.", parents=[_common()])
    reg_show.set_defaults(func=cmd_registry_show)

    verify = sub.add_parser("verify", help="Verify project + registry consistency.", parents=[_common()])
    verify.set_defaults(func=cmd_verify)

    return parser


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_init(args) -> int:
    result = init_project(
        args.project,
        escrow_key_path=args.escrow_key,
        create_escrow=not args.no_escrow,
        install_templates=not args.no_templates,
        force=args.force,
    )
    print(f"Project : {result.project_path}")
    state = "created" if result.created_registry else "kept"
    print(f"Registry: {result.registry_file} ({state})")
    if result.escrow_key_path is not None:
        key_state = "created" if result.escrow_key_created else "existing"
        print(f"Escrow  : {result.escrow_key_path} ({key_state})")
    if result.supervisor_public_key:
        print(f"Escrow public key: {result.supervisor_public_key}")
    for path in result.templates_written:
        print(f"Template: {path}")
    return 0


def _resolve_key(args) -> tuple[str, str, str]:
    """Return ``(researcher_id, display_name, recipient)`` from CLI arguments."""
    if getattr(args, "from_file", None):
        request = read_registration(args.from_file)
        if args.researcher_id and args.researcher_id != request.researcher_id:
            raise ValidationError(
                f"--researcher_id {args.researcher_id!r} does not match "
                f"registration {request.researcher_id!r}."
            )
        if args.key or args.key_file:
            raise ValidationError("--from cannot be combined with --key/--key-file.")
        return (
            args.researcher_id or request.researcher_id,
            args.name or request.display_name,
            request.age_public_key,
        )
    if not args.researcher_id:
        raise ValidationError("A researcher ID is required (or use --from FILE).")
    if not args.name:
        raise ValidationError("--name is required when not importing a registration file.")
    if args.key_file:
        recipient = public_key_for_identity_file(expand_path(args.key_file))
    elif args.key:
        recipient = args.key
    else:
        raise ValidationError("Provide a public key with --key, --key-file or --from.")
    return args.researcher_id, args.name, recipient


def cmd_researcher_add(args) -> int:
    researcher_id, name, recipient = _resolve_key(args)
    entry = add_researcher(args.project, researcher_id, name, recipient)
    print(f"Registered {entry.display_name or researcher_id} <{researcher_id}>")
    print(f"Public key: {entry.age_public_key}")
    print(f"Active    : {'yes' if entry.active else 'no'}")
    return 0


def _set_active(args, active: bool) -> int:
    entry = set_researcher_active(args.project, args.researcher_id, active)
    print(f"{'Activated' if active else 'Deactivated'} {args.researcher_id}.")
    return 0


def cmd_researcher_remove(args) -> int:
    issued = remove_researcher(args.project, args.researcher_id, force=args.force)
    if issued:
        print(f"Removed {args.researcher_id} (had {issued} issued interview(s)).")
    else:
        print(f"Removed {args.researcher_id}.")
    return 0


def cmd_researcher_list(args) -> int:
    rows = list_researchers(args.project)
    if not rows:
        print("No researchers registered.")
        return 0
    width = max(len(r.researcher_id) for r in rows)
    for row in rows:
        status = "active" if row.active else "inactive"
        print(
            f"{row.researcher_id:<{width}}  {row.display_name:<28}  "
            f"{status:<8}  {row.issued:>4} interview(s)"
        )
    return 0


def cmd_researcher_qr(args) -> int:
    recipient = researcher_public_key(args.project, args.researcher_id)
    return _print_or_write_qr(recipient, args.out, args.fmt)


def cmd_escrow_show(args) -> int:
    info = escrow_info(args.escrow_key)
    print(f"Escrow key  : {info.key_path}")
    print(f"Public key  : {info.public_key}")
    if args.qr:
        if not qr_available():
            raise QrUnavailableError(
                "QR rendering needs 'qrcode'. Install it with: pip install 'interview-intake[qr]'"
            )
        print()
        sys.stdout.write(render_ascii(info.public_key))
    return 0


def cmd_escrow_backup(args) -> int:
    result = backup_escrow(
        args.escrow_key,
        args.out,
        include_secret_qr=not args.no_secret_qr,
        qr_format=args.fmt,
    )
    print(f"Backup written to: {result.directory}")
    print(f"Private key copy : {result.key_copy}")
    if result.public_qr:
        print(f"Public key QR    : {result.public_qr}")
    if result.secret_qr:
        print(f"SECRET key QR    : {result.secret_qr}  (handle as a secret!)")
    if not qr_available():
        print("note: install 'qrcode' to also produce QR images (pip install '.[qr]').")
    print("Store a copy offline. Never keep the escrow key on researcher machines.")
    return 0


def cmd_registry_show(args) -> int:
    import json

    from .registry import load_registry

    registry = load_registry(args.project)
    print(json.dumps(registry.to_dict(), indent=2))
    return 0


def cmd_verify(args) -> int:
    report = verify_supervisor(args.project)
    for warning in report.base.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in report.base.errors:
        print(f"error: {error}", file=sys.stderr)
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    print(f"Checked {report.base.checked} issued interview(s): {'OK' if report.ok else 'FAILED'}")
    return 0 if report.ok else 1


def _print_or_write_qr(text: str, out: Optional[str], fmt: Optional[str]) -> int:
    if out:
        path = write_qr(text, expand_path(out), fmt=fmt)
        print(f"Wrote QR: {path}")
        return 0
    if not qr_available():
        raise QrUnavailableError(
            "QR rendering needs 'qrcode'. Install it with: pip install 'interview-intake[qr]'"
        )
    sys.stdout.write(render_ascii(text))
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
