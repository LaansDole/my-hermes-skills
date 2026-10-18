# refusal-fallback-alert

Hermes plugin that alerts when an Anthropic safety classifier blocks a turn -- e.g.
`Refusal (cyber): This request triggered restrictions on violative cyber content` --
in the main agent or any delegated subagent.

It is observe-only. The retry itself is Hermes's built-in fallback chain: Hermes maps
Anthropic `stop_reason: "refusal"` to `content_filter`, fires the `api_request_error`
hook with `reason=content_policy_blocked`, then activates `fallback_providers`
(`agent/turn_truncation.py::handle_content_policy_refusal`).

On each refusal the plugin:

- appends a JSON line to `$HERMES_HOME/logs/refusal-fallback.log` (time, session, task, provider, model, refusal text)
- posts a macOS notification (no-op on other platforms)

## Install

```bash
ln -s ~/Projects/auto-learn-for-me/plugins/refusal-fallback-alert ~/.hermes/plugins/refusal-fallback-alert
hermes plugins enable refusal-fallback-alert
```

## Pair it with the fallback config (does the actual retry)

```bash
# Opus 5.5 refusal -> retry the turn on Opus 4.8 at xhigh
hermes config set fallback_providers '[{"provider":"anthropic","model":"claude-opus-4-8"}]'
hermes config set agent.reasoning_overrides.claude-opus-4-8 xhigh
# subagents pinned to their own model/provider don't inherit the parent chain:
hermes config set delegation.fallback_providers '[{"provider":"anthropic","model":"claude-opus-4-8"}]'
```

Background: [Claude Cookbook -- Classifier fallback and billing](https://platform.claude.com/cookbook/fable-5-fallback-billing-guide)
(server-side `fallbacks` only supports Fable 5 -> Opus 4.8, so Opus 5.5 needs client-side fallback),
[Qualiteg -- cyber-safeguard false positives in Claude Code](https://journal.qualiteg.com/claude-code-usage-policy-violation-fix/).

## Caveats

- Hermes fallback is turn-scoped: the next user message retries the primary, which may re-refuse if the triggering content is still in history.
- The same chain also fires on 429 / 5xx / auth errors from the primary.
- Only covers Hermes and its in-process subagents -- not standalone Claude Code / omp processes.

## Undo

```bash
hermes plugins disable refusal-fallback-alert
hermes fallback clear
```
