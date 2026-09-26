"""极简的 OpenAI 兼容本地模型服务（开发／测试用，不替代真实模型）。

用途：

1. **离线验证本地适配器**：没有安装 Ollama／LM Studio 时，也能端到端验证
   「本地提供方」的接线（真实 socket、真实 HTTP、不联网、不花钱）；
2. **严格模式**：默认会像严格的本地推理服务那样，**拒绝 DeepSeek 专有字段**
   （``thinking``／``reasoning_effort``）——这正是本地适配器最容易踩的坑，
   因此用它来证明本地请求体没有泄漏云服务专有字段。

它**不产生**任何有意义的对话内容：只回放固定的行动脚本，用于验证链路而非质量。
真实质量仍须接真实本地模型并人工观察。

用法::

    # 终端 1：启动假本地服务（默认 127.0.0.1:11434，模拟 Ollama）
    uv run python scripts/fake_local_model.py --port 11434 --model qwen2.5:7b

    # 终端 2：让 SceneWeave 使用本地提供方
    #   .env 中设置 SCENEWEAVE_MODEL_PROVIDER=local
    #            SCENEWEAVE_MODEL_BASE_URL=http://127.0.0.1:11434/v1
    #            SCENEWEAVE_MODEL_NAME=qwen2.5:7b
"""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: 回放用行动脚本：交替 SPEAK／PASS，使场景既能推进也能停下。
DEFAULT_ACTIONS: tuple[dict[str, Any], ...] = (
    {"action": "SPEAK", "text": "今晚要不要一起吃饭？"},
    {"action": "SPEAK", "text": "我想先休息一会儿。"},
    {"action": "PASS", "text": ""},
    {"action": "PASS", "text": ""},
)

#: 严格模式拒绝的字段（DeepSeek 专有；本地服务不认识它们）。
REJECTED_FIELDS = ("thinking", "reasoning_effort")

#: 场景：正常、空内容、被截断、非法 JSON、服务端错误。
SCENARIOS = ("speak", "empty", "truncated", "invalid-json", "server-error")


@dataclass
class Recorder:
    """记录收到的请求，供测试断言（不含任何凭证）。"""

    payloads: list[dict[str, Any]] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    @property
    def calls(self) -> int:
        return len(self.payloads)


class _Handler(BaseHTTPRequestHandler):
    server_version = "FakeLocalModel/1.0"

    # 由 serve() 注入
    recorder: Recorder
    actions: tuple[dict[str, Any], ...] = DEFAULT_ACTIONS
    scenario: str = "speak"
    model: str = "fake-local-model"
    strict: bool = True
    latency_seconds: float = 0.0

    def log_message(self, *args: Any) -> None:  # noqa: D102 - 静音，避免污染测试输出
        return

    # --- 辅助 ---

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str, kind: str = "invalid_request_error") -> None:
        self._send(status, {"error": {"message": message, "type": kind, "code": status}})

    def _next_action(self, index: int) -> dict[str, Any]:
        if not self.actions:
            return {"action": "PASS", "text": ""}
        return self.actions[min(index, len(self.actions) - 1)]

    # --- 路由 ---

    def do_GET(self) -> None:  # noqa: N802 - http.server 约定
        self.recorder.paths.append(self.path)
        if self.path.rstrip("/").endswith("/v1/models"):
            self._send(200, {"object": "list", "data": [{"id": self.model, "object": "model"}]})
            return
        self._error(404, f"未知路径：{self.path}", kind="not_found")

    def do_POST(self) -> None:  # noqa: N802 - http.server 约定
        self.recorder.paths.append(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except ValueError:
            self._error(400, "请求体不是合法 JSON")
            return

        self.recorder.payloads.append(payload)
        self.recorder.headers.append({k.lower(): v for k, v in self.headers.items()})

        if not self.path.rstrip("/").endswith("/v1/chat/completions"):
            self._error(404, f"未知路径：{self.path}", kind="not_found")
            return

        if self.strict:
            leaked = [name for name in REJECTED_FIELDS if name in payload]
            if leaked:
                # 模拟严格的本地服务：不认识这些云服务专有字段，直接拒绝。
                self._error(400, f"不支持的字段：{', '.join(leaked)}（本地服务不认识）")
                return

        if self.scenario == "server-error":
            self._error(500, "模拟的本地服务内部错误", kind="server_error")
            return

        if self.latency_seconds:
            import time as _time

            _time.sleep(self.latency_seconds)

        index = len(self.recorder.payloads) - 1
        if self.scenario == "empty":
            content, finish = None, "stop"
        elif self.scenario == "truncated":
            content, finish = '{"action": "SPEAK", "text": "被截断的输', "length"
        elif self.scenario == "invalid-json":
            content, finish = "这不是 JSON", "stop"
        else:
            content, finish = json.dumps(self._next_action(index), ensure_ascii=False), "stop"

        self._send(
            200,
            {
                "id": f"chatcmpl-fake-{index}",
                "object": "chat.completion",
                "created": 0,
                "model": payload.get("model", self.model),
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": finish,
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": 11,
                },
            },
        )


@dataclass
class FakeLocalServer:
    """运行中的假本地服务，可用作上下文管理器。"""

    base_url: str
    recorder: Recorder
    _httpd: ThreadingHTTPServer
    _thread: threading.Thread

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)

    def __enter__(self) -> FakeLocalServer:
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    scenario: str = "speak",
    actions: tuple[dict[str, Any], ...] | None = None,
    model: str = "fake-local-model",
    strict: bool = True,
    latency_seconds: float = 0.0,
) -> FakeLocalServer:
    """在后台线程启动假本地服务；``port=0`` 表示由系统分配空闲端口。"""

    if scenario not in SCENARIOS:
        raise ValueError(f"scenario 必须是 {SCENARIOS} 之一，收到 {scenario!r}")

    recorder = Recorder()
    handler = type(
        "BoundHandler",
        (_Handler,),
        {
            "recorder": recorder,
            "actions": actions if actions is not None else DEFAULT_ACTIONS,
            "scenario": scenario,
            "model": model,
            "strict": strict,
            "latency_seconds": latency_seconds,
        },
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    actual_port = httpd.server_address[1]
    return FakeLocalServer(
        base_url=f"http://{host}:{actual_port}/v1",
        recorder=recorder,
        _httpd=httpd,
        _thread=thread,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI 兼容的假本地模型服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=11434, help="0 表示自动分配")
    parser.add_argument("--model", default="fake-local-model")
    parser.add_argument("--scenario", choices=SCENARIOS, default="speak")
    parser.add_argument(
        "--lenient",
        action="store_true",
        help="宽松模式：不拒绝 thinking／reasoning_effort 等云服务专有字段",
    )
    parser.add_argument("--latency", type=float, default=0.0, help="每次响应前的人为延迟（秒）")
    args = parser.parse_args()

    server = serve(
        host=args.host,
        port=args.port,
        model=args.model,
        scenario=args.scenario,
        strict=not args.lenient,
        latency_seconds=args.latency,
    )
    print(f"假本地模型服务已启动：{server.base_url}")
    print(f"  POST {server.base_url}/chat/completions")
    print(f"  GET  {server.base_url}/models")
    print(f"  模型名：{args.model}｜场景：{args.scenario}｜严格模式：{not args.lenient}")
    print("  提示：这不是真实模型，只回放固定脚本，用于验证链路而非对话质量。")
    print("  按 Ctrl+C 停止。")
    try:
        while True:
            import time as _time

            _time.sleep(1)
    except KeyboardInterrupt:
        print("\n停止中…")
        server.stop()
        print(f"共收到 {server.recorder.calls} 次调用。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
