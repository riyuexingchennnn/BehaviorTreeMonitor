"""BehaviorTree.CPP Groot2 Monitor 协议定义"""

import struct
import random
from typing import Dict, Any, Optional


PROTOCOL_ID = 2


class RequestType:
    """对应 BT::Monitor::RequestType"""
    FULLTREE = ord('T')
    STATUS = ord('S')
    BLACKBOARD = ord('B')
    HOOK_INSERT = ord('I')
    HOOK_REMOVE = ord('R')
    BREAKPOINT_REACHED = ord('N')
    BREAKPOINT_UNLOCK = ord('U')
    HOOKS_DUMP = ord('D')
    REMOVE_ALL_HOOKS = ord('A')
    DISABLE_ALL_HOOKS = ord('X')
    TOGGLE_RECORDING = ord('r')
    GET_TRANSITIONS = ord('t')
    UNDEFINED = 0


class NodeStatus:
    """节点状态枚举"""
    IDLE = 0
    RUNNING = 1
    SUCCESS = 2
    FAILURE = 3
    SKIPPED = 4

    IDLE_FROM_SUCCESS = 10 + SUCCESS  # 12
    IDLE_FROM_FAILURE = 10 + FAILURE  # 13
    IDLE_FROM_RUNNING = 10 + RUNNING  # 11

    @staticmethod
    def to_string(status: int) -> str:
        mapping = {
            NodeStatus.IDLE: "IDLE",
            NodeStatus.RUNNING: "RUNNING",
            NodeStatus.SUCCESS: "SUCCESS",
            NodeStatus.FAILURE: "FAILURE",
            NodeStatus.SKIPPED: "SKIPPED",
            NodeStatus.IDLE_FROM_SUCCESS: "IDLE_FROM_SUCCESS",
            NodeStatus.IDLE_FROM_FAILURE: "IDLE_FROM_FAILURE",
            NodeStatus.IDLE_FROM_RUNNING: "IDLE_FROM_RUNNING",
        }
        return mapping.get(status, "UNKNOWN")


def create_request_header(request_type: int) -> bytes:
    """创建请求头 (6字节): protocol(1) + type(1) + unique_id(4)"""
    unique_id = random.randint(0, 0xFFFFFFFF)
    return struct.pack('<BBL', PROTOCOL_ID, request_type, unique_id)


def parse_reply_header(data: bytes) -> Optional[Dict[str, Any]]:
    """解析回复头 (22字节): protocol(1) + type(1) + unique_id(4) + tree_uuid(16)"""
    if len(data) < 22:
        return None
    protocol, req_type, unique_id = struct.unpack('<BBL', data[:6])
    tree_uuid = data[6:22]
    return {
        'protocol': protocol,
        'type': chr(req_type),
        'unique_id': unique_id,
        'tree_uuid': tree_uuid.hex(),
    }


def parse_status_buffer(data: bytes) -> Dict[int, int]:
    """解析状态缓冲区: 每个节点 uid(2字节LE) + status(1字节)"""
    statuses = {}
    offset = 0
    while offset + 3 <= len(data):
        uid = struct.unpack('<H', data[offset:offset + 2])[0]
        status = data[offset + 2]
        statuses[uid] = status
        offset += 3
    return statuses
