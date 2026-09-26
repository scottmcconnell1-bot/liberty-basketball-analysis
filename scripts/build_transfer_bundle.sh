#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="${1:-$(date +%Y%m%d_%H%M%S)}"
# Override with LIBERTY_TRANSFER_OUT_DIR to build outside the repo (tests do this).
OUT_DIR="${LIBERTY_TRANSFER_OUT_DIR:-${ROOT_DIR}/transfer-bundles}"
ARCHIVE_PATH="${OUT_DIR}/liberty-basketball-analysis-transfer-${STAMP}.tar.gz"

# NOTE: film_analysis.db is copied as-is. If the app is running (WAL mode), take a
# consistent snapshot first with `python scripts/backup_db.py` and ship that instead.

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

# Every importable package/dir the app needs at runtime. stat_book/ and static/
# were missing until 2026-09-09 (restore failed with ImportError / no CSS+JS).
for rel_dir in templates static tests docs scripts deploy blueprints services src stat_book data/stat_books; do
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

# Model weights live in models/ (Git LFS). Ship the real files; skip pointer stubs.
# LIBERTY_TRANSFER_SKIP_MODELS=1 leaves them out (tests; or when the target has LFS).
if [[ "${LIBERTY_TRANSFER_SKIP_MODELS:-0}" != "1" && -d "${ROOT_DIR}/models" ]]; then
  while IFS= read -r -d '' model_file; do
    if head -c 40 "${model_file}" | grep -q 'git-lfs'; then
      echo "Skipping LFS pointer (run: git lfs pull --include='models/*.pt'): ${model_file#${ROOT_DIR}/}" >&2
      continue
    fi
    INCLUDE_PATHS+=("${model_file#${ROOT_DIR}/}")
  done < <(find "${ROOT_DIR}/models" -maxdepth 1 -type f \( -name '*.pt' -o -name '*.json' \) -print0 | sort -z)
fi

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
