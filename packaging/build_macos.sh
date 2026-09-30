#!/usr/bin/env bash
#
# Build the standalone macOS deliverables: one `.app` bundle per role, plus
# (by default) a `.dmg` disk image that contains the `.app`.
#
# Usage (from anywhere):
#   packaging/build_macos.sh [--app-only] [--version X.Y.Z] [--dist-dir DIR]
#
# The PyInstaller specs (`packaging/*.spec`) are the single source of truth for
# what gets bundled; this script only orchestrates them and wraps the result.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-python3}"
VERSION=""
DIST_DIR="${ROOT}/dist"
BUILD_DIR="${ROOT}/build"
MAKE_DMG=1

usage() {
  cat <<'EOF'
Build macOS .app bundles and .dmg images for the Interview apps.

Usage: packaging/build_macos.sh [options]

Options:
  --app-only          build the .app bundles but skip the .dmg images
  --version X.Y.Z     version used in the .dmg filenames
                      (default: the installed package __version__)
  --dist-dir DIR      output directory (default: <repo>/dist)
  -h, --help          show this help

Environment:
  PYTHON              interpreter to build with (default: python3)
  CODESIGN_IDENTITY   Developer ID identity passed to codesign (optional)
  NOTARY_PROFILE      notarytool keychain profile; enables notarization
                      + stapling when CODESIGN_IDENTITY is also set (optional)

Requires macOS, Python 3.11+, and the build extras:
  pip install -e '.[pyrage,qr,packaging]'
`create-dmg` is used when available and hdiutil otherwise.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --app-only) MAKE_DMG=0 ;;
    --version)  VERSION="${2:-}"; [ -n "${VERSION}" ] || die "--version needs a value"; shift ;;
    --dist-dir) DIST_DIR="${2:-}"; [ -n "${DIST_DIR}" ] || die "--dist-dir needs a value"; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done

[ "$(uname -s)" = "Darwin" ] || die "build_macos.sh must run on macOS (found $(uname -s))"
command -v "${PYTHON}" >/dev/null 2>&1 || die "python interpreter '${PYTHON}' not found (set PYTHON=...)"
"${PYTHON}" -m PyInstaller --version >/dev/null 2>&1 \
  || die "PyInstaller missing; run: ${PYTHON} -m pip install -e '.[pyrage,qr,packaging]'"

if [ -z "${VERSION}" ]; then
  VERSION="$("${PYTHON}" -c 'import interview_intake; print(interview_intake.__version__)' 2>/dev/null || true)"
  VERSION="${VERSION:-0.0.0}"
fi

cd "${ROOT}"
rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

# "spec basename : app display name" - the name must match _spec_common.build().
APPS=(
  "interview-intake:Interview Intake"
  "interview-supervisor:Interview Supervisor"
)

sign_app() {
  local app="$1"
  [ -n "${CODESIGN_IDENTITY:-}" ] || return 0
  echo "==> codesign: $(basename "${app}")"
  codesign --deep --force --options runtime --timestamp \
    --sign "${CODESIGN_IDENTITY}" "${app}"
  if [ -n "${NOTARY_PROFILE:-}" ]; then
    local zip="${BUILD_DIR}/$(basename "${app}").zip"
    echo "==> notarize + staple: $(basename "${app}")"
    /usr/bin/ditto -c -k --keepParent "${app}" "${zip}"
    xcrun notarytool submit "${zip}" --keychain-profile "${NOTARY_PROFILE}" --wait
    xcrun stapler staple "${app}"
  fi
}

make_dmg() {
  local app="$1"
  local base dmg
  base="$(basename "${app%.app}")"
  dmg="${DIST_DIR}/${base}-${VERSION}.dmg"
  rm -f "${dmg}"
  if command -v create-dmg >/dev/null 2>&1; then
    echo "==> create-dmg: $(basename "${dmg}")"
    if create-dmg \
      --volname "${base}" \
      --window-pos 200 120 \
      --window-size 660 400 \
      --icon-size 100 \
      --app-drop-link 480 185 \
      --hide-extension "${base}.app" \
      "${dmg}" "${app}"; then
      return 0
    fi
    echo "warning: create-dmg failed; falling back to hdiutil" >&2
    rm -f "${dmg}"
  fi
  echo "==> hdiutil: $(basename "${dmg}")"
  hdiutil create -volname "${base}" -srcfolder "${app}" -ov -format UDZO "${dmg}"
}

built_apps=()
for entry in "${APPS[@]}"; do
  spec="${entry%%:*}"
  name="${entry#*:}"
  echo "==> PyInstaller: ${name}"
  "${PYTHON}" -m PyInstaller \
    --noconfirm --clean \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}/${spec}" \
    "packaging/${spec}.spec"
  app="${DIST_DIR}/${name}.app"
  [ -d "${app}" ] || die "expected app bundle not found: ${app}"
  sign_app "${app}"
  built_apps+=("${app}")
done

if [ "${MAKE_DMG}" -eq 1 ]; then
  for app in "${built_apps[@]}"; do
    make_dmg "${app}"
  done
fi

echo
echo "==> Build complete (version ${VERSION}):"
ls -1 "${DIST_DIR}"
