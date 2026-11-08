import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Connection,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import dagre from '@dagrejs/dagre'
import { useBoardGraph, useBoardMutations } from '../api/boards'
import type { CardSummary, GraphEdge, Label } from '../lib/types'
import CardFace from './CardFace'

const EDGE = { child: '#949db7', waiting: '#c27803', done: '#15803d' } as const

/** Cizgi aciklamasi: renk tek basina anlam tasimasin diye yaninda yazi. */
function EdgeKey({ color, dashed, children }: { color: string; dashed?: boolean; children: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="26" height="8" aria-hidden>
        <line x1="1" y1="4" x2="25" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dashed ? '5 3' : undefined} />
      </svg>
      {children}
    </span>
  )
}

const NODE_W = 240
const NODE_H = 90

type CardNodeData = { card: CardSummary; labels: Map<number, Label>; external: boolean }
type CardNode = Node<CardNodeData, 'card'>

function CardNodeView({ data }: NodeProps<CardNode>) {
  return (
    <div style={{ width: NODE_W }} className={data.external ? 'opacity-60' : ''}>
      {/* Sol: bu kartin on kosullari buraya baglanir. Sag: bu karti bekleyenler. */}
      <Handle type="target" position={Position.Left} className="!h-3 !w-3 !border-2 !border-white !bg-slate-400" />
      <CardFace card={data.card} labels={data.labels} />
      {data.external && <p className="mt-0.5 text-[12px] text-slate-500">Başka board'dan</p>}
      <Handle type="source" position={Position.Right} className="!h-3 !w-3 !border-2 !border-white !bg-slate-900" />
    </div>
  )
}

const nodeTypes = { card: CardNodeView }

/** Konumu olmayan (ya da hepsi istenirse) dugumleri soldan saga dagre ile yerlestirir. */
function autoLayout(cards: CardSummary[], edges: GraphEdge[], all: boolean) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 30, ranksep: 70 })
  g.setDefaultEdgeLabel(() => ({}))
  cards.forEach((c) => g.setNode(String(c.id), { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(String(e.source), String(e.target)))
  dagre.layout(g)
  const pos = new Map<number, { x: number; y: number }>()
  cards.forEach((c) => {
    if (!all && c.graph_x != null && c.graph_y != null) {
      pos.set(c.id, { x: c.graph_x, y: c.graph_y })
    } else {
      const n = g.node(String(c.id))
      pos.set(c.id, { x: n.x - NODE_W / 2, y: n.y - NODE_H / 2 })
    }
  })
  return pos
}

interface Props {
  boardId: number
  labels: Map<number, Label>
  onOpenCard: (id: number) => void
}

export default function GraphView({ boardId, labels, onOpenCard }: Props) {
  const graph = useBoardGraph(boardId)
  const m = useBoardMutations(boardId)
  const [nodes, setNodes] = useState<CardNode[]>([])
  const [hideDone, setHideDone] = useState(false)

  const visible = useMemo(
    () => graph.data?.nodes.filter((c) => !(hideDone && c.status === 'completed')) ?? [],
    [graph.data, hideDone],
  )

  const buildNodes = useCallback(
    (all: boolean) => {
      if (!graph.data) return []
      const pos = autoLayout(visible, graph.data.edges, all)
      return visible.map<CardNode>((c) => ({
        id: String(c.id),
        type: 'card',
        position: pos.get(c.id)!,
        deletable: false, // Delete tusu sadece ipleri silsin, karti degil
        data: { card: c, labels, external: c.board_id !== boardId },
      }))
    },
    [graph.data, visible, labels, boardId],
  )

  useEffect(() => setNodes(buildNodes(false)), [buildNodes])

  const visibleIds = new Set(visible.map((c) => String(c.id)))
  const statusOf = new Map(graph.data?.nodes.map((c) => [String(c.id), c.status]))
  const edges: Edge[] = (graph.data?.edges ?? [])
    .filter((e) => visibleIds.has(String(e.source)) && visibleIds.has(String(e.target)))
    .map((e) => {
      const dep = e.type === 'dependency'
      const open = dep && statusOf.get(String(e.source)) !== 'completed'
      // Durum renkleri: bekleyen on kosul amber, biten yesil, alt kart iliskisi soluk murekkep
      const color = !dep ? EDGE.child : open ? EDGE.waiting : EDGE.done
      return {
        id: `${e.type}-${e.source}-${e.target}`,
        source: String(e.source),
        target: String(e.target),
        animated: open,
        deletable: dep, // alt kart iliskisi kart detayindan degistirilir
        style: { stroke: color, strokeWidth: dep ? 2 : 1.5, strokeDasharray: dep ? undefined : '6 4' },
        markerEnd: dep ? { type: MarkerType.ArrowClosed, color } : undefined,
      }
    })

  const onNodesChange = useCallback(
    (changes: NodeChange<CardNode>[]) => setNodes((ns) => applyNodeChanges(changes, ns)),
    [],
  )

  // source = on kosul, target = onu bekleyen kart
  const onConnect = (c: Connection) => {
    if (c.source && c.target && c.source !== c.target)
      m.addDependency.mutate({ id: Number(c.target), dependsOn: Number(c.source) })
  }

  const onEdgesDelete = (deleted: Edge[]) =>
    deleted
      .filter((e) => e.id.startsWith('dependency-'))
      .forEach((e) => m.removeDependency.mutate({ id: Number(e.target), dependsOn: Number(e.source) }))

  function relayout() {
    const next = buildNodes(true)
    setNodes(next)
    next
      .filter((n) => n.data.card.board_id === boardId)
      .forEach((n) => m.savePosition.mutate({ id: Number(n.id), x: n.position.x, y: n.position.y }))
  }

  if (graph.isLoading) return <p className="p-6 text-slate-500">Yükleniyor…</p>
  if (graph.error) return <p className="p-6 text-red-600">{graph.error.message}</p>

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-slate-200 bg-white px-4 py-2.5 text-[13px] text-slate-600">
        <span>
          <b className="text-slate-900">Sağ</b> noktadan diğer kartın <b className="text-slate-900">sol</b> noktasına çek:
          “bu bitmeden o başlamaz”. İpi seçip Delete ile kaldır.
        </span>
        <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <EdgeKey color={EDGE.waiting}>Ön koşul, bekliyor</EdgeKey>
          <EdgeKey color={EDGE.done}>Ön koşul, bitti</EdgeKey>
          <EdgeKey color={EDGE.child} dashed>Alt kart</EdgeKey>
        </span>
        <span className="ml-auto flex items-center gap-4">
          <label className="flex items-center gap-1.5">
            <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
            Bitenleri gizle
          </label>
          <button onClick={relayout} className="rounded-md border border-slate-300 px-3 py-1 text-slate-800 hover:border-slate-900">
            Otomatik yerleştir
          </button>
        </span>
      </div>
      {(m.addDependency.error || m.removeDependency.error) && (
        <p className="absolute bottom-3 left-3 z-10 rounded bg-red-50 px-3 py-1.5 text-sm text-red-700">
          {(m.addDependency.error ?? m.removeDependency.error)?.message}
        </p>
      )}
      {visible.length === 0 ? (
        <p className="p-6 text-slate-500">Bu board'da gösterilecek kart yok.</p>
      ) : (
        <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onConnect={onConnect}
          onEdgesDelete={onEdgesDelete}
          onNodeClick={(_, n) => onOpenCard(Number(n.id))}
          onNodeDragStop={(_, n) => {
            if (n.data.card.board_id === boardId)
              m.savePosition.mutate({ id: Number(n.id), x: n.position.x, y: n.position.y })
          }}
          deleteKeyCode={['Delete', 'Backspace']}
          nodesConnectable
          fitView
          minZoom={0.2}
        >
          <Background gap={18} size={1.2} />
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
        </div>
      )}
    </div>
  )
}
