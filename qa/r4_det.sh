#!/bin/bash
cd "$(dirname "$0")/.."
for cfg in "qa_s3_link 7 1000" "qa_s3_link 20261104 1000" "qa_s6_load100_flock 7 600"; do
  set -- $cfg
  PYTHONUNBUFFERED=1 uv run --with psutil python -X utf8 qa/diag_determinism.py --scenario $1 --seed $2 --frames $3 --runs 2
done
PYTHONUNBUFFERED=1 uv run --with psutil --with mcap python -X utf8 qa/run_qa.py --only 024 --build-dir build/msvc-debug
echo R4DET_DONE
