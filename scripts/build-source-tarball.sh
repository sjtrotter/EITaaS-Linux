#!/bin/sh
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_ref=${1:-HEAD}
output_dir=${2:-"$project_root/dist"}

version=$(
    git -c safe.directory="$project_root" -C "$project_root" \
        show "$source_ref:pyproject.toml" |
        sed -n 's/^version = "\([^"]*\)"$/\1/p'
)

if [ -z "$version" ]; then
    echo "could not determine project version at $source_ref" >&2
    exit 1
fi

archive_name="eitaas-linux-$version.tar.gz"
mkdir -p "$output_dir"

git -c safe.directory="$project_root" -C "$project_root" \
    archive --format=tar --prefix="eitaas-linux-$version/" "$source_ref" |
    gzip -n > "$output_dir/$archive_name"

printf '%s\n' "$output_dir/$archive_name"
