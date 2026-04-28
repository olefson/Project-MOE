from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import statistics
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from main import SYSTEM_PROMPT, get_current_time_context, run_agent_turn
from memory import format_context, get_relevant, init_db
from tools import get_tool_definitions
from transcription import transcribe_upload
from tts import speak as tts_speak

DEFAULT_CHAT_TEXT = "Tell me about the animated series Arcane, by RIOT"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * (p / 100.0)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return values[lo]
    frac = rank - lo
    return values[lo] * (1.0 - frac) + values[hi] * frac


def ci95(values: list[float], seed: int = 42, samples: int = 1000) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(samples):
        pick = [values[rng.randrange(0, n)] for _ in range(n)]
        means.append(sum(pick) / n)
    means.sort()
    return percentile(means, 2.5), percentile(means, 97.5)


@dataclass
class RunRecord:
    run_id: str
    mode: str
    endpoint: str
    start_ts: str
    end_ts: str
    latency_ms_total: float | None
    http_status: int | None
    success: bool
    error_type: str | None
    error_message: str | None
    transcript_chars: int
    reply_chars: int
    tool_call_count: int
    memory_count: int
    session_id: str | None
    audio_filename: str | None
    attempt_index: int
    is_warmup: bool


def summarize_endpoint(records: list[RunRecord]) -> dict[str, Any]:
    warmups = [r for r in records if r.is_warmup]
    measured = [r for r in records if not r.is_warmup]
    ok = [r for r in measured if r.success and r.latency_ms_total is not None]
    latencies = sorted([r.latency_ms_total for r in ok if r.latency_ms_total is not None])
    ci_low, ci_high = ci95(latencies)
    return {
        "count_total": len(measured),
        "count_success": len(ok),
        "count_failure": len(measured) - len(ok),
        "failure_rate": ((len(measured) - len(ok)) / len(measured)) if measured else None,
        "warmup_count": len(warmups),
        "mean_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "p50_ms": statistics.median(latencies) if latencies else None,
        "median_ms": statistics.median(latencies) if latencies else None,
        "std_ms": statistics.stdev(latencies) if len(latencies) > 1 else (0.0 if len(latencies) == 1 else None),
        "min_ms": min(latencies) if latencies else None,
        "max_ms": max(latencies) if latencies else None,
        "p90_ms": percentile(latencies, 90),
        "p95_ms": percentile(latencies, 95),
        "p99_ms": percentile(latencies, 99),
        "ci95_low_ms": ci_low,
        "ci95_high_ms": ci_high,
    }


def write_raw(records: list[RunRecord], out_dir: Path) -> None:
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv_path = raw_dir / "latency_runs.csv"
    jsonl_path = raw_dir / "latency_runs.jsonl"
    fieldnames = list(asdict(records[0]).keys()) if records else list(RunRecord.__annotations__.keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in records:
            writer.writerow(asdict(row))
    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")


def build_messages(client: OpenAI, user_text: str) -> tuple[list[dict], int]:
    time_block = get_current_time_context()
    entries = get_relevant(client, user_text, top_k=7)
    context_str = format_context(entries)
    if context_str:
        system = SYSTEM_PROMPT + "\n\n" + time_block + "\n\n[Relevant memory]:\n" + context_str
    else:
        system = SYSTEM_PROMPT + "\n\n" + time_block
    return [{"role": "system", "content": system}, {"role": "user", "content": user_text}], len(entries)


def run_audible_benchmark(
    *,
    mode: str,
    transcript: str,
    audio_name: str,
    client: OpenAI,
    tools: list[dict],
    warmup_runs: int,
    measured_runs: int,
    inter_run_delay: float,
) -> list[RunRecord]:
    total_runs = warmup_runs + measured_runs
    rows: list[RunRecord] = []
    for i in range(1, total_runs + 1):
        is_warmup = i <= warmup_runs
        run_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        start_ts = now_iso()
        reply = ""
        tool_calls_made: list[dict] = []
        memory_count = 0
        t0 = time.perf_counter()
        ok = False
        err_type: str | None = None
        err_msg: str | None = None
        try:
            messages, memory_count = build_messages(client, transcript)
            reply, _, tool_calls_made, spoke_stream = run_agent_turn(client, messages, tools)
            if (
                reply
                and os.getenv("PMO_TTS", "1").strip().lower() not in ("0", "false", "no")
                and not spoke_stream
            ):
                tts_speak(reply)
            ok = True
        except Exception as e:
            err_type = "turn_error"
            err_msg = str(e)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        rows.append(
            RunRecord(
                run_id=run_id,
                mode=mode,
                endpoint="audible_turn",
                start_ts=start_ts,
                end_ts=now_iso(),
                latency_ms_total=elapsed_ms if ok else None,
                http_status=None,
                success=ok,
                error_type=err_type,
                error_message=err_msg,
                transcript_chars=len(transcript),
                reply_chars=len(reply),
                tool_call_count=len(tool_calls_made),
                memory_count=memory_count,
                session_id=session_id,
                audio_filename=audio_name,
                attempt_index=i,
                is_warmup=is_warmup,
            )
        )
        if i < total_runs:
            time.sleep(inter_run_delay)
    return rows


def resolve_transcript(client: OpenAI, audio_path: Path, explicit_text: str | None) -> str:
    if explicit_text and explicit_text.strip():
        return explicit_text.strip()
    blob = audio_path.read_bytes()
    transcript = transcribe_upload(client, blob, audio_path.name)
    if not transcript:
        raise RuntimeError("Failed to produce transcript from input audio")
    return transcript


def run_all(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    init_db()
    client = OpenAI(api_key=api_key)
    tools = get_tool_definitions()
    audio_path = Path(args.audio).resolve()
    transcript = resolve_transcript(client, audio_path, args.chat_text)

    records = run_audible_benchmark(
        mode=args.mode,
        transcript=transcript,
        audio_name=audio_path.name,
        client=client,
        tools=tools,
        warmup_runs=args.warmup_runs,
        measured_runs=args.measured_runs,
        inter_run_delay=args.inter_run_delay,
    )
    write_raw(records, out_dir)

    endpoint_groups: dict[str, list[RunRecord]] = {}
    for row in records:
        endpoint_groups.setdefault(row.endpoint, []).append(row)
    summary = {
        "mode": args.mode,
        "audio": str(audio_path),
        "transcript_used": transcript,
        "warmup_runs": args.warmup_runs,
        "measured_runs": args.measured_runs,
        "inter_run_delay": args.inter_run_delay,
        "measurement_definition": "transcript_ready_to_audio_finished",
        "created_at": now_iso(),
        "endpoint_summaries": {k: summarize_endpoint(v) for k, v in endpoint_groups.items()},
    }
    summary_dir = out_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{args.mode}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark PMO audible completion latency for one mode.")
    parser.add_argument("--mode", required=True, choices=["chunk_off", "chunk_on"])
    parser.add_argument("--audio", required=True, help="Path to Arcane.m4a")
    parser.add_argument("--chat-text", default=None, help="Optional override transcript text")
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--measured-runs", type=int, default=15)
    parser.add_argument("--inter-run-delay", type=float, default=1.5)
    parser.add_argument("--output-dir", required=True, help="Timestamped benchmark output folder")
    return parser.parse_args()


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    args = parse_args()
    audio_path = Path(args.audio)
    if not audio_path.exists():
        raise FileNotFoundError(f"Missing audio fixture: {args.audio}")
    run_all(args)


if __name__ == "__main__":
    main()
