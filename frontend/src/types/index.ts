/** 行为树节点类型 */
export type BtNodeType =
  | 'root'
  | 'sequence'
  | 'fallback'
  | 'parallel'
  | 'decorator'
  | 'action'
  | 'condition'
  | 'subtree'

/** 节点状态 */
export type NodeStatusStr =
  | 'IDLE'
  | 'RUNNING'
  | 'SUCCESS'
  | 'FAILURE'
  | 'SKIPPED'
  | 'IDLE_FROM_SUCCESS'
  | 'IDLE_FROM_FAILURE'
  | 'IDLE_FROM_RUNNING'
  | 'UNKNOWN'

/** 端口 */
export interface NodePort {
  name: string
  value: string
  isOutput: boolean
}

/** 解析后的树节点 */
export interface TreeNode {
  tag: string
  name: string
  uid: string
  type: BtNodeType
  attributes: Record<string, string>
  children: TreeNode[]
  isSubtreeContainer?: boolean
  x: number
  y: number
  width: number
  depth: number
  subtreeWidth: number
  subtreeHeight: number
  treeWidth?: number
  treeHeight?: number
}

/** WebSocket 消息 */
export interface WsMessage {
  type: string
  connected?: boolean
  tree_xml?: string | null
  tree_uuid?: string | null
  data?: Record<string, string> | string | null
  message?: string
}
