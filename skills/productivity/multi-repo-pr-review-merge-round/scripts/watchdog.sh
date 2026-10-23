#!/bin/zsh
# Composite watchdog for omp -p lanes (zsh: macOS bash 3 lacks assoc arrays).
# usage: zsh watchdog.sh <round_dir> <tag>:<abs-cwd> [...]
# Events on stdout: STALLED, QUOTA-SUSPECT, EXITED-ALL. Samples -> <round_dir>/watchdog.log
D=$1; shift
LOG=$D/watchdog.log
SESS=~/.omp/agent/sessions
typeset -A CWD LAST FLAT
for spec in "$@"; do CWD[${spec%%:*}]=${spec#*:}; done
ev() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
ev "WATCHDOG-START tags=${(k)CWD}"
for cycle in $(seq 1 200); do
  alive=0
  for t in ${(k)CWD}; do
    L=$D/$t.log
    if [ ! -f "$L" ]; then alive=$((alive+1)); continue; fi   # queued
    if grep -q "OMP-EXIT" "$L"; then continue; fi
    alive=$((alive+1))
    slug=$(echo "${CWD[$t]#$HOME}" | sed "s|/|-|g")
    f=$(ls -t "$SESS/$slug"/*.jsonl 2>/dev/null | head -1)   # omp resumes the newest session per cwd
    sz=$(stat -f %z "$f" 2>/dev/null || echo 0)
    if grep -qiE 'quota|usage limit|RATE_LIMITED|MODEL_NOT_IN_PLAN' "$L"; then
      ev "QUOTA-SUSPECT $t $(grep -iE 'usage limit|quota|MODEL_NOT_IN_PLAN' "$L" | tail -1 | cut -c1-200)"
    fi
    if [ "$sz" = "${LAST[$t]}" ]; then FLAT[$t]=$(( ${FLAT[$t]:-0}+1 )); else FLAT[$t]=0; fi
    LAST[$t]=$sz
    echo "$(date +%H:%M:%S) sample $t bytes=$sz flat=${FLAT[$t]} file=${f:t}" >> "$LOG"
    if [ "${FLAT[$t]}" -ge 6 ]; then ev "STALLED $t bytes=$sz (6x180s flat)"; FLAT[$t]=0; fi
  done
  if [ $alive -eq 0 ]; then ev "EXITED-ALL"; exit 0; fi
  sleep 180
done
ev "WATCHDOG-CEILING"
