#!/bin/sh
# Build the combined eitaas-linux RPM (bundled Remmina/FreeRDP client, CLI,
# and helper GUI) from the canonical source tarball and the pins in
# packaging/remmina/sources.json.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=${EITAAS_BUILD_ROOT:-"$project_root/.build/eitaas-bundle"}
cache="$build_root/cache"
source_archive=${1:-}
version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project_root/pyproject.toml")
source_name="eitaas-linux-$version"

if [ -n "${EITAAS_RPM_TOPDIR:-}" ]; then
    topdir=$EITAAS_RPM_TOPDIR
else
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT HUP INT TERM
    topdir="$scratch/rpmbuild"
fi

mkdir -p "$topdir/BUILD" "$topdir/BUILDROOT" "$topdir/RPMS" "$topdir/SOURCES" \
    "$topdir/SPECS" "$topdir/SRPMS" "$cache"
if [ -n "$source_archive" ]; then
    cp "$source_archive" "$topdir/SOURCES/v$version.tar.gz"
else
    git -c safe.directory="$project_root" -C "$project_root" \
        archive --prefix="$source_name/" HEAD | gzip -n > "$topdir/SOURCES/v$version.tar.gz"
fi

# Both pinned upstream archives are verified against sources.json and land in
# SOURCES under the file names the spec's Source1/Source2 URLs declare, so the
# source RPM carries the complete corresponding source.
"$project_root/scripts/prepare-bundle-source.py" --project-root "$project_root" \
    fetch --cache "$cache" --destination "$topdir/SOURCES"

cp "$project_root/packaging/rpm/eitaas-linux.spec" "$topdir/SPECS/"
rpmbuild --define "_topdir $topdir" --define "_smp_build_ncpus 1" \
    -ba "$topdir/SPECS/eitaas-linux.spec"
mkdir -p "$project_root/dist"
find "$topdir/RPMS" "$topdir/SRPMS" -type f -name '*.rpm' -exec cp {} "$project_root/dist/" \;
