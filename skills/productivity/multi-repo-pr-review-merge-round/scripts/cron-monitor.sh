#!/bin/bash
# Gate for the merge-round cron job. Deterministic output (no timestamps):
#   month-ended | busy | exhausted-until-<iso> | available
# The cron agent wakes only when this output changes.
D=~/.hermes/cache/merge-round
END_EPOCH=$(date -j -f "%Y-%m-%dT%H:%M:%S" "2026-10-31T23:59:00" +%s)
NOW=$(date +%s)
if [ "$NOW" -ge "$END_EPOCH" ]; then echo "month-ended"; exit 0; fi
if pgrep -f "omp -p --model commandcode" >/dev/null || pgrep -f "lane.sh" >/dev/null; then echo "busy"; exit 0; fi
# Latest reset time mentioned in any lane log
latest=""
for f in "$D"/*.log; do
  [ -f "$f" ] || continue
  r=$(grep -oE 'resets at [0-9T:.-]+Z' "$f" | tail -1 | awk '{print $3}')
  [ -n "$r" ] && { [ -z "$latest" ] || [[ "$r" > "$latest" ]]; } && latest=$r
done
if [ -n "$latest" ]; then
  rs=$(date -j -u -f "%Y-%m-%dT%H:%M:%S" "${latest%%.*}" +%s 2>/dev/null)
  if [ -n "$rs" ] && [ "$NOW" -lt "$rs" ]; then echo "exhausted-until-${latest%%.*}Z"; exit 0; fi
fi
echo "available"
