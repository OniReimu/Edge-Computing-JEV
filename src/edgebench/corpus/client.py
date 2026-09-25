"""OpenRouter client for corpus generation and blind verification with spend caps and logging.

Used by the `pilot` subcommand. The frozen EdgeIntent v1 corpus was produced through the file exchange instead
(generators Gemini-3.8-Flash and Claude-Opus-5.5, verifier Claude-Opus-5.5; see data/edgebench/v1/manifest.json).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable

from src.edgebench.interpreters.transport import make_request

GENERATOR_MODEL = "anthropic/claude-sonnet-5"
VERIFIER_MODEL = "openai/gpt-5.6-sol"
SPEND_CAP_USD = 120.0


@dataclass
class CallLog:
    timestamp: float
    call_index: int
    call_type: str  # "generation" | "verification"
    prompt_hash: str
    model: str
    resolved_model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    raw_output: str


class CorpusLLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai",
        path: str = "/api/v1/chat/completions",
        log_dir: str | Path = "runs/_corpus",
        spend_cap_usd: float = SPEND_CAP_USD,
        transport_override: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.path = path
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "calls.jsonl"
        self.spend_cap_usd = spend_cap_usd
        self.transport_override = transport_override

        self.call_count = 0
        self.total_cost_usd = 0.0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

        # Load existing cumulative cost from log file if present
        self._sync_existing_logs()

    def _sync_existing_logs(self) -> None:
        if not self.log_file.exists():
            return
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    self.call_count += 1
                    self.total_cost_usd += float(data.get("cost_usd", 0.0))
                    tokens = data.get("tokens", {})
                    self.total_input_tokens += int(tokens.get("input", 0))
                    self.total_output_tokens += int(tokens.get("output", 0))
                except Exception:
                    pass

    def check_spend_cap(self) -> None:
        if self.total_cost_usd >= self.spend_cap_usd:
            raise RuntimeError(
                f"Hard spend cap exceeded: ${self.total_cost_usd:.4f} >= ${self.spend_cap_usd:.2f}"
            )

    def _log_call(self, log: CallLog) -> None:
        self.call_count += 1
        self.total_cost_usd += log.cost_usd
        self.total_input_tokens += log.input_tokens
        self.total_output_tokens += log.output_tokens

        record = {
            "timestamp": log.timestamp,
            "call_index": log.call_index,
            "call_type": log.call_type,
            "prompt_hash": log.prompt_hash,
            "model": log.model,
            "resolved_model": log.resolved_model,
            "tokens": {
                "input": log.input_tokens,
                "output": log.output_tokens,
                "total": log.input_tokens + log.output_tokens,
            },
            "cost_usd": log.cost_usd,
            "raw_output": log.raw_output,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        if self.call_count % 50 == 0:
            print(f"[Call {self.call_count}] Running cost: ${self.total_cost_usd:.4f}")

    def call_chat_completion(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
        schema_name: str,
        temperature: float,
        call_type: str,
    ) -> dict[str, Any]:
        self.check_spend_cap()

        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        prompt_str = json.dumps(payload, sort_keys=True)
        prompt_hash = hashlib.sha256(prompt_str.encode("utf-8")).hexdigest()

        if self.transport_override is not None:
            status, raw_resp, latency_s, err_type = self.transport_override(payload)
        else:
            status, raw_resp, latency_s, _, _, err_type, _ = make_request(
                base_url=self.base_url,
                path=self.path,
                payload=payload,
                api_key=self.api_key,
                timeout_s=60.0,
            )

        if err_type is not None or status != 200:
            raise RuntimeError(f"OpenRouter API error: status={status}, err={err_type}, body={raw_resp[:300]}")

        try:
            body = json.loads(raw_resp)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse OpenRouter response JSON: {exc}, raw: {raw_resp[:300]}") from exc

        resolved_model = str(body.get("model", model))
        usage = body.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("completion_tokens", 0) or usage.get("output_tokens", 0) or 0)
        cost_usd = float(usage.get("cost", 0.0) or 0.0)

        # Fallback price calculation if cost is 0.0
        if cost_usd == 0.0:
            if "claude-sonnet-5" in model:
                # Approx $3 / $15 per Mtok
                cost_usd = (input_tokens * 3.0 + output_tokens * 15.0) / 1e6
            elif "gpt-5.6" in model:
                # Approx $2.50 / $10 per Mtok
                cost_usd = (input_tokens * 2.5 + output_tokens * 10.0) / 1e6

        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError(f"No choices returned in response: {raw_resp[:300]}")

        content_str = choices[0].get("message", {}).get("content", "")
        try:
            parsed_content = json.loads(content_str)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse content JSON schema from model: {exc}, content: {content_str[:300]}") from exc

        # Log call
        log_entry = CallLog(
            timestamp=time.time(),
            call_index=self.call_count + 1,
            call_type=call_type,
            prompt_hash=prompt_hash,
            model=model,
            resolved_model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            raw_output=content_str,
        )
        self._log_call(log_entry)

        return parsed_content
