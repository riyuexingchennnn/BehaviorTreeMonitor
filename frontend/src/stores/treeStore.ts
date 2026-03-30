import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import type { TreeNode, NodePort, BtNodeType } from '@/types'

// ---- 常量 ----
const MIN_NODE_WIDTH = 50
const NODE_BASE_HEIGHT = 28
const PORT_HEIGHT = 18
const LEVEL_GAP = 40
const SIBLING_GAP = 8

// ---- 辅助函数 ----
const CJK_RANGE = /[\u2E80-\u9FFF\uF900-\uFAFF\uFE30-\uFE4F]/

export function measureTextWidth(text: string, charWidth: number): number {
  let w = 0
  for (const ch of text) {
    w += CJK_RANGE.test(ch) ? charWidth * 2 : charWidth
  }
  return w
}

const SKIP_ATTRS = new Set(['ID', '_uid', 'name', '_children_count', '__shared_blackboard'])

export function getNodePorts(node: TreeNode): NodePort[] {
  const ports: NodePort[] = []
  for (const [key, value] of Object.entries(node.attributes)) {
    if (!SKIP_ATTRS.has(key) && !key.startsWith('_')) {
      const isOutput = key.startsWith('OUT:') || key === 'output_key'
      ports.push({ name: key.replace('OUT:', ''), value, isOutput })
    }
  }
  return ports
}

export function getNodeHeight(node: TreeNode): number {
  return NODE_BASE_HEIGHT + getNodePorts(node).length * PORT_HEIGHT
}

function calculateNodeWidth(node: TreeNode): number {
  const ports = getNodePorts(node)
  const nameWidth = 22 + measureTextWidth(node.name, 7) + 12
  let maxLabelWidth = 0
  let maxValueWidth = 0
  for (const port of ports) {
    const labelWidth = 28 + measureTextWidth(port.name, 6)
    const valueWidth = measureTextWidth(String(port.value || ''), 6) + 8
    maxLabelWidth = Math.max(maxLabelWidth, labelWidth)
    maxValueWidth = Math.max(maxValueWidth, valueWidth)
  }
  const portWidth = ports.length > 0 ? maxLabelWidth + 8 + maxValueWidth + 16 : 0
  return Math.max(MIN_NODE_WIDTH, nameWidth, portWidth)
}

function getNodeType(tagName: string, modelTypes: Record<string, string>): BtNodeType {
  // 优先从 TreeNodesModel 获取类型
  const modelType = modelTypes[tagName]?.toLowerCase()
  if (modelType === 'condition') return 'condition'
  if (modelType === 'action') return 'action'
  if (modelType === 'subtree') return 'subtree'
  if (modelType === 'decorator') return 'decorator'

  const control = ['Sequence', 'ReactiveSequence', 'SequenceWithMemory', 'SequenceStar']
  const fallback = ['Fallback', 'ReactiveFallback', 'FallbackStar']
  const decorators = [
    'Inverter', 'ForceSuccess', 'ForceFailure', 'Repeat',
    'RepeatUntilFailure', 'Retry', 'Timeout', 'Delay',
    'KeepRunningUntilFailure', 'RunOnce',
  ]
  if (tagName === 'Root') return 'root'
  if (control.some(n => tagName.includes(n))) return 'sequence'
  if (fallback.some(n => tagName.includes(n))) return 'fallback'
  if (tagName.includes('Parallel')) return 'parallel'
  if (decorators.some(n => tagName.includes(n))) return 'decorator'
  if (tagName === 'SubTree' || tagName === 'SubTreePlus') return 'subtree'
  if (tagName.includes('Condition') || tagName.includes('Check')) return 'condition'
  return 'action'
}

let uidCounter = 0
function generateUid(): string {
  return `_gen_${++uidCounter}`
}

// ---- 布局算法 ----
function collectLevelInfo(node: TreeNode, depth: number, levelHeights: Record<number, number>, levelWidths: Record<number, number>) {
  node.width = calculateNodeWidth(node)
  node.depth = depth
  const h = getNodeHeight(node)
  if (!levelHeights[depth] || levelHeights[depth] < h) levelHeights[depth] = h
  if (!levelWidths[depth] || levelWidths[depth] < node.width) levelWidths[depth] = node.width
  node.children?.forEach(c => collectLevelInfo(c, depth + 1, levelHeights, levelWidths))
}

function calculateSubtreeWidth(node: TreeNode): number {
  if (!node.children || node.children.length === 0) {
    node.subtreeWidth = node.width
    return node.width
  }
  let total = 0
  node.children.forEach(c => (total += calculateSubtreeWidth(c)))
  total += (node.children.length - 1) * SIBLING_GAP
  node.subtreeWidth = Math.max(node.width, total)
  return node.subtreeWidth
}

function calculateSubtreeHeight(node: TreeNode): number {
  const h = getNodeHeight(node)
  if (!node.children || node.children.length === 0) {
    node.subtreeHeight = h
    return h
  }
  let total = 0
  node.children.forEach(c => (total += calculateSubtreeHeight(c)))
  total += (node.children.length - 1) * SIBLING_GAP
  node.subtreeHeight = Math.max(h, total)
  return node.subtreeHeight
}

function positionNodes(node: TreeNode, centerX: number, levelY: Record<number, number>) {
  node.x = centerX - node.width / 2
  node.y = levelY[node.depth]
  if (!node.children || node.children.length === 0) return
  let totalChildWidth = 0
  node.children.forEach(c => (totalChildWidth += c.subtreeWidth))
  totalChildWidth += (node.children.length - 1) * SIBLING_GAP
  let childCenterX = centerX - totalChildWidth / 2
  node.children.forEach(child => {
    const cc = childCenterX + child.subtreeWidth / 2
    positionNodes(child, cc, levelY)
    childCenterX += child.subtreeWidth + SIBLING_GAP
  })
}

function positionNodesHorizontal(node: TreeNode, centerY: number, levelX: Record<number, number>) {
  node.x = levelX[node.depth]
  node.y = centerY - getNodeHeight(node) / 2
  if (!node.children || node.children.length === 0) return
  let totalChildHeight = 0
  node.children.forEach(c => (totalChildHeight += c.subtreeHeight))
  totalChildHeight += (node.children.length - 1) * SIBLING_GAP
  let childCenterY = centerY - totalChildHeight / 2
  node.children.forEach(child => {
    const cc = childCenterY + child.subtreeHeight / 2
    positionNodesHorizontal(child, cc, levelX)
    childCenterY += child.subtreeHeight + SIBLING_GAP
  })
}

function layoutTree(root: TreeNode, horizontal: boolean) {
  const levelHeights: Record<number, number> = {}
  const levelWidths: Record<number, number> = {}
  collectLevelInfo(root, 0, levelHeights, levelWidths)
  const maxDepth = Math.max(...Object.keys(levelHeights).map(Number))

  if (horizontal) {
    calculateSubtreeHeight(root)
    const levelX: Record<number, number> = {}
    let currentX = 50
    for (let d = 0; d <= maxDepth; d++) {
      levelX[d] = currentX
      currentX += (levelWidths[d] || MIN_NODE_WIDTH) + LEVEL_GAP
    }
    positionNodesHorizontal(root, 50 + root.subtreeHeight / 2, levelX)
    root.treeWidth = currentX - LEVEL_GAP
    root.treeHeight = root.subtreeHeight
  } else {
    calculateSubtreeWidth(root)
    const levelY: Record<number, number> = {}
    let currentY = 50
    for (let d = 0; d <= maxDepth; d++) {
      levelY[d] = currentY
      currentY += (levelHeights[d] || NODE_BASE_HEIGHT) + LEVEL_GAP
    }
    positionNodes(root, 50 + root.subtreeWidth / 2, levelY)
    root.treeWidth = root.subtreeWidth
    root.treeHeight = currentY - LEVEL_GAP
  }
}

// ---- Store ----
export const useTreeStore = defineStore('tree', () => {
  const connected = ref(false)
  const connecting = ref(false)
  const host = ref('localhost')
  const port = ref(1667)
  const horizontal = ref(true)

  const treeData = ref<TreeNode | null>(null)
  const nodeStatuses: Record<string, string> = reactive({})

  const stats = computed(() => {
    const r = { idle: 0, running: 0, success: 0, failure: 0 }
    for (const s of Object.values(nodeStatuses)) {
      const lower = s.toLowerCase()
      if (lower.includes('running')) r.running++
      else if (lower.includes('success')) r.success++
      else if (lower.includes('failure')) r.failure++
      else r.idle++
    }
    return r
  })

  // XML 解析
  type BehaviorTreeEntry = {
    id: string
    fullpath: string
    element: Element
  }
  const behaviorTreesById: Record<string, BehaviorTreeEntry[]> = {}
  const behaviorTreeEntries: BehaviorTreeEntry[] = []
  let currentModelTypes: Record<string, string> = {}

  function parseTree(xmlString: string) {
    const doc = new DOMParser().parseFromString(xmlString, 'text/xml')

    // 从 TreeNodesModel 提取节点类型映射
    currentModelTypes = {}
    doc.querySelectorAll('TreeNodesModel > *').forEach(el => {
      const id = el.getAttribute('ID')
      if (id) currentModelTypes[id] = el.tagName
    })

    for (const k of Object.keys(behaviorTreesById)) delete behaviorTreesById[k]
    behaviorTreeEntries.length = 0
    doc.querySelectorAll('BehaviorTree').forEach(bt => {
      const id = bt.getAttribute('ID')
      if (!id) return
      const entry: BehaviorTreeEntry = {
        id,
        fullpath: bt.getAttribute('_fullpath') ?? '',
        element: bt,
      }
      behaviorTreeEntries.push(entry)
      if (!behaviorTreesById[id]) behaviorTreesById[id] = []
      behaviorTreesById[id].push(entry)
    })

    const root = doc.querySelector('root')
    const mainId =
      root?.getAttribute('main_tree_to_execute') ??
      root?.querySelector('BehaviorTree')?.getAttribute('ID')
    const mainCandidates = mainId ? (behaviorTreesById[mainId] ?? []) : []
    mainCandidates.sort((a, b) => a.fullpath.length - b.fullpath.length)
    const mainTree = mainCandidates[0]?.element ?? doc.querySelector('BehaviorTree')
    if (!mainTree) return

    function parseNode(el: Element, depth: number): TreeNode | null {
      if (el.nodeType !== 1) return null
      const tag = el.tagName
      if (['root', 'TreeNodesModel', 'include'].includes(tag)) return null

      if (tag === 'BehaviorTree') {
        for (const child of Array.from(el.children)) {
          const parsed = parseNode(child, depth)
          if (parsed) return parsed
        }
        return null
      }

      const uid = el.getAttribute('_uid') ?? generateUid()
      const attrs: Record<string, string> = {}
      for (const a of Array.from(el.attributes)) attrs[a.name] = a.value

      if (tag === 'SubTree' || tag === 'SubTreePlus') {
        const subtreeId = el.getAttribute('ID') ?? tag
        const node: TreeNode = {
          tag,
          name: subtreeId,
          uid,
          type: 'subtree',
          attributes: attrs,
          children: [],
          isSubtreeContainer: true,
          subtreeId,
          expanded: false,
          x: 0, y: 0, width: 0, depth, subtreeWidth: 0, subtreeHeight: 0,
        }
        if (!(uid in nodeStatuses)) nodeStatuses[uid] = 'IDLE'
        return node
      }

      const children: TreeNode[] = []
      for (const child of Array.from(el.children)) {
        const parsed = parseNode(child, depth + 1)
        if (parsed) children.push(parsed)
      }

      const node: TreeNode = {
        tag,
        name: el.getAttribute('name') ?? el.getAttribute('ID') ?? tag,
        uid,
        type: getNodeType(tag, currentModelTypes),
        attributes: attrs,
        children,
        x: 0, y: 0, width: 0, depth, subtreeWidth: 0, subtreeHeight: 0,
      }
      if (!(uid in nodeStatuses)) nodeStatuses[uid] = 'IDLE'
      return node
    }

    const rootUid = mainTree.getAttribute('_uid') ?? `_root_${mainId ?? 'main'}`
    const rootChildren: TreeNode[] = []
    for (const child of Array.from(mainTree.children)) {
      const parsed = parseNode(child, 1)
      if (parsed) rootChildren.push(parsed)
    }

    const parsedRoot: TreeNode = {
      tag: 'Root',
      name: mainId ?? 'Root',
      uid: rootUid,
      type: 'root',
      attributes: { ID: mainId ?? 'Root' },
      children: rootChildren,
      x: 0,
      y: 0,
      width: 0,
      depth: 0,
      subtreeWidth: 0,
      subtreeHeight: 0,
    }
    if (!(rootUid in nodeStatuses)) nodeStatuses[rootUid] = 'IDLE'

    if (rootChildren.length > 0) {
      layoutTree(parsedRoot, horizontal.value)
      treeData.value = parsedRoot
    }
  }

  function relayout() {
    if (treeData.value) {
      layoutTree(treeData.value, horizontal.value)
      // 触发响应式更新
      treeData.value = { ...treeData.value }
    }
  }

  function toggleLayout() {
    horizontal.value = !horizontal.value
    relayout()
  }

  function updateStatus(data: Record<string, string>) {
    for (const [uid, status] of Object.entries(data)) {
      nodeStatuses[uid] = status
    }
  }

  function parseSubtreeChildren(el: Element, depth: number): TreeNode[] {
    const children: TreeNode[] = []
    for (const child of Array.from(el.children)) {
      const parsed = parseSubtreeNode(child, depth)
      if (parsed) children.push(parsed)
    }
    return children
  }

  function parseSubtreeNode(el: Element, depth: number): TreeNode | null {
    if (el.nodeType !== 1) return null
    const tag = el.tagName
    if (['root', 'TreeNodesModel', 'include'].includes(tag)) return null

    if (tag === 'BehaviorTree') {
      for (const child of Array.from(el.children)) {
        const parsed = parseSubtreeNode(child, depth)
        if (parsed) return parsed
      }
      return null
    }

    const uid = el.getAttribute('_uid') ?? generateUid()
    const attrs: Record<string, string> = {}
    for (const a of Array.from(el.attributes)) attrs[a.name] = a.value

    if (tag === 'SubTree' || tag === 'SubTreePlus') {
      const subtreeId = el.getAttribute('ID') ?? tag
      const node: TreeNode = {
        tag,
        name: subtreeId,
        uid,
        type: 'subtree',
        attributes: attrs,
        children: [],
        isSubtreeContainer: true,
        subtreeId,
        expanded: false,
        x: 0, y: 0, width: 0, depth, subtreeWidth: 0, subtreeHeight: 0,
      }
      if (!(uid in nodeStatuses)) nodeStatuses[uid] = 'IDLE'
      return node
    }

    const children: TreeNode[] = []
    for (const child of Array.from(el.children)) {
      const parsed = parseSubtreeNode(child, depth + 1)
      if (parsed) children.push(parsed)
    }

    const node: TreeNode = {
      tag,
      name: el.getAttribute('name') ?? el.getAttribute('ID') ?? tag,
      uid,
      type: getNodeType(tag, currentModelTypes),
      attributes: attrs,
      children,
      x: 0, y: 0, width: 0, depth, subtreeWidth: 0, subtreeHeight: 0,
    }
    if (!(uid in nodeStatuses)) nodeStatuses[uid] = 'IDLE'
    return node
  }

  function statusScore(status?: string): number {
    if (!status) return 0
    const s = status.toLowerCase()
    if (s.includes('running')) return 5
    if (s.includes('success') || s.includes('failure')) return 3
    if (s.includes('idle')) return 1
    return 0
  }

  function behaviorTreeScore(btElement: Element): number {
    let score = 0
    for (const el of Array.from(btElement.querySelectorAll('*'))) {
      const uid = el.getAttribute('_uid')
      if (!uid) continue
      score += statusScore(nodeStatuses[uid])
    }
    return score
  }

  // Some runtimes expose subtree instances with suffixed IDs (e.g. MyTree::instance).
  // Prefer the candidate whose node statuses are most active.
  function resolveSubtreeBehaviorTree(subtreeId: string, subtreePath?: string): Element | null {
    let candidates = behaviorTreesById[subtreeId] ?? []

    // Fallback: some runtimes may suffix subtree IDs.
    if (candidates.length === 0) {
      candidates = behaviorTreeEntries.filter(e =>
        e.id === subtreeId || e.id.startsWith(`${subtreeId}::`) || e.id.startsWith(`${subtreeId}/`)
      )
    }

    if (candidates.length === 0) return null
    if (candidates.length === 1) return candidates[0].element

    if (subtreePath) {
      const exactByPath = candidates.find(e => e.fullpath === subtreePath)
      if (exactByPath) return exactByPath.element
    }

    let best = candidates[0]
    let bestScore = behaviorTreeScore(best.element)
    for (const c of candidates.slice(1)) {
      const s = behaviorTreeScore(c.element)
      if (s > bestScore) {
        best = c
        bestScore = s
      }
    }
    return best.element
  }

  function toggleSubtree(node: TreeNode) {
    if (!node.isSubtreeContainer || !node.subtreeId) return

    if (node.expanded) {
      // 收起: 保留状态数据，仅清除子节点
      node.children = []
      node.expanded = false
    } else {
      // 展开: 从 behaviorTrees 解析子节点
      const subtreePath = node.attributes['_fullpath']
      const btElement = resolveSubtreeBehaviorTree(node.subtreeId, subtreePath)
      if (!btElement) return
      node.children = parseSubtreeChildren(btElement, node.depth + 1)
      node.expanded = true
    }

    relayout()
  }

  return {
    connected, connecting, host, port, horizontal,
    treeData, nodeStatuses, stats,
    parseTree, updateStatus, toggleLayout, toggleSubtree,
    NODE_BASE_HEIGHT,
    PORT_HEIGHT,
  }
})
