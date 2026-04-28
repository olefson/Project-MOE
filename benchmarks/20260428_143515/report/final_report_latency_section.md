# PMO Audible Latency Benchmark

## Method
- Input recording: `Arcane.m4a`.
- Transcript used: "Tell me about the animated series Arcane, by RIOT".
- Metric boundary: transcript ready -> full PMO audio playback finished.
- Runs per mode: 15 measured + 1 warmup.
- Modes: `chunk_off` (`PMO_TTS_STREAM=0`) vs `chunk_on` (`PMO_TTS_STREAM=1`), with `PMO_TTS=1` in both.

## Results

| Endpoint | Mode | Mean (ms) | P50 (ms) | P90 (ms) | P95 (ms) | P99 (ms) | Std (ms) | Failures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `audible_turn` | chunk_off | 84301.111 | 84163.316 | 96292.185 | 97312.388 | 98024.455 | 8370.096 | 0 |
| `audible_turn` | chunk_on | 63369.399 | 63492.205 | 69163.183 | 71837.003 | 76065.559 | 5964.812 | 0 |

## Chunking Delta (chunk_on - chunk_off)
- `audible_turn`: mean -20931.712 ms (-24.830%), median -20671.111 ms (-24.561%), p95 -25475.385 ms (-26.179%).

## Validity Notes
- OFF and ON were run back-to-back in one automation pass to reduce environment drift.
- This metric is user-facing voice latency, not HTTP request latency.

## Reproducibility
- Timestamp: 20260428_143515
- Python: 3.13.7 (tags/v3.13.7:bcee1c3, Aug 14 2025, 14:15:11) [MSC v.1944 64 bit (AMD64)]
- OS: Windows-11-10.0.26200-SP0
- Git commit: 34efbe4754776c5ad8ddafb61e28e8f200953159
- PMO_STT: openai
- PMO_TTS: 1
