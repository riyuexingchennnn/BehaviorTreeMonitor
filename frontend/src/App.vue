<template>
  <div class="app">
    <!-- 顶部工具栏 -->
    <header class="toolbar">
      <div class="toolbar-left">
        <div class="toolbar-title">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path
              d="M12 3L12 8M12 8L6 14M12 8L18 14M6 14L6 21M18 14L18 21M6 14L3 21M6 14L9 21M18 14L15 21M18 14L21 21"
              stroke="#4ecdc4" stroke-width="2" stroke-linecap="round"
            />
          </svg>
          <span>BehaviorTree Monitor</span>
        </div>
      </div>

      <div class="connection-panel">
        <input v-model="store.host" class="host" type="text" placeholder="localhost" :disabled="store.connected" />
        <span style="color: var(--text-muted)">:</span>
        <input v-model.number="store.port" class="port" type="number" placeholder="1667" :disabled="store.connected" />
        <button class="btn" :class="store.connected ? 'btn-danger' : 'btn-primary'" @click="toggleConnection">
          {{ store.connecting ? '连接中...' : store.connected ? '断开' : '连接' }}
        </button>
        <div class="status-indicator" :class="connectionStatus">
          <span class="status-dot"></span>
          <span>{{ statusText }}</span>
        </div>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main-content">
      <div ref="containerRef" class="canvas-container">
        <div class="canvas-bg"></div>

        <!-- 状态统计 -->
        <div v-if="store.connected" class="status-bar">
          <div class="stat-item">
            <span class="stat-dot idle"></span>
            <span class="stat-count">{{ store.stats.idle }}</span>
            <span class="stat-label">IDLE</span>
          </div>
          <div class="stat-item">
            <span class="stat-dot running"></span>
            <span class="stat-count">{{ store.stats.running }}</span>
            <span class="stat-label">RUNNING</span>
          </div>
          <div class="stat-item">
            <span class="stat-dot success"></span>
            <span class="stat-count">{{ store.stats.success }}</span>
            <span class="stat-label">SUCCESS</span>
          </div>
          <div class="stat-item">
            <span class="stat-dot failure"></span>
            <span class="stat-count">{{ store.stats.failure }}</span>
            <span class="stat-label">FAILURE</span>
          </div>
        </div>

        <!-- SVG 画布 -->
        <svg
          ref="canvasRef"
          class="tree-canvas"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseleave="onMouseUp"
          @wheel.prevent="onWheel"
        >
          <g :transform="`translate(${panX}, ${panY}) scale(${zoom})`">
            <!-- 连接线 -->
            <g class="connections">
              <template v-for="conn in connections" :key="conn.id">
                <path :d="conn.path" class="connection-line-glow" />
                <path :d="conn.path" class="connection-line" />
              </template>
            </g>
            <!-- 节点 -->
            <g class="nodes">
              <BehaviorNode
                v-for="node in visibleNodes"
                :key="node.uid"
                :node="node"
                @mouseenter="showTooltip"
                @mouseleave="hideTooltip"
                @toggle-subtree="onToggleSubtree"
              />
            </g>
          </g>
        </svg>

        <!-- 缩放控制 -->
        <div class="zoom-controls">
          <button class="btn" title="放大" @click="zoomIn">+</button>
          <button class="btn" title="缩小" @click="zoomOut">−</button>
          <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
          <button class="btn" title="适应" @click="zoomFit">◎</button>
          <button class="btn" title="重置" @click="zoomReset">↺</button>
          <span class="zoom-divider"></span>
          <button class="btn" :title="store.horizontal ? '切换为竖向布局' : '切换为横向布局'" @click="onToggleLayout">
            {{ store.horizontal ? '⇄' : '⇵' }}
          </button>
        </div>

        <!-- 空状态 -->
        <div v-if="!store.connected || !store.treeData" class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 3L12 8M12 8L6 14M12 8L18 14M6 14L6 21M18 14L18 21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            <circle cx="12" cy="3" r="2" fill="currentColor" />
            <circle cx="6" cy="14" r="2" fill="currentColor" />
            <circle cx="18" cy="14" r="2" fill="currentColor" />
          </svg>
          <h3>{{ store.connected ? '等待行为树数据...' : '未连接到BT服务器' }}</h3>
          <p>{{ store.connected ? '正在获取树结构' : '请输入服务器地址并点击连接' }}</p>
        </div>

        <!-- 提示框 -->
        <div v-if="tooltip.visible" class="tooltip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
          <div class="tooltip-title">{{ tooltip.node?.name }}</div>
          <div class="tooltip-type">{{ tooltip.node?.tag }}</div>
          <div v-for="(value, key) in tooltipAttrs" :key="key" class="tooltip-attr">
            <span class="tooltip-attr-name">{{ key }}:</span>
            <span class="tooltip-attr-value">{{ value }}</span>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import BehaviorNode from './components/BehaviorNode.vue'
import { useTreeStore, getNodeHeight } from './stores/treeStore'
import { useWebSocket } from './composables/useWebSocket'
import type { TreeNode, WsMessage } from './types'

const store = useTreeStore()
const connectionError = ref('')

// ---- WebSocket ----
const { connect: wsConnect, send: wsSend, close: wsClose } = useWebSocket(handleMessage)

function handleMessage(msg: WsMessage) {
  switch (msg.type) {
    case 'connection_status':
      store.connected = !!msg.connected
      store.connecting = false
      if (msg.connected) {
        connectionError.value = ''
      } else if (msg.message) {
        connectionError.value = msg.message
        console.error('连接失败:', msg.message)
      }
      if (msg.connected && msg.tree_xml) {
        store.parseTree(msg.tree_xml)
        nextTick(() => setTimeout(zoomFit, 100))
      }
      break
    case 'tree':
      if (typeof msg.data === 'string') {
        store.parseTree(msg.data)
        nextTick(() => setTimeout(zoomFit, 100))
      }
      break
    case 'status':
      if (msg.data && typeof msg.data === 'object') {
        store.updateStatus(msg.data as Record<string, string>)
      }
      break
    case 'disconnected':
      store.connected = false
      store.connecting = false
      break
    case 'error':
      console.error('服务器错误:', msg.message)
      store.connecting = false
      break
  }
}

function toggleConnection() {
  if (store.connected) {
    wsSend({ type: 'disconnect' })
    store.connected = false
  } else {
    store.connecting = true
    wsSend({ type: 'connect', host: store.host, port: store.port })
  }
}

// ---- 计算属性 ----
const connectionStatus = computed(() => {
  if (store.connecting) return 'connecting'
  if (store.connected) return 'connected'
  return 'disconnected'
})

const statusText = computed(() => {
  if (store.connecting) return '连接中...'
  if (store.connected) return '已连接'
  if (connectionError.value) return '连接失败'
  return '未连接'
})

const visibleNodes = computed<TreeNode[]>(() => {
  if (!store.treeData) return []
  const nodes: TreeNode[] = []
  const traverse = (n: TreeNode) => {
    nodes.push(n)
    n.children?.forEach(traverse)
  }
  traverse(store.treeData)
  return nodes
})

interface Connection {
  id: string
  path: string
}

const connections = computed<Connection[]>(() => {
  if (!store.treeData) return []
  const conns: Connection[] = []
  const isH = store.horizontal
  const traverse = (node: TreeNode) => {
    node.children?.forEach(child => {
      let sx: number, sy: number, ex: number, ey: number, path: string
      if (isH) {
        // 水平: 父节点右侧中点 → 子节点左侧中点
        sx = node.x + node.width
        sy = node.y + getNodeHeight(node) / 2
        ex = child.x
        ey = child.y + getNodeHeight(child) / 2
        const mx = (sx + ex) / 2
        path = `M ${sx} ${sy} C ${mx} ${sy}, ${mx} ${ey}, ${ex} ${ey}`
      } else {
        // 垂直: 父节点底部中点 → 子节点顶部中点
        sx = node.x + node.width / 2
        sy = node.y + getNodeHeight(node)
        ex = child.x + child.width / 2
        ey = child.y
        const my = (sy + ey) / 2
        path = `M ${sx} ${sy} C ${sx} ${my}, ${ex} ${my}, ${ex} ${ey}`
      }
      conns.push({ id: `${node.uid}-${child.uid}`, path })
      traverse(child)
    })
  }
  traverse(store.treeData)
  return conns
})

// ---- 画布状态 ----
const containerRef = ref<HTMLDivElement | null>(null)
const canvasRef = ref<SVGSVGElement | null>(null)
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const isDragging = ref(false)
const lastMouse = reactive({ x: 0, y: 0 })

function onMouseDown(e: MouseEvent) {
  if (e.button === 0) {
    isDragging.value = true
    lastMouse.x = e.clientX
    lastMouse.y = e.clientY
  }
}

function onMouseMove(e: MouseEvent) {
  if (isDragging.value) {
    panX.value += e.clientX - lastMouse.x
    panY.value += e.clientY - lastMouse.y
    lastMouse.x = e.clientX
    lastMouse.y = e.clientY
  }
}

function onMouseUp() {
  isDragging.value = false
}

function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.max(0.1, Math.min(3, zoom.value * delta))
  const rect = canvasRef.value!.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  panX.value = mx - (mx - panX.value) * (newZoom / zoom.value)
  panY.value = my - (my - panY.value) * (newZoom / zoom.value)
  zoom.value = newZoom
}

function zoomIn() {
  zoom.value = Math.min(3, zoom.value * 1.2)
}
function zoomOut() {
  zoom.value = Math.max(0.1, zoom.value / 1.2)
}
function zoomReset() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}
function zoomFit() {
  const tree = store.treeData
  if (!tree || !containerRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  const padding = 100
  const tw = (tree.treeWidth ?? tree.width) + padding
  const th = (tree.treeHeight ?? 100) + padding
  const sx = rect.width / tw
  const sy = rect.height / th
  const scale = Math.min(sx, sy) * 0.9
  zoom.value = Math.min(scale, 2)
  const sw = tw * zoom.value
  const sh = th * zoom.value
  panX.value = (rect.width - sw) / 2 + (padding / 2) * zoom.value
  panY.value = (rect.height - sh) / 2 + (padding / 2) * zoom.value
}

function onToggleLayout() {
  store.toggleLayout()
  nextTick(() => setTimeout(zoomFit, 50))
}

function onToggleSubtree(node: TreeNode) {
  store.toggleSubtree(node)
  nextTick(() => setTimeout(zoomFit, 100))
}

// ---- 提示框 ----
const tooltip = reactive<{ visible: boolean; x: number; y: number; node: TreeNode | null }>({
  visible: false,
  x: 0,
  y: 0,
  node: null,
})

const TOOLTIP_SKIP = new Set(['_uid', '_children_count', 'ID'])
const tooltipAttrs = computed(() => {
  if (!tooltip.node?.attributes) return {} as Record<string, string>
  const result: Record<string, string> = {}
  for (const [k, v] of Object.entries(tooltip.node.attributes)) {
    if (!TOOLTIP_SKIP.has(k) && !k.startsWith('_')) result[k] = v
  }
  return result
})

function showTooltip(event: MouseEvent, node: TreeNode) {
  tooltip.visible = true
  tooltip.x = event.clientX + 15
  tooltip.y = event.clientY + 15
  tooltip.node = node
}

function hideTooltip() {
  tooltip.visible = false
}

// ---- 生命周期 ----
onMounted(() => {
  wsConnect()
  setTimeout(() => {
    if (!store.connected && !store.connecting) {
      store.connecting = true
      wsSend({ type: 'connect', host: store.host, port: store.port })
    }
  }, 500)
})

onUnmounted(() => {
  wsClose()
})
</script>
