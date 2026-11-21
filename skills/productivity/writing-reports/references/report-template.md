# <Title: states the question or the finding, not a slogan>

- **Date:** YYYY-MM-DD
- **Report type:** <Benchmark study | Evidence review | Technical investigation | Technical guide>
- **Keywords:** <3-6 terms, comma-separated>
- **Data collected:** <fetch / run dates; "Inputs as supplied by caller, not independently verified" in Trusted-Input Mode>

## Abstract

**Background.** <1-2 sentences: why the question matters.>
**Objective.** <The research question(s), stated so they can be answered.>
**Methods.** <Sources and how they were found, runs and how they were measured, the analysis.>
**Results.** <The key numbers, each with its source [1].>
**Conclusions.** <The answer, in one or two sentences. The docs site shows this paragraph's first sentence as the report summary.>

## 1. Introduction

<Context and motivation. Prior work or reports this builds on [2]. End with the questions:>

- **RQ1.** <question>
- **RQ2.** <question>

## 2. Methods

### 2.1 Sources and search strategy

<Where the evidence came from, search terms, fetch dates, what was excluded and why.>

### 2.2 Evidence classification

<Each result is one of: measured (own run), third-party benchmark, vendor-reported, community report, derived (computed from the others). State which types this report uses.>

### 2.3 Experimental setup

<Hardware, versions, harness, number of runs, task fixtures. Omit for pure evidence reviews.>

### 2.4 Analysis

<Formula for every derived metric (e.g. "blend = 3:1 in:out") and the statistical test, if any.>

## 3. Results

### 3.1 <Result for RQ1>

Table 1. <Caption: what the table shows and the evidence type.>

| <col> | <col> | <col> |
| --- | ---: | ---: |
|  |  |  |

<What was observed, with its source [3]. Interpretation belongs in the Discussion.>

### 3.2 <Result for RQ2>

## 4. Discussion

### 4.1 Principal findings

<Answer each RQ in turn, hedged to the strength of the evidence.>

### 4.2 Comparison with prior work

<Agreement or disagreement with other sources [2] and likely reasons. Untested explanations are labeled ASSUMPTION:.>

### 4.3 Practical implications

<The recommendation or decision for the reader, with its conditions.>

## 5. Limitations

- <Threats to validity: sample size, single-source numbers, staleness, harness bias, ceiling effects.>

## 6. Conclusion

<One paragraph. No new evidence.>

## Data and code availability

<Repo paths to harnesses, raw data or scripts. Omit the section if none.>

## References

[1] <Publisher, Title (date)>: <https://example.com/source-1>
[2] <Publisher, Title (date)>: <https://example.com/source-2>
[3] <Publisher, Title (date)>: <https://example.com/source-3>
