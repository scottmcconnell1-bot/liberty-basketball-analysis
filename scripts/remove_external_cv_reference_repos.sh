#!/usr/bin/env bash
# Remove third-party CV repos cloned only for comparison (not Liberty dependencies).
set -euo pipefail

REFERENCE_DIR="${REFERENCE_DIR:-/home/monk-admin/PROJECTS/abdullahtarek_basketball}"

if [[ ! -d "$REFERENCE_DIR" ]]; then
  echo "Nothing to remove: $REFERENCE_DIR does not exist."
  exit 0
fi

echo "Removing external reference clone: $REFERENCE_DIR"
rm -rf "$REFERENCE_DIR"
echo "Done. Liberty repo is unchanged at /home/monk-admin/PROJECTS/liberty-basketball-analysis"
