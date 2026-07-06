#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="${1:-$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${ROOT_DIR}/transfer-bundles"
ARCHIVE_PATH="${OUT_DIR}/liberty-basketball-analysis-transfer-${STAMP}.tar.gz"

mkdir -p "${OUT_DIR}"

declare -a INCLUDE_PATHS=()
for rel_path in \
  README.md \
  "Start Liberty.bat" \
  .dockerignore \
  .env.example \
  Dockerfile \
  docker-compose.yml \
  docker-compose.gpu.yml \
  pytest.ini \
  requirements.txt \
  requirements.docker.txt \
  schema.sql \
  film_analysis.db \
  uploads
do
  if [[ -e "${ROOT_DIR}/${rel_path}" ]]; then
    INCLUDE_PATHS+=("${rel_path}")
  fi
done

for rel_dir in templates tests docs scripts deploy blueprints services src; do
  if [[ -d "${ROOT_DIR}/${rel_dir}" ]]; then
    INCLUDE_PATHS+=("${rel_dir}")
  fi
done

while IFS= read -r -d '' py_file; do
  base_name="$(basename "${py_file}")"
  if [[ "${base_name}" == benchmark_* ]]; then
    continue
  fi
  INCLUDE_PATHS+=("${py_file#${ROOT_DIR}/}")
done < <(find "${ROOT_DIR}" -maxdepth 1 -type f -name '*.py' -print0 | sort -z)

while IFS= read -r -d '' model_file; do
  INCLUDE_PATHS+=("${model_file#${ROOT_DIR}/}")
done < <(find "${ROOT_DIR}" -maxdepth 1 -type f -name '*.pt' -print0 | sort -z)

if [[ ${#INCLUDE_PATHS[@]} -eq 0 ]]; then
  echo "No files selected for the transfer bundle." >&2
  exit 1
fi

tar \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='.pytest_cache' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='transfer-bundles' \
  -czf "${ARCHIVE_PATH}" \
  -C "${ROOT_DIR}" \
  "${INCLUDE_PATHS[@]}"

echo "Created transfer bundle:"
echo "  ${ARCHIVE_PATH}"
