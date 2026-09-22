# -*- coding: utf-8 -*-
"""
现代网页界面的本地服务
========================

完全基于 Python 标准库实现（``http.server`` + ``json``），不需要安装任何第三方包：

* ``GET  /``                       前端页面（单页应用，静态文件位于 ``static/``）
* ``GET  /api/models``             返回所有已注册模型的描述 + 可用界面后端
* ``POST /api/model/<key>/action`` 执行模型动作，返回 JSON 结果

计算在前端发起的 HTTP 请求里同步完成（单次生成只需几毫秒，批量统计由前端分块调用），
因此不需要 WebSocket / SSE，天然支持中断与进度显示。
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlsplit

from ... import __version__
from ...registry import load_models
from ...spec import ModelSpec

__all__ = ["serve", "build_server"]

STATIC_DIR = Path(__file__).resolve().parent / "static"
_ACTION_RE = re.compile(r"^/api/model/([^/]+)/action$")


class PrismathHandler(BaseHTTPRequestHandler):
    """处理静态文件与 JSON API 的请求处理器。"""

    server_version = f"Prismath/{__version__}"
    protocol_version = "HTTP/1.1"

    # ---------------- 工具方法 ----------------
    @property
    def spec(self) -> ModelSpec:
        return self.server.model_spec  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: Any) -> None:  # 精简日志
        if os.environ.get("PRISMATH_VERBOSE"):
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):  # 浏览器提前断开
            pass

    def _json(self, payload: Dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _file(self, relative: str) -> None:
        """安全地返回 ``static/`` 下的静态文件。"""
        target = (STATIC_DIR / relative).resolve()
        try:
            target.relative_to(STATIC_DIR)   # 阻止 ../ 越权访问
        except ValueError:
            self._json({"ok": False, "error": "非法路径"}, 403)
            return
        if not target.is_file():
            self._json({"ok": False, "error": f"文件不存在：{relative}"}, 404)
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ---------------- 路由 ----------------
    def do_GET(self) -> None:  # noqa: N802  (BaseHTTPRequestHandler 约定)
        path = unquote(urlsplit(self.path).path)
        if path == "/api/models":
            self._json(
                {
                    "ok": True,
                    "models": [spec.to_dict() for spec in load_models()],
                    "uis": [ui.to_dict() for ui in _ui_list()],
                }
            )
            return
        if path in ("/", "/index.html"):
            self._file("index.html")
            return
        if path.startswith("/api/"):
            self._json({"ok": False, "error": f"未知接口：{path}"}, 404)
            return
        self._file(path.lstrip("/"))

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        match = _ACTION_RE.match(path)
        if not match:
            self._json({"ok": False, "error": f"未知接口：{path}"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body: Dict[str, Any] = json.loads(raw.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError) as exc:
            self._json({"ok": False, "error": f"请求体不是合法 JSON：{exc}"}, 400)
            return

        key = match.group(1)
        if key != self.spec.key:      # 服务一次只承载一个模型，避免状态混淆
            self._json({"ok": False, "error": f"当前服务运行的是模型 {self.spec.key}"}, 404)
            return

        action = str(body.get("action", ""))
        try:
            result = self.spec.run(action, body.get("params"), body.get("payload"))
        except Exception as exc:      # 把模型异常回传给前端展示
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 400)
            return
        self._json({"ok": True, "action": action, "result": result})


def _ui_list():
    """延迟读取界面后端列表，避免与 ui/__init__ 形成循环导入。"""
    from .. import list_uis

    return list_uis()


class PrismathServer(ThreadingHTTPServer):
    """带模型引用的多线程 HTTP 服务。"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, model_spec: ModelSpec) -> None:
        self.model_spec = model_spec
        super().__init__(address, handler)


def build_server(spec: ModelSpec, host: str = "127.0.0.1", port: int = 8765) -> PrismathServer:
    """创建服务实例（端口被占用时自动向后尝试）。"""
    local = "127.0.0.1" if host in ("localhost", "127.0.0.1", "") else host
    last_error: Optional[OSError] = None

    for candidate in ([port] if port == 0 else [port + i for i in range(10)] + [0]):
        try:
            return PrismathServer((local, candidate), PrismathHandler, spec)
        except OSError as exc:
            last_error = exc
    raise last_error if last_error else OSError("无法绑定端口")


def _banner(spec: ModelSpec, url: str) -> None:
    line = "─" * 62
    print(f"\n┌{line}┐")
    print(f"│ 数学模型可视化 · {spec.name:<38}│")
    print(f"│ 主题：{spec.topic:<50}│")
    print(f"├{line}┤")
    print(f"│ 本地地址：{url:<49}│")
    print(f"│ 提示：在网页左侧切换模型、调节参数；按 Ctrl+C 退出服务。{' ' * 9}│")
    print(f"└{line}┘\n")


def serve(
    spec: ModelSpec,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    desktop: bool = False,
) -> int:
    """启动网页界面服务并（可选）打开浏览器。"""
    if not (STATIC_DIR / "index.html").is_file():
        print(f"缺少前端文件：{STATIC_DIR / 'index.html'}", file=sys.stderr)
        return 1

    httpd = build_server(spec, host=host, port=port)
    bound_host, bound_port = httpd.server_address[0], httpd.server_address[1]
    url = f"http://{bound_host}:{bound_port}/"
    _banner(spec, url)

    if desktop and _start_desktop_window(spec, url, httpd):
        return 0

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止，再见。")
    finally:
        httpd.server_close()
    return 0


def _start_desktop_window(spec: ModelSpec, url: str, httpd: PrismathServer) -> bool:
    """若安装了 pywebview，则把网页装进一个独立的桌面窗口（可选增强）。"""
    try:
        import webview  # type: ignore
    except ImportError:
        print("未安装 pywebview（pip install pywebview），改用默认浏览器打开。")
        return False

    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    webview.create_window(f"{spec.name} · 数学模型可视化", url, width=1480, height=940)
    webview.start()
    httpd.shutdown()
    return True


def _free_port() -> int:
    """取一个空闲端口（备用工具函数）。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
