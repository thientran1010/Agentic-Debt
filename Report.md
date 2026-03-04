# Report — Temporal Technical Debt Accumulation in LLM Multi‑Agent Workflows (ChatDev Traces)

Generated: 2026-03-04

## Research Question (Q1)
**How does technical debt accumulate in LLM‑MA workflows for software development tasks?**

This report shifts analysis from “final-state” evaluation to **temporal** evaluation by tracking code‑smell deltas across sequential workflow phases (post‑coding → post‑review → final). The goal is to identify **where** debt is introduced/removed, **what kinds** of debt dominate, and **how** verification effort relates to debt accumulation.

## Data & Method

### Inputs
- **Traces**: `agent_debt/traces/*/*.log` (multi‑phase chat + embedded code blocks).
- **Token usage**: `agent_debt/data/ChatDev_GPT-5_Trace_Analysis_Results.json` (bucketed into Design/Coding/Code Review/Testing/Documentation).
- **Smell detector**: **DPy (DesignitePython)** run on reconstructed snapshots.

### Snapshots (per project)
- **post_coding**: Python files reconstructed from code blocks after the Coding phase.
- **post_review**: post_coding + updates from CodeReviewModification messages.
- **final**: Python files from the final on-disk project directory.

### Smell layers and derived metrics
DPy returns four smell layers; we aggregate them into three analysis “granularities”:
- **Architecture smells** (DPy)
- **Design smells** (DPy)
- **Implementation smells** (DPy)
- **ML smells** (DPy)

Derived:
- **Coarse smells** = architecture + design
- **Fine smells** = implementation + ML
- **Total smells** = coarse + fine

Additional metrics:
- **Diversity** = number of **unique smell types** present (coarse/fine/total).
- **Density** = smells per KLOC, where KLOC uses **non‑empty LOC** in the reconstructed snapshot (per phase).

### Phase-to-phase deltas
For each project and smell metric:
- **Δreview** = post_review − post_coding
- **Δfinal** = final − post_review
- **Δtotal** = final − post_coding

### Reproduce
Run the analysis and write structured results to JSON:
```bash
python3 agent_debt/scripts/temporal_debt_report.py \
  --out-json agent_debt/data/temporal_debt_results.json
```

All tables below are computed from: `agent_debt/data/temporal_debt_results.json`.

## Results (Quantitative)

### Dataset overview
| Item | Value |
| :-- | --: |
| Total projects (traces) | 30 |
| Python-supported projects | 28 |
| Non-Python projects | 2 (CandyCrush, Tetris) |
| Code review cycles per project | 3 (fixed across projects) |
| Test cycles per project | mean 0.54, median 0, max 3 |
| Code review tokens (per project) | mean 72982, median 67044, Q1 61370, Q3 85121 |
| Testing tokens (per project) | mean 5863, median 0, Q1 0, Q3 10023 |

**Important constraint:** because **review cycles are fixed (3 for all projects)**, we cannot test whether “more review iterations” correlates with more debt (no variance). We instead use **token volume** as a proxy for verification effort.

### Where the smells live (final snapshot)
| Smell layer | Total count @Final | Projects with >0 (n=28) |
| :-- | --: | --: |
| Architecture | 0 | 0 |
| Design | 12 | 10 |
| Implementation | 1010 | 28 |
| ML | 0 | 0 |

Interpretation: the measurable debt signal in this dataset is **overwhelmingly fine‑grained implementation debt** (with ML + architecture smells absent and design smells rare).

### Mean smell volume by phase (Python projects, n=28)
| Metric | Post-coding | Post-review | Final |
| :-- | --: | --: | --: |
| Coarse smells (arch+design) | 0.43 | 0.43 | 0.43 |
| Fine smells (impl+ML) | 35.25 | 35.32 | 36.07 |
| Total smells | 35.68 | 35.75 | 36.50 |

**Observation:** coarse smell volume is flat, while fine (implementation) smells drift upward.

### Smell deltas (mean/median and positive-rate)
| Granularity | Δreview mean | Δreview median | P(Δreview>0) | Δfinal mean | Δfinal median | P(Δfinal>0) | Δtotal mean | Δtotal median | P(Δtotal>0) |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| coarse | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0.0% |
| fine | 0.07 | 1.00 | 53.6% | 0.75 | 0.00 | 25.0% | 0.82 | 2.00 | 64.3% |
| total | 0.07 | 1.00 | 53.6% | 0.75 | 0.00 | 25.0% | 0.82 | 2.00 | 64.3% |

Key takeaways:
- **Code review is the most consistently “debt‑injecting” step**: median Δreview(fine)=+1 and 53.6% of projects increase.
- **Final step is usually inert**: median Δfinal(fine)=0 and only 25% of projects increase (many projects have 0 testing tokens).
- **Coarse deltas are 0 everywhere** (no measured architecture/design smell changes across phases).

### Fine delta distributions (volatility)
| Delta | Mean | Median | Stdev | Min | Q1 | Q3 | Max |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| review | 0.07 | 1.00 | 6.21 | -20.00 | -0.25 | 3.00 | 9.00 |
| final | 0.75 | 0.00 | 5.05 | -10.00 | 0.00 | 0.25 | 21.00 |
| total | 0.82 | 2.00 | 6.00 | -17.00 | 0.00 | 4.25 | 9.00 |

Interpretation: even when the **mean drift is small**, the process is **high‑variance**: verification can either *reduce* smells substantially (e.g., -20) or *add* a large spike (e.g., +21).

### Diversity (unique smell types) and density (smells/KLOC)
Phase means:
| Metric | Post-coding | Post-review | Final |
| :-- | --: | --: | --: |
| Coarse diversity (unique types) | 0.39 | 0.39 | 0.39 |
| Fine diversity (unique types) | 3.86 | 4.07 | 4.11 |
| Total diversity (unique types) | 4.25 | 4.46 | 4.50 |

| Metric | Post-coding | Post-review | Final |
| :-- | --: | --: | --: |
| Coarse density (smells/KLOC) | 0.75 | 0.71 | 0.74 |
| Fine density (smells/KLOC) | 71.53 | 68.80 | 70.11 |
| Total density (smells/KLOC) | 72.29 | 69.51 | 70.86 |

Final distributions (robust view of skew/outliers):
| Metric | Mean | Median | Stdev | Min | Q1 | Q3 | Max |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| Total smells @Final (count) | 36.50 | 26.00 | 31.88 | 10.00 | 16.00 | 46.25 | 139.00 |
| Total density (smells/KLOC) @Final | 70.86 | 56.24 | 68.71 | 16.71 | 35.62 | 88.72 | 383.98 |
| Total diversity (unique types) @Final | 4.50 | 4.00 | 1.71 | 2.00 | 3.00 | 6.00 | 9.00 |

Interpretation: debt is **heavy‑tailed**. Most projects cluster around moderate density, but a small number of traces become extreme outliers (max 383.98 smells/KLOC).

### Smell composition (what dominates)
Fine smells at final (implementation‑dominated):
| Smell type (fine) | Count @Final | Share of fine smells |
| :-- | --: | --: |
| Magic number | 600 | 59.4% |
| Long statement | 281 | 27.8% |
| Complex method | 75 | 7.4% |
| Empty catch block | 23 | 2.3% |
| Long parameter list | 9 | 0.9% |
| Long method | 9 | 0.9% |
| Long identifier | 7 | 0.7% |
| Complex conditional | 6 | 0.6% |

Coarse smells at final (design‑only; architecture = 0 everywhere in this dataset):
| Smell type (coarse/design) | Count @Final | Share of coarse smells |
| :-- | --: | --: |
| Feature envy | 4 | 33.3% |
| Multifaceted abstraction | 2 | 16.7% |
| Insufficient modularization | 2 | 16.7% |
| Deficient encapsulation | 2 | 16.7% |
| Wide hierarchy | 1 | 8.3% |
| Broken modularization | 1 | 8.3% |

Debt injection by smell type (net increases aggregated across all projects):

**Fine smells increased from post-coding → post-review**
| Smell type | Net increase (all projects) |
| :-- | --: |
| Long statement | 21 |
| Empty catch block | 10 |
| Complex method | 4 |
| Long parameter list | 1 |

**Fine smells increased from post-review → final**
| Smell type | Net increase (all projects) |
| :-- | --: |
| Magic number | 11 |
| Long statement | 10 |
| Complex method | 1 |
| Empty catch block | 1 |
| Long method | 1 |

Interpretation: the pipeline’s accumulated debt is primarily the kind introduced by **rapid patching**:
- *Magic numbers* and *long statements* suggest “get it working” fixes with literals and increasingly complex control flow.
- *Empty catch blocks* suggest suppression of errors to stabilize runtime behavior.

## Project-Level Findings

### Outliers (final)
Top density projects:
| Project | Total@Final | LOC@Final | Smells/KLOC@Final |
| :-- | --: | --: | --: |
| Sudoku | 139 | 362 | 383.98 |
| Chess | 99 | 684 | 144.74 |
| DouDizhuPoker | 114 | 1173 | 97.19 |
| Gomoku | 46 | 478 | 96.23 |
| StrandsGame | 47 | 490 | 95.92 |
| Pong | 45 | 491 | 91.65 |
| Tiny Rouge | 48 | 527 | 91.08 |
| StrandsNYT | 51 | 580 | 87.93 |

Top total smell counts:
| Project | Total@Final | Smells/KLOC@Final | Unique@Final |
| :-- | --: | --: | --: |
| Sudoku | 139 | 383.98 | 5 |
| DouDizhuPoker | 114 | 97.19 | 7 |
| Chess | 99 | 144.74 | 9 |
| StrandsNYT | 51 | 87.93 | 6 |
| Tiny Rouge | 48 | 91.08 | 4 |
| Checkers | 47 | 71.87 | 6 |
| StrandsGame | 47 | 95.92 | 6 |
| Gomoku | 46 | 96.23 | 3 |

Top diversity projects:
| Project | Unique@Final | Total@Final | Smells/KLOC@Final |
| :-- | --: | --: | --: |
| Chess | 9 | 99 | 144.74 |
| DouDizhuPoker | 7 | 114 | 97.19 |
| SnakeGame | 7 | 30 | 60.36 |
| BudgetTracker | 6 | 21 | 28.61 |
| Checkers | 6 | 47 | 71.87 |
| MonopolyGo | 6 | 28 | 34.44 |
| StrandsGame | 6 | 47 | 95.92 |
| StrandsNYT | 6 | 51 | 87.93 |

### Biggest phase-to-phase swings
Δreview (fine) — largest increases:
| Project | Δreview (fine) | Fine@Coding | Fine@Review | ReviewTokens |
| :-- | --: | --: | --: | --: |
| TheCrossword | 9 | 15 | 24 | 74258 |
| GoldMiner | 7 | 35 | 42 | 69538 |
| DouDizhuPoker | 6 | 107 | 113 | 145032 |
| DetectPalindromes | 5 | 17 | 22 | 62109 |
| SnakeGame | 4 | 25 | 29 | 61655 |

Δreview (fine) — largest decreases:
| Project | Δreview (fine) | Fine@Coding | Fine@Review | ReviewTokens |
| :-- | --: | --: | --: | --: |
| Pong | -20 | 44 | 24 | 55452 |
| Mastermind | -17 | 29 | 12 | 43283 |
| ConnectionsNYT | -7 | 26 | 19 | 67023 |
| TextBasedSpaceInvaders | -5 | 25 | 20 | 56402 |
| Tiny Rouge | -2 | 44 | 42 | 73776 |

Δfinal (fine) — largest increases:
| Project | Δfinal (fine) | Fine@Review | Fine@Final | TestTokens |
| :-- | --: | --: | --: | --: |
| Pong | 21 | 24 | 45 | 9369 |
| Checkers | 6 | 41 | 47 | 10710 |
| Tiny Rouge | 5 | 42 | 47 | 0 |
| FlappyBird | 4 | 25 | 29 | 12145 |
| StrandsNYT | 2 | 48 | 50 | 28561 |

Δfinal (fine) — decreases (only projects with negative Δfinal):
| Project | Δfinal (fine) | Fine@Review | Fine@Final | TestTokens |
| :-- | --: | --: | --: | --: |
| Chess | -10 | 106 | 96 | 19656 |
| ConnectionsNYT | -9 | 19 | 10 | 9794 |

### Design-smell presence (rare, stable)
Only 10/28 Python projects have any design smells; **architecture smells are 0** throughout.
| Project | DesignSmells@Final | TopDesignSmells@Final |
| :-- | --: | --: |
| Chess | 3 | Insufficient modularization×2, Feature envy×1 |
| BudgetTracker | 1 | Multifaceted abstraction×1 |
| DouDizhuPoker | 1 | Feature envy×1 |
| FibonacciNumbers | 1 | Multifaceted abstraction×1 |
| MonopolyGo | 1 | Wide hierarchy×1 |
| SnakeGame | 1 | Feature envy×1 |
| StrandsGame | 1 | Deficient encapsulation×1 |
| StrandsNYT | 1 | Feature envy×1 |
| Tiny Rouge | 1 | Broken modularization×1 |
| TriviaQuiz | 1 | Deficient encapsulation×1 |

## Discussion (Interpretation for Q1)

### 1) Debt accumulation is phase-dependent and mostly fine-grained
Across the pipeline, measurable debt changes concentrate in **implementation smells**:
- **Coarse smells are effectively “frozen”** (Δ=0), and architecture smells never appear in the detector output.
- **Fine smells drift upward** from post-coding to final (mean +0.82), but with high volatility.

This supports a temporal mechanism in which verification largely operates through **local edits** (patching) rather than structural refactoring that would change architecture/design smell signals.

### 2) The verification loop is a major carrier of debt mutation (not only injection)
The review step has a small positive drift (median +1) but large dispersion (min -20, max +9). This indicates:
- Some reviews do cleanups/refactors that remove smells (large negative deltas).
- Others introduce debt while fixing correctness issues (positive deltas).

The final step is frequently inert (median 0), consistent with the token data where **testing tokens have median 0** (many traces do not execute meaningful testing loops).

### 3) Smell composition matches “rapid fix” failure modes
Across projects, two smell types dominate:
- **Magic number (59.4%)** and **Long statement (27.8%)** account for ~87% of fine smells at final.
- During review, the net increases are driven mostly by **Long statement** and **Empty catch block**.
- When final changes occur, they are often dominated by **Magic number** and **Long statement** increases.

This aligns with an accumulation pattern where agents converge on functional behavior using quick fixes (literals, added conditional branches, error suppression), which increases implementation-level debt even when functional correctness improves.

### 4) Verification effort (tokens) weakly–moderately correlates with debt change
Two dataset-level correlations (Pearson, n=28):
- `corr(code_review_tokens, Δreview implementation smells) = 0.319`
- `corr(testing_tokens, Δfinal implementation smells) = -0.210`

Interpretation:
- More code-review activity tends to coincide with **slightly more fine-grained debt introduced during review** (possibly because more review time leads to more incremental patches).
- More testing activity weakly coincides with **slightly less fine-grained debt introduced during final**, but the testing signal is sparse (median testing tokens = 0), so this should be treated as a weak indicator.

### 5) Mini case studies (quantitative + temporal narrative)
- **Sudoku (high density, stable debt)**: 139 fine smells at all snapshots; 123 are **Magic number**; density 383.98 smells/KLOC. This suggests a “debt‑heavy baseline” that is not corrected by verification when no testing loop occurs.
- **Pong (high volatility across phases)**: fine smells 44 → 24 → 45, driven by **Magic number** swings (28 → 12 → 28). Review reduces debt sharply, but final changes reintroduce it (likely via last‑minute bug fixes).
- **ConnectionsNYT (consistent cleanup)**: fine smells 26 → 19 → 10; **Magic number** drops (11 → 6 → 1) and **Long statement** drops (13 → 10 → 7). This is an example where verification removes fine-grained debt rather than accumulating it.

### 6) What “accumulation” looks like in LLM‑MA pipelines (mechanistic summary)
In these traces, technical debt accumulation is best described as:
- **Front‑loaded** by the initial coding step (large baseline smell volume),
- **Mutated** during verification (review introduces or removes fine smells),
- **Often not structurally addressed** (coarse smells stay constant; architecture smells absent),
- **Heavy‑tailed** across projects (a few traces become extreme density outliers).

## Limitations / Threats to Validity
- **Detector scope**: DPy may under-detect architectural issues in small projects; architecture smells are 0 here, which could reflect tool sensitivity rather than true absence.
- **Smell meaning**: some “magic numbers” are expected in games (e.g., screen sizes, colors). Counts still reflect maintainability risk, but not every instance is equally harmful.
- **Snapshot reconstruction**: code is reconstructed from chat logs and a heuristic replacement threshold; missing/partial code blocks could affect counts.
- **Token usage as effort proxy**: tokens are noisy; correlation ≠ causation.
- **Testing sparsity**: many projects have 0 testing tokens, limiting inference about the Testing phase’s causal role.

## Conclusion
In this ChatDev trace dataset (28 Python projects), technical debt accumulation is **not uniform across phases**:
- Debt signals are **dominated by fine-grained implementation smells**, especially **Magic number** and **Long statement**.
- The **code review phase** is the main locus of temporal change (median +1 fine smell), with high variance (can both reduce and increase debt).
- The **final/testing phase** often shows no change (median 0) due to sparse testing activity.
- Coarse (architecture+design) debt signals remain **stable**, suggesting verification prioritizes correctness over structural improvements (or that coarse signals are not captured by the detector for these traces).

## Appendix A — Per-project table (Python projects, sorted by final density)
| Project | Fine@Coding | Fine@Review | Fine@Final | Δreview | Δfinal | Δtotal | Unique@Final | Smells/KLOC@Final | ReviewTokens | TestTokens |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| Sudoku | 139 | 139 | 139 | 0 | 0 | 0 | 5 | 383.98 | 87149 | 0 |
| Chess | 105 | 106 | 96 | 1 | -10 | -9 | 9 | 144.74 | 110653 | 19656 |
| DouDizhuPoker | 107 | 113 | 113 | 6 | 0 | 6 | 7 | 97.19 | 145032 | 0 |
| Gomoku | 45 | 45 | 46 | 0 | 1 | 1 | 3 | 96.23 | 66926 | 8433 |
| StrandsGame | 46 | 46 | 46 | 0 | 0 | 0 | 6 | 95.92 | 98286 | 0 |
| Pong | 44 | 24 | 45 | -20 | 21 | 1 | 4 | 91.65 | 55452 | 9369 |
| Tiny Rouge | 44 | 42 | 47 | -2 | 5 | 3 | 4 | 91.08 | 73776 | 0 |
| StrandsNYT | 45 | 48 | 50 | 3 | 2 | 5 | 6 | 87.93 | 95263 | 28561 |
| GoldMiner | 35 | 42 | 42 | 7 | 0 | 7 | 5 | 83.17 | 69538 | 10935 |
| ConnectFour | 26 | 28 | 28 | 2 | 0 | 2 | 3 | 77.35 | 48092 | 0 |
| Checkers | 42 | 41 | 47 | -1 | 6 | 5 | 6 | 71.87 | 83918 | 10710 |
| FlappyBird | 24 | 25 | 29 | 1 | 4 | 5 | 4 | 63.88 | 61876 | 12145 |
| 2048 | 16 | 16 | 16 | 0 | 0 | 0 | 4 | 61.54 | 65538 | 0 |
| SnakeGame | 25 | 29 | 29 | 4 | 0 | 4 | 7 | 60.36 | 61655 | 16359 |
| TextBasedSpaceInvaders | 25 | 20 | 21 | -5 | 1 | -4 | 3 | 52.11 | 56402 | 6399 |
| Wordle | 19 | 23 | 23 | 4 | 0 | 4 | 3 | 47.33 | 67066 | 0 |
| DetectPalindromes | 17 | 22 | 22 | 5 | 0 | 5 | 4 | 45.27 | 62109 | 0 |
| ReversiOthello | 16 | 16 | 16 | 0 | 0 | 0 | 3 | 40.30 | 60736 | 8630 |
| TheCrossword | 15 | 24 | 24 | 9 | 0 | 9 | 6 | 39.93 | 74258 | 0 |
| FibonacciNumbers | 9 | 9 | 9 | 0 | 0 | 0 | 3 | 39.84 | 36247 | 0 |
| TicTacToe | 10 | 13 | 13 | 3 | 0 | 3 | 2 | 36.01 | 45036 | 0 |
| MonopolyGo | 28 | 27 | 27 | -1 | 0 | -1 | 6 | 34.44 | 102882 | 0 |
| Mastermind | 29 | 12 | 12 | -17 | 0 | -17 | 3 | 29.34 | 43283 | 0 |
| BudgetTracker | 17 | 20 | 20 | 3 | 0 | 3 | 6 | 28.61 | 84999 | 0 |
| Minesweeper | 8 | 10 | 10 | 2 | 0 | 2 | 2 | 23.31 | 61582 | 0 |
| TriviaQuiz | 15 | 17 | 17 | 2 | 0 | 2 | 5 | 22.96 | 85488 | 23169 |
| ConnectionsNYT | 26 | 19 | 10 | -7 | -9 | -16 | 4 | 20.92 | 67023 | 9794 |
| EpisodeChooseYourStory | 10 | 13 | 13 | 3 | 0 | 3 | 3 | 16.71 | 73240 | 0 |

