# Report — Temporal Technical Debt Accumulation in LLM Multi‑Agent Workflows (ChatDev Traces)

## Research Question (Q1)
**How does technical debt accumulate in LLM‑MA workflows for software development tasks?**

This report shifts analysis from “final-state” evaluation to **temporal** evaluation by tracking code‑smell deltas across sequential workflow phases (post‑coding → post‑review → final). The goal is to identify **where** debt is introduced/removed and **what kinds** of debt dominate.

## Data & Method

### Inputs 
- **Traces**: `agent_debt/traces/*/*.log` (multi‑phase chat + embedded code blocks).
- **Token usage (proxy)**: `agent_debt/data/ChatDev_GPT-5_Trace_Analysis_Results.json` (used only to proxy verification effort; see Discussion §4).
- **Smell detector**: **DPy (DesignitePython)** run on reconstructed snapshots.

### Snapshots (per project) 
- **post_coding**: Python files reconstructed from code blocks after the Coding phase.
- **post_review**: post_coding + updates from CodeReviewModification messages.
- **final**: Python files from the final on-disk project directory.

### Smell layers and derived metrics 
DPy smell layers used in this analysis:
- **Architecture smells** (DPy)
- **Design smells** (DPy)
- **Implementation smells** (DPy)

Derived:
- **Coarse smells** = architecture + design
- **Fine smells** = implementation
- **Total smells** = coarse + fine

Additional metrics:
- **Diversity** = number of **unique smell types** present (coarse/fine/total).
- **Density** (as used in this report) = **smell count** (not normalized by LOC/KLOC).

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

Token correlations (Discussion §4) use `agent_debt/data/ChatDev_GPT-5_Trace_Analysis_Results.json` (override with `--token-json`).

DPy outputs are cached under `agent_debt/data/processed_data/temporal_debt/`. To force recomputation, add `--force-dpy`.

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

**Constraint:** code review cycles are fixed (3 for all projects), so we cannot test whether “more review iterations ⇒ more debt” using this dataset (no variance). We instead use **token volume** (Code Review / Testing tokens) as a proxy for verification effort.

### Where the smells live (final snapshot)
| Smell layer | Total count @Final | Projects with >0 (n=28) |
| :-- | --: | --: |
| Architecture | 0 | 0 |
| Design | 12 | 10 |
| Implementation | 1010 | 28 |

Interpretation: the measurable debt signal here is dominated by **fine‑grained implementation debt** (architecture smells are absent; design smells are rare).

### Mean smell volume by phase (Python projects, n=28)
| Metric | Post-coding | Post-review | Final |
| :-- | --: | --: | --: |
| Coarse smells (arch+design) | 0.43 | 0.43 | 0.43 |
| Fine smells (implementation) | 35.25 | 35.32 | 36.07 |
| Total smells | 35.68 | 35.75 | 36.50 |

### Smell deltas (mean/median and positive-rate)
| Granularity | Δreview mean | Δreview median | P(Δreview>0) | Δfinal mean | Δfinal median | P(Δfinal>0) | Δtotal mean | Δtotal median | P(Δtotal>0) |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| coarse | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0.0% | 0.00 | 0.00 | 0.0% |
| fine | 0.07 | 1.00 | 53.6% | 0.75 | 0.00 | 25.0% | 0.82 | 2.00 | 64.3% |
| total | 0.07 | 1.00 | 53.6% | 0.75 | 0.00 | 25.0% | 0.82 | 2.00 | 64.3% |

Key takeaways:
- **Review** is the main locus of change: median Δreview(fine)=+1 and 53.6% of projects increase.
- **Final** is often inert: median Δfinal(fine)=0 and only 25% of projects increase.
- **Coarse deltas are 0** throughout (no measured architecture/design changes across phases).

### Fine delta distributions (volatility)
| Delta | Mean | Median | Stdev | Min | Q1 | Q3 | Max |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| review | 0.07 | 1.00 | 6.21 | -20.00 | -0.25 | 3.00 | 9.00 |
| final | 0.75 | 0.00 | 5.05 | -10.00 | 0.00 | 0.25 | 21.00 |
| total | 0.82 | 2.00 | 6.00 | -17.00 | 0.00 | 4.25 | 9.00 |

Interpretation: even when mean drift is small, the process is **high‑variance**: verification can *reduce* smells substantially or introduce large spikes.

### Diversity (unique smell types)
Phase means:
| Metric | Post-coding | Post-review | Final |
| :-- | --: | --: | --: |
| Coarse diversity (unique types) | 0.39 | 0.39 | 0.39 |
| Fine diversity (unique types) | 3.86 | 4.07 | 4.11 |
| Total diversity (unique types) | 4.25 | 4.46 | 4.50 |

Final distribution:
| Metric | Mean | Median | Stdev | Min | Q1 | Q3 | Max |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| Total diversity (unique types) @Final | 4.50 | 4.00 | 1.71 | 2.00 | 3.00 | 6.00 | 9.00 |

### Density (smell count; not normalized)
Final distributions:
| Metric (smell count) | Mean | Median | Stdev | Min | Q1 | Q3 | Max |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| Coarse smells @Final | 0.43 | 0.00 | 0.69 | 0.00 | 0.00 | 1.00 | 3.00 |
| Fine smells @Final | 36.07 | 25.50 | 31.62 | 9.00 | 16.00 | 46.00 | 139.00 |
| Total smells @Final | 36.50 | 26.00 | 31.88 | 10.00 | 16.00 | 46.25 | 139.00 |

Interpretation: smell counts are **heavy‑tailed** (max 139), with most projects clustering around modest totals and a few extreme outliers.

### Smell composition (what dominates)
Fine smells at final (implementation):
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

Coarse smells at final (design-only; architecture = 0 everywhere in this dataset):
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

Interpretation: debt changes are dominated by smells typical of **rapid patching** (literals, longer statements, error suppression).

## Project-Level Findings

### Outliers by total smell count (final)
| Project | Fine@Final | Coarse@Final | Total@Final | Unique@Final |
| :-- | --: | --: | --: | --: |
| Sudoku | 139 | 0 | 139 | 5 |
| DouDizhuPoker | 113 | 1 | 114 | 7 |
| Chess | 96 | 3 | 99 | 9 |
| StrandsNYT | 50 | 1 | 51 | 6 |
| Tiny Rouge | 47 | 1 | 48 | 4 |
| Checkers | 47 | 0 | 47 | 6 |
| StrandsGame | 46 | 1 | 47 | 6 |
| Gomoku | 46 | 0 | 46 | 3 |
| Pong | 45 | 0 | 45 | 4 |
| GoldMiner | 42 | 0 | 42 | 5 |

### Top diversity projects (final)
| Project | Unique@Final | Total@Final |
| :-- | --: | --: |
| Chess | 9 | 99 |
| DouDizhuPoker | 7 | 114 |
| SnakeGame | 7 | 30 |
| BudgetTracker | 6 | 21 |
| Checkers | 6 | 47 |
| MonopolyGo | 6 | 28 |
| StrandsGame | 6 | 47 |
| StrandsNYT | 6 | 51 |
| TheCrossword | 6 | 24 |
| GoldMiner | 5 | 42 |

### Biggest phase-to-phase swings (fine smells)
Δreview (fine) — largest increases:
| Project | Δreview (fine) | Fine@Coding | Fine@Review | ReviewCycles |
| :-- | --: | --: | --: | --: |
| TheCrossword | 9 | 15 | 24 | 3 |
| GoldMiner | 7 | 35 | 42 | 3 |
| DouDizhuPoker | 6 | 107 | 113 | 3 |
| DetectPalindromes | 5 | 17 | 22 | 3 |
| SnakeGame | 4 | 25 | 29 | 3 |

Δreview (fine) — largest decreases:
| Project | Δreview (fine) | Fine@Coding | Fine@Review | ReviewCycles |
| :-- | --: | --: | --: | --: |
| Pong | -20 | 44 | 24 | 3 |
| Mastermind | -17 | 29 | 12 | 3 |
| ConnectionsNYT | -7 | 26 | 19 | 3 |
| TextBasedSpaceInvaders | -5 | 25 | 20 | 3 |
| Tiny Rouge | -2 | 44 | 42 | 3 |

Δfinal (fine) — largest increases:
| Project | Δfinal (fine) | Fine@Review | Fine@Final | TestCycles |
| :-- | --: | --: | --: | --: |
| Pong | 21 | 24 | 45 | 1 |
| Checkers | 6 | 41 | 47 | 1 |
| Tiny Rouge | 5 | 42 | 47 | 0 |
| FlappyBird | 4 | 25 | 29 | 1 |
| StrandsNYT | 2 | 48 | 50 | 2 |

Δfinal (fine) — decreases:
| Project | Δfinal (fine) | Fine@Review | Fine@Final | TestCycles |
| :-- | --: | --: | --: | --: |
| Chess | -10 | 106 | 96 | 1 |
| ConnectionsNYT | -9 | 19 | 10 | 1 |

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

### 2) Verification is a carrier of debt mutation (not only injection)
The review step has a small positive drift (median +1) but large dispersion (min -20, max +9). This indicates:
- Some reviews do cleanups/refactors that remove smells (large negative deltas).
- Others introduce debt while fixing correctness issues (positive deltas).

The final step is frequently inert (median 0), consistent with the workflow observation that most projects have **0 test cycles**.

### 3) Smell composition matches “rapid fix” failure modes
Two smell types dominate:
- **Magic number (59.4%)** and **Long statement (27.8%)** account for ~87% of fine smells at final.
- During review, net increases are driven mostly by **Long statement** and **Empty catch block**.
- When final changes occur, they are often dominated by **Magic number** and **Long statement** increases.

### 4) Verification effort (tokens) weakly–moderately correlates with debt change
Because review cycles are fixed, we use token volume as a proxy for verification effort.

Two dataset-level correlations (Pearson):
- `corr(code_review_tokens, Δreview implementation smells) = 0.319` (n=28)
- `corr(testing_tokens, Δfinal implementation smells) = -0.210` (n=12; projects with non‑zero testing tokens)

Interpretation:
- More code‑review activity tends to coincide with slightly more fine‑grained debt introduced during review (possibly because more review time leads to more incremental patches).
- More testing activity weakly coincides with slightly less fine‑grained debt introduced during final, but the testing signal is sparse (median testing tokens = 0), so this should be treated as a weak indicator.

### 5) What “accumulation” looks like in LLM‑MA pipelines (mechanistic summary)
In these traces, technical debt accumulation is best described as:
- **Front‑loaded** by the initial coding step (large baseline smell volume),
- **Mutated** during verification (review introduces or removes fine smells),
- **Often not structurally addressed** (coarse smells stay constant; architecture smells absent),
- **Heavy‑tailed** across projects (a few traces become extreme outliers by smell count).

## Limitations / Threats to Validity
- **Detector scope**: DPy may under-detect architectural issues in small projects; architecture smells are 0 here, which could reflect tool sensitivity rather than true absence.
- **Smell meaning**: some “magic numbers” are expected in games (screen sizes, colors). Counts still reflect maintainability risk, but not every instance is equally harmful.
- **Snapshot reconstruction**: code is reconstructed from chat logs and a heuristic replacement threshold; missing/partial code blocks could affect counts.
- **No size normalization**: because “density” is treated as **smell count**, cross-project comparisons may partially reflect differences in codebase size.
- **Testing sparsity**: most traces have 0 test cycles and median testing tokens = 0, limiting inference about the Testing phase’s role.

## Conclusion
In this ChatDev trace dataset (28 Python projects), technical debt accumulation is **not uniform across phases**:
- Debt signals are **dominated by fine-grained implementation smells**, especially **Magic number** and **Long statement**.
- The **code review phase** is the main locus of temporal change (median +1 fine smell), with high variance (can both reduce and increase debt).
- The **final/testing phase** often shows no change (median 0), consistent with sparse testing iterations.
- Coarse (architecture+design) debt signals remain **stable**, suggesting verification prioritizes correctness over structural improvements (or that coarse signals are not captured by the detector for these traces).

## Appendix A — Per-project table (Python projects, sorted by Total@Final)
| Project | Fine@Coding | Fine@Review | Fine@Final | Coarse@Final | Total@Final | Δreview(fine) | Δfinal(fine) | Δtotal(fine) | Unique@Final |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| Sudoku | 139 | 139 | 139 | 0 | 139 | 0 | 0 | 0 | 5 |
| DouDizhuPoker | 107 | 113 | 113 | 1 | 114 | 6 | 0 | 6 | 7 |
| Chess | 105 | 106 | 96 | 3 | 99 | 1 | -10 | -9 | 9 |
| StrandsNYT | 45 | 48 | 50 | 1 | 51 | 3 | 2 | 5 | 6 |
| Tiny Rouge | 44 | 42 | 47 | 1 | 48 | -2 | 5 | 3 | 4 |
| Checkers | 42 | 41 | 47 | 0 | 47 | -1 | 6 | 5 | 6 |
| StrandsGame | 46 | 46 | 46 | 1 | 47 | 0 | 0 | 0 | 6 |
| Gomoku | 45 | 45 | 46 | 0 | 46 | 0 | 1 | 1 | 3 |
| Pong | 44 | 24 | 45 | 0 | 45 | -20 | 21 | 1 | 4 |
| GoldMiner | 35 | 42 | 42 | 0 | 42 | 7 | 0 | 7 | 5 |
| SnakeGame | 25 | 29 | 29 | 1 | 30 | 4 | 0 | 4 | 7 |
| FlappyBird | 24 | 25 | 29 | 0 | 29 | 1 | 4 | 5 | 4 |
| ConnectFour | 26 | 28 | 28 | 0 | 28 | 2 | 0 | 2 | 3 |
| MonopolyGo | 28 | 27 | 27 | 1 | 28 | -1 | 0 | -1 | 6 |
| TheCrossword | 15 | 24 | 24 | 0 | 24 | 9 | 0 | 9 | 6 |
| Wordle | 19 | 23 | 23 | 0 | 23 | 4 | 0 | 4 | 3 |
| DetectPalindromes | 17 | 22 | 22 | 0 | 22 | 5 | 0 | 5 | 4 |
| BudgetTracker | 17 | 20 | 20 | 1 | 21 | 3 | 0 | 3 | 6 |
| TextBasedSpaceInvaders | 25 | 20 | 21 | 0 | 21 | -5 | 1 | -4 | 3 |
| TriviaQuiz | 15 | 17 | 17 | 1 | 18 | 2 | 0 | 2 | 5 |
| 2048 | 16 | 16 | 16 | 0 | 16 | 0 | 0 | 0 | 4 |
| ReversiOthello | 16 | 16 | 16 | 0 | 16 | 0 | 0 | 0 | 3 |
| EpisodeChooseYourStory | 10 | 13 | 13 | 0 | 13 | 3 | 0 | 3 | 3 |
| TicTacToe | 10 | 13 | 13 | 0 | 13 | 3 | 0 | 3 | 2 |
| Mastermind | 29 | 12 | 12 | 0 | 12 | -17 | 0 | -17 | 3 |
| ConnectionsNYT | 26 | 19 | 10 | 0 | 10 | -7 | -9 | -16 | 4 |
| FibonacciNumbers | 9 | 9 | 9 | 1 | 10 | 0 | 0 | 0 | 3 |
| Minesweeper | 8 | 10 | 10 | 0 | 10 | 2 | 0 | 2 | 2 |
