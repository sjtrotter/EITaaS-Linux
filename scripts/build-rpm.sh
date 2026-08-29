#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=$(mktemp -d)
trap 'rm -rf "$build_root"' EXIT HUP INT TERM
topdir="$build_root/rpmbuild"
source_name="EITaaS-Linux-0.1.0"

mkdir -p "$topdir/BUILD" "$topdir/BUILDROOT" "$topdir/RPMS" "$topdir/SOURCES" "$topdir/SPECS" "$topdir/SRPMS"
git -C "$project_root" archive --prefix="$source_name/" HEAD | gzip -n > "$topdir/SOURCES/v0.1.0.tar.gz"
cp "$project_root/packaging/rpm/eitaas-linux.spec" "$topdir/SPECS/"
rpmbuild --define "_topdir $topdir" -ba "$topdir/SPECS/eitaas-linux.spec"
mkdir -p "$project_root/dist"
find "$topdir/RPMS" "$topdir/SRPMS" -type f -name '*.rpm' -exec cp {} "$project_root/dist/" \;
