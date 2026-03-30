"""WebSocket/ZMQ 桥接服务器"""

import asyncio
import json
import os
import logging
from typing import Optional, Dict
from urllib.parse import urlparse

import zmq
import zmq.asyncio
from aiohttp import web
import aiohttp

from .protocol import (
    RequestType, NodeStatus,
    create_request_header, parse_reply_header, parse_status_buffer,
)

logger = logging.getLogger(__name__)


class Groot2WebBridge:
    """ZeroMQ 到 WebSocket 的桥接器"""

    def __init__(self):
        self.zmq_host: str = "localhost"
        self.zmq_port: int = 1667
        self.zmq_context: Optional[zmq.asyncio.Context] = None
        self.zmq_socket: Optional[zmq.asyncio.Socket] = None
        self.connected: bool = False
        self.tree_xml: Optional[str] = None
        self.tree_uuid: Optional[str] = None
        self.last_error: Optional[str] = None
        self.websockets: set = set()
        self.status_poll_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_host_port(host: str, port: int) -> tuple[str, int]:
        """Normalize host/port from user input.

        Host is treated as pure host/IP. We still tolerate accidental
        scheme/path inputs and only keep the hostname part.
        """
        raw = (host or "localhost").strip()
        if not raw:
            raw = "localhost"

        try:
            normalized_port = int(port)
        except (TypeError, ValueError):
            normalized_port = 1667
        normalized_host = raw

        try:
            parsed = urlparse(raw if "://" in raw else f"//{raw}")
            if parsed.hostname:
                normalized_host = parsed.hostname
        except ValueError:
            # Keep original values if parsing fails; connect_zmq will report error later.
            pass

        return normalized_host, normalized_port

    async def _precheck_tcp(self, host: str, port: int) -> Optional[str]:
        """Quick TCP reachability check for clearer diagnostics."""
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.0)
            writer.close()
            await writer.wait_closed()
            _ = reader
            return None
        except TimeoutError:
            return f"TCP 连接超时: {host}:{port}"
        except OSError as e:
            return f"TCP 不可达 {host}:{port} ({e.strerror or str(e)})"
        except Exception as e:
            return f"TCP 检测失败 {host}:{port} ({e})"

    async def connect_zmq(self, host: str, port: int) -> bool:
        self.zmq_host, self.zmq_port = self.normalize_host_port(host, port)
        self.last_error = None
        try:
            precheck_error = await self._precheck_tcp(self.zmq_host, self.zmq_port)
            if precheck_error:
                self.connected = False
                self.last_error = precheck_error
                logger.warning(precheck_error)
                return False

            if self.zmq_context is None:
                self.zmq_context = zmq.asyncio.Context()
            if self.zmq_socket is not None:
                self.zmq_socket.close()

            self.zmq_socket = self.zmq_context.socket(zmq.REQ)
            self.zmq_socket.setsockopt(zmq.LINGER, 0)
            self.zmq_socket.setsockopt(zmq.RCVTIMEO, 6000)
            self.zmq_socket.setsockopt(zmq.SNDTIMEO, 3000)

            address = f"tcp://{self.zmq_host}:{self.zmq_port}"
            logger.info(f"连接到 ZeroMQ: {address}")
            self.zmq_socket.connect(address)

            self.tree_xml = await self._request_tree()
            if self.tree_xml:
                self.connected = True
                logger.info("成功连接到 BT.CPP 服务器")
                return True
            self.connected = False
            self.last_error = f"连接超时或对端未响应: {address}"
            return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
            self.connected = False
            self.last_error = str(e)
            return False

    async def disconnect_zmq(self):
        self.stop_polling()
        if self.zmq_socket:
            self.zmq_socket.close()
            self.zmq_socket = None
        self.connected = False
        self.tree_xml = None
        self.tree_uuid = None
        logger.info("已断开 ZeroMQ 连接")

    async def _send_request(self, request_type: int, payload: bytes = b'') -> Optional[list]:
        async with self._lock:
            if not self.zmq_socket:
                return None
            try:
                header = create_request_header(request_type)
                if payload:
                    await self.zmq_socket.send_multipart([header, payload])
                else:
                    await self.zmq_socket.send(header)
                return await self.zmq_socket.recv_multipart()
            except zmq.error.Again:
                logger.warning("ZeroMQ 请求超时")
                await self._reconnect()
                return None
            except Exception as e:
                logger.error(f"ZeroMQ 请求失败: {e}")
                return None

    async def _reconnect(self):
        logger.info("尝试重新连接...")
        self.connected = False
        if self.zmq_socket:
            self.zmq_socket.close()
            self.zmq_socket = self.zmq_context.socket(zmq.REQ)
            self.zmq_socket.setsockopt(zmq.LINGER, 0)
            self.zmq_socket.setsockopt(zmq.RCVTIMEO, 3000)
            self.zmq_socket.setsockopt(zmq.SNDTIMEO, 1000)
            self.zmq_socket.connect(f"tcp://{self.zmq_host}:{self.zmq_port}")

    async def _request_tree(self) -> Optional[str]:
        reply = await self._send_request(RequestType.FULLTREE)
        if reply and len(reply) >= 2:
            header = parse_reply_header(reply[0])
            if header:
                self.tree_uuid = header['tree_uuid']
            return reply[1].decode('utf-8')
        return None

    async def _request_status(self) -> Optional[Dict[int, int]]:
        reply = await self._send_request(RequestType.STATUS)
        if reply and len(reply) >= 2:
            return parse_status_buffer(reply[1])
        return None

    async def _request_blackboard(self, bb_names: str = "") -> Optional[bytes]:
        reply = await self._send_request(RequestType.BLACKBOARD, bb_names.encode('utf-8'))
        if reply and len(reply) >= 2:
            return reply[1]
        return None

    async def broadcast(self, message: dict):
        if not self.websockets:
            return
        data = json.dumps(message)
        dead = set()
        for ws in self.websockets:
            try:
                await ws.send_str(data)
            except Exception:
                dead.add(ws)
        self.websockets -= dead

    async def status_polling_loop(self):
        while True:
            try:
                if self.connected and self.websockets:
                    status = await self._request_status()
                    if status:
                        await self.broadcast({
                            'type': 'status',
                            'data': {str(k): NodeStatus.to_string(v) for k, v in status.items()},
                        })
                    else:
                        self.connected = False
                        await self.broadcast({'type': 'disconnected'})
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"状态轮询错误: {e}")
                await asyncio.sleep(1)

    def start_polling(self):
        if self.status_poll_task is None or self.status_poll_task.done():
            self.status_poll_task = asyncio.create_task(self.status_polling_loop())

    def stop_polling(self):
        if self.status_poll_task:
            self.status_poll_task.cancel()
            self.status_poll_task = None

    async def cleanup(self):
        self.stop_polling()
        await self.disconnect_zmq()
        if self.zmq_context:
            self.zmq_context.term()
            self.zmq_context = None


# ---------------------------------------------------------------------------
# aiohttp application factory
# ---------------------------------------------------------------------------

_bridge: Optional[Groot2WebBridge] = None


def _get_bridge() -> Groot2WebBridge:
    assert _bridge is not None
    return _bridge


async def _ws_handler(request: web.Request) -> web.WebSocketResponse:
    bridge = _get_bridge()
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logger.info(f"WebSocket 连接: {request.remote}")
    bridge.websockets.add(ws)
    try:
        await ws.send_json({
            'type': 'connection_status',
            'connected': bridge.connected,
            'tree_xml': bridge.tree_xml if bridge.connected else None,
            'tree_uuid': bridge.tree_uuid if bridge.connected else None,
        })
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    await _handle_ws_message(ws, data)
                except json.JSONDecodeError:
                    await ws.send_json({'type': 'error', 'message': 'Invalid JSON'})
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f'WebSocket error: {ws.exception()}')
    finally:
        bridge.websockets.discard(ws)
        logger.info(f"WebSocket 关闭: {request.remote}")
    return ws


async def _handle_ws_message(ws: web.WebSocketResponse, data: dict):
    bridge = _get_bridge()
    msg_type = data.get('type')

    if msg_type == 'connect':
        host = data.get('host', 'localhost')
        port = data.get('port', 1667)
        success = await bridge.connect_zmq(host, port)
        await ws.send_json({
            'type': 'connection_status',
            'connected': success,
            'tree_xml': bridge.tree_xml if success else None,
            'tree_uuid': bridge.tree_uuid if success else None,
            'message': None if success else (bridge.last_error or f"无法连接到 {host}:{port}"),
        })
        if success:
            bridge.start_polling()

    elif msg_type == 'disconnect':
        await bridge.disconnect_zmq()
        await ws.send_json({'type': 'connection_status', 'connected': False})

    elif msg_type == 'get_tree':
        if bridge.connected:
            tree_xml = await bridge._request_tree()
            await ws.send_json({'type': 'tree', 'data': tree_xml})
        else:
            await ws.send_json({'type': 'error', 'message': '未连接到服务器'})

    elif msg_type == 'get_status':
        if bridge.connected:
            status = await bridge._request_status()
            if status:
                await ws.send_json({
                    'type': 'status',
                    'data': {str(k): NodeStatus.to_string(v) for k, v in status.items()},
                })
        else:
            await ws.send_json({'type': 'error', 'message': '未连接到服务器'})

    elif msg_type == 'get_blackboard':
        if bridge.connected:
            bb_names = data.get('names', '')
            bb_data = await bridge._request_blackboard(bb_names)
            if bb_data:
                await ws.send_json({'type': 'blackboard', 'data': bb_data.hex()})
            else:
                await ws.send_json({'type': 'blackboard', 'data': None})
        else:
            await ws.send_json({'type': 'error', 'message': '未连接到服务器'})

    else:
        await ws.send_json({'type': 'error', 'message': f'未知消息类型: {msg_type}'})


async def _index_handler(request: web.Request) -> web.Response:
    static_dir = request.app['static_dir']
    index_path = os.path.join(static_dir, 'index.html')
    if os.path.exists(index_path):
        return web.FileResponse(index_path)
    return web.Response(text="前端文件未找到", status=404)


async def _on_startup(app: web.Application):
    global _bridge
    _bridge = Groot2WebBridge()
    logger.info("Groot2 Monitor 服务器已启动")


async def _on_cleanup(app: web.Application):
    global _bridge
    if _bridge:
        await _bridge.cleanup()
        _bridge = None


def create_app(static_dir: str) -> web.Application:
    """创建 aiohttp 应用，static_dir 为前端 dist 目录路径"""
    app = web.Application()
    app['static_dir'] = static_dir
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)

    app.router.add_get('/ws', _ws_handler)

    assets_dir = os.path.join(static_dir, 'assets')
    if os.path.isdir(assets_dir):
        app.router.add_static('/assets', assets_dir, name='assets')

    app.router.add_get('/', _index_handler)

    # 其他静态文件（favicon 等）—— 防止路径遍历
    def _static_file(request: web.Request) -> web.Response:
        filename = request.match_info['filename']
        safe_name = os.path.basename(filename)
        filepath = os.path.join(static_dir, safe_name)
        if os.path.isfile(filepath):
            return web.FileResponse(filepath)
        return web.Response(status=404)

    app.router.add_get('/{filename}', _static_file)

    return app
