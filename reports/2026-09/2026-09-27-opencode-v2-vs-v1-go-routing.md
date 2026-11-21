# What changed from OpenCode v1 to v2, and does OpenCode Go route between models?

- **Date:** 2026-09-27
- **Report type:** Evidence review
- **Keywords:** OpenCode, v2 migration, OpenCode Go, model routing, plugins, permissions
- **Data collected:** official docs, release records and GitHub issues fetched 2026-09-27.

## Abstract

**Background.** OpenCode v2 arrived with a new architecture and alongside OpenCode Go, a subscription that the docs describe in terms of "routing". Users moving from v1 need to know what breaks, and Go subscribers need to know whether Go picks or switches models for them.
**Objective.** To identify the user-visible and migration-relevant differences between OpenCode v2 and v1, and to establish what OpenCode Go documents about model selection, routing and quotas.
**Methods.** Official documentation was reviewed: the V2 migration guide [1], V2 docs home [2], Go guide [3], V2 providers guide [4], agents [5], V2 plugins [6] and permissions [7] guides, the V1.0 release notes [8] and the v2.0.18 release commit [9], plus GitHub issue records [10, 11, 12, 13, 14]. Issue reports were treated as examples, not estimates of incidence.
**Results.** V2 normalizes supported V1 config in memory, but V1 plugins and server API integrations are explicit breaks and unsupported legacy fields can be dropped [1]. The latest tag at research time was v2.0.18 (commit dated 2026-09-25) [2, 9]. Go is an optional $10/month Zen subscription with a curated catalog and per-model dollar limits (five-hour 20%, weekly 50%, monthly 100% of the monthly limit) [3]. Go routing is session-aware serving with a stable `x-opencode-session` header [3]; users still select models with `/models` [3, 4].
**Conclusions.** OpenCode v2 is a major agent-platform and configuration revision, not a new "smarter model" tier, and OpenCode Go does not document task-aware model selection or guaranteed cross-model failover. Try v2 after checking plugins and API clients, and implement model choice and fallback explicitly when using Go.

## 1. Introduction

OpenCode is an open coding-agent tool whose 1.0 release rewrote the terminal UI [8]; v2 is a further major revision [2]. At the same time OpenCode Zen offers Go, a subscription to a curated set of open coding models [3]. Two practical questions follow: what a v1 user must change to adopt v2, and what "routing" in Go actually means for model choice and reliability.

- **RQ1.** What are the user-visible and migration-relevant differences between OpenCode v1 and v2?
- **RQ2.** What does OpenCode Go provide, and how are its quotas structured?
- **RQ3.** Does Go choose models, route between them, or fail over automatically?
- **RQ4.** What operational problems have been reported?

## 2. Methods

### 2.1 Sources and search strategy

Sources, all fetched 2026-09-27: the official V2 migration guide [1], V2 documentation home [2], current Go guide [3], V2 providers guide [4], current agents guide [5], V2 plugins guide [6], current permissions guide [7], V1.0 release notes [8], the v2.0.18 release commit [9], and GitHub issue records on V1 plugin compatibility [10], V1 session migration [11], Go `MissingSessionID` [12], V2 provider model filtering [13] and a Go upstream quota error [14]. How the issues were selected was not recorded.

### 2.2 Evidence classification

- **Vendor-reported:** official documentation and release records [1, 2, 3, 4, 5, 6, 7, 8, 9].
- **Community report:** GitHub issue reports, self-reported and possibly fixed or route-specific [10, 11, 12, 13, 14].
- **Derived:** none beyond restating Go's documented allowance percentages.

### 2.3 Experimental setup

No software was installed or run; no Go requests were made.

### 2.4 Analysis

Side-by-side comparison of v1 and v2 documentation, and a reading of the Go guide against the specific claims a user might infer (automatic model choice, cross-model failover, unlimited usage).

## 3. Results

### 3.1 V1 and V2 compared (RQ1)

Table 1. V1 vs V2 at a glance (vendor-reported); the last column is interpretation.

| Area | V1 | V2 | Practical effect |
| --- | --- | --- | --- |
| Release lineage | V1.0 (2025) rewrote the terminal UI from Go/Bubble Tea to OpenTUI (Zig + SolidJS), while retaining the server connection model [8]. | V2 is a subsequent major architecture and product revision; as of this research date, the repository’s latest tag is v2.0.18 (commit dated 2026-09-25) [2, 9]. | V2’s “2” is not merely a TUI redesign or model upgrade. |
| Clients | Terminal-first experience with web/IDE/server integrations. | Terminal, desktop, web, IDE and headless server workflows, built around a richer client/server API [2]. | More ways to use and control sessions; integrations need to target the new API contract. |
| Config | Singular fields and tool-grouped permission maps, e.g. `agent`, `provider`, `command`, `permission`. | Native plural maps and ordered permissions; V2 normalizes supported V1 config in memory and need not rewrite it [1]. | Most users can try V2 before converting configs; convert carefully when ready. |
| Agents | Agent/mode definitions using V1 fields such as `prompt`, `disable`, and separate `variant`. | More uniform `agents` definitions, `system`, `disabled`, model-plus-variant references, and ordered permission rules [1, 5]. | Easier to make roles and guardrails explicit; audit your model/permission overrides. |
| Plugins | V1 hook-function plugin format. | New V2 plugin API and object-based plugin definitions [1, 6, 10]. | Existing V1 plugins will not run unchanged; port or replace before relying on them. |
| Server API | V1 API and integrations. | New server API and client contracts [1]. | Scripts, custom clients, and IDE integrations may need porting. |
| TUI settings | Layered `tui.json` / `tui.jsonc`. | Global `cli.json`; migration is automatic [1]. | Check the resulting CLI preferences after first launch. |
| Models | Provider and model catalogs, with model selected by provider/model ID. | Broad provider catalog remains; V2 adds Go as a provider and continues explicit model selection with `/models` [3, 4]. | Go does not remove model choice or guarantee the same behavior across models. |

V2 warns about and ignores config fields with no equivalent [1].

### 3.2 OpenCode Go (RQ2, RQ3)

Table 2. OpenCode Go: subscription, models and routing, as documented (vendor-reported).

| Question | Current documented behavior |
| --- | --- |
| What is it? | Optional $10/month subscription from OpenCode Zen, intended to offer reliable, globally accessible popular open coding models [3]. |
| How do I connect? | Subscribe in the Zen console, copy the Go key, run `/connect`, choose OpenCode Go, then use `/models` to select from available models [3, 4]. |
| What does routing mean here? | OpenCode describes Go as an ordinary provider and publishes per-model price/usage limits. It recommends a stable `x-opencode-session` for each conversation so the service can optimize routing and prompt caching [3]. This supports session-aware backend routing/cache affinity, not an advertised “send task to best model” classifier or guaranteed automatic cross-model failover. |
| Does Go choose the model for me? | No evidence in the docs: OpenCode users select from the Go model list; model availability can change as models are added/tested [3, 4]. Choose the model explicitly for the task, or configure your own workflow outside Go. |
| Is the allowance unlimited? | No. The $10 subscription has per-model dollar limits and rolling windows: each model’s five-hour allowance is 20% of its monthly limit, weekly allowance 50%, monthly allowance 100%. The listed limits and rates differ by model [3]. |
| What if a quota is exhausted? | The guide says free models may remain available when a usage limit is reached; do not assume paid-model requests automatically switch to another paid model [3]. |
| Is it a single upstream? | The guide describes a curated model/provider combination tested with upstream teams; the client sees a Go provider/API. Model rates and routes are managed by the service, not controlled as separate user-selected providers [3]. |

At retrieval the catalog included, among others, GLM-5.3/5.3-Flash, GPT-6 Luna, Kimi K3, Qwen3.8 Max/Flash, DeepSeek V4 variants, MiniMax M3, Grok 4.7/4.6, and others [3]. The Go guide lists per-model dollar budgets, for example $60/month for GLM-5.3-Flash, $15/month for GLM-5.3, $15/month for GPT-6 Luna, and $15/month for Kimi K3 [3]. These are usage-value limits, not a promised number of requests or an amount of cash credit refundable to the user.

Routing operates at two distinct layers:

1. **Your model choice:** OpenCode’s `/models` picker selects a model ID from the Go catalog. Agents can also be assigned models in configuration. That is user-controlled dispatch [4, 5].
2. **Go’s provider-side serving:** The Go service routes a request for that selected model to its supported serving setup. A stable session header lets the service optimize routing and reuse prompt cache across turns [3]. The docs do not promise dynamic semantic routing among different model families, transparent fallback to a different model, or that the same model ID is always served by one fixed underlying provider.

### 3.3 Reported operational issues (RQ4)

- The official guide says V1 plugins and server clients need porting [1]. Public reports document V1 plugin schema failures and cases of V1 history migration issues, including very large embedded attachments [10, 11].
- The Go guide requires a stable session ID header for optimization, and a public issue shows requests can fail with `MissingSessionID` when a client omits it [3, 12].
- A V2 issue report describes V1 provider `whitelist`/`blacklist` settings not carrying over to a native equivalent [13].
- A Go upstream quota error has also been reported [14].

## 4. Discussion

### 4.1 Principal findings

RQ1: OpenCode v2 is a major agent-platform and configuration revision, not a new “smarter model” tier, and its strongest improvements are its new architecture and expanded client workflows [1, 2]. V1 config is largely intended to keep working, but plugins and server API integrations are explicit breaks; unsupported legacy fields can be dropped [1]. RQ2: Go is an optional $10/month Zen subscription with a curated model catalog and a usage-value allowance, not a flat, unlimited allocation [3]. RQ3: Go does not document task-aware model selection or guaranteed cross-model failover [4]; its "routing" is provider-side serving with session affinity. For model-agnostic behavior, a separate orchestration layer must decide when to switch models and how to handle failures, and that capability should not be inferred from the word “routing” in the Go guide.

Improvements and trade-offs, as interpreted from the sources:

1. **Broader client and workflow support:** V2’s web/desktop experience, sessions, server APIs, and multi-agent workflows make OpenCode useful beyond a single terminal UI [2]. This is the clearest product-level improvement, especially for managing concurrent sessions and review workflows.
2. **More explicit agent and permission structure:** V2 uses named agents and ordered permission rules, making allow/ask/deny precedence more inspectable than V1’s grouped tool configuration [1, 5]. This helps teams encode safer review/build roles, but does not mean default permissions are automatically restrictive; review the effective policy [7].
3. **A managed open-model option:** Go packages access to tested model/provider combinations behind one subscription and provider integration [3]. That reduces the setup burden of creating accounts and endpoints for every listed model; it adds service dependency, quota windows, and less control over the upstream route.
4. **A deliberate compatibility path:** Supported V1 config and definitions are intended to work without a wholesale rewrite; conversion is optional and can be staged [1]. This reduces the initial upgrade cost, but “accepted” config is not necessarily “supported”.
5. **Migration hazards are real:** RQ4's plugin and history-migration reports [10, 11] should be treated as reported edge cases, not proof that every upgrade loses data.
6. **Go session metadata is operationally important:** non-OpenCode clients should be checked for header propagation on both primary and auxiliary requests [3, 12].
7. **Model filtering may need a V2 review:** if a V1 config filters models, confirm the actual V2 model list rather than assuming those filters still apply [13].

### 4.2 Comparison with prior work

“V1” means the pre-2.0 major line; V1.0’s TUI rewrite was itself a distinct change from the V2 architecture revision [8]. The V2 change is therefore larger in scope than the 1.0 transition, which kept the server connection model.

### 4.3 Practical implications

- **Try V2** if you want its desktop/web and multi-session workflows, and your critical integrations are not tied to V1 plugins or the V1 server API. Keep a copy of the V1 setup during validation [1, 2].
- **Before switching for daily use:** verify sign-in/credentials, selected model IDs and variants, agents, MCP servers, permissions, V1 session visibility, plugin replacements, and any API clients. Back up session data first; test migration on a copy if histories or large attachments matter [1, 11].
- **Use Go when** convenient access to its curated models and the $10/month plan fit your workload. It is especially compelling when you will deliberately select among the cheaper high-limit models. Check the current model limits before leaning on expensive/low-limit models [3].
- **For routing reliability:** set a specific model per agent/task where possible, pass a stable session ID, and implement fallback explicitly in your client/workflow. Test a representative multi-turn coding session and inspect both usage and failures before treating Go as a transparent router [3, 12, 14].

## 5. Limitations

- **Staleness.** Go model list, prices, dollar budgets, and free model availability are subject to change; this is a snapshot fetched 2026-09-27 [3].
- **Vendor estimates.** Request-count estimates on the Go page depend on its illustrative cached/input/output token assumptions. They are vendor estimates, not guarantees of your usage or task throughput [3].
- **Issue reports.** GitHub issue reports are self-reported and may be fixed or route-specific; they establish known failure modes, not their prevalence [10, 11, 12]. How the issues were selected was not recorded.
- **Absent evidence.** No independent benchmark of Go versus direct upstream accounts, no same-prompt comparison of all Go models, and no guarantee of task-aware router/failover behavior were found in the reviewed official material. Absence from the docs does not prove the service never does these things.
- **No hands-on test.** Nothing was installed or run.

## 6. Conclusion

OpenCode v2 is an architecture and configuration revision that keeps most V1 config working but breaks V1 plugins and server API clients. OpenCode Go is a $10/month curated-model subscription with per-model dollar windows whose "routing" means session-aware serving of the model you chose, not automatic model selection or failover; model choice and fallback remain the user's job.

## References

[1] OpenCode V2 Migration Guide: <https://opencode.ai/v2/docs/migrate-v1>
[2] OpenCode V2 documentation home: <https://opencode.ai/v2/docs>
[3] OpenCode Go guide: <https://opencode.ai/docs/go>
[4] OpenCode V2 Providers guide: <https://opencode.ai/v2/docs/providers>
[5] OpenCode Agents guide: <https://opencode.ai/docs/agents>
[6] OpenCode V2 Plugins guide: <https://opencode.ai/v2/docs/plugins>
[7] OpenCode Permissions guide: <https://opencode.ai/docs/permissions>
[8] OpenCode 1.0.0 release notes: <https://github.com/anomalyco/opencode/releases/tag/v1.0.0>
[9] OpenCode v2.0.18 release commit: <https://github.com/anomalyco/opencode/commit/cd9a14a6b688d4021bee381dfd39d2cef9c0f862>
[10] OpenCode issue #48138: V1 plugin compatibility: <https://github.com/anomalyco/opencode/issues/48138>
[11] OpenCode issue #50339: V1 session migration with large attachments: <https://github.com/anomalyco/opencode/issues/50339>
[12] OpenCode issue #47763: Go MissingSessionID report: <https://github.com/anomalyco/opencode/issues/47763>
[13] OpenCode issue #49986: V2 provider model filtering: <https://github.com/anomalyco/opencode/issues/49986>
[14] OpenCode issue #49936: Go upstream quota error report: <https://github.com/anomalyco/opencode/issues/49936>
