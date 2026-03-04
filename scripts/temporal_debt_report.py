#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import subprocess
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


PHASE_BUCKETS: dict[str, str] = {
    "DemandAnalysis": "Design",
    "LanguageChoose": "Design",
    "Coding": "Coding",
    "CodeComplete": "Code Completion",
    "CodeReviewComment": "Code Review",
    "CodeReviewModification": "Code Review",
    "TestErrorSummary": "Testing",
    "TestModification": "Testing",
    "EnvironmentDoc": "Documentation",
    "Reflection": "Documentation",
    "Manual": "Documentation",
}


@dataclass(frozen=True)
class LogMessage:
    role: str
    header: str
    start_line: int  # 0-based line index in the original log
    body_lines: list[str]


MESSAGE_HEADER_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} .*? INFO\] (.*?): \*\*(.*?)\*\*$")
TIMESTAMP_LINE_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} .*? INFO\] ")

PY_CODEBLOCK_RE = re.compile(
    r"(?ms)^\s*([A-Za-z0-9_./-]+\.py)\s*$\n+```python\s*\n(.*?)\n```\s*$"
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_log_messages(lines: list[str]) -> list[LogMessage]:
    messages: list[LogMessage] = []
    current_role: Optional[str] = None
    current_header: Optional[str] = None
    current_start: Optional[int] = None
    current_body: list[str] = []

    def flush() -> None:
        nonlocal current_role, current_header, current_start, current_body
        if current_role is None or current_header is None or current_start is None:
            return
        messages.append(
            LogMessage(
                role=current_role,
                header=current_header,
                start_line=current_start,
                body_lines=current_body,
            )
        )
        current_role = None
        current_header = None
        current_start = None
        current_body = []

    for i, line in enumerate(lines):
        m = MESSAGE_HEADER_RE.match(line)
        if m:
            flush()
            current_role = m.group(1)
            current_header = m.group(2)
            current_start = i
            current_body = []
            continue

        if TIMESTAMP_LINE_RE.match(line):
            flush()
            continue

        if current_role is not None:
            current_body.append(line)

    flush()
    return messages


def extract_python_files_from_message(message: LogMessage) -> dict[str, str]:
    body = "\n".join(message.body_lines)
    files = {}
    for fname, code in PY_CODEBLOCK_RE.findall(body):
        files[fname] = code
    return files


def load_final_python_snapshot(project_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(project_dir.rglob("*.py")):
        rel = path.relative_to(project_dir).as_posix()
        files[rel] = _read_text(path)
    return files


def count_nonempty_loc(files: dict[str, str]) -> int:
    loc = 0
    for code in files.values():
        for line in code.splitlines():
            if line.strip():
                loc += 1
    return loc


def smell_type_counts(items: list[dict[str, Any]]) -> Counter[str]:
    c: Counter[str] = Counter()
    for d in items:
        smell = d.get("Smell")
        if isinstance(smell, str) and smell:
            c[smell] += 1
    return c


def per_kloc(count: int, loc: int) -> float:
    return (count * 1000.0 / loc) if loc > 0 else 0.0


def per_file(count: int, n_files: int) -> float:
    return (count / n_files) if n_files > 0 else 0.0


def apply_updates(
    base_state: dict[str, str],
    updates: Iterable[dict[str, str]],
    *,
    replace_threshold: float,
) -> dict[str, str]:
    state = dict(base_state)
    for files in updates:
        if not files:
            continue
        ratio = len(files) / max(1, len(state))
        if ratio >= replace_threshold:
            state = dict(files)
        else:
            state.update(files)
    return state


def find_dpy_binary(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser()

    cwd_candidate = Path.cwd() / "DPy"
    if cwd_candidate.exists():
        return cwd_candidate

    # script is ChatDev_GPT-5_Reasoning/scripts/*.py; DPy is at repo root (/home/kira/DPy)
    script_candidate = Path(__file__).resolve().parents[2] / "DPy"
    return script_candidate


def run_dpy(dpy_path: Path, input_dir: Path, output_dir: Path) -> dict[str, list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [str(dpy_path), "analyze", "-i", str(input_dir), "-o", str(output_dir), "-f", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            "DPy failed\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{res.stdout}\n"
            f"stderr:\n{res.stderr}\n"
        )

    def read_smells(suffix: str) -> list[dict[str, Any]]:
        matches = list(output_dir.glob(f"*_{suffix}.json"))
        if not matches:
            return []
        # DPy writes exactly one file per category; if multiple exist, merge.
        out: list[dict[str, Any]] = []
        for p in matches:
            try:
                data = json.loads(_read_text(p))
            except json.JSONDecodeError:
                continue
            if isinstance(data, list):
                out.extend([d for d in data if isinstance(d, dict)])
        return out

    return {
        "architecture_smells": read_smells("architecture_smells"),
        "design_smells": read_smells("design_smells"),
        "implementation_smells": read_smells("implementation_smells"),
        "ml_smells": read_smells("ml_smells"),
    }


def bucket_token_totals(project_token_data: dict[str, Any]) -> dict[str, int]:
    totals: dict[str, int] = Counter()
    for phase in project_token_data.get("phases", []):
        phase_name = phase.get("phase_name")
        bucket = PHASE_BUCKETS.get(phase_name, phase_name or "Unknown")
        for usage in phase.get("token_usage", []):
            totals[bucket] += int(usage.get("total_tokens", 0))
    return dict(totals)


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sum((x - mx) ** 2 for x in xs)
    deny = sum((y - my) ** 2 for y in ys)
    den = math.sqrt(denx * deny)
    return num / den if den else 0.0


def describe_distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "n": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "stdev": 0.0,
            "min": 0.0,
            "q1": 0.0,
            "q3": 0.0,
            "max": 0.0,
        }
    xs = sorted(float(v) for v in values)
    n = len(xs)

    def percentile(p: float) -> float:
        if n == 1:
            return xs[0]
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return xs[int(k)]
        return xs[f] + (xs[c] - xs[f]) * (k - f)

    return {
        "n": float(n),
        "mean": float(statistics.mean(xs)),
        "median": float(statistics.median(xs)),
        "stdev": float(statistics.stdev(xs)) if n > 1 else 0.0,
        "min": float(xs[0]),
        "q1": float(percentile(0.25)),
        "q3": float(percentile(0.75)),
        "max": float(xs[-1]),
    }


def extract_last_phase_message_excerpt(
    messages: list[LogMessage],
    *,
    phase_substring: str,
    max_lines: int,
) -> str:
    phase_msgs = [m for m in messages if phase_substring in m.header]
    if not phase_msgs:
        return ""
    body = phase_msgs[-1].body_lines
    excerpt = "\n".join(body[:max_lines]).strip()
    return excerpt


def extract_last_test_reports_excerpt(lines: list[str], *, max_lines: int = 60) -> str:
    # Find last "[Test Reports]" header and capture subsequent non-timestamp lines.
    last_idx = None
    for i in range(len(lines) - 1, -1, -1):
        if "Test Reports" in lines[i] and ("**[Test Reports]**" in lines[i] or "[Test Reports]" in lines[i]):
            last_idx = i
            break
    if last_idx is None:
        return ""

    captured: list[str] = [lines[last_idx].strip()]
    for j in range(last_idx + 1, min(last_idx + 1 + max_lines, len(lines))):
        if TIMESTAMP_LINE_RE.match(lines[j]):
            break
        captured.append(lines[j].rstrip())
    return "\n".join(captured).strip()


def write_snapshot(snapshot_dir: Path, files: dict[str, str]) -> None:
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for rel, code in files.items():
        p = snapshot_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(code, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract temporal technical-debt signals from ChatDev traces and write JSON results.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--traces", type=Path, default=Path("agent_debt/traces"))
    parser.add_argument(
        "--token-json",
        type=Path,
        default=Path("agent_debt/data/ChatDev_GPT-5_Trace_Analysis_Results.json"),
        help="Token usage summary JSON (produced by token_usage_extractor_chatdev_gpt_5.py).",
    )
    parser.add_argument("--dpy", type=str, default=None, help="Path to the DPy binary.")
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("agent_debt/data/temporal_debt_results.json"),
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("agent_debt/data/processed_data/temporal_debt"),
        help="Where to store reconstructed snapshots and DPy outputs.",
    )
    parser.add_argument(
        "--replace-threshold",
        type=float,
        default=0.6,
        help="If an update outputs >= this fraction of current files, treat it as a full replacement snapshot.",
    )
    parser.add_argument(
        "--max-excerpt-lines",
        type=int,
        default=40,
        help="Max lines to keep for qualitative excerpts in the JSON output.",
    )
    parser.add_argument(
        "--include-excerpts",
        action="store_true",
        help="Include small excerpts from CodeReviewComment and Test Reports in per-project JSON rows.",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Write only the aggregated summary to JSON (omit the per-project table).",
    )
    args = parser.parse_args()
    include_excerpts = bool(args.include_excerpts and (not args.summary_only))

    dpy_path = find_dpy_binary(args.dpy)
    if not dpy_path.exists():
        raise SystemExit(f"DPy not found at: {dpy_path}")

    token_data = json.loads(_read_text(args.token_json)) if args.token_json.exists() else {}
    token_projects = {p.get("project_name"): p for p in token_data.get("projects", []) if isinstance(p, dict)}

    traces_dir: Path = args.traces
    if not traces_dir.exists():
        raise SystemExit(f"Traces dir not found: {traces_dir}")

    artifacts_dir: Path = args.artifacts_dir
    snapshots_dir = artifacts_dir / "snapshots"
    dpy_dir = artifacts_dir / "dpy_outputs"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    dpy_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    agg_impl_smells: dict[str, Counter[str]] = {
        "post_coding": Counter(),
        "post_review": Counter(),
        "final": Counter(),
    }
    agg_coarse_smells: dict[str, Counter[str]] = {
        "post_coding": Counter(),
        "post_review": Counter(),
        "final": Counter(),
    }
    agg_fine_smells: dict[str, Counter[str]] = {
        "post_coding": Counter(),
        "post_review": Counter(),
        "final": Counter(),
    }

    log_files = sorted(traces_dir.rglob("*.log"))
    for log_path in log_files:
        project_dir = log_path.parent
        project_name = project_dir.name.split("_DefaultOrganization_")[0]

        log_lines = _read_text(log_path).splitlines()
        messages = parse_log_messages(log_lines)

        # Token + meta are always collected when available, even for non-Python projects.
        token_project = token_projects.get(project_name, {})
        bucketed_tokens = bucket_token_totals(token_project) if token_project else {}
        review_tokens = int(bucketed_tokens.get("Code Review", 0))
        test_tokens = int(bucketed_tokens.get("Testing", 0))

        review_cycles = sum(1 for m in messages if "on : CodeReviewModification" in m.header)
        test_cycles = sum(1 for m in messages if "on : TestModification" in m.header)
        if include_excerpts:
            review_excerpt = extract_last_phase_message_excerpt(
                messages,
                phase_substring="on : CodeReviewComment",
                max_lines=args.max_excerpt_lines,
            )
            test_excerpt = extract_last_test_reports_excerpt(log_lines, max_lines=args.max_excerpt_lines)

        coding_msgs = [m for m in messages if "on : Coding" in m.header]
        coding_files = extract_python_files_from_message(coding_msgs[0]) if coding_msgs else {}

        final_files = load_final_python_snapshot(project_dir)
        python_supported = bool(coding_files or final_files)

        counts: dict[str, Any]
        deltas: dict[str, Any]

        if not python_supported:
            counts = {"post_coding": None, "post_review": None, "final": None}
            deltas = {
                "impl_post_review_minus_post_coding": None,
                "impl_final_minus_post_review": None,
                "impl_final_minus_post_coding": None,
                "coarse_post_review_minus_post_coding": None,
                "coarse_final_minus_post_review": None,
                "coarse_final_minus_post_coding": None,
                "fine_post_review_minus_post_coding": None,
                "fine_final_minus_post_review": None,
                "fine_final_minus_post_coding": None,
                "total_post_review_minus_post_coding": None,
                "total_final_minus_post_review": None,
                "total_final_minus_post_coding": None,
            }
            row = {
                "project": project_name,
                "log_path": str(log_path),
                "dir_path": str(project_dir),
                "python_supported": False,
                "review_cycles": review_cycles,
                "test_cycles": test_cycles,
                "tokens": {
                    "by_bucket": bucketed_tokens,
                    "code_review_total_tokens": review_tokens,
                    "testing_total_tokens": test_tokens,
                },
                "counts": counts,
                "deltas": deltas,
                "software_info": token_project.get("software_info", {}),
            }
            if include_excerpts:
                row["excerpts"] = {
                    "code_review_comment": review_excerpt,
                    "last_test_reports": test_excerpt,
                }
            results.append(row)
            continue

        # If we cannot reconstruct post_coding from the log (rare), fall back to final snapshot.
        post_coding_files = coding_files if coding_files else final_files

        review_mod_msgs = [m for m in messages if "on : CodeReviewModification" in m.header]
        review_updates = [extract_python_files_from_message(m) for m in review_mod_msgs]
        post_review_files = apply_updates(
            post_coding_files,
            review_updates,
            replace_threshold=args.replace_threshold,
        )

        # Final snapshot comes from the on-disk trace directory by default.
        final_snapshot_files = final_files if final_files else post_review_files

        # Persist snapshots to disk (reproducibility).
        project_snap_root = snapshots_dir / project_name
        post_coding_dir = project_snap_root / "post_coding"
        post_review_dir = project_snap_root / "post_review"
        final_dir = project_snap_root / "final"
        write_snapshot(post_coding_dir, post_coding_files)
        write_snapshot(post_review_dir, post_review_files)
        write_snapshot(final_dir, final_snapshot_files)

        # Run DPy.
        smells_coding = run_dpy(dpy_path, post_coding_dir, dpy_dir / project_name / "post_coding")
        smells_review = run_dpy(dpy_path, post_review_dir, dpy_dir / project_name / "post_review")
        smells_final = run_dpy(dpy_path, final_dir, dpy_dir / project_name / "final")
        coding_arch = smell_type_counts(smells_coding["architecture_smells"])
        coding_design = smell_type_counts(smells_coding["design_smells"])
        coding_impl = smell_type_counts(smells_coding["implementation_smells"])
        coding_ml = smell_type_counts(smells_coding["ml_smells"])
        coding_coarse = coding_arch + coding_design
        coding_fine = coding_impl + coding_ml
        coding_total = coding_coarse + coding_fine
        coding_loc = count_nonempty_loc(post_coding_files)
        coding_files_n = len(post_coding_files)

        review_arch = smell_type_counts(smells_review["architecture_smells"])
        review_design = smell_type_counts(smells_review["design_smells"])
        review_impl = smell_type_counts(smells_review["implementation_smells"])
        review_ml = smell_type_counts(smells_review["ml_smells"])
        review_coarse = review_arch + review_design
        review_fine = review_impl + review_ml
        review_total = review_coarse + review_fine
        review_loc = count_nonempty_loc(post_review_files)
        review_files_n = len(post_review_files)

        final_arch = smell_type_counts(smells_final["architecture_smells"])
        final_design = smell_type_counts(smells_final["design_smells"])
        final_impl = smell_type_counts(smells_final["implementation_smells"])
        final_ml = smell_type_counts(smells_final["ml_smells"])
        final_coarse = final_arch + final_design
        final_fine = final_impl + final_ml
        final_total = final_coarse + final_fine
        final_loc = count_nonempty_loc(final_snapshot_files)
        final_files_n = len(final_snapshot_files)

        counts = {
            "post_coding": {
                # Raw category counts (DPy buckets)
                "arch": sum(coding_arch.values()),
                "design": sum(coding_design.values()),
                "impl": sum(coding_impl.values()),
                "ml": sum(coding_ml.values()),
                # Granularity (coarse vs fine)
                "coarse": sum(coding_coarse.values()),  # architecture + design
                "fine": sum(coding_fine.values()),  # implementation + ml
                "total": sum(coding_total.values()),
                # Diversity (distinct smell types)
                "coarse_unique": len(coding_coarse),
                "fine_unique": len(coding_fine),
                "total_unique": len(coding_total),
                # Density
                "loc": coding_loc,
                "coarse_per_kloc": per_kloc(sum(coding_coarse.values()), coding_loc),
                "fine_per_kloc": per_kloc(sum(coding_fine.values()), coding_loc),
                "total_per_kloc": per_kloc(sum(coding_total.values()), coding_loc),
                "coarse_per_file": per_file(sum(coding_coarse.values()), coding_files_n),
                "fine_per_file": per_file(sum(coding_fine.values()), coding_files_n),
                "total_per_file": per_file(sum(coding_total.values()), coding_files_n),
                # Representative smell types
                "impl_top": coding_impl.most_common(10),
                "coarse_top": coding_coarse.most_common(10),
                "n_files": coding_files_n,
            },
            "post_review": {
                "arch": sum(review_arch.values()),
                "design": sum(review_design.values()),
                "impl": sum(review_impl.values()),
                "ml": sum(review_ml.values()),
                "coarse": sum(review_coarse.values()),
                "fine": sum(review_fine.values()),
                "total": sum(review_total.values()),
                "coarse_unique": len(review_coarse),
                "fine_unique": len(review_fine),
                "total_unique": len(review_total),
                "loc": review_loc,
                "coarse_per_kloc": per_kloc(sum(review_coarse.values()), review_loc),
                "fine_per_kloc": per_kloc(sum(review_fine.values()), review_loc),
                "total_per_kloc": per_kloc(sum(review_total.values()), review_loc),
                "coarse_per_file": per_file(sum(review_coarse.values()), review_files_n),
                "fine_per_file": per_file(sum(review_fine.values()), review_files_n),
                "total_per_file": per_file(sum(review_total.values()), review_files_n),
                "impl_top": review_impl.most_common(10),
                "coarse_top": review_coarse.most_common(10),
                "n_files": review_files_n,
            },
            "final": {
                "arch": sum(final_arch.values()),
                "design": sum(final_design.values()),
                "impl": sum(final_impl.values()),
                "ml": sum(final_ml.values()),
                "coarse": sum(final_coarse.values()),
                "fine": sum(final_fine.values()),
                "total": sum(final_total.values()),
                "coarse_unique": len(final_coarse),
                "fine_unique": len(final_fine),
                "total_unique": len(final_total),
                "loc": final_loc,
                "coarse_per_kloc": per_kloc(sum(final_coarse.values()), final_loc),
                "fine_per_kloc": per_kloc(sum(final_fine.values()), final_loc),
                "total_per_kloc": per_kloc(sum(final_total.values()), final_loc),
                "coarse_per_file": per_file(sum(final_coarse.values()), final_files_n),
                "fine_per_file": per_file(sum(final_fine.values()), final_files_n),
                "total_per_file": per_file(sum(final_total.values()), final_files_n),
                "impl_top": final_impl.most_common(10),
                "coarse_top": final_coarse.most_common(10),
                "n_files": final_files_n,
            },
        }

        agg_impl_smells["post_coding"].update(coding_impl)
        agg_impl_smells["post_review"].update(review_impl)
        agg_impl_smells["final"].update(final_impl)

        agg_coarse_smells["post_coding"].update(coding_coarse)
        agg_coarse_smells["post_review"].update(review_coarse)
        agg_coarse_smells["final"].update(final_coarse)

        agg_fine_smells["post_coding"].update(coding_fine)
        agg_fine_smells["post_review"].update(review_fine)
        agg_fine_smells["final"].update(final_fine)

        delta_review = counts["post_review"]["impl"] - counts["post_coding"]["impl"]
        delta_final = counts["final"]["impl"] - counts["post_review"]["impl"]
        delta_total = counts["final"]["impl"] - counts["post_coding"]["impl"]

        delta_review_coarse = counts["post_review"]["coarse"] - counts["post_coding"]["coarse"]
        delta_final_coarse = counts["final"]["coarse"] - counts["post_review"]["coarse"]
        delta_total_coarse = counts["final"]["coarse"] - counts["post_coding"]["coarse"]

        delta_review_fine = counts["post_review"]["fine"] - counts["post_coding"]["fine"]
        delta_final_fine = counts["final"]["fine"] - counts["post_review"]["fine"]
        delta_total_fine = counts["final"]["fine"] - counts["post_coding"]["fine"]

        delta_review_total = counts["post_review"]["total"] - counts["post_coding"]["total"]
        delta_final_total = counts["final"]["total"] - counts["post_review"]["total"]
        delta_total_total = counts["final"]["total"] - counts["post_coding"]["total"]

        results.append(
            {
                "project": project_name,
                "log_path": str(log_path),
                "dir_path": str(project_dir),
                "python_supported": True,
                "review_cycles": review_cycles,
                "test_cycles": test_cycles,
                "tokens": {
                    "by_bucket": bucketed_tokens,
                    "code_review_total_tokens": review_tokens,
                    "testing_total_tokens": test_tokens,
                },
                "counts": counts,
                "deltas": {
                    "impl_post_review_minus_post_coding": delta_review,
                    "impl_final_minus_post_review": delta_final,
                    "impl_final_minus_post_coding": delta_total,
                    "coarse_post_review_minus_post_coding": delta_review_coarse,
                    "coarse_final_minus_post_review": delta_final_coarse,
                    "coarse_final_minus_post_coding": delta_total_coarse,
                    "fine_post_review_minus_post_coding": delta_review_fine,
                    "fine_final_minus_post_review": delta_final_fine,
                    "fine_final_minus_post_coding": delta_total_fine,
                    "total_post_review_minus_post_coding": delta_review_total,
                    "total_final_minus_post_review": delta_final_total,
                    "total_final_minus_post_coding": delta_total_total,
                },
                "software_info": token_project.get("software_info", {}),
            }
        )
        if include_excerpts:
            results[-1]["excerpts"] = {
                "code_review_comment": review_excerpt,
                "last_test_reports": test_excerpt,
            }

    # Aggregate summary statistics (Python subset).
    python_rows = [r for r in results if r.get("python_supported")]
    impl_coding = [r["counts"]["post_coding"]["impl"] for r in python_rows]
    impl_review = [r["counts"]["post_review"]["impl"] for r in python_rows]
    impl_final = [r["counts"]["final"]["impl"] for r in python_rows]
    deltas_review = [r["deltas"]["impl_post_review_minus_post_coding"] for r in python_rows]
    deltas_final = [r["deltas"]["impl_final_minus_post_review"] for r in python_rows]
    deltas_total = [r["deltas"]["impl_final_minus_post_coding"] for r in python_rows]

    coarse_coding = [r["counts"]["post_coding"]["coarse"] for r in python_rows]
    coarse_review = [r["counts"]["post_review"]["coarse"] for r in python_rows]
    coarse_final = [r["counts"]["final"]["coarse"] for r in python_rows]
    coarse_deltas_review = [r["deltas"]["coarse_post_review_minus_post_coding"] for r in python_rows]
    coarse_deltas_final = [r["deltas"]["coarse_final_minus_post_review"] for r in python_rows]
    coarse_deltas_total = [r["deltas"]["coarse_final_minus_post_coding"] for r in python_rows]

    fine_coding = [r["counts"]["post_coding"]["fine"] for r in python_rows]
    fine_review = [r["counts"]["post_review"]["fine"] for r in python_rows]
    fine_final = [r["counts"]["final"]["fine"] for r in python_rows]
    fine_deltas_review = [r["deltas"]["fine_post_review_minus_post_coding"] for r in python_rows]
    fine_deltas_final = [r["deltas"]["fine_final_minus_post_review"] for r in python_rows]
    fine_deltas_total = [r["deltas"]["fine_final_minus_post_coding"] for r in python_rows]

    total_coding = [r["counts"]["post_coding"]["total"] for r in python_rows]
    total_review = [r["counts"]["post_review"]["total"] for r in python_rows]
    total_final = [r["counts"]["final"]["total"] for r in python_rows]
    total_deltas_review = [r["deltas"]["total_post_review_minus_post_coding"] for r in python_rows]
    total_deltas_final = [r["deltas"]["total_final_minus_post_review"] for r in python_rows]
    total_deltas_total = [r["deltas"]["total_final_minus_post_coding"] for r in python_rows]

    coarse_unique_coding = [r["counts"]["post_coding"]["coarse_unique"] for r in python_rows]
    coarse_unique_review = [r["counts"]["post_review"]["coarse_unique"] for r in python_rows]
    coarse_unique_final = [r["counts"]["final"]["coarse_unique"] for r in python_rows]

    fine_unique_coding = [r["counts"]["post_coding"]["fine_unique"] for r in python_rows]
    fine_unique_review = [r["counts"]["post_review"]["fine_unique"] for r in python_rows]
    fine_unique_final = [r["counts"]["final"]["fine_unique"] for r in python_rows]

    total_unique_coding = [r["counts"]["post_coding"]["total_unique"] for r in python_rows]
    total_unique_review = [r["counts"]["post_review"]["total_unique"] for r in python_rows]
    total_unique_final = [r["counts"]["final"]["total_unique"] for r in python_rows]

    coarse_per_kloc_coding = [r["counts"]["post_coding"]["coarse_per_kloc"] for r in python_rows]
    coarse_per_kloc_review = [r["counts"]["post_review"]["coarse_per_kloc"] for r in python_rows]
    coarse_per_kloc_final = [r["counts"]["final"]["coarse_per_kloc"] for r in python_rows]

    fine_per_kloc_coding = [r["counts"]["post_coding"]["fine_per_kloc"] for r in python_rows]
    fine_per_kloc_review = [r["counts"]["post_review"]["fine_per_kloc"] for r in python_rows]
    fine_per_kloc_final = [r["counts"]["final"]["fine_per_kloc"] for r in python_rows]

    total_per_kloc_coding = [r["counts"]["post_coding"]["total_per_kloc"] for r in python_rows]
    total_per_kloc_review = [r["counts"]["post_review"]["total_per_kloc"] for r in python_rows]
    total_per_kloc_final = [r["counts"]["final"]["total_per_kloc"] for r in python_rows]

    delta_review_pos_frac = (
        sum(1 for d in deltas_review if d > 0) / len(deltas_review) if deltas_review else 0
    )
    delta_final_pos_frac = (
        sum(1 for d in deltas_final if d > 0) / len(deltas_final) if deltas_final else 0
    )
    delta_total_pos_frac = (
        sum(1 for d in deltas_total if d > 0) / len(deltas_total) if deltas_total else 0
    )

    coarse_delta_review_pos_frac = (
        sum(1 for d in coarse_deltas_review if d > 0) / len(coarse_deltas_review) if coarse_deltas_review else 0
    )
    coarse_delta_final_pos_frac = (
        sum(1 for d in coarse_deltas_final if d > 0) / len(coarse_deltas_final) if coarse_deltas_final else 0
    )
    coarse_delta_total_pos_frac = (
        sum(1 for d in coarse_deltas_total if d > 0) / len(coarse_deltas_total) if coarse_deltas_total else 0
    )

    fine_delta_review_pos_frac = (
        sum(1 for d in fine_deltas_review if d > 0) / len(fine_deltas_review) if fine_deltas_review else 0
    )
    fine_delta_final_pos_frac = (
        sum(1 for d in fine_deltas_final if d > 0) / len(fine_deltas_final) if fine_deltas_final else 0
    )
    fine_delta_total_pos_frac = (
        sum(1 for d in fine_deltas_total if d > 0) / len(fine_deltas_total) if fine_deltas_total else 0
    )

    total_delta_review_pos_frac = (
        sum(1 for d in total_deltas_review if d > 0) / len(total_deltas_review) if total_deltas_review else 0
    )
    total_delta_final_pos_frac = (
        sum(1 for d in total_deltas_final if d > 0) / len(total_deltas_final) if total_deltas_final else 0
    )
    total_delta_total_pos_frac = (
        sum(1 for d in total_deltas_total if d > 0) / len(total_deltas_total) if total_deltas_total else 0
    )

    # Token correlations (only where token data exists).
    rows_with_tokens = [r for r in python_rows if r["tokens"]["code_review_total_tokens"] > 0]
    review_token_corr = pearson(
        [float(r["tokens"]["code_review_total_tokens"]) for r in rows_with_tokens],
        [float(r["deltas"]["impl_post_review_minus_post_coding"]) for r in rows_with_tokens],
    )
    rows_with_test_tokens = [r for r in python_rows if r["tokens"]["testing_total_tokens"] > 0]
    test_token_corr = pearson(
        [float(r["tokens"]["testing_total_tokens"]) for r in rows_with_test_tokens],
        [float(r["deltas"]["impl_final_minus_post_review"]) for r in rows_with_test_tokens],
    )

    delta_smells_review = agg_impl_smells["post_review"] - agg_impl_smells["post_coding"]
    delta_smells_final = agg_impl_smells["final"] - agg_impl_smells["post_review"]

    delta_coarse_smells_review = agg_coarse_smells["post_review"] - agg_coarse_smells["post_coding"]
    delta_coarse_smells_final = agg_coarse_smells["final"] - agg_coarse_smells["post_review"]

    delta_fine_smells_review = agg_fine_smells["post_review"] - agg_fine_smells["post_coding"]
    delta_fine_smells_final = agg_fine_smells["final"] - agg_fine_smells["post_review"]

    summary = {
        "n_projects_total": len(results),
        "n_projects_python": len(python_rows),
        "implementation_smells": {
            "post_coding_mean": statistics.mean(impl_coding) if impl_coding else 0,
            "post_review_mean": statistics.mean(impl_review) if impl_review else 0,
            "final_mean": statistics.mean(impl_final) if impl_final else 0,
            "delta_review_mean": statistics.mean(deltas_review) if deltas_review else 0,
            "delta_review_median": statistics.median(deltas_review) if deltas_review else 0,
            "delta_final_mean": statistics.mean(deltas_final) if deltas_final else 0,
            "delta_final_median": statistics.median(deltas_final) if deltas_final else 0,
            "delta_total_mean": statistics.mean(deltas_total) if deltas_total else 0,
            "delta_total_median": statistics.median(deltas_total) if deltas_total else 0,
            "delta_review_positive_fraction": delta_review_pos_frac,
            "delta_final_positive_fraction": delta_final_pos_frac,
            "delta_total_positive_fraction": delta_total_pos_frac,
            "top_impl_smells_final": agg_impl_smells["final"].most_common(10),
            "top_impl_smell_increases_review": delta_smells_review.most_common(10),
            "top_impl_smell_increases_final": delta_smells_final.most_common(10),
        },
        "granularity": {
            "definitions": {
                "coarse": "architecture_smells + design_smells",
                "fine": "implementation_smells + ml_smells",
            },
            "coarse_mean": {
                "post_coding": statistics.mean(coarse_coding) if coarse_coding else 0,
                "post_review": statistics.mean(coarse_review) if coarse_review else 0,
                "final": statistics.mean(coarse_final) if coarse_final else 0,
            },
            "fine_mean": {
                "post_coding": statistics.mean(fine_coding) if fine_coding else 0,
                "post_review": statistics.mean(fine_review) if fine_review else 0,
                "final": statistics.mean(fine_final) if fine_final else 0,
            },
            "total_mean": {
                "post_coding": statistics.mean(total_coding) if total_coding else 0,
                "post_review": statistics.mean(total_review) if total_review else 0,
                "final": statistics.mean(total_final) if total_final else 0,
            },
            "delta_means": {
                "coarse_review": statistics.mean(coarse_deltas_review) if coarse_deltas_review else 0,
                "coarse_final": statistics.mean(coarse_deltas_final) if coarse_deltas_final else 0,
                "coarse_total": statistics.mean(coarse_deltas_total) if coarse_deltas_total else 0,
                "fine_review": statistics.mean(fine_deltas_review) if fine_deltas_review else 0,
                "fine_final": statistics.mean(fine_deltas_final) if fine_deltas_final else 0,
                "fine_total": statistics.mean(fine_deltas_total) if fine_deltas_total else 0,
                "total_review": statistics.mean(total_deltas_review) if total_deltas_review else 0,
                "total_final": statistics.mean(total_deltas_final) if total_deltas_final else 0,
                "total_total": statistics.mean(total_deltas_total) if total_deltas_total else 0,
            },
            "delta_medians": {
                "coarse_review": statistics.median(coarse_deltas_review) if coarse_deltas_review else 0,
                "coarse_final": statistics.median(coarse_deltas_final) if coarse_deltas_final else 0,
                "coarse_total": statistics.median(coarse_deltas_total) if coarse_deltas_total else 0,
                "fine_review": statistics.median(fine_deltas_review) if fine_deltas_review else 0,
                "fine_final": statistics.median(fine_deltas_final) if fine_deltas_final else 0,
                "fine_total": statistics.median(fine_deltas_total) if fine_deltas_total else 0,
                "total_review": statistics.median(total_deltas_review) if total_deltas_review else 0,
                "total_final": statistics.median(total_deltas_final) if total_deltas_final else 0,
                "total_total": statistics.median(total_deltas_total) if total_deltas_total else 0,
            },
            "delta_positive_fractions": {
                "coarse_review": coarse_delta_review_pos_frac,
                "coarse_final": coarse_delta_final_pos_frac,
                "coarse_total": coarse_delta_total_pos_frac,
                "fine_review": fine_delta_review_pos_frac,
                "fine_final": fine_delta_final_pos_frac,
                "fine_total": fine_delta_total_pos_frac,
                "total_review": total_delta_review_pos_frac,
                "total_final": total_delta_final_pos_frac,
                "total_total": total_delta_total_pos_frac,
            },
            "top_coarse_smells_final": agg_coarse_smells["final"].most_common(10),
            "top_fine_smells_final": agg_fine_smells["final"].most_common(10),
            "top_coarse_smell_increases_review": delta_coarse_smells_review.most_common(10),
            "top_coarse_smell_increases_final": delta_coarse_smells_final.most_common(10),
            "top_fine_smell_increases_review": delta_fine_smells_review.most_common(10),
            "top_fine_smell_increases_final": delta_fine_smells_final.most_common(10),
        },
        "diversity": {
            "coarse_unique_mean": {
                "post_coding": statistics.mean(coarse_unique_coding) if coarse_unique_coding else 0,
                "post_review": statistics.mean(coarse_unique_review) if coarse_unique_review else 0,
                "final": statistics.mean(coarse_unique_final) if coarse_unique_final else 0,
            },
            "fine_unique_mean": {
                "post_coding": statistics.mean(fine_unique_coding) if fine_unique_coding else 0,
                "post_review": statistics.mean(fine_unique_review) if fine_unique_review else 0,
                "final": statistics.mean(fine_unique_final) if fine_unique_final else 0,
            },
            "total_unique_mean": {
                "post_coding": statistics.mean(total_unique_coding) if total_unique_coding else 0,
                "post_review": statistics.mean(total_unique_review) if total_unique_review else 0,
                "final": statistics.mean(total_unique_final) if total_unique_final else 0,
            },
        },
        "density": {
            "coarse_per_kloc_mean": {
                "post_coding": statistics.mean(coarse_per_kloc_coding) if coarse_per_kloc_coding else 0,
                "post_review": statistics.mean(coarse_per_kloc_review) if coarse_per_kloc_review else 0,
                "final": statistics.mean(coarse_per_kloc_final) if coarse_per_kloc_final else 0,
            },
            "fine_per_kloc_mean": {
                "post_coding": statistics.mean(fine_per_kloc_coding) if fine_per_kloc_coding else 0,
                "post_review": statistics.mean(fine_per_kloc_review) if fine_per_kloc_review else 0,
                "final": statistics.mean(fine_per_kloc_final) if fine_per_kloc_final else 0,
            },
            "total_per_kloc_mean": {
                "post_coding": statistics.mean(total_per_kloc_coding) if total_per_kloc_coding else 0,
                "post_review": statistics.mean(total_per_kloc_review) if total_per_kloc_review else 0,
                "final": statistics.mean(total_per_kloc_final) if total_per_kloc_final else 0,
            },
        },
        "distributions": {
            "deltas": {
                "impl": {
                    "review": describe_distribution([float(x) for x in deltas_review]),
                    "final": describe_distribution([float(x) for x in deltas_final]),
                    "total": describe_distribution([float(x) for x in deltas_total]),
                },
                "coarse": {
                    "review": describe_distribution([float(x) for x in coarse_deltas_review]),
                    "final": describe_distribution([float(x) for x in coarse_deltas_final]),
                    "total": describe_distribution([float(x) for x in coarse_deltas_total]),
                },
                "fine": {
                    "review": describe_distribution([float(x) for x in fine_deltas_review]),
                    "final": describe_distribution([float(x) for x in fine_deltas_final]),
                    "total": describe_distribution([float(x) for x in fine_deltas_total]),
                },
                "total": {
                    "review": describe_distribution([float(x) for x in total_deltas_review]),
                    "final": describe_distribution([float(x) for x in total_deltas_final]),
                    "total": describe_distribution([float(x) for x in total_deltas_total]),
                },
            },
            "density_per_kloc": {
                "coarse_final": describe_distribution([float(x) for x in coarse_per_kloc_final]),
                "fine_final": describe_distribution([float(x) for x in fine_per_kloc_final]),
                "total_final": describe_distribution([float(x) for x in total_per_kloc_final]),
            },
            "diversity_unique": {
                "coarse_final": describe_distribution([float(x) for x in coarse_unique_final]),
                "fine_final": describe_distribution([float(x) for x in fine_unique_final]),
                "total_final": describe_distribution([float(x) for x in total_unique_final]),
            },
        },
        "correlations": {
            "pearson(code_review_tokens, delta_review_impl_smells)": review_token_corr,
            "pearson(testing_tokens, delta_final_impl_smells)": test_token_corr,
        },
    }

    out_payload = {"summary": summary} if args.summary_only else {"summary": summary, "projects": results}
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out_payload, indent=2), encoding="utf-8")
    print(f"Wrote JSON: {args.out_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
