#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root=$(mktemp -d)
trap 'rm -rf "$build_root"' EXIT HUP INT TERM
source_dir="$build_root/eitaas-linux-0.1.0"

mkdir -p "$source_dir"
git -c safe.directory="$project_root" -C "$project_root" archive HEAD | tar -x -C "$source_dir"
cp -a "$source_dir/packaging/debian" "$source_dir/debian"
cd "$source_dir"
dpkg-buildpackage --build=binary --no-sign
mkdir -p "$project_root/dist"
find "$build_root" -maxdepth 1 -type f \( -name '*.deb' -o -name '*.buildinfo' -o -name '*.changes' \) -exec cp {} "$project_root/dist/" \;
