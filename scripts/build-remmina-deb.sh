#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${EITAAS_REMMINA_DEB_BUILD_ROOT:-"$project_root/.build/eitaas-remmina-deb"}
source_root="$build_root/eitaas-remmina-1.4.43+eitaas0.8"

mkdir -p "$build_root/cache" "$project_root/dist"
rm -rf "$source_root"
"$project_root/scripts/prepare-remmina-deb-source.py" \
  --project-root "$project_root" --cache "$build_root/cache" --output "$source_root"

cd "$source_root"
dpkg-buildpackage --build=source,binary --unsigned-source --unsigned-changes --jobs=1
find "$build_root" -maxdepth 1 -type f \
  \( -name '*.deb' -o -name '*.ddeb' -o -name '*.dsc' -o -name '*.tar.xz' -o -name '*.buildinfo' \
     -o -name '*.changes' \) -exec cp {} "$project_root/dist/" \;
