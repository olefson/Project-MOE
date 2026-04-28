from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from benchmark_pmo_latency import DEFAULT_CHAT_TEXT


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def maybe_git_commit(project_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip() or None
    except Exception:
        pass
    return None


def to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def pct_delta(new: float | None, old: float | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return ((new - old) / old) * 100.0


def compare_mode(on_summary: dict[str, Any], off_summary: dict[str, Any]) -> dict[str, Any]:
    def endpoint_summary(summary: dict[str, Any], endpoint: str) -> dict[str, Any]:
        return summary.get("endpoint_summaries", {}).get(endpoint, {})

    comp: dict[str, Any] = {"by_endpoint": {}}
    endpoints = sorted(
        set(on_summary.get("endpoint_summaries", {}).keys())
        | set(off_summary.get("endpoint_summaries", {}).keys())
    )
    for ep in endpoints:
        on_ep = endpoint_summary(on_summary, ep)
        off_ep = endpoint_summary(off_summary, ep)
        on_mean = to_float(on_ep.get("mean_ms"))
        off_mean = to_float(off_ep.get("mean_ms"))
        on_median = to_float(on_ep.get("median_ms"))
        off_median = to_float(off_ep.get("median_ms"))
        on_p95 = to_float(on_ep.get("p95_ms"))
        off_p95 = to_float(off_ep.get("p95_ms"))
        comp["by_endpoint"][ep] = {
            "delta_mean_ms": (on_mean - off_mean) if on_mean is not None and off_mean is not None else None,
            "delta_median_ms": (on_median - off_median) if on_median is not None and off_median is not None else None,
            "delta_p95_ms": (on_p95 - off_p95) if on_p95 is not None and off_p95 is not None else None,
            "percent_change_mean": pct_delta(on_mean, off_mean),
            "percent_change_median": pct_delta(on_median, off_median),
            "percent_change_p95": pct_delta(on_p95, off_p95),
            "chunk_on": on_ep,
            "chunk_off": off_ep,
        }
    return comp


def render_report(
    *,
    comparison: dict[str, Any],
    off_summary: dict[str, Any],
    on_summary: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    def fmt(v: Any) -> str:
        if v is None:
            return "n/a"
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    lines: list[str] = []
    lines.append("# PMO Audible Latency Benchmark")
    lines.append("")
    lines.append("## Method")
    lines.append(f"- Input recording: `{Path(off_summary['audio']).name}`.")
    lines.append(f"- Transcript used: \"{off_summary['transcript_used']}\".")
    lines.append("- Metric boundary: transcript ready -> full PMO audio playback finished.")
    lines.append(
        f"- Runs per mode: {off_summary['measured_runs']} measured + {off_summary['warmup_runs']} warmup."
    )
    lines.append("- Modes: `chunk_off` (`PMO_TTS_STREAM=0`) vs `chunk_on` (`PMO_TTS_STREAM=1`), with `PMO_TTS=1` in both.")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Endpoint | Mode | Mean (ms) | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Std (ms) | Failures |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for endpoint in sorted(set(off_summary["endpoint_summaries"]) | set(on_summary["endpoint_summaries"])):
        off_ep = off_summary["endpoint_summaries"].get(endpoint, {})
        on_ep = on_summary["endpoint_summaries"].get(endpoint, {})
        lines.append(
            f"| `{endpoint}` | chunk_off | {fmt(off_ep.get('mean_ms'))} | {fmt(off_ep.get('p50_ms'))} | {fmt(off_ep.get('p90_ms'))} | {fmt(off_ep.get('p95_ms'))} | {fmt(off_ep.get('p99_ms'))} | {fmt(off_ep.get('std_ms'))} | {fmt(off_ep.get('count_failure'))} |"
        )
        lines.append(
            f"| `{endpoint}` | chunk_on | {fmt(on_ep.get('mean_ms'))} | {fmt(on_ep.get('p50_ms'))} | {fmt(on_ep.get('p90_ms'))} | {fmt(on_ep.get('p95_ms'))} | {fmt(on_ep.get('p99_ms'))} | {fmt(on_ep.get('std_ms'))} | {fmt(on_ep.get('count_failure'))} |"
        )
    lines.append("")
    lines.append("## Chunking Delta (chunk_on - chunk_off)")
    for endpoint, ep_comp in comparison["by_endpoint"].items():
        lines.append(
            f"- `{endpoint}`: mean {fmt(ep_comp['delta_mean_ms'])} ms ({fmt(ep_comp['percent_change_mean'])}%), "
            f"median {fmt(ep_comp['delta_median_ms'])} ms ({fmt(ep_comp['percent_change_median'])}%), "
            f"p95 {fmt(ep_comp['delta_p95_ms'])} ms ({fmt(ep_comp['percent_change_p95'])}%)."
        )
    lines.append("")
    lines.append("## Validity Notes")
    lines.append("- OFF and ON were run back-to-back in one automation pass to reduce environment drift.")
    lines.append("- This metric is user-facing voice latency, not HTTP request latency.")
    lines.append("")
    lines.append("## Reproducibility")
    lines.append(f"- Timestamp: {metadata['timestamp']}")
    lines.append(f"- Python: {metadata['python_version']}")
    lines.append(f"- OS: {metadata['platform']}")
    lines.append(f"- Git commit: {metadata.get('git_commit')}")
    lines.append(f"- PMO_STT: {metadata.get('pmo_stt')}")
    lines.append(f"- PMO_TTS: {metadata.get('pmo_tts')}")
    return "\n".join(lines) + "\n"


def run_mode(
    *,
    mode: str,
    tts_stream_value: str,
    args: argparse.Namespace,
    bench_dir: Path,
    logs_dir: Path,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PMO_TTS"] = "1"
    env["PMO_TTS_STREAM"] = tts_stream_value
    env.setdefault("PYTHONUNBUFFERED", "1")

    runner_log = logs_dir / f"runner_{mode}.log"
    script_path = PROJECT_ROOT / "scripts" / "benchmark_pmo_latency.py"
    runner_cmd = [
        sys.executable,
        str(script_path),
        "--mode",
        mode,
        "--audio",
        str(Path(args.audio).resolve()),
        "--chat-text",
        args.chat_text,
        "--warmup-runs",
        str(args.warmup_runs),
        "--measured-runs",
        str(args.measured_runs),
        "--inter-run-delay",
        str(args.inter_run_delay),
        "--output-dir",
        str(bench_dir),
    ]

    with runner_log.open("w", encoding="utf-8") as rlog:
        r = subprocess.run(
            runner_cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=rlog,
            stderr=subprocess.STDOUT,
            timeout=args.mode_timeout_s,
        )
    if r.returncode != 0:
        raise RuntimeError(f"Benchmark runner failed in {mode}; check {runner_log}")
    summary_path = bench_dir / "summary" / f"{mode}_summary.json"
    return json.loads(summary_path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PMO latency suite end-to-end.")
    parser.add_argument("--audio", required=True, help="Path to Arcane.m4a")
    parser.add_argument("--chat-text", default=DEFAULT_CHAT_TEXT)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measured-runs", type=int, default=15)
    parser.add_argument("--inter-run-delay", type=float, default=1.5)
    parser.add_argument("--mode-timeout-s", type=int, default=7200)
    parser.add_argument("--output-root", default=str(PROJECT_ROOT / "benchmarks"))
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()
    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        raise FileNotFoundError(f"Missing audio fixture: {audio_path}")

    out_root = Path(args.output_root).resolve()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bench_dir = out_root / ts
    logs_dir = bench_dir / "logs"
    summary_dir = bench_dir / "summary"
    report_dir = bench_dir / "report"
    for d in (logs_dir, summary_dir, report_dir):
        d.mkdir(parents=True, exist_ok=True)

    off_summary = run_mode(
        mode="chunk_off",
        tts_stream_value="0",
        args=args,
        bench_dir=bench_dir,
        logs_dir=logs_dir,
    )
    on_summary = run_mode(
        mode="chunk_on",
        tts_stream_value="1",
        args=args,
        bench_dir=bench_dir,
        logs_dir=logs_dir,
    )

    comparison = compare_mode(on_summary, off_summary)
    comparison_path = summary_dir / "comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    metadata = {
        "timestamp": ts,
        "python_version": sys.version,
        "platform": platform.platform(),
        "git_commit": maybe_git_commit(PROJECT_ROOT),
        "pmo_tts": "1",
        "pmo_stt": os.getenv("PMO_STT", "openai"),
        "audio_fixture": str(audio_path),
        "warmup_runs": args.warmup_runs,
        "measured_runs": args.measured_runs,
        "inter_run_delay": args.inter_run_delay,
        "chat_text": args.chat_text,
        "measurement_definition": "transcript_ready_to_audio_finished",
    }
    metadata_path = summary_dir / "reproducibility.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    report = render_report(
        comparison=comparison,
        off_summary=off_summary,
        on_summary=on_summary,
        metadata=metadata,
    )
    report_path = report_dir / "final_report_latency_section.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"Benchmark suite complete: {bench_dir}")
    print(f"Report: {report_path}")
    print(f"Comparison: {comparison_path}")


if __name__ == "__main__":
    main()
