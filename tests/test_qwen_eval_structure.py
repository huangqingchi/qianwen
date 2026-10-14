"""验证单项评测能独立运行、写分数，并处理流式及错误响应。"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


RUNNER = Path(__file__).resolve().parents[1] / "评测" / "run.py"
PROJECT_ROOT = RUNNER.parents[1]


class FakeChat(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer local-test-key":
            status, body = 401, {"error": {"code": "invalid_api_key", "message": "bad key"}}
        elif payload["model"].startswith("not-a-real-model"):
            status, body = 404, {"error": {"code": "model_not_found", "message": "bad model"}}
        elif not isinstance(payload["messages"], list):
            status, body = 400, {"error": {"code": "invalid_parameter", "message": "bad messages"}}
        else:
            messages = payload["messages"]
            if messages and messages[0]["role"] == "system":
                question = messages[-1]["content"]
                cached = (0 if "第一个问题" in question else
                          1024 if "第二个问题" in question else 1536)
                usage = {"prompt_tokens": 2048, "completion_tokens": 1,
                         "total_tokens": 2049,
                         "prompt_tokens_details": {"cached_tokens": cached}}
            else:
                usage = {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
            status, body = 200, {
                "id": "test-1", "object": "chat.completion", "model": payload["model"],
                "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "OK"}}],
                "usage": usage,
            }
        if payload.get("stream") and status == 200:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in (
                {"choices": [{"delta": {"content": "OK"}}]},
                {"choices": [], "usage": body["usage"]},
            ):
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def test_each_item_has_its_own_score_and_report(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeChat)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = {**os.environ, "DASHSCOPE_API_KEY": "local-test-key"}
        for item, expected_count in (("用量统计", 2), ("错误契约", 3), ("缓存命中", 1)):
            output = tmp_path / item
            # 模块方式和“从项目外执行脚本”各跑一次，覆盖两种启动路径。
            if item == "用量统计":
                command = [sys.executable, "-m", "评测.run"]
                working_dir = PROJECT_ROOT
            else:
                command = [sys.executable, str(RUNNER)]
                working_dir = tmp_path
            process = subprocess.run(
                [*command, "--item", item,
                 "--base-url", f"http://127.0.0.1:{server.server_port}",
                 "--output-dir", str(output)],
                cwd=working_dir, env=env, capture_output=True, timeout=30,
            )
            assert process.returncode == 0, process.stderr.decode(errors="replace")
            result = json.loads((output / item / "结果.json").read_text(encoding="utf-8"))
            assert result["计分"]["通过数"] == expected_count
            assert result["计分"]["本地用例分数"] == 100
            assert all(check["结果"] == "通过" for check in result["用例结果"])
            if item == "用量统计":
                assert "输入 token 数" in result["用例结果"][0]
                assert "令牌" not in json.dumps(result, ensure_ascii=False)
            if item == "缓存命中":
                assert result["用例结果"][0]["缓存命中率（%）"] == 62.5
            assert (output / item / "报告.md").exists()
            assert (output / "总览.md").exists()
            pdf = output / "评测汇总.pdf"
            assert pdf.read_bytes().startswith(b"%PDF-")
            assert len(list(output.glob("*/结果.json"))) == 1
            assert "local-test-key" not in json.dumps(result)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_module_command_works_from_project_root():
    process = subprocess.run(
        [sys.executable, "-m", "评测.run", "--list"],
        cwd=PROJECT_ROOT, capture_output=True, timeout=10,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
