"""Qt WebEngine 应用"""

import os
import sys
import signal
import logging
import threading
from typing import Optional

from aiohttp import web
import asyncio

from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtGui import QIcon

from .server import create_app

logger = logging.getLogger(__name__)


def _get_dist_dir() -> str:
    """获取前端 dist 目录路径（支持 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        # 开发模式
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, 'dist')


class _ServerThread(threading.Thread):
    """在后台线程运行 aiohttp 服务器"""

    def __init__(self, static_dir: str, host: str, port: int):
        super().__init__(daemon=True)
        self.static_dir = static_dir
        self.host = host
        self.port = port
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._runner: Optional[web.AppRunner] = None
        self._ready = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start())
        self._ready.set()
        self.loop.run_forever()

    async def _start(self):
        app = create_app(self.static_dir)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"服务器已启动: http://{self.host}:{self.port}")

    def wait_ready(self, timeout: float = 10.0):
        self._ready.wait(timeout)

    def stop(self):
        if self.loop and self._runner:
            asyncio.run_coroutine_threadsafe(self._runner.cleanup(), self.loop)
            self.loop.call_soon_threadsafe(self.loop.stop)


class MonitorWindow(QMainWindow):
    def __init__(self, url: str):
        super().__init__()
        self.setWindowTitle("BehaviorTree Monitor")
        self.resize(1400, 900)

        icon_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._view = QWebEngineView()
        # 禁用磁盘缓存，确保每次加载最新资源
        profile = self._view.page().profile()
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
        self._view.setUrl(QUrl(url))
        self.setCentralWidget(self._view)


def run(host: str = "127.0.0.1", port: int = 18080):
    """启动应用：后台 aiohttp 服务 + Qt 窗口"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    dist_dir = _get_dist_dir()
    if not os.path.isdir(dist_dir):
        logger.error(f"前端 dist 目录不存在: {dist_dir}")
        logger.error("请先运行: cd frontend && pnpm install && pnpm build")
        sys.exit(1)

    # 启动后台服务器
    server = _ServerThread(dist_dir, host, port)
    server.start()
    server.wait_ready()

    # Qt 应用
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("BehaviorTree Monitor")

    # 允许 Ctrl+C 退出
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    # 定时器驱动 Python signal 处理
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)

    window = MonitorWindow(f"http://{host}:{port}")
    window.show()

    exit_code = qt_app.exec()
    server.stop()
    sys.exit(exit_code)
