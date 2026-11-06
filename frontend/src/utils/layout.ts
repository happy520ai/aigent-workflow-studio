// frontend/src/utils/layout.ts —— T35：Kahn 分层自动布局（纯函数，可被 vitest 单测）
export interface LayoutNodeInput {
  id: string;
  x?: number;
  y?: number;
}

export interface LayoutEdgeInput {
  source: string;
  target: string;
}

export interface LayoutPosition {
  id: string;
  x: number;
  y: number;
}

export interface LayoutOptions {
  /** 层间距（px，横向） */
  layerGap?: number;
  /** 层内节点间距（px，纵向） */
  itemGap?: number;
  /** 画布左上起点 */
  originX?: number;
  originY?: number;
}

/**
 * Kahn 拓扑分层：层号决定 x，层内出现顺序决定 y。
 * 环上的节点作为最后一层兜底（与后端 compile_topological_layers 的环路兜底语义一致）。
 * 引用完整性：未在 nodes 中出现的 edge 端点忽略。
 */
export function computeLayeredLayout(
  nodes: LayoutNodeInput[],
  edges: LayoutEdgeInput[],
  opts: LayoutOptions = {}
): LayoutPosition[] {
  const layerGap = opts.layerGap ?? 250;
  const itemGap = opts.itemGap ?? 130;
  const originX = opts.originX ?? 80;
  const originY = opts.originY ?? 80;

  const ids = nodes.map((n) => n.id);
  const idSet = new Set(ids);
  const adjacency = new Map<string, string[]>();
  const inDegree = new Map<string, number>();
  for (const id of ids) {
    adjacency.set(id, []);
    inDegree.set(id, 0);
  }
  for (const e of edges) {
    if (!idSet.has(e.source) || !idSet.has(e.target) || e.source === e.target) continue;
    adjacency.get(e.source)!.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }

  // Kahn 分层
  let frontier = ids.filter((id) => (inDegree.get(id) ?? 0) === 0);
  const layers: string[][] = [];
  const assigned = new Set<string>();
  while (frontier.length > 0) {
    layers.push(frontier);
    for (const id of frontier) assigned.add(id);
    const next: string[] = [];
    for (const id of frontier) {
      for (const nxt of adjacency.get(id) ?? []) {
        const d = (inDegree.get(nxt) ?? 0) - 1;
        inDegree.set(nxt, d);
        if (d === 0 && !assigned.has(nxt)) next.push(nxt);
      }
    }
    frontier = next.filter((id) => !assigned.has(id));
  }
  // 环兜底：剩余节点按原顺序作为最后一层
  const rest = ids.filter((id) => !assigned.has(id));
  if (rest.length > 0) layers.push(rest);

  const positions: LayoutPosition[] = [];
  layers.forEach((layer, layerIdx) => {
    layer.forEach((id, itemIdx) => {
      positions.push({
        id,
        x: originX + layerIdx * layerGap,
        y: originY + itemIdx * itemGap,
      });
    });
  });
  return positions;
}
