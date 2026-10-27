#!/usr/bin/env bash
# Template: drive ONE continuous recording of the runbook journey in a sandbox headless Chrome.
# Copy next to your capture notes, fill the APP_URL / step functions, then run:
#   bash record-journey.sh <out_dir>
# Requires: Chrome started with --remote-debugging-port=$CDP_PORT and a fresh --user-data-dir,
# the app's servers already up and health-checked, python3 with websocket-client.
set -u
SKILL_SCRIPTS="${SKILL_SCRIPTS:?set SKILL_SCRIPTS to the demo-runbook skill scripts/ dir}"
export CDP_PORT="${CDP_PORT:-9333}"
APP_URL="${APP_URL:?set APP_URL, e.g. http://localhost:3100/app/}"
OUT="$1"; mkdir -p "$OUT"
CDP="python3 $SKILL_SCRIPTS/cdp.py"
STOP="$OUT/STOP"; rm -f "$STOP"

log() { echo "[$(date +%T)] $*" | tee -a "$OUT/steps.log"; }   # wall-clock step log -> caption times
click_text() { $CDP eval "(()=>{const b=[...document.querySelectorAll('button')].find(b=>$1.test(b.innerText.trim())); if(!b) return 'missing'; b.click(); return 'ok'})()"; }
escape_key() { $CDP eval 'document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true})); "esc"' >/dev/null; }
wait_for_text() {  # wait_for_text '<regex>' <timeout_s>
  local start; start=$(date +%s)
  until $CDP eval "/$1/.test(document.body.innerText)" | grep -q true; do
    sleep 2; [ $(( $(date +%s) - start )) -gt "$2" ] && { log "TIMEOUT waiting for $1"; return 1; }
  done
}

$CDP nav about:blank >/dev/null
python3 "$SKILL_SCRIPTS/record_screencast.py" "$OUT/frames" "$STOP" > "$OUT/record.log" 2>&1 &
REC=$!
sleep 1

# ---- Setup steps (one log line per runbook step; sleeps = time a viewer needs to read the screen) ----
log "open the app (fresh browser profile)"
$CDP nav "$APP_URL" >/dev/null; sleep 8
# log "import <thing>";            click_text '/BROWSE/i'; sleep 2.5
# log "reload so the scene rebuilds"; $CDP nav "$APP_URL" >/dev/null; sleep 9

run_case() {  # run_case <tag> <input_file>
  log "== $1"
  # Prefer the app's own buttons/stores over clicking moving targets, e.g.:
  # $CDP eval '(async()=>{const m=await import("/<base>/src/store.ts"); m.useStore.getState().reset(); return 1})()' >/dev/null
  # click_text '/START/i' >/dev/null; sleep 2
  log "paste the input and press Enter"
  $CDP type "$2" >/dev/null; sleep 2.5          # let the viewer read the input
  $CDP enter >/dev/null
  sleep 1.5
  # Switch log panels to their LIVE view now: completion modals open by themselves and cover the screen later.
  # click_text '/^ACTIVITY$/' >/dev/null
  wait_for_text 'FINAL ANSWER|DONE' 240
  log "run finished"
  sleep 4                                        # hold on the result
  log "close the result"
  escape_key; sleep 2
}

# run_case "A" inputs/a.txt
# run_case "B" inputs/b.txt

log "done"
touch "$STOP"; wait $REC
cat "$OUT/record.log"
