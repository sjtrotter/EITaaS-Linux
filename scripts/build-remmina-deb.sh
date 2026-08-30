#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${EITAAS_REMMINA_DEB_BUILD_ROOT:-"$project_root/.build/eitaas-remmina-deb"}

# packaging/remmina/debian/changelog is the single source of truth for the
# Debian version; dpkg-parsechangelog ships with the dpkg-dev that
# dpkg-buildpackage below already requires.
version=$(dpkg-parsechangelog \
  -l "$project_root/packaging/remmina/debian/changelog" -S Version)
source_root="$build_root/eitaas-remmina-$version"

mkdir -p "$build_root/cache" "$project_root/dist"
rm -rf "$source_root"
"$project_root/scripts/prepare-remmina-deb-source.py" \
  --project-root "$project_root" --cache "$build_root/cache" --output "$source_root"

cd "$source_root"
dpkg-buildpackage --build=source,binary --unsigned-source --unsigned-changes --jobs=1
find "$build_root" -maxdepth 1 -type f \
  \( -name '*.deb' -o -name '*.ddeb' -o -name '*.dsc' -o -name '*.tar.xz' -o -name '*.buildinfo' \
     -o -name '*.changes' \) -exec cp {} "$project_root/dist/" \;
