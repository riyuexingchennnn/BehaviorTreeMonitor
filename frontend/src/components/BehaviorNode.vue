<template>
  <g
    class="node-group"
    :class="[statusClass, typeClass, { 'is-subtree': props.node.isSubtreeContainer }]"
    :transform="`translate(${props.node.x}, ${props.node.y})`"
    @mouseenter="$emit('mouseenter', $event, props.node)"
    @mouseleave="$emit('mouseleave')"
  >
    <!-- 节点背景 -->
    <rect class="node-box" :width="props.node.width" :height="height" rx="4" />

    <!-- 图标（靠左） -->
    <text class="node-icon" x="8" y="15">{{ nodeIcon }}</text>

    <!-- 名称（在图标右侧区域居中） -->
    <text class="node-title" :x="(22 + props.node.width) / 2" y="15" text-anchor="middle">{{ props.node.name }}</text>

    <!-- 端口列表 -->
    <g class="ports" :transform="`translate(0, ${store.NODE_BASE_HEIGHT})`">
      <g
        v-for="(port, index) in ports"
        :key="port.name"
        class="port-group"
        :transform="`translate(0, ${index * store.PORT_HEIGHT})`"
      >
        <line class="port-divider" x1="3" :x2="props.node.width - 3" y1="0" y2="0" />
        <text :class="port.isOutput ? 'port-out' : 'port-in'" x="7" y="13" font-size="8">
          {{ port.isOutput ? 'OUT' : 'IN' }}:
        </text>
        <text class="port-label" x="30" y="13">{{ port.name }}</text>
        <rect
          class="port-value-bg"
          :x="props.node.width - maxValueWidth - 8"
          y="2"
          :width="maxValueWidth + 4"
          :height="store.PORT_HEIGHT - 4"
          rx="2"
        />
        <text class="port-value" :x="props.node.width - maxValueWidth - 6" y="13" text-anchor="start">
          {{ port.value }}
        </text>
      </g>
    </g>
  </g>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TreeNode, NodePort } from '@/types'
import { useTreeStore, getNodePorts, getNodeHeight, measureTextWidth } from '@/stores/treeStore'

const props = defineProps<{ node: TreeNode }>()
defineEmits<{
  mouseenter: [event: MouseEvent, node: TreeNode]
  mouseleave: []
}>()

const store = useTreeStore()

const height = computed(() => getNodeHeight(props.node))
const ports = computed<NodePort[]>(() => getNodePorts(props.node))

const status = computed(() => store.nodeStatuses.get(props.node.uid) ?? 'IDLE')

const statusClass = computed(() => {
  const s = status.value.toLowerCase()
  if (s.includes('running')) return 'status-running'
  if (s.includes('success')) return 'status-success'
  if (s.includes('failure')) return 'status-failure'
  return 'status-idle'
})

const typeClass = computed(() => `type-${props.node.type}`)

const ICONS: Record<string, string> = {
  root: '🌳',
  sequence: '→',
  fallback: '?',
  parallel: '⇉',
  decorator: '↻',
  action: '⚡',
  condition: '≠×',
  subtree: '📦',
}

const nodeIcon = computed(() => ICONS[props.node.type] ?? '●')

const maxValueWidth = computed(() => {
  let max = 20
  for (const port of ports.value) {
    const w = measureTextWidth(String(port.value || ''), 6) + 8
    if (w > max) max = w
  }
  return max
})
</script>

<style scoped>
.port-in {
  fill: #4ecdc4;
  font-weight: 600;
}
.port-out {
  fill: #f39c12;
  font-weight: 600;
}
.port-value-bg {
  fill: #ffffff;
}
.port-divider {
  stroke: var(--border-color);
  stroke-width: 0.5;
}
.is-subtree .node-box {
  stroke-dasharray: 4 2;
}
/* 控制节点名称：粉红色 */
.type-sequence .node-title,
.type-fallback .node-title,
.type-parallel .node-title {
  fill: #ff79c6;
}
/* 装饰器节点名称：蓝绿色 */
.type-decorator .node-title {
  fill: #4ecdc4;
}
</style>
