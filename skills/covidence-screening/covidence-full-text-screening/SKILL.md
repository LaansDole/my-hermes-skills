---
name: covidence-full-text-screening
description: Read a paper's full text (PDF, arXiv, DOI URL) and apply the review's PCC criteria to give a structured Include/Exclude verdict. Distinct from covidence-full-text-retrieval (which uploads PDFs to Covidence) — this skill provides the intellectual screening decision at the full-text stage.
version: 1.0.0
metadata:
  hermes:
    tags: [covidence, systematic-review, full-text, screening, pdf, pymupdf, pcc]
    requires_toolsets: [terminal]
---

# Covidence Full-Text Screening

## When to use this skill

Use this skill when the user says any of:
- "do a full-text review on this paper"
- "screen this at full text"
- "give me a verdict on this paper"
- "read this paper and tell me if it fits [the review]"
- "can you review this paper" + they supply a URL or arXiv ID

Do NOT confuse this with `covidence-full-text-retrieval`, which uploads PDFs to Covidence. That skill never gives an Include/Exclude verdict. This skill never touches the browser or Covidence UI.

## PCC Criteria (review 773228)

The user's current review criteria are stored in memory. Always read memory before screening. For review 773228 ("LLM-Driven Collaborative and Multi-Agent Framework in Healthcare Settings"):

- **Population**: Include clinical datasets/patients/HC professionals/medical workflows. Exclude non-HC domains, veterinary, HC-as-benchmark-only.
- **Concept**: Include LLM-driven multi-agent (2+ agents: role-play/debate/hierarchical/collab pipelines). Exclude single-agent LLM, pre-LLM ABM, tool-chaining "multi-single-agent" (ReAct-style).
- **Context**: Include clinical/telehealth/med-ed-sim/public-health-sim/HC-admin. Exclude non-HC settings, general SW dev, open-domain chatbots, bench biomedicine (drug discovery/genomics/protein-folding), HC-as-superficial-demo.
- **Other**: Include English peer-reviewed + preprints. Exclude non-English, inaccessible full-texts.

## Workflow

### Step 1 — Get the full text

Try in order until you have the text:

1. **arXiv ID present**: `curl -sL --max-time 60 -o /tmp/paper.pdf "https://arxiv.org/pdf/{arxiv_id}"`
2. **DOI present**: try Unpaywall `https://api.unpaywall.org/v2/{doi}?email=dolelongan@gmail.com`, grab `best_oa_location.url_for_pdf`, curl that.
3. **Direct PDF URL**: curl it directly.

Validate the download: `stat -f%z /tmp/paper.pdf` must be > 1024 bytes.

### Step 2 — Extract text with PyMuPDF

```bash
pip3 install pymupdf -q 2>/dev/null
python3 -c "
import fitz  # package name is pymupdf, import name is fitz
doc = fitz.open('/tmp/paper.pdf')
text = ''
for i, page in enumerate(doc):
    text += f'\n--- PAGE {i+1} ---\n' + page.get_text()
print(text)
"
```

If the paper is long (>14 pages), read in two slices: first 35000 chars, then the rest. This avoids truncation.

### Step 3 — Apply PCC criteria and give verdict

Read the full text carefully. For each criterion, determine PASS or FAIL and give a brief justification from the paper's actual content (methods section, population described, agent count/type, clinical setting).

## Verdict Format and Delivery

Always deliver the verdict via pbcopy so the user can Cmd+V directly into Word without Warp terminal soft-wrap artifacts. Do NOT print the verdict text to the terminal — pipe it to pbcopy only, then print a one-line confirmation.

Plain text rules inside the piped content:
- No markdown symbols (no **, ##, ---, backticks, *, _)
- ALL CAPS section headers
- Single blank line between sections
- No hard line breaks mid-sentence

Use the heredoc pattern (handles single quotes safely):

```bash
cat > /tmp/hermes_verdict.txt << 'EOF'
VERDICT: INCLUDE   [or EXCLUDE]

POPULATION - PASS [or FAIL]
[1-3 sentences from the paper justifying the call]

CONCEPT - PASS [or FAIL]
[1-3 sentences — specifically name the agents, their count, how they collaborate]

CONTEXT - PASS [or FAIL]
[1-3 sentences — name the clinical domain/setting]

OTHER - PASS [or FAIL]
[language + accessibility]

[Optional: flag any quality concerns (citation mismatches, questionable claims) worth noting at extraction stage — label clearly as a quality note, not an exclusion reason]
EOF
pbcopy < /tmp/hermes_verdict.txt && echo "Verdict copied to clipboard — Cmd+V into Word." && rm /tmp/hermes_verdict.txt
```

After running: briefly summarise the decision (one line) in the terminal so the user knows the outcome without having to paste first.

A single failing criterion = EXCLUDE. All four must pass for INCLUDE.

## Voting rule (same as T&A screening)

- INCLUDE: abstract/full text clearly meets all criteria
- EXCLUDE: clearly fails one or more criteria
- Maybe: only when a criterion is genuinely unresolvable even from the full text (rare at this stage — the whole point of full-text screening is that Maybe is almost never needed)

## Pitfalls

- **"full-text review" ≠ Covidence upload**: the user uses "full-text review" to mean "screen at the full-text stage." Do not launch CDP/browser or the covidence-full-text-retrieval workflow.
- **pymupdf import name**: `pip3 install pymupdf` but `import fitz` in Python. Do not use `import pymupdf`.
- **Long papers**: slice the extracted text into two terminal calls (first 35000 chars, then rest) rather than one giant print — avoids output truncation.
- **HC-as-benchmark-only exclusion**: if the paper applies an LLM multi-agent system to a medical QA dataset purely as a benchmark (no clinical workflow, no patients/clinicians involved in the loop), this fails the Population AND Context criteria simultaneously.
- **ReAct / tool-chaining exclusion**: a single LLM calling multiple tools in sequence is NOT multi-agent. There must be 2+ distinct agents with separate roles that communicate/deliberate with each other.

## References

See `references/paper-2512.14321-example.md` for a worked example verdict from this skill's inaugural use.
