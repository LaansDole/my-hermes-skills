# Screening Criteria
# Review: LLM-Driven Collaborative and Multi-Agent Framework in Healthcare Settings (Covidence #773228)
# Stage: Title & Abstract (T&A). Votes Yes/Maybe/No. This mirrors the full-text PCC criteria
# (covidence-full-text-review/references/CRITERIA.md), including the tightened multi-agent interaction rule.

## PICO / PCC

- **Population**: Clinical datasets, patients, healthcare professionals (physicians, nurses, pharmacists,
  allied health), or healthcare workflows are the subject of the study OR system being evaluated.
  Simulation of clinical interactions (standardised patient agents, clinical role-play) counts as valid
  healthcare population.
- **Concept / Intervention**: An LLM-driven multi-agent framework involving 2+ distinct LLM agents that
  ACTIVELY interact toward a shared clinical task. "Actively interact" = at least one agent's reasoning is
  conditioned on another agent's output via feedback/critique/consensus/reconciliation (debate, peer review,
  iterative consensus, role-play with feedback, or an orchestrator that routes AND reconciles agents' work).
- **Comparison**: Not applicable / any or no comparator.
- **Outcome(s)**: Not a restricting criterion at this review (task performance, accuracy, clinical utility,
  agent collaboration efficacy — any reported outcome).

## Inclusion criteria

- LLM-driven multi-agent framework (2+ distinct LLM agents interacting), described, implemented, or evaluated.
- Healthcare population, task, or workflow central to the study (clinical, telehealth, med-ed simulation,
  public-health simulation with clinical relevance, HC administration).
- English-language: peer-reviewed articles, conference papers, preprints (arXiv/medRxiv/bioRxiv).

## Exclusion criteria

- Single-agent LLM with tool-calling (ReAct) / prompt chaining / RAG — no genuine inter-agent coordination.
- SEQUENTIAL ROLE-SPECIALIZED PIPELINE: multiple distinct LLM roles invoked one-by-one in a fixed order with NO
  inter-agent interaction (no feedback/critique/debate/consensus between agents); an agent looping against a
  tool does not count. (Role-prompt chains and two-agent chat where one never reacts to the other are excluded.)
- Pre-LLM multi-agent systems (agent-based models, symbolic AI, rule-based).
- Multi-single-agent tool pipelines orchestrated by ONE LLM controller (single controller issuing API/tool calls).
- Purely conceptual/survey papers that do not implement or evaluate a multi-agent system.
- Non-healthcare domains where healthcare appears only incidentally or as a benchmark dataset; veterinary-only.
- Non-English.

## Study types to include

- Empirical/benchmark evaluations, system-design papers with evaluation, comparative studies of agent frameworks.
- Exclude pure opinion/editorial and papers unable to report any system implementation.
