# Building ai-please-learn: a browser lab where neural networks visibly learn games, built in 28 hours by coordinated coding agents

- **Date:** 2026-11-22
- **Report type:** Technical investigation (project report)
- **Keywords:** neuroevolution, NEAT, DQN, PPO, browser machine learning, LLM-generated environments, coding agents, omp, GitHub Pages
- **Data collected:** repository history, test runs, benchmarks and live-site checks, 2026-11-21 to 2026-11-22. All measured on the author's machine (Apple M4 Pro, Node 22) or against the live site.

## Abstract

**Background.** Code Bullet's videos [1] and ml-visualized.com [2] made it fun to watch a machine learn: a stick figure falls over a thousand times, then walks. ai-please-learn (app name EvoLab) [3, 4] tries to recreate that experience for any game. You play the game first, set the rewards, pick a learning method, and watch the networks learn. You can also describe a new game in one sentence and a language model writes it.
**Objective.** To report what was built and how well it works: whether the learners improve on every game, whether LLM-written games are playable and trainable, and how reliable this way of building was (a coordinator agent writing briefs, coding agents implementing them, independent reviewers checking the result).
**Methods.** The app was built in 135 commits over about 28 hours of wall-clock time by 38 `omp -p` coding-agent dispatches, coordinated by Hermes. Evidence comes from headless learning benchmarks (seed 1) [5], three LLM generation trials with `gpt-6-luna` [6], 341 unit tests and 51 browser tests, two rounds of parallel code review, a code-against-report fact-check, and browser checks on the live site.
**Results.** Every built-in benchmark passed its pre-set learning margin. For example, NEAT Snake's best score rose from 11.05 to 215.05 in 40 generations, and the 3D walker's from 2.37 to 275.46 in 40 generations, with a champion that walks 27.12 m without falling (measured, single seed) [5]. `gpt-6-luna` wrote 10 of 10 requested games that passed the sandbox validator in trials 2 and 3, with no repair rounds, at about $0.01 to $0.015 per batch of five [6]. The final live check passed 21 of 21. Review found 1 serious bug (fake PPO zero scores), which was fixed and verified.
**Conclusions.** ai-please-learn works as intended: all six built-in games and LLM-written games train visibly in the browser with three learning methods, and the site explains its own maths. The main open weaknesses are statistical (single-seed results, budgets that are not comparable across methods) and generated games that plateau early; both are listed with fixes on the site's Math page [7].

## 1. Introduction

Watching a learner improve is more convincing than reading a loss curve. Code Bullet's videos [1] show the learner failing in many ways before it succeeds, and ml-visualized.com [2] shows the network itself. Neither lets the viewer pick the game, change the reward, or compare methods. The goal set for this project was:

> When I was young, I often watched machine learning videos where the machine gradually learned something [...] The goal of this project is to replicate those approaches but with whatever input I have.

That goal sets three requirements: a common loop for every game (play it, set the rewards, choose the network, watch it learn), several learning methods behind that loop, and a way to add a game from a sentence. The project was also an experiment in building software unattended with coding agents.

- **RQ1.** Do NEAT, DQN and PPO, written from scratch in TypeScript, learn every built-in game in a browser?
- **RQ2.** Can an LLM write new games that pass validation and then train?
- **RQ3.** How reliable was the agent-built process, and what did review catch?
- **RQ4.** What remains weak?

## 2. Methods

### 2.1 System under study

- **Live site:** <https://laansdole.github.io/ai-please-learn/> [3].
- **Source:** the repository LaansDole/ai-please-learn [4], final commit `7f98ace`.
- **Size:** about 10,600 lines of TypeScript, with no ML library and no GPU.
- **Games:** Pong, Snake, Flappy, Car, Tetris and a 3D stick-figure walker, built on three.js and the Rapier physics engine.
- **Learners:**
  - NEAT [8]
  - DQN [9] with the Double DQN target [10]
  - PPO [11] with GAE [12]
  - Adam [13] as the optimizer
- **Language model:** `gpt-6-luna` through the OpenAI API by default, with LM Studio and Ollama as local alternatives.

### 2.2 Build process

Hermes (the coordinator) wrote a brief for each piece of work and launched `omp -p` coding agents, mostly Claude Fable 5.2 at medium effort. It watched them, verified their output, pushed, and checked the live site. The coordinator wrote no app code apart from one-line edits.

Each brief required the superpowers workflow skills (TDD and verification before completion), plus the Impeccable design skill for UI work. Reviews used independent subagents on Claude Opus 5.5.

### 2.3 Measurements

- **Learning benchmarks:** `npm run bench`, headless, seed 1, default rewards. Each benchmark asserts a fixed margin between early and late iterations [5].
- **LLM trials:** `npm run llm-trial` runs the app's own prompt, sandbox, validator and repair loop on five fixed sentences [6].
- **Tests:** Vitest unit tests and Playwright browser tests.
- **Live checks:** a scripted Chrome session in a fresh profile against the deployed site. It trains every game, runs a real generation, and checks routing, the demo video and the console.
- **Review:** 4 parallel reviewers (one per code area), then a verification reviewer on the fixes. The Math report was fact-checked separately: every equation, number and reference was checked against the source code and the papers.

### 2.4 Derived figures

Wall-clock time is the gap between the first commit (2026-11-21 17:27) and the last (2026-11-22 21:43), 28 h 16 min. It includes idle time and is not effort. LLM cost per batch is tokens multiplied by the list price on the run date, as recorded in [6].

## 3. Results

### 3.1 Learning on built-in games (RQ1)

Table 1. Headless learning benchmarks, seed 1 [5]. "Start" is the best score of the first iteration (for DQN and PPO, the mean of the early episodes or updates), "End" the best of the last five (for DQN and PPO, the late mean).

| Game | Method | Iterations | Start | End | Asserted margin | Seconds |
|---|---|---:|---:|---:|---|---:|
| Pong | NEAT | 30 | 6.54 | 33.72 | +8 | 3.4 |
| Snake | NEAT | 40 | 11.05 | 215.05 | +40 | 0.3 |
| Flappy | NEAT | 40 | 23.55 | 378.99 | +100 | 2.5 |
| Car | NEAT | 30 | 62.39 | 319.51 | +20, 2x start, 3 laps | 9.5 |
| Tetris | NEAT | 15 | 648.45 | 2429.40 | +300 | 2.4 |
| Walker (3D) | NEAT | 40 | 2.37 | 275.46 | +5, replay of at least 1.0 m | 25.3 |
| Pong | DQN | 160,000 steps | -10.61 (mean) | 11.81 (mean) | +5 | 6.1 |
| Car | PPO | 150 updates | -2.32 (mean) | 106.62 (mean) | +10 | 7.0 |

Two changes to the original spec were needed:

- **DQN Pong budget:** doubled from 80,000 to 160,000 steps, the first tuning step the spec allows. At 80,000 steps it gained only +3.1.
- **Car grip limit:** without it, the first generation already drove 7 laps flat out, so there was nothing left to learn. The fix capped grip so that corners need braking [5].

On the live site, every game trained at max speed, and every Learn header read "Still learning" within 7 to 12 s in the final check.

### 3.2 LLM-written games (RQ2)

Table 2. LLM generation trials with `gpt-6-luna`, five fixed sentences per run [6].

| Run | Change before the run | Passed | Repairs | Mean latency per call | Cost |
|---|---|---:|---:|---:|---:|
| 1 | none | 0/5 | 0 | 1.7 s | n/a |
| 2 | client retries without `temperature` | 5/5 | 0 | 31.4 s | $0.0104 |
| 3 | learnability check, richer prompt | 5/5 | 0 | 43.4 s | $0.0144 |

- **Run 1:** stopped at the first sentence, because the API rejects a non-default `temperature` for this model. Since then the app sends no temperature at all.
- **Run 3:** added a learnability check. Random play must not reach the episode ceiling, and scores must vary.
- **Live generations:** in the browser, generations took 39 s to 163 s, and every generated game opened, played and trained.
- **NEAT on generated games:** Apple Basket games reached records of 250, 80.4 and 19.9 in three separate generations of the same sentence (demo recordings), and often stalled early.

### 3.3 Process and review (RQ3)

- **Volume:** 38 coding-agent dispatches produced 135 commits (55 `feat`, 38 `fix`). 16 Pages deploys ran and all succeeded.
- **Tests at the end:** 341 unit tests and 51 browser tests. One browser test, a responsiveness timing check, failed while another app was using most of the CPU and GPU. It was not retested on an idle machine.
- **Review round 2:** 4 reviewers found 1 serious bug and 14 smaller ones. The serious bug: PPO updates in which no episode finished were recorded as score 0, which faked a record of 0 and a "Stalled" verdict. A verification reviewer confirmed 20 of 21 items fixed, plus one partly fixed; its 4 small leftovers were then fixed.
- **Math report fact-check:** 165 claims and all 45 cited file paths were checked against the code. It found 0 wrong equations or numbers and 14 wording or citation issues, all fixed. It also showed that a benchmark label ("rollout 128") was a typo for 256.
- **Failures caught by checking rather than by agents:**
  - two harness bugs in the live checker
  - a demo recording scrolled past the new header, which was discarded and recorded again
  - a capped text width that came back twice, until every cap was removed
- **Model choice:** a later change picks between Claude Opus 5.5 and Fable 5.2 for each brief with a Jev judge [14]. It matched hand labels on 14 of 15 of this project's briefs.

### 3.4 What the site offers

The live site [3] has six tabs:

- **Gallery:** the six games and any generated ones.
- **Create:** describe a game in a sentence.
- **Demo:** a 5-minute recorded run with chapters [15].
- **Math:** a researcher-facing report on every learner, with 220 typeset equations and an 11-item "Room for improvement" table [7].
- **Settings:** OpenAI, LM Studio or Ollama.
- **GitHub:** a link to the repository.

The interface uses a light "Field guide" design chosen by the owner from three mockups. Text fills its container everywhere, at the owner's request.

## 4. Discussion

### 4.1 Answers to the research questions

- **RQ1:** yes, within the limits of one seed. All six games improve by the asserted margins. The 3D walker, the hardest case, learns to walk 27 m.
- **RQ2:** yes. After two client and prompt fixes, all 10 requested games passed validation without repairs. They are trainable but often easy: records stall early, so validating a game does not make it interesting.
- **RQ3:** the agent-built process produced a working, tested product quickly. Independent review and live checks were essential: the one serious bug, two harness bugs and a recurring layout regression would have shipped without them.
- **RQ4:** see 4.2 and Section 5.

### 4.2 Practical implications

- The Math page's improvement list [7] is the agenda: multi-seed reporting with confidence intervals [16], budgets compared in environment steps, observation and reward normalisation, and a stronger learnability check.
- For generated games, the generator should push difficulty higher (ramping, sparse rewards), not only check that random play fails.
- A medical spin-off is specified but not built: learning DynamiClinic's single-vs-team routing decision from recorded benchmark results. It is a research prototype only.

## 5. Limitations

- **Single seed:** every benchmark number comes from seed 1, plus a few extra seeds named in [5]. No confidence intervals were computed, so the numbers show learning happens, not how reliably.
- **Budgets are not comparable:** NEAT counts generations, DQN steps and PPO updates. Table 1 does not compare the methods with each other.
- **LLM results:** one model, five sentences per run, three runs. Generation time on the live site varied from 39 s to 163 s, depending on load.
- **Self-built and self-checked:** the reviewers and fact-checkers were also language models. Their checks were tied to code and tests, but no human code review took place.
- **Timing test not resolved:** one browser test failed under heavy machine load and was not retested on an idle machine.
- **Wall-clock time is not effort:** the 28 hours include idle and overnight time.

## 6. Conclusion

ai-please-learn works: six built-in games and LLM-written games train visibly in the browser with NEAT, DQN and PPO, and the site documents its own maths and weaknesses. The next useful work is statistical rigour (several seeds, intervals, equal budgets) and harder generated games.

## Data and code availability

- **Source and benchmarks:** LaansDole/ai-please-learn [4]. Benchmarks: `docs/benchmarks.md` [5]. LLM trials: `docs/llm-trial/RESULTS.md` [6].
- **Report on the maths:** `docs/math.md`, also shown on the Math page [7].
- **Demo runbook:** `docs/demo/runbook/README.md` [15].

## References

[1] Code Bullet, YouTube channel: <https://www.youtube.com/@CodeBullet>
[2] ml-visualized.com: <https://ml-visualized.com/>
[3] ai-please-learn (EvoLab), live site: <https://laansdole.github.io/ai-please-learn/>
[4] LaansDole/ai-please-learn, source repository: <https://github.com/LaansDole/ai-please-learn>
[5] Learning benchmarks, docs/benchmarks.md: <https://github.com/LaansDole/ai-please-learn/blob/main/docs/benchmarks.md>
[6] Concept from text: trials against a real LLM, docs/llm-trial/RESULTS.md: <https://github.com/LaansDole/ai-please-learn/blob/main/docs/llm-trial/RESULTS.md>
[7] How the learners work (Math page): <https://laansdole.github.io/ai-please-learn/math>
[8] Stanley, K. O. and Miikkulainen, R. (2002). Evolving Neural Networks through Augmenting Topologies. Evolutionary Computation 10(2): <https://doi.org/10.1162/106365602320169811>
[9] Mnih, V. et al. (2015). Human-level control through deep reinforcement learning. Nature 518: <https://doi.org/10.1038/nature14236>
[10] van Hasselt, H., Guez, A. and Silver, D. (2016). Deep Reinforcement Learning with Double Q-learning. AAAI: <https://arxiv.org/abs/1509.06461>
[11] Schulman, J. et al. (2017). Proximal Policy Optimization Algorithms: <https://arxiv.org/abs/1707.06347>
[12] Schulman, J. et al. (2016). High-Dimensional Continuous Control Using Generalized Advantage Estimation. ICLR: <https://arxiv.org/abs/1506.02438>
[13] Kingma, D. P. and Ba, J. (2015). Adam: A Method for Stochastic Optimization. ICLR: <https://arxiv.org/abs/1412.6980>
[14] Does TypeSafe Jev deliver fast, calibrated structured decisions? A first-hands evaluation (2026-09-19): <https://laansdole.github.io/my-hermes-skills/reports/2026-09/2026-09-19-typesafe-jev-first-hands.html>
[15] Demo runbook and video: <https://laansdole.github.io/ai-please-learn/demo/>
[16] Agarwal, R. et al. (2021). Deep Reinforcement Learning at the Edge of the Statistical Precipice. NeurIPS: <https://arxiv.org/abs/2108.13264>
