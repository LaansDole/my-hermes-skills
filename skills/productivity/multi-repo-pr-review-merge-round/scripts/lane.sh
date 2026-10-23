#!/bin/bash
# Serial omp -p job lane with usage-exhaustion detection.
# usage: lane.sh <lane> <round_dir> <provider/model[:effort]> <tag>:<abs-cwd> [...]
# Brief per job: <round_dir>/<tag>.md   Log: <round_dir>/<tag>.log
# Events on stdout (for notify): JOB-DONE, LANE-DONE, USAGE-EXHAUSTED
LANE=$1; D=$2; MODEL=$3; shift 3
for spec in "$@"; do
  tag=${spec%%:*}; cwd=${spec#*:}
  echo "=== $LANE START $tag $(date +%H:%M:%S)"
  (cd "$cwd" && omp -p --model "$MODEL" @"$D/$tag.md" > "$D/$tag.log" 2>&1; echo "OMP-EXIT:$?" >> "$D/$tag.log")
  echo "=== $LANE END $tag $(tail -1 "$D/$tag.log") $(date +%H:%M:%S)"
  if grep -qE "usage limit|RATE_LIMITED|MODEL_NOT_IN_PLAN|429 " "$D/$tag.log"; then
    echo "USAGE-EXHAUSTED $LANE at $tag: $(grep -m1 -oE 'resets at [^ ]*' "$D/$tag.log")"
    exit 0
  fi
  echo "JOB-DONE $LANE $tag"
done
echo "LANE-DONE $LANE"
