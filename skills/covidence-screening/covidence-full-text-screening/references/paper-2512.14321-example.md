# Worked Example: arXiv:2512.14321

**Title**: Multi-Agent Medical Decision Consensus Matrix System: An Intelligent Collaborative Framework for Oncology MDT Consultations  
**Authors**: Xudong Han, Xianglun Gao, Xiaoyi Qu, Zhenyu Yu  
**Submitted**: Dec 16 2025, cs.MA  
**PDF**: https://arxiv.org/pdf/2512.14321  

## Verdict: INCLUDE

### POPULATION - PASS
Applied to oncology MDT consultation workflows. Validated on 50 real anonymized cancer cases from 3 cancer centers, evaluated by 12 clinical experts. Also evaluated on 5 medical benchmarks but the primary validation is clinical.

### CONCEPT - PASS
7 distinct fine-tuned LLM agents (Qwen-2.5-72B per role): oncologist, radiologist, nurse, psychologist, patient advocate, nutritionist, rehabilitation therapist. Each has a separate knowledge base, role-specific prompting, separate preference scoring function, and self-assessed confidence score. Agents engage in up to 3 rounds of deliberation with a consensus matrix (Kendall's W). Discordant agents receive targeted feedback and reconsider. RL optimizer (PPO/DQN/Q-Learning) coordinates inter-agent interaction modeled as an MDP. Genuine hierarchical/collaborative multi-agent pipeline.

### CONTEXT - PASS
Clinical decision support for oncology treatment planning. Simulates the MDT consultation workflow — a recognized gold-standard clinical process. Not drug discovery, not genomics, not open-domain chatbot.

### OTHER - PASS
English. arXiv preprint, accessible full text.

## Quality Flag (for extraction stage)
Reference list contains mismatched citations — several refs (e.g. refs 5-8) cite unrelated ML/vision papers (V-PETL bench, MMAP cross-domain learning) interspersed among MDT clinical literature. Ref 38 (TeamMedAgents, cited as arXiv:2508.08115) postdates the paper's Dec 2025 submission, which is chronologically impossible — likely a placeholder or fabricated citation. Worth flagging for quality assessment at data extraction stage. Does not affect inclusion.

## Key numbers for extraction
- Agents: 7 (oncologist, radiologist, nurse, psychologist, patient advocate, nutritionist, rehabilitation therapist)
- Base model: Qwen-2.5-72B (8-bit quantized, 36GB VRAM/agent)
- Consensus metric: Kendall's W (threshold 0.7)
- RL methods: Q-Learning, PPO (best), DQN
- Benchmarks: MedQA, PubMedQA, DDXPlus, MedBullets, SymCat
- Avg accuracy: 87.5% vs 83.8% strongest baseline (TeamMedAgents)
- Consensus rate: 89.3%, mean Kendall's W = 0.823
- Expert rating: 8.9/10 (50 real cases, 12 experts)
- Clinical domain: oncology MDT
