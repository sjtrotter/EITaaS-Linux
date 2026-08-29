#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=$(mktemp -d)
trap 'rm -rf "$build_root"' EXIT HUP INT TERM
topdir="$build_root/rpmbuild"
source_archive=${1:-}
version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project_root/pyproject.toml")
source_name="eitaas-linux-$version"

mkdir -p "$topdir/BUILD" "$topdir/BUILDROOT" "$topdir/RPMS" "$topdir/SOURCES" "$topdir/SPECS" "$topdir/SRPMS"
if [ -n "$source_archive" ]; then
    cp "$source_archive" "$topdir/SOURCES/v$version.tar.gz"
else
    git -c safe.directory="$project_root" -C "$project_root" \
        archive --prefix="$source_name/" HEAD | gzip -n > "$topdir/SOURCES/v$version.tar.gz"
fi
cp "$project_root/packaging/rpm/eitaas-linux.spec" "$topdir/SPECS/"
rpmbuild --define "_topdir $topdir" -ba "$topdir/SPECS/eitaas-linux.spec"
mkdir -p "$project_root/dist"
find "$topdir/RPMS" "$topdir/SRPMS" -type f -name '*.rpm' -exec cp {} "$project_root/dist/" \;
