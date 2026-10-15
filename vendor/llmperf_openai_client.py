"""OpenAI-compatible streaming client for LLMPerf's Ray load runner."""

import json
import time

import ray
import requests

from llmperf import common_metrics
from llmperf.models import RequestConfig
from llmperf.ray_llm_client import LLMClient


@ray.remote
class OpenAIChatCompletionsClient(LLMClient):
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()

    def llm_request(self, request_config: RequestConfig):
        prompt, prompt_len = request_config.prompt
        body = {
            "model": request_config.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            **(request_config.sampling_params or {}),
        }
        started = time.perf_counter()
        first_event = first_visible = None
        event_times = []
        visible = []
        usage = None
        status = None
        done = False
        finish_reason = None
        error_code = None
        try:
            with self.session.post(
                f"{self.base_url}/chat/completions", json=body, stream=True,
                timeout=(15, 180), headers={"Authorization": f"Bearer {self.api_key}"},
            ) as response:
                status = response.status_code
                response.raise_for_status()
                data_lines = []
                for raw in response.iter_lines(decode_unicode=False):
                    if raw:
                        if raw.startswith(b"data:"):
                            data_lines.append(raw[5:].strip())
                        continue
                    if not data_lines:
                        continue
                    data = b"\n".join(data_lines)
                    data_lines = []
                    if data == b"[DONE]":
                        done = True
                        break
                    event = json.loads(data)
                    if "error" in event:
                        raise ValueError("stream_error")
                    if event.get("usage"):
                        usage = event["usage"]
                    for choice in event.get("choices") or []:
                        if choice.get("finish_reason") is not None:
                            finish_reason = choice["finish_reason"]
                        delta = choice.get("delta") or {}
                        content = delta.get("content") or ""
                        reasoning = delta.get("reasoning_content") or ""
                        if content or reasoning:
                            now_ms = (time.perf_counter() - started) * 1000
                            event_times.append(round(now_ms, 2))
                            if first_event is None:
                                first_event = now_ms
                            if content:
                                if first_visible is None:
                                    first_visible = now_ms
                                visible.append(content)
                if not done:
                    error_code = "incomplete_stream"
                elif finish_reason == "length":
                    error_code = "truncated_output"
                elif finish_reason not in (None, "stop"):
                    error_code = "unexpected_finish_reason"
                elif not visible:
                    error_code = "empty_answer"
        except requests.HTTPError:
            error_code = f"http_{status}"
        except requests.Timeout:
            error_code = "timeout"
        except requests.RequestException:
            error_code = "connection_error"
        except (ValueError, json.JSONDecodeError):
            error_code = "invalid_stream"

        elapsed = time.perf_counter() - started
        output_tokens = (usage or {}).get("completion_tokens")
        input_tokens = (usage or {}).get("prompt_tokens")
        metrics = {
            common_metrics.ERROR_CODE: error_code,
            common_metrics.ERROR_MSG: "",
            common_metrics.TTFT: first_event / 1000 if first_event is not None else None,
            common_metrics.E2E_LAT: elapsed,
            common_metrics.INTER_TOKEN_LAT: None,
            common_metrics.NUM_INPUT_TOKENS: input_tokens,
            common_metrics.NUM_OUTPUT_TOKENS: output_tokens,
            common_metrics.NUM_TOTAL_TOKENS: (usage or {}).get("total_tokens"),
            common_metrics.REQ_OUTPUT_THROUGHPUT: None,
            "http_status": status,
            "done": done,
            "finish_reason": finish_reason,
            "first_generated_event_ms": round(first_event, 2) if first_event is not None else None,
            "first_visible_text_ms": round(first_visible, 2) if first_visible is not None else None,
            "generated_event_ms": event_times,
            "visible_chars": len("".join(visible)),
            "usage": usage,
            "requested_input_tokens_estimate": prompt_len,
        }
        return metrics, "".join(visible), request_config
