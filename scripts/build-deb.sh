#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=$(mktemp -d)
trap 'rm -rf "$build_root"' EXIT HUP INT TERM
source_archive=${1:-}
version=$(sed -n 's/^version = "\([^"]*\)"$/\1/p' "$project_root/pyproject.toml")
source_dir="$build_root/eitaas-linux-$version"
orig_archive="$build_root/eitaas-linux_$version.orig.tar.gz"

if [ -n "$source_archive" ]; then
    cp "$source_archive" "$orig_archive"
else
    mkdir -p "$source_dir"
    git -c safe.directory="$project_root" -C "$project_root" archive HEAD | tar -x -C "$source_dir"
    tar -czf "$orig_archive" -C "$build_root" "eitaas-linux-$version"
fi
if [ ! -d "$source_dir" ]; then
    tar -xzf "$orig_archive" -C "$build_root"
fi
cp -a "$source_dir/packaging/debian" "$source_dir/debian"
cd "$source_dir"
dpkg-buildpackage --build=source --no-sign
dpkg-buildpackage --build=binary --no-sign
mkdir -p "$project_root/dist"
find "$build_root" -maxdepth 1 -type f \( \
    -name '*.deb' -o -name '*.dsc' -o -name '*.debian.tar.*' -o \
    -name '*.orig.tar.*' -o -name '*.buildinfo' -o -name '*.changes' \
\) -exec cp {} "$project_root/dist/" \;
