#!/usr/bin/env bash
#
# Build the standalone Linux deliverables: one PyInstaller onedir bundle per
# role, optionally wrapped as an `.AppImage` and/or a `.deb`.
#
# Usage (from anywhere):
#   packaging/build_linux.sh [--appimage] [--deb] [--all]
#                            [--version X.Y.Z] [--dist-dir DIR]
#
# The PyInstaller specs (`packaging/*.spec`) are the single source of truth for
# what gets bundled; this script only orchestrates them and packages the result.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON="${PYTHON:-python3}"
VERSION=""
DIST_DIR="${ROOT}/dist"
BUILD_DIR="${ROOT}/build"
DESKTOP_DIR="${SCRIPT_DIR}/desktop"
ICONS_DIR="${SCRIPT_DIR}/icons"
MAKE_APPIMAGE=0
MAKE_DEB=0

usage() {
  cat <<'EOF'
Build Linux onedir bundles, .AppImage and .deb packages for the Interview apps.

Usage: packaging/build_linux.sh [options]

Options:
  --appimage          also build a .AppImage (needs `appimagetool` on PATH)
  --deb               also build a .deb package (needs `dpkg-deb`)
  --all               build both the .AppImage and the .deb
  --version X.Y.Z     version used in the package filenames
                      (default: the installed package __version__)
  --dist-dir DIR      output directory (default: <repo>/dist)
  -h, --help          show this help

Environment:
  PYTHON              interpreter to build with (default: python3)

Requires Linux, Python 3.11+, python3-tk and the build extras:
  pip install -e '.[pyrage,qr,packaging]'
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --appimage) MAKE_APPIMAGE=1 ;;
    --deb)      MAKE_DEB=1 ;;
    --all)      MAKE_APPIMAGE=1; MAKE_DEB=1 ;;
    --version)  VERSION="${2:-}"; [ -n "${VERSION}" ] || die "--version needs a value"; shift ;;
    --dist-dir) DIST_DIR="${2:-}"; [ -n "${DIST_DIR}" ] || die "--dist-dir needs a value"; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          die "unknown argument: $1 (try --help)" ;;
  esac
  shift
done

[ "$(uname -s)" = "Linux" ] || die "build_linux.sh must run on Linux (found $(uname -s))"
command -v "${PYTHON}" >/dev/null 2>&1 || die "python interpreter '${PYTHON}' not found (set PYTHON=...)"
"${PYTHON}" -m PyInstaller --version >/dev/null 2>&1 \
  || die "PyInstaller missing; run: ${PYTHON} -m pip install -e '.[pyrage,qr,packaging]'"
if [ "${MAKE_APPIMAGE}" -eq 1 ] && ! command -v appimagetool >/dev/null 2>&1; then
  die "--appimage requested but appimagetool is not on PATH"
fi
if [ "${MAKE_DEB}" -eq 1 ] && ! command -v dpkg-deb >/dev/null 2>&1; then
  die "--deb requested but dpkg-deb is not on PATH"
fi

if [ -z "${VERSION}" ]; then
  VERSION="$("${PYTHON}" -c 'import interview_intake; print(interview_intake.__version__)' 2>/dev/null || true)"
  VERSION="${VERSION:-0.0.0}"
fi

cd "${ROOT}"
rm -rf "${BUILD_DIR}" "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

# "spec basename : app display name : package slug" - the display name must
# match _spec_common.build(); the slug is the lowercase package name.
APPS=(
  "interview-intake:Interview Intake:interview-intake"
  "interview-supervisor:Interview Supervisor:interview-supervisor"
)

build_appimage() {
  local app_dir="$1" name="$2" slug="$3"
  local appdir="${BUILD_DIR}/AppDir-${slug}"
  local out="${DIST_DIR}/${name}-${VERSION}-$(uname -m).AppImage"
  rm -rf "${appdir}"
  mkdir -p "${appdir}/usr/bin"
  cp -a "${app_dir}" "${appdir}/usr/bin/${name}"
  cat > "${appdir}/AppRun" <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\${HERE}/usr/bin/${name}/${name}" "\$@"
EOF
  chmod +x "${appdir}/AppRun"
  cp "${DESKTOP_DIR}/${slug}.desktop" "${appdir}/${slug}.desktop"
  cp "${ICONS_DIR}/${slug}.png" "${appdir}/${slug}.png"
  cp "${ICONS_DIR}/${slug}.png" "${appdir}/.DirIcon"
  echo "==> appimagetool: $(basename "${out}")"
  ARCH="$(uname -m)" appimagetool --no-appstream "${appdir}" "${out}"
}

build_deb() {
  local app_dir="$1" name="$2" slug="$3"
  local arch pkgdir deb
  arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
  pkgdir="${BUILD_DIR}/deb-${slug}"
  deb="${DIST_DIR}/${slug}_${VERSION}_${arch}.deb"
  rm -rf "${pkgdir}"
  mkdir -p \
    "${pkgdir}/DEBIAN" \
    "${pkgdir}/usr/bin" \
    "${pkgdir}/usr/share/applications" \
    "${pkgdir}/usr/share/icons/hicolor/256x256/apps"
  cp -a "${app_dir}" "${pkgdir}/usr/bin/${name}"
  ln -sf "${name}/${name}" "${pkgdir}/usr/bin/${slug}-gui"
  ln -sf "${name}/${slug}" "${pkgdir}/usr/bin/${slug}"
  cp "${DESKTOP_DIR}/${slug}.desktop" "${pkgdir}/usr/share/applications/${slug}.desktop"
  cp "${ICONS_DIR}/${slug}.png" "${pkgdir}/usr/share/icons/hicolor/256x256/apps/${slug}.png"
  cat > "${pkgdir}/DEBIAN/control" <<EOF
Package: ${slug}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${arch}
Maintainer: Interview Intake contributors <noreply@example.com>
Depends: libc6
Description: ${name} desktop app.
 Ingests/interview tooling for the Interview Intake project. Ships a windowed
 GUI (${slug}-gui) and a console CLI (${slug}) in /usr/bin.
EOF
  echo "==> dpkg-deb: $(basename "${deb}")"
  dpkg-deb --build --root-owner-group "${pkgdir}" "${deb}"
}

built=()
for entry in "${APPS[@]}"; do
  spec="${entry%%:*}"
  rest="${entry#*:}"
  name="${rest%%:*}"
  slug="${rest#*:}"
  echo "==> PyInstaller: ${name}"
  "${PYTHON}" -m PyInstaller \
    --noconfirm --clean \
    --distpath "${DIST_DIR}" \
    --workpath "${BUILD_DIR}/${spec}" \
    "packaging/${spec}.spec"
  app_dir="${DIST_DIR}/${name}"
  [ -d "${app_dir}" ] || die "expected bundle not found: ${app_dir}"
  if [ "${MAKE_APPIMAGE}" -eq 1 ]; then
    build_appimage "${app_dir}" "${name}" "${slug}"
  fi
  if [ "${MAKE_DEB}" -eq 1 ]; then
    build_deb "${app_dir}" "${name}" "${slug}"
  fi
  built+=("${app_dir}")
done

echo
echo "==> Build complete (version ${VERSION}):"
ls -1 "${DIST_DIR}"
