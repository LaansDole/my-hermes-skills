# Full-Text Eligibility Criteria
# Review: LLM-Driven Collaborative and Multi-Agent Framework in Healthcare Settings (Covidence #773228)
# Framework: PCC (Population / Concept / Context)
# Stage: Full-text review — decisions must be Include or Exclude (no Maybe)

## INCLUSION CRITERIA

### Population
- Clinical datasets, patients, healthcare professionals (physicians, nurses, pharmacists, allied health),
  or healthcare workflows are the subject of the study OR system being evaluated.
- Simulation of clinical interactions (e.g. standardised patient agents, clinical role-play) counts
  as a valid healthcare population.

### Concept
- The paper describes, implements, or empirically evaluates an LLM-driven multi-agent framework
  involving 2 or more distinct LLM agents collaborating toward a shared task.
- Valid agent roles include but are not limited to: coordinator/orchestrator, specialist/domain expert,
  critic/evaluator, debater, voter, patient-simulator, supervisor.
- Collaboration patterns: MULTI-ROUND or BIDIRECTIONAL interaction where agents exchange and react to
  each other's outputs — debate/discussion, peer review / critique, iterative consensus, role-play with
  feedback, or a coordinator that actively routes AND reconciles/synthesizes participant contributions.
  A "hierarchical" or "divide-and-conquer" structure qualifies ONLY if the agents actually interact
  (an orchestrator actively directs, monitors, and reconciles agents' work), NOT merely because distinct
  roles are invoked one-after-another.
- REQUIRED: at least one agent's reasoning must be conditioned on ANOTHER agent's output via feedback
  (critique, correction, consensus, or reconciliation). Conditioning on shared input data or on raw
  tool results does NOT count as inter-agent collaboration.
- The multi-agent coordination must be driven by LLMs (GPT-4, LLaMA, Gemini, Claude, etc.),
  not pre-LLM symbolic or rule-based multi-agent systems.

### Context
- Clinical settings: diagnosis support, clinical decision support systems (CDSS), treatment planning,
  medication management, triage, radiology/pathology analysis.
- Telehealth and remote care delivery.
- Medical education simulation (standardised patient exams, clinical role-play for training).
- Public health simulation with clinical relevance.
- Clinician-facing healthcare administration (clinical documentation, EHR management, scheduling
  with clinical impact). Payer-side administration (utilization management, coverage determination,
  prior authorization) does NOT qualify — see Context exclusion.

### Other
- English-language publications (peer-reviewed journal articles, conference papers, preprints on arXiv/medRxiv/bioRxiv).
- Accessible full text (already uploaded in Covidence at this stage).

## EXCLUSION CRITERIA

### Population
- Studies in non-healthcare domains where healthcare appears only incidentally or as a benchmark dataset
  (e.g. using a medical QA dataset to benchmark a general-purpose agent, with no clinical deployment intent).
- Veterinary-only studies.

### Concept
- Single-agent LLM systems with tool-calling (ReAct-style), prompt chaining, or retrieval augmentation
  but WITHOUT genuine multi-agent coordination between distinct LLM agent instances.
- SEQUENTIAL ROLE-SPECIALIZED PIPELINE (role-prompt chain): multiple distinct LLM "agents" (or roles)
  invoked one-by-one in a FIXED order per stage, where each performs a single role and hands output
  downstream with NO inter-agent interaction (no feedback, critique, debate, consensus, or reconciliation
  between agents). An agent looping against a TOOL (e.g. retrying SQL after execution errors, sampling a DB)
  does NOT constitute collaboration with another agent.
- Pre-LLM multi-agent systems (agent-based models, symbolic AI, rule-based systems) even if applied to healthcare.
- "Multi-single-agent" tool pipelines where multiple tools are orchestrated by one LLM controller
  (a single controller issuing API/tool calls is NOT multi-agent coordination).
- Papers that discuss or survey multi-agent frameworks but do not implement or evaluate one
  (purely conceptual papers with no system implementation).

### Context
- Non-healthcare settings: general software development, open-domain QA, customer service, finance,
  logistics, social simulation with no clinical population.
- Healthcare mentioned only as a superficial demo or motivating example without any clinical evaluation.
- Payer-side utilization management / coverage determination (e.g. prior authorization, insurance
  coverage verdicts): the system's output is an insurance/coverage decision, not a clinical
  recommendation, and the workflow is a payer function with no clinical care delivery.
- Bench biomedicine without clinical translation: drug discovery, genomics, protein folding,
  molecular biology — unless directly linked to a clinical decision workflow.
- Open-domain chatbots deployed without a specific healthcare context.

### Other
- Non-English publications.
- Full text inaccessible (already filtered at retrieval stage; should not appear here).

## COVIDENCE EXCLUSION REASONS (exact dropdown options, review #773228)

When casting an Exclude vote, select the FIRST applicable reason from this list:

- Adult population
- Paediatric population
- Wrong comparator
- Wrong dose
- Wrong indication
- Wrong intervention  <- use for wrong Concept (non-LLM-driven, single-agent, pre-LLM ABM, ReAct tool-chaining)
- Wrong outcomes
- Wrong patient population  <- use for wrong Population (non-HC domain, veterinary, HC-as-benchmark-only)
- Wrong route of administration
- Wrong setting  <- use for wrong Context (non-HC setting, bench biomedicine, superficial demo, payer-side utilization management / coverage determination)
- Wrong study design

PCC-to-dropdown mapping:
- Wrong Concept -> Wrong intervention
- Wrong Population -> Wrong patient population
- Wrong Context -> Wrong setting

## DECISION GUIDANCE

At full-text review stage you have the complete paper. Apply criteria strictly:

1. Verify the multi-agent architecture and INTERACTION explicitly: the paper must (a) describe 2+ distinct
   LLM agent instances with defined roles AND (b) show at least one agent's reasoning conditioned on another
   agent's output through feedback/critique/consensus/reconciliation — not merely distinct roles invoked in a
   fixed sequence, and not merely an agent looping against a tool.
2. Verify the healthcare context explicitly: a clinical population, clinical task, or healthcare
   workflow must be central to the paper's evaluation or deployment, not peripheral. Payer-side
   utilization management / coverage determination (e.g. prior authorization) does NOT qualify —
   the output is a coverage verdict, not a clinical recommendation (Wrong setting).
3. When a criterion remains ambiguous after reading the full text, default to EXCLUDE with the note:
   "Insufficient information in full text to confirm <criterion> — criterion not resolved at FT stage."
4. Confidence levels: HIGH = unambiguous; MEDIUM = one criterion inferred; LOW = partial extraction.
