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
- Collaboration patterns include: hierarchical pipelines, debate/discussion, peer review,
  role-play simulation, divide-and-conquer, and consensus mechanisms.
- The multi-agent coordination must be driven by LLMs (GPT-4, LLaMA, Gemini, Claude, etc.),
  not pre-LLM symbolic or rule-based multi-agent systems.

### Context
- Clinical settings: diagnosis support, clinical decision support systems (CDSS), treatment planning,
  medication management, triage, radiology/pathology analysis.
- Telehealth and remote care delivery.
- Medical education simulation (standardised patient exams, clinical role-play for training).
- Public health simulation with clinical relevance.
- Healthcare administration (clinical documentation, EHR management, scheduling with clinical impact).

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
- Pre-LLM multi-agent systems (agent-based models, symbolic AI, rule-based systems) even if applied to healthcare.
- "Multi-single-agent" tool pipelines where multiple tools are orchestrated by one LLM controller
  (the LLM must act as a participant agent, not just an orchestrator of API calls).
- Papers that discuss or survey multi-agent frameworks but do not implement or evaluate one
  (purely conceptual papers with no system implementation).

### Context
- Non-healthcare settings: general software development, open-domain QA, customer service, finance,
  logistics, social simulation with no clinical population.
- Healthcare mentioned only as a superficial demo or motivating example without any clinical evaluation.
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
- Wrong setting  <- use for wrong Context (non-HC setting, bench biomedicine, superficial demo)
- Wrong study design

PCC-to-dropdown mapping:
- Wrong Concept -> Wrong intervention
- Wrong Population -> Wrong patient population
- Wrong Context -> Wrong setting

## DECISION GUIDANCE

At full-text review stage you have the complete paper. Apply criteria strictly:

1. Verify the multi-agent architecture explicitly: the paper must describe 2+ distinct LLM agent
   instances with defined roles and coordination logic — not just "we use an LLM with tools".
2. Verify the healthcare context explicitly: a clinical population, clinical task, or healthcare
   workflow must be central to the paper's evaluation or deployment, not peripheral.
3. When a criterion remains ambiguous after reading the full text, default to EXCLUDE with the note:
   "Insufficient information in full text to confirm <criterion> — criterion not resolved at FT stage."
4. Confidence levels: HIGH = unambiguous; MEDIUM = one criterion inferred; LOW = partial extraction.
