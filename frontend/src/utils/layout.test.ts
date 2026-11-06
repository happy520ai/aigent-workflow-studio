// frontend/src/utils/layout.test.ts —— T50：Kahn 分层自动布局纯函数单测
import { describe, expect, it } from 'vitest';
import { computeLayeredLayout } from './layout';

describe('computeLayeredLayout', () => {
  it('线性链 A->B->C 分三层，x 随层号递增', () => {
    const nodes = [{ id: 'A' }, { id: 'B' }, { id: 'C' }];
    const edges = [{ source: 'A', target: 'B' }, { source: 'B', target: 'C' }];
    const pos = Object.fromEntries(computeLayeredLayout(nodes, edges).map((p) => [p.id, p]));
    expect(pos.A.x).toBeLessThan(pos.B.x);
    expect(pos.B.x).toBeLessThan(pos.C.x);
    expect(pos.A.x).toBe(80); // originX
    expect(pos.B.x).toBe(80 + 250); // + layerGap
    expect(pos.A.y).toBe(80); // 层内首个
  });

  it('同层多节点 y 按层内序号排布', () => {
    const nodes = [{ id: 'root' }, { id: 'a' }, { id: 'b' }];
    const edges = [{ source: 'root', target: 'a' }, { source: 'root', target: 'b' }];
    const pos = Object.fromEntries(computeLayeredLayout(nodes, edges).map((p) => [p.id, p]));
    expect(pos.a.x).toBe(pos.b.x); // 同层
    expect(pos.b.y).toBe(pos.a.y + 130); // itemGap
  });

  it('环上节点作为兜底层落位（不成环即拒绝之外仍可布局）', () => {
    const nodes = [{ id: 'A' }, { id: 'B' }];
    const edges = [{ source: 'A', target: 'B' }, { source: 'B', target: 'A' }];
    const pos = computeLayeredLayout(nodes, edges);
    expect(pos).toHaveLength(2);
    const ids = pos.map((p) => p.id).sort();
    expect(ids).toEqual(['A', 'B']);
  });

  it('悬空边端点被忽略，不崩溃', () => {
    const nodes = [{ id: 'A' }];
    const edges = [{ source: 'A', target: 'ghost' }, { source: 'ghost', target: 'A' }];
    const pos = computeLayeredLayout(nodes, edges);
    expect(pos).toHaveLength(1);
    expect(pos[0].id).toBe('A');
  });

  it('自定义间距与原点生效', () => {
    const nodes = [{ id: 'A' }, { id: 'B' }];
    const edges = [{ source: 'A', target: 'B' }];
    const pos = Object.fromEntries(
      computeLayeredLayout(nodes, edges, { layerGap: 500, itemGap: 40, originX: 10, originY: 20 }).map((q) => [q.id, q])
    );
    expect(pos.A).toEqual({ id: 'A', x: 10, y: 20 });
    expect(pos.B.x).toBe(510);
  });
});
