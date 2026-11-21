# Why do Hermes voice replies crackle on macOS? afplay cuts Ogg/Opus off after ~1s

- **Date:** 2026-10-24
- **Report type:** Technical investigation
- **Keywords:** Hermes, macOS, afplay, Ogg/Opus, text-to-speech, voice mode
- **Data collected:** measurements on macOS 26.6.2 (Apple Silicon) on or before 2026-10-24 (exact run date not recorded); upstream issue and PRs read on GitHub on 2026-10-24.

## Abstract

**Background.** Hermes CLI voice-mode replies sounded crackly or broken on macOS when using a local command TTS provider, although the generated audio files appeared clean.
**Objective.** To find the cause, a workaround, and the status of an upstream fix.
**Methods.** On macOS 26.6.2 (Apple Silicon), the CoreAudio unified log, the Hermes `agent.log`, and `afplay` and `play_audio_file()` timings were examined, and upstream main `bf0203a` and PR #132143 at `31d1554` were tested locally [1]. The upstream issue and PRs were read on GitHub.
**Results.** `afplay` played every Ogg clip for ~1.09 s regardless of length and exited 0; on a 28.2 s Opus file it exited after 1.99 s, while the same audio as WAV played for 29.0 s (measured). On main, `play_audio_file()` returned after 2.10 s on a 3.9 s clip; with PR #132143 it returned after 5.91 s. The issue is tracked as #122494 [2].
**Conclusions.** The audio files were fine; playback was cutting them off. On macOS 15 and later `afplay` plays about the first second of an Ogg/Opus file and exits 0, so Hermes never falls back to another player. Setting the provider's `voice_compatible` to `false` works around it, and PR #132143 fixes it upstream.

## 1. Introduction

In CLI voice mode, Hermes reads each reply aloud one sentence at a time. A TTS provider with `voice_compatible: true` gets its output converted to `.ogg` [2], which Hermes then plays with the system player. The user heard crackling and stuttering rather than a clean voice. Analysis of the audio files themselves found no defect, so the investigation moved to playback.

- **RQ1.** Where in the pipeline is the audio damaged?
- **RQ2.** What is a working configuration today?
- **RQ3.** Does the proposed upstream fix resolve it, and what is its status?

## 2. Methods

### 2.1 Sources and search strategy

Local sources: the CoreAudio unified log (`log show`), the Hermes `agent.log`, and timings of `afplay` and Hermes's `play_audio_file()`. Upstream sources, read on GitHub on 2026-10-24: PR #132143 [1], issue #122494 [2], PR #103892 [3], `tools/voice_mode.py` on main [4], and the earlier closed issue #26404 [5].

### 2.2 Evidence classification

- **Measured:** all timings and test results in Table 1.
- **Community report / upstream records:** issue and PR descriptions [1, 2, 3, 5] and source on main [4].

### 2.3 Experimental setup

macOS 26.6.2 on Apple Silicon. Both upstream branches were tested locally: main `bf0203a` and PR #132143 at `31d1554` [1]. Durations were checked with `ffprobe` (clip length) and `/usr/bin/time -p afplay -v 0.01 FILE` (playback time). The Hermes voice test files were run on both branches. The TTS provider and voice used were not recorded.

### 2.4 Analysis

Playback time was compared with clip duration. CoreAudio client lifetime was taken from the interval between afplay's `client starting` and `client stopping` log lines.

## 3. Results

### 3.1 Audio file checks (RQ1)

Silence detection, peak and click analysis, Whisper transcripts and voice/temperature A/B tests all showed a clean file. A listening A/B was misleading: the Ogg sample played right after a spoken label, and its first second sounded fine.

"Hermes output" here meant the per-sentence reply reading in voice mode, not a single `text_to_speech` call. `agent.log` shows these as runs of `Generating speech` / `TTS audio saved` lines right after `response ready`.

### 3.2 Playback measurements (RQ1, RQ3)

Table 1. Playback and test measurements (measured).

| Check | Result |
| --- | --- |
| CoreAudio log, afplay `client starting` -> `client stopping` | ~1.09 s on every Ogg clip, whether 2 s or 9 s long |
| Per-sentence reply playback (agent.log + CoreAudio) | A new sentence every ~1.9 s, regardless of length |
| `afplay` on a 28.2 s Opus `.ogg` | exits 0 after 1.99 s |
| `afplay` on the same audio decoded to WAV | 29.0 s (full) |
| `play_audio_file()` on a 3.9 s `.ogg`, main `bf0203a` | returns after 2.10 s (truncated) |
| `play_audio_file()` on the same `.ogg`, PR #132143 | returns after 5.91 s (full clip + decode) |
| Voice test files on PR #132143 | 101 passed, 1 failed, 6 skipped; base: 95 passed, the same 1 failure |

The one failure in both runs is `TestPlayBeep::test_beep_calls_sounddevice_play`. It expects sounddevice output, which Hermes skips on macOS.

Setting `voice_compatible` to `false` made Hermes play the provider's own WAV, which played in full.

### 3.3 Upstream status, 2026-10-24 (RQ3)

- Issue #122494 (open): macOS CLI voice replies cut off after ~2 s. It names both defects: afplay truncates Ogg/Opus with exit code 0, and plugin/command providers get Opus even in the CLI [2].
- PR #132143 (open, fixes #122494): decodes `.ogg/.oga/.opus` to a temp WAV with the built-in macOS `afconvert`, then plays it with `afplay`. It also stops a reply that was interrupted from restarting in another player [1]. Verified locally (Table 1), and a confirming comment was posted on the PR.
- PR #103892 (open, has merge conflicts): the older approach, which sends non-CoreAudio formats to ffplay before afplay [3].
- Main still passes `.ogg` straight to `afplay` (`_system_player_candidates` in `tools/voice_mode.py`) [4].

## 4. Discussion

### 4.1 Principal findings

RQ1: the audio files were fine; playback was cutting them off. On macOS 15 and later, `afplay` opens an Ogg/Opus file, plays about the first second, and exits 0 [2]. Hermes treats exit 0 as success, so it never tries another player. Because voice mode plays one sentence at a time and every sentence was an `.ogg`, each was cut off after about one second, which sounds like crackling or stuttering rather than a missing ending. RQ3: PR #132143 restores full playback at the cost of a decode step (5.91 s for a 3.9 s clip) and introduces no new test failures; the single failing test is environmental and not caused by the PR.

### 4.2 Comparison with prior work

An earlier Edge TTS MP3->OGG case, issue #26404, was closed as fixed on 2026-05-24 [5]; the present defect affects a local command TTS provider. Issue #122494 describes the cut-off as ~2 s [2]; the ~1.09 s CoreAudio figure in Table 1 is the audio client's active time, while the ~2 s figures are process or function return times, so the two are consistent. Lesson for diagnosis: compare a player's run time with the clip length (`ffprobe` duration vs `/usr/bin/time -p afplay -v 0.01 FILE`) instead of listening, because the first second of a truncated clip sounds fine.

### 4.3 Practical implications

- Workaround (RQ2): `hermes config set --force tts.providers.<name>.voice_compatible false`. The provider's own WAV is then played and plays in full.
- Once #132143 is merged, set `voice_compatible` back to `true` if you want native voice messages on Telegram and other chat apps.

## 5. Limitations

- **Single machine.** All measurements come from one Mac on macOS 26.6.2; the claim that the behaviour applies to macOS 15 and later rests on the upstream issue [2].
- **Sample of clips.** The number of clips timed beyond those in Table 1 was not recorded.
- **Moving target.** The PRs were open at the time of writing; their final merged form may differ.
- **Unrecorded details.** The TTS provider, voice and exact run date were not recorded.

## 6. Conclusion

Hermes voice replies crackle on macOS because `afplay` truncates Ogg/Opus clips to about one second while exiting successfully, and voice mode plays every sentence as Ogg. Disabling `voice_compatible` avoids the Ogg path today, and PR #132143, verified locally, fixes the playback upstream.

## References

[1] PR #132143, decode Ogg/Opus for afplay so macOS plays the whole reply (NousResearch/hermes-agent): <https://github.com/NousResearch/hermes-agent/pull/132143>
[2] Issue #122494, macOS CLI voice replies cut off after ~2s (NousResearch/hermes-agent): <https://github.com/NousResearch/hermes-agent/issues/122494>
[3] PR #103892, afplay silently truncated Ogg/Opus clips on macOS (NousResearch/hermes-agent): <https://github.com/NousResearch/hermes-agent/pull/103892>
[4] `tools/voice_mode.py` on main (NousResearch/hermes-agent): <https://github.com/NousResearch/hermes-agent/blob/main/tools/voice_mode.py>
[5] Issue #26404, the earlier Edge TTS MP3->OGG case, closed as fixed (NousResearch/hermes-agent, closed 2026-05-24): <https://github.com/NousResearch/hermes-agent/issues/26404>
