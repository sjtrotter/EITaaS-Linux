#!/bin/sh
# Build the combined eitaas-linux DEB and its native source package. The
# source tree carries the repository sources plus both verified upstream
# archives with the ordered patch series from packaging/remmina/sources.json
# already applied, so the source package is complete corresponding source.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${EITAAS_BUILD_ROOT:-"$project_root/.build/eitaas-bundle"}
cache="$build_root/cache"
source_archive=${1:-}

# debian/changelog is the single source of truth for the Debian version.
# Debian file names carry no epoch, so drop one if the changelog gains it.
version=$(dpkg-parsechangelog -l "$project_root/packaging/debian/changelog" -S Version)
version=${version#*:}
source_root="$build_root/eitaas-linux-$version"

mkdir -p "$cache" "$project_root/dist"
rm -rf "$source_root"
if [ -n "$source_archive" ]; then
    "$project_root/scripts/prepare-bundle-source.py" --project-root "$project_root" \
        tree --cache "$cache" --output "$source_root" --debian \
        --source-archive "$source_archive"
else
    "$project_root/scripts/prepare-bundle-source.py" --project-root "$project_root" \
        tree --cache "$cache" --output "$source_root" --debian
fi

cd "$source_root"
dpkg-buildpackage --build=source,binary --unsigned-source --unsigned-changes --jobs=1
find "$build_root" -maxdepth 1 -type f \( \
    -name '*.deb' -o -name '*.ddeb' -o -name '*.dsc' -o -name '*.tar.xz' -o \
    -name '*.buildinfo' -o -name '*.changes' \
\) -exec cp {} "$project_root/dist/" \;
