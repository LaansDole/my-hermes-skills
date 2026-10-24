# Hermes voice replies crackle on macOS: afplay cuts Ogg/Opus off after ~1s

- **Date:** 2026-10-24
- **Scope:** Why Hermes CLI voice-mode replies sounded crackly or broken on macOS with a local command TTS provider, the workaround, and where the upstream fix stands.
- **Method:** Measured on macOS 26.6.2 (Apple Silicon). Sources: the CoreAudio unified log (`log show`), the Hermes `agent.log`, `afplay` and `play_audio_file()` timings, and both upstream branches tested locally: main `bf0203a` and PR #132143 at `31d1554`. Upstream issue and PRs read on GitHub on 2026-10-24.

---

## Verdict

The audio files were fine. Playback was cutting them off. On macOS 15 and later, `afplay` opens an Ogg/Opus file, plays about the first second, and exits 0. Hermes treats exit 0 as success, so it never tries another player. In CLI voice mode Hermes reads each reply aloud one sentence at a time. A TTS provider with `voice_compatible: true` gets its output converted to `.ogg`, so every sentence was cut off after about one second. That sounds like crackling or stuttering, not like a missing ending.

Workaround: `hermes config set --force tts.providers.<name>.voice_compatible false`. The provider's own WAV is then played and plays in full. Upstream fix: NousResearch/hermes-agent PR #132143 (open, for issue #122494).

---

## Evidence (measured)

| Check | Result |
| --- | --- |
| CoreAudio log, afplay `client starting` -> `client stopping` | ~1.09 s on every Ogg clip, whether 2 s or 9 s long |
| Per-sentence reply playback (agent.log + CoreAudio) | A new sentence every ~1.9 s, regardless of length |
| `afplay` on a 28.2 s Opus `.ogg` | exits 0 after 1.99 s |
| `afplay` on the same audio decoded to WAV | 29.0 s (full) |
| `play_audio_file()` on a 3.9 s `.ogg`, main `bf0203a` | returns after 2.10 s (truncated) |
| `play_audio_file()` on the same `.ogg`, PR #132143 | returns after 5.91 s (full clip + decode) |
| Voice test files on PR #132143 | 101 passed, 1 failed, 6 skipped; base: 95 passed, the same 1 failure |

The one failure in both runs is `TestPlayBeep::test_beep_calls_sounddevice_play`. It expects sounddevice output, which Hermes skips on macOS, so it is environmental and not caused by the PR.

---

## Why the first diagnosis went wrong

- Checking the file alone found nothing. Silence detection, peak and click analysis, Whisper transcripts and voice/temperature A/B tests all showed a clean file. The defect was in playback.
- A listening A/B misled us. The Ogg sample played right after a spoken label, and its first second sounded fine. Compare `afplay`'s run time with the clip length instead: `ffprobe` duration vs `/usr/bin/time -p afplay -v 0.01 FILE`.
- "Hermes output" meant the per-sentence reply reading in voice mode, not a single `text_to_speech` call. `agent.log` shows these as runs of `Generating speech` / `TTS audio saved` lines right after `response ready`.

---

## Upstream status (2026-10-24)

- Issue #122494 (open): macOS CLI voice replies cut off after ~2 s. It names both defects: afplay truncates Ogg/Opus with exit code 0, and plugin/command providers get Opus even in the CLI.
- PR #132143 (open, fixes #122494): decodes `.ogg/.oga/.opus` to a temp WAV with the built-in macOS `afconvert`, then plays it with `afplay`. It also stops a reply that was interrupted from restarting in another player. Verified locally, and a confirming comment was posted on the PR.
- PR #103892 (open, has merge conflicts): the older approach, which sends non-CoreAudio formats to ffplay before afplay.
- Main still passes `.ogg` straight to `afplay` (`_system_player_candidates` in `tools/voice_mode.py`).

Once #132143 is merged, set `voice_compatible` back to `true` if you want native voice messages on Telegram and other chat apps.

---

## References

- Issue #122494, macOS CLI voice replies cut off after ~2s (NousResearch/hermes-agent): <https://github.com/NousResearch/hermes-agent/issues/122494>
- PR #132143, decode Ogg/Opus for afplay so macOS plays the whole reply: <https://github.com/NousResearch/hermes-agent/pull/132143>
- PR #103892, afplay silently truncated Ogg/Opus clips on macOS: <https://github.com/NousResearch/hermes-agent/pull/103892>
- Issue #26404, the earlier Edge TTS MP3->OGG case, closed as fixed: <https://github.com/NousResearch/hermes-agent/issues/26404>
- `tools/voice_mode.py` on main: <https://github.com/NousResearch/hermes-agent/blob/main/tools/voice_mode.py>
