# OpenCode v2 vs v1: what changed, and how Go handles model routing

- **Date:** 2026-09-27
- **Scope:** User-visible and migration-relevant differences between OpenCode v2 and v1, with emphasis on the OpenCode Go subscription, model selection, routing behavior, and operational trade-offs.
- **Method:** Reviewed the official V2 migration guide, V2 provider docs, current Go guide, V1.0 release notes, current agent/permissions/plugin docs, and GitHub release/issue records. Fetched 2026-09-27. Operational issue reports are examples, not estimates of incidence.

---

## Verdict

OpenCode v2 is a major agent-platform and configuration revision—not a new “smarter model” tier—and its strongest improvements are its new architecture and expanded client workflows.[1][2] V1 config is largely intended to keep working, but plugins and server API integrations are explicit breaks; unsupported legacy fields can be dropped.[1] OpenCode Go is an optional $10/month Zen subscription with a curated model catalog.

Go does not document task-aware model selection or guaranteed cross-model failover.[4]

---

## V1 vs V2 at a glance

| Area | V1 | V2 | Practical effect |
| --- | --- | --- | --- |
| Release lineage | V1.0 (2025) rewrote the terminal UI from Go/Bubble Tea to OpenTUI (Zig + SolidJS), while retaining the server connection model.[8] | V2 is a subsequent major architecture and product revision; as of this research date, the repository’s latest tag is v2.0.18 (commit dated 2026-09-25).[2][9] | V2’s “2” is not merely a TUI redesign or model upgrade. |
| Clients | Terminal-first experience with web/IDE/server integrations. | Terminal, desktop, web, IDE and headless server workflows, built around a richer client/server API.[2] | More ways to use and control sessions; integrations need to target the new API contract. |
| Config | Singular fields and tool-grouped permission maps, e.g. `agent`, `provider`, `command`, `permission`. | Native plural maps and ordered permissions; V2 normalizes supported V1 config in memory and need not rewrite it.[1] | Most users can try V2 before converting configs; convert carefully when ready. |
| Agents | Agent/mode definitions using V1 fields such as `prompt`, `disable`, and separate `variant`. | More uniform `agents` definitions, `system`, `disabled`, model-plus-variant references, and ordered permission rules.[1][5] | Easier to make roles and guardrails explicit; audit your model/permission overrides. |
| Plugins | V1 hook-function plugin format. | New V2 plugin API and object-based plugin definitions.[1][6][10] | Existing V1 plugins will not run unchanged; port or replace before relying on them. |
| Server API | V1 API and integrations. | New server API and client contracts.[1] | Scripts, custom clients, and IDE integrations may need porting. |
| TUI settings | Layered `tui.json` / `tui.jsonc`. | Global `cli.json`; migration is automatic.[1] | Check the resulting CLI preferences after first launch. |
| Models | Provider and model catalogs, with model selected by provider/model ID. | Broad provider catalog remains; V2 adds Go as a provider and continues explicit model selection with `/models`.[3][4] | Go does not remove model choice or guarantee the same behavior across models. |

---

## OpenCode Go: subscription, models, and routing

| Question | Current documented behavior |
| --- | --- |
| What is it? | Optional $10/month subscription from OpenCode Zen, intended to offer reliable, globally accessible popular open coding models.[3] |
| How do I connect? | Subscribe in the Zen console, copy the Go key, run `/connect`, choose OpenCode Go, then use `/models` to select from available models.[3][4] |
| What does routing mean here? | OpenCode describes Go as an ordinary provider and publishes per-model price/usage limits. It recommends a stable `x-opencode-session` for each conversation so the service can optimize routing and prompt caching.[3] This supports session-aware backend routing/cache affinity—not an advertised “send task to best model” classifier or guaranteed automatic cross-model failover. |
| Does Go choose the model for me? | No evidence in the docs: OpenCode users select from the Go model list; model availability can change as models are added/tested.[3][4] Choose the model explicitly for the task, or configure your own workflow outside Go. |
| Is the allowance unlimited? | No. The $10 subscription has per-model dollar limits and rolling windows: each model’s five-hour allowance is 20% of its monthly limit, weekly allowance 50%, monthly allowance 100%. The listed limits and rates differ by model.[3] |
| What if a quota is exhausted? | The guide says free models may remain available when a usage limit is reached; do not assume paid-model requests automatically switch to another paid model.[3] |
| Is it a single upstream? | The guide describes a curated model/provider combination tested with upstream teams; the client sees a Go provider/API. Model rates and routes are managed by the service, not controlled as separate user-selected providers.[3] |

The catalog changes. At retrieval it included, among others, GLM-5.3/5.3-Flash, GPT-6 Luna, Kimi K3, Qwen3.8 Max/Flash, DeepSeek V4 variants, MiniMax M3, Grok 4.7/4.6, and others.[3] The Go guide’s per-model dollar budgets show why the subscription is not a flat, unlimited allocation: for example, it lists $60/month for GLM-5.3-Flash, $15/month for GLM-5.3, $15/month for GPT-6 Luna, and $15/month for Kimi K3.[3] These are usage-value limits, not a promised number of requests or an amount of cash credit refundable to the user.

### What is “LLM routing” in Go?

There are two distinct layers:

1. **Your model choice:** OpenCode’s `/models` picker selects a model ID from the Go catalog. Agents can also be assigned models in configuration. That is user-controlled dispatch.[4][5]
2. **Go’s provider-side serving:** The Go service routes a request for that selected model to its supported serving setup. A stable session header lets the service optimize routing and reuse prompt cache across turns.[3] The docs do not promise dynamic semantic routing among different model families, transparent fallback to a different model, or that the same model ID is always served by one fixed underlying provider.

For model-agnostic behavior, a separate orchestration layer must decide when to switch models and how to handle failures. Do not infer that capability from the word “routing” in the Go guide.

---

## Improvements and trade-offs

1. **Broader client and workflow support:** V2’s web/desktop experience, sessions, server APIs, and multi-agent workflows make OpenCode useful beyond a single terminal UI.[2] This is the clearest product-level improvement, especially for managing concurrent sessions and review workflows.
2. **More explicit agent and permission structure:** V2 uses named agents and ordered permission rules, making allow/ask/deny precedence more inspectable than V1’s grouped tool configuration.[1][5] This helps teams encode safer review/build roles, but does not mean default permissions are automatically restrictive—review the effective policy.[7]
3. **A managed open-model option:** Go packages access to tested model/provider combinations behind one subscription and provider integration.[3] That reduces the setup burden of creating accounts and endpoints for every listed model; it adds service dependency, quota windows, and less control over the upstream route.
4. **A deliberate compatibility path:** Supported V1 config and definitions are intended to work without a wholesale rewrite; conversion is optional and can be staged.[1] This reduces the initial upgrade cost, but “accepted” config is not necessarily “supported”: V2 warns and ignores fields with no equivalent.
5. **Migration hazards are real:** The official guide says V1 plugins and server clients need porting.[1] Public reports document V1 plugin schema failures and cases of V1 history migration issues, including very large embedded attachments; treat these as reported edge cases, not proof that every upgrade loses data.[10][11]
6. **Go session metadata is operationally important:** The guide requires a stable session ID header for optimization, and a public issue shows requests can fail with `MissingSessionID` when a client omits it.[3][12] Non-OpenCode clients should be checked for header propagation on both primary and auxiliary requests.
7. **Model filtering may need a V2 review:** A V2 issue report describes V1 provider `whitelist`/`blacklist` settings not carrying over to a native equivalent.[13] If your V1 config filters models, confirm the actual V2 model list rather than assuming those filters still apply.

---

## Recommendation

- **Try V2** if you want its desktop/web and multi-session workflows, and your critical integrations are not tied to V1 plugins or the V1 server API. Keep a copy of the V1 setup during validation.[1][2]
- **Before switching for daily use:** verify sign-in/credentials, selected model IDs and variants, agents, MCP servers, permissions, V1 session visibility, plugin replacements, and any API clients. Back up session data first; test migration on a copy if histories or large attachments matter.[1][11]
- **Use Go when** convenient access to its curated models and the $10/month plan fit your workload. It is especially compelling when you will deliberately select among the cheaper high-limit models. Check the current model limits before leaning on expensive/low-limit models.[3]
- **For routing reliability:** set a specific model per agent/task where possible, pass a stable session ID, and implement fallback explicitly in your client/workflow. Test a representative multi-turn coding session and inspect both usage and failures before treating Go as a transparent router.[3][12][14]

---

## Caveats

- Go model list, prices, dollar budgets, and free model availability are subject to change; this is a snapshot fetched 2026-09-27.[3]
- Request-count estimates on the Go page depend on its illustrative cached/input/output token assumptions. They are vendor estimates, not guarantees of your usage or task throughput.[3]
- GitHub issue reports are self-reported and may be fixed or route-specific; they establish known failure modes, not their prevalence.[10][11][12]
- No independent benchmark of Go versus direct upstream accounts, no same-prompt comparison of all Go models, and no guarantee of task-aware router/failover behavior were found in the reviewed official material.
- “V1” means the pre-2.0 major line; V1.0’s TUI rewrite was itself a distinct change from the V2 architecture revision.[8]

---

## Sources

[1] https://opencode.ai/v2/docs/migrate-v1 — OpenCode V2 Migration Guide
[2] https://opencode.ai/v2/docs — OpenCode V2 documentation home
[3] https://opencode.ai/docs/go — OpenCode Go guide
[4] https://opencode.ai/v2/docs/providers — OpenCode V2 Providers guide
[5] https://opencode.ai/docs/agents — OpenCode Agents guide
[6] https://opencode.ai/v2/docs/plugins — OpenCode V2 Plugins guide
[7] https://opencode.ai/docs/permissions — OpenCode Permissions guide
[8] https://github.com/anomalyco/opencode/releases/tag/v1.0.0 — OpenCode 1.0.0 release notes
[9] https://github.com/anomalyco/opencode/commit/cd9a14a6b688d4021bee381dfd39d2cef9c0f862 — OpenCode v2.0.18 release commit
[10] https://github.com/anomalyco/opencode/issues/48138 — OpenCode issue #48138: V1 plugin compatibility
[11] https://github.com/anomalyco/opencode/issues/50339 — OpenCode issue #50339: V1 session migration with large attachments
[12] https://github.com/anomalyco/opencode/issues/47763 — OpenCode issue #47763: Go MissingSessionID report
[13] https://github.com/anomalyco/opencode/issues/49986 — OpenCode issue #49986: V2 provider model filtering
[14] https://github.com/anomalyco/opencode/issues/49936 — OpenCode issue #49936: Go upstream quota error report
