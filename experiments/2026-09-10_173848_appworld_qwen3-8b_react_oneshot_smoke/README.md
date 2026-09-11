# AppWorld Qwen3-8B smoke test

- Scope: environment validation, not a benchmark claim.
- Dataset: all three task variants from one dev scenario (`50e1ac9`).
- Agent: official `simplified_react_code_agent`.
- Model preset: official `qwen3-8b-with-reasoning`.
- Prompt: official prompt unchanged. It contains one worked Spotify example, so this run is one-shot rather than strict zero-shot.
- Model weights: `/root/autodl-tmp/models/Qwen3-8B` (read-only use).
- AppWorld source/data: original benchmark remains read-only; outputs and mutable database copies stay below this experiment directory.
- Inference server: vLLM 0.10.2, one GPU, local OpenAI-compatible endpoint managed by the AppWorld runner.
