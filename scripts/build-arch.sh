#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
package_dir="$project_root/packaging/arch"

if [ "$(id -u)" -eq 0 ]; then
    echo 'makepkg must run as an unprivileged user' >&2
    exit 1
fi

cd "$package_dir"
makepkg --cleanbuild --force
mkdir -p "$project_root/dist"
find . -maxdepth 1 -type f -name '*.pkg.tar.*' -exec cp {} "$project_root/dist/" \;
