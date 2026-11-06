// frontend/src/components/BioluminescentCanvas.tsx
import React, { useEffect, useRef } from 'react';

export interface CanvasNodePos {
  id: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  themeColor: string;
}

export interface CanvasEdgeLink {
  id: string;
  source: string;
  target: string;
  latencyMs: number;
  confidencePct: number;
  connectionStatus: string;
  highlighted?: boolean;
}

interface Props {
  isRunning: boolean;
  nodes: CanvasNodePos[];
  edges: CanvasEdgeLink[];
}

interface CubicCurve {
  x0: number;
  y0: number;
  cx1: number;
  cy1: number;
  cx2: number;
  cy2: number;
  x1: number;
  y1: number;
  startWidth: number;
  endWidth: number;
  color: string;
  depth: number;
}

interface CometPulse {
  curveIndex: number;
  t: number;
  speed: number;
  tailLength: number;
  color: string;
  size: number;
}

// 计算三次贝塞尔曲线上任意 t (0~1) 的精确坐标
function getCubicPoint(c: CubicCurve, t: number): { x: number; y: number } {
  const mt = 1 - t;
  const mt2 = mt * mt;
  const mt3 = mt2 * mt;
  const t2 = t * t;
  const t3 = t2 * t;
  return {
    x: mt3 * c.x0 + 3 * mt2 * t * c.cx1 + 3 * mt * t2 * c.cx2 + t3 * c.x1,
    y: mt3 * c.y0 + 3 * mt2 * t * c.cy1 + 3 * mt * t2 * c.cy2 + t3 * c.y1,
  };
}

export const BioluminescentCanvas: React.FC<Props> = ({ isRunning, nodes, edges }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const nodesRef = useRef<CanvasNodePos[]>(nodes);
  const edgesRef = useRef<CanvasEdgeLink[]>(edges);
  const runningRef = useRef<boolean>(isRunning);

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  useEffect(() => {
    edgesRef.current = edges;
  }, [edges]);

  useEffect(() => {
    runningRef.current = isRunning;
  }, [isRunning]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let time = 0;
    let dendriteCurves: CubicCurve[] = [];
    let dendritePulses: CometPulse[] = [];
    let synapsePulses: { edgeIdx: number; strandIdx: number; t: number; speed: number; color: string }[] = [];

    // 构建有机变径分形树节数据
    const buildOrganicDendrites = (width: number, height: number) => {
      dendriteCurves = [];
      dendritePulses = [];

      const createBranchTree = (
        x: number,
        y: number,
        angle: number,
        length: number,
        thickness: number,
        depth: number,
        color: string
      ) => {
        if (depth <= 0 || length < 12) return;

        const bend1 = angle + (Math.sin(depth * 2.1 + angle) * 0.28);
        const bend2 = angle - (Math.cos(depth * 1.7 - angle) * 0.24);
        const endX = x + Math.cos(angle) * length;
        const endY = y + Math.sin(angle) * length;

        const curve: CubicCurve = {
          x0: x,
          y0: y,
          cx1: x + Math.cos(bend1) * (length * 0.38),
          cy1: y + Math.sin(bend1) * (length * 0.38),
          cx2: x + Math.cos(bend2) * (length * 0.72),
          cy2: y + Math.sin(bend2) * (length * 0.72),
          x1: endX,
          y1: endY,
          startWidth: thickness,
          endWidth: Math.max(0.35, thickness * 0.58),
          color,
          depth,
        };
        const curveIdx = dendriteCurves.length;
        dendriteCurves.push(curve);

        // 为主干与次级树突挂载彗星脉冲粒子
        if (depth >= 2) {
          dendritePulses.push({
            curveIndex: curveIdx,
            t: Math.random(),
            speed: 0.004 + Math.random() * 0.006,
            tailLength: 0.22,
            color: color === '#38bdf8' ? '#00f5d4' : '#f472b6',
            size: Math.max(1.2, thickness * 0.55),
          });
        }

        // 双分叉与三分叉有机生长
        const subCount = depth === 5 ? 3 : 2;
        for (let i = 0; i < subCount; i++) {
          const spread = (i - (subCount - 1) / 2) * (0.42 + (depth % 2) * 0.12);
          createBranchTree(
            endX,
            endY,
            angle + spread,
            length * (0.68 + (i % 2) * 0.08),
            curve.endWidth,
            depth - 1,
            color
          );
        }
      };

      // 左下角巨型神经元胞体 (坐标占比约 21%, 77%)
      const leftSomaX = width * 0.21;
      const leftSomaY = height * 0.77;
      const leftAngles = [-2.6, -2.1, -1.5, -0.85, -0.25, 0.35, 0.95, 1.65, 2.35, 2.95];
      leftAngles.forEach((ang, idx) => {
        const len = idx % 2 === 0 ? 95 : 70;
        createBranchTree(leftSomaX, leftSomaY, ang, len, 4.8, 5, '#38bdf8');
      });

      // 右上角巨型神经元胞体 (坐标占比约 76%, 19%)
      const rightSomaX = width * 0.76;
      const rightSomaY = height * 0.19;
      const rightAngles = [-2.8, -2.2, -1.55, -0.9, -0.2, 0.4, 1.05, 1.7, 2.3, 2.85];
      rightAngles.forEach((ang, idx) => {
        const len = idx % 2 === 0 ? 92 : 68;
        createBranchTree(rightSomaX, rightSomaY, ang, len, 4.6, 5, '#c084fc');
      });

      // 初始化节点间突触束上的高速彗星光流
      synapsePulses = Array.from({ length: 28 }, (_, i) => ({
        edgeIdx: i % 4,
        strandIdx: i % 5,
        t: (i * 0.17) % 1,
        speed: 0.0065 + (i % 4) * 0.0022,
        color: i % 3 === 0 ? '#00f5d4' : i % 3 === 1 ? '#38bdf8' : '#e879f9',
      }));
    };

    const handleResize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = parent.clientWidth * dpr;
      canvas.height = parent.clientHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildOrganicDendrites(parent.clientWidth, parent.clientHeight);
    };

    handleResize();
    window.addEventListener('resize', handleResize);

    // 绘制带有极坐标谐波细胞膜的生物神经元胞体 (Soma)
    const drawOrganicSoma = (
      cx: number,
      cy: number,
      primaryColor: string,
      secondaryColor: string,
      phaseSeed: number
    ) => {
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      // 1. 远距生物荧光星云光晕
      const outerRadius = 155 + Math.sin(time * 1.8 + phaseSeed) * 14;
      const nebulaGrad = ctx.createRadialGradient(cx, cy, 4, cx, cy, outerRadius);
      nebulaGrad.addColorStop(0, primaryColor);
      nebulaGrad.addColorStop(0.22, secondaryColor);
      nebulaGrad.addColorStop(0.55, 'rgba(59, 130, 246, 0.08)');
      nebulaGrad.addColorStop(1, 'rgba(7, 10, 18, 0)');
      ctx.fillStyle = nebulaGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, outerRadius, 0, Math.PI * 2);
      ctx.fill();

      // 2. 极坐标谐波有机细胞质膜 (模拟真实神经细胞星形不规则包膜)
      ctx.beginPath();
      const steps = 64;
      for (let i = 0; i <= steps; i++) {
        const theta = (i / steps) * Math.PI * 2;
        const r =
          34 +
          Math.sin(theta * 5 + time * 1.5 + phaseSeed) * 6.5 +
          Math.cos(theta * 8 - time * 2.1) * 4.2;
        const px = cx + Math.cos(theta) * r;
        const py = cy + Math.sin(theta) * r;
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      const somaBodyGrad = ctx.createRadialGradient(cx, cy, 5, cx, cy, 44);
      somaBodyGrad.addColorStop(0, 'rgba(255, 255, 255, 0.65)');
      somaBodyGrad.addColorStop(0.45, primaryColor);
      somaBodyGrad.addColorStop(1, 'rgba(15, 23, 42, 0.05)');
      ctx.fillStyle = somaBodyGrad;
      ctx.fill();

      // 3. 细胞核暗色内腔与高光核仁 (Nucleolus)
      ctx.globalCompositeOperation = 'source-over';
      ctx.beginPath();
      ctx.arc(cx, cy, 16, 0, Math.PI * 2);
      ctx.fillStyle = '#14112e';
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = primaryColor;
      ctx.stroke();

      ctx.globalCompositeOperation = 'lighter';
      const coreGlow = ctx.createRadialGradient(cx, cy, 1, cx, cy, 14);
      coreGlow.addColorStop(0, '#ffffff');
      coreGlow.addColorStop(0.5, primaryColor);
      coreGlow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = coreGlow;
      ctx.beginPath();
      ctx.arc(cx, cy, 11 + Math.sin(time * 3 + phaseSeed) * 2, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();
    };

    // 绘制彗星拖尾脉冲粒子 (沿任意三次贝塞尔曲线高速滑行)
    const drawCometOnCurve = (
      curve: CubicCurve,
      tHead: number,
      tailLen: number,
      color: string,
      baseSize: number
    ) => {
      const segments = 14;
      for (let s = 0; s < segments; s++) {
        const ratio = s / segments;
        const tSample = tHead - ratio * tailLen;
        if (tSample < 0 || tSample > 1) continue;
        const pt = getCubicPoint(curve, tSample);
        const alpha = (1 - ratio) * 0.85;
        const radius = baseSize * (1 - ratio * 0.75);

        ctx.beginPath();
        ctx.arc(pt.x, pt.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = s === 0 ? '#ffffff' : color;
        ctx.globalAlpha = alpha;
        ctx.fill();
      }
      ctx.globalAlpha = 1.0;
    };

    // 绘制端口星芒光晕 (Port Lens Flare)
    const drawPortFlare = (x: number, y: number, color: string) => {
      const flareGrad = ctx.createRadialGradient(x, y, 0.5, x, y, 16);
      flareGrad.addColorStop(0, '#ffffff');
      flareGrad.addColorStop(0.3, color);
      flareGrad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = flareGrad;
      ctx.beginPath();
      ctx.arc(x, y, 16, 0, Math.PI * 2);
      ctx.fill();
    };

    const renderFrame = () => {
      const parent = canvas.parentElement;
      const width = parent ? parent.clientWidth : canvas.width;
      const height = parent ? parent.clientHeight : canvas.height;

      if (runningRef.current) {
        time += 0.025;
      }

      ctx.clearRect(0, 0, width, height);

      // ==================== 第一层：背景分形树突网络（双通道加色发光） ====================
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      dendriteCurves.forEach((c, idx) => {
        const swayX = Math.sin(time * 1.4 + idx * 0.5) * (6 - c.depth);
        const swayY = Math.cos(time * 1.2 + idx * 0.3) * (6 - c.depth);
        const dynamicCurve: CubicCurve = {
          ...c,
          cx1: c.cx1 + swayX,
          cy1: c.cy1 + swayY,
          x1: c.x1 + swayX * 0.6,
          y1: c.y1 + swayY * 0.6,
        };

        // 外层生物辉光通道
        ctx.beginPath();
        ctx.moveTo(dynamicCurve.x0, dynamicCurve.y0);
        ctx.bezierCurveTo(
          dynamicCurve.cx1,
          dynamicCurve.cy1,
          dynamicCurve.cx2,
          dynamicCurve.cy2,
          dynamicCurve.x1,
          dynamicCurve.y1
        );
        ctx.strokeStyle = dynamicCurve.color;
        ctx.lineWidth = dynamicCurve.startWidth * 2.2;
        ctx.globalAlpha = 0.14;
        ctx.lineCap = 'round';
        ctx.stroke();

        // 内层高亮神经芯线
        ctx.beginPath();
        ctx.moveTo(dynamicCurve.x0, dynamicCurve.y0);
        ctx.bezierCurveTo(
          dynamicCurve.cx1,
          dynamicCurve.cy1,
          dynamicCurve.cx2,
          dynamicCurve.cy2,
          dynamicCurve.x1,
          dynamicCurve.y1
        );
        ctx.strokeStyle = c.depth >= 4 ? '#e0f2fe' : dynamicCurve.color;
        ctx.lineWidth = dynamicCurve.startWidth * 0.65;
        ctx.globalAlpha = Math.min(0.65, c.depth * 0.13);
        ctx.stroke();

        // 树突分叉处突触小结光斑 (Synaptic Boutons)
        if (c.depth === 3 || c.depth === 4) {
          ctx.beginPath();
          ctx.arc(dynamicCurve.x1, dynamicCurve.y1, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = '#ffffff';
          ctx.globalAlpha = 0.45 + Math.sin(time * 3 + idx) * 0.25;
          ctx.fill();
        }
      });

      // 绘制沿背景树突放射的动作电位彗星
      dendritePulses.forEach((p) => {
        if (runningRef.current) {
          p.t += p.speed;
          if (p.t > 1.2) p.t = 0;
        }
        const targetCurve = dendriteCurves[p.curveIndex];
        if (targetCurve) {
          drawCometOnCurve(targetCurve, p.t, p.tailLength, p.color, p.size);
        }
      });

      ctx.restore();

      // 绘制左下角与右上角两个核心神经元胞体
      drawOrganicSoma(width * 0.21, height * 0.77, 'rgba(56, 189, 248, 0.75)', 'rgba(99, 102, 241, 0.35)', 0.5);
      drawOrganicSoma(width * 0.76, height * 0.19, 'rgba(232, 121, 249, 0.75)', 'rgba(168, 85, 247, 0.35)', 3.1);

      // ==================== 第二层：节点间多股交织神经突触束 ====================
      const currentNodes = nodesRef.current;
      const currentEdges = edgesRef.current;

      ctx.save();
      ctx.globalCompositeOperation = 'lighter';

      currentEdges.forEach((edge, edgeIdx) => {
        const src = currentNodes.find((n) => n.id === edge.source);
        const dst = currentNodes.find((n) => n.id === edge.target);
        if (!src || !dst) return;

        const sx = src.x + (src.width || 195);
        const sy = src.y + 62;
        const tx = dst.x;
        const ty = dst.y + 55;
        const dx = tx - sx;

        // 每个连接由 5 股交织抖动的神经微丝组成
        const strandCount = 5;
        for (let s = 0; s < strandCount; s++) {
          const offset = (s - (strandCount - 1) / 2) * 9;
          const wave = Math.sin(time * 2.4 + s * 1.3 + edgeIdx) * 6;

          const strandCurve: CubicCurve = {
            x0: sx,
            y0: sy,
            cx1: sx + dx * 0.42,
            cy1: sy + offset * 1.4 + wave,
            cx2: sx + dx * 0.58,
            cy2: ty - offset * 1.4 - wave,
            x1: tx,
            y1: ty,
            startWidth: s === 2 ? 2.6 : 1.1,
            endWidth: s === 2 ? 2.6 : 1.1,
            color: s % 2 === 0 ? '#38bdf8' : '#a855f7',
            depth: 1,
          };

          // 1. 绘制微丝外发光光晕
          ctx.beginPath();
          ctx.moveTo(strandCurve.x0, strandCurve.y0);
          ctx.bezierCurveTo(
            strandCurve.cx1,
            strandCurve.cy1,
            strandCurve.cx2,
            strandCurve.cy2,
            strandCurve.x1,
            strandCurve.y1
          );
          ctx.strokeStyle = strandCurve.color;
          ctx.lineWidth = s === 2 ? 6.5 : 2.8;
          ctx.globalAlpha = s === 2 ? 0.24 : 0.12;
          ctx.stroke();

          // 2. 绘制微丝高亮芯线
          ctx.beginPath();
          ctx.moveTo(strandCurve.x0, strandCurve.y0);
          ctx.bezierCurveTo(
            strandCurve.cx1,
            strandCurve.cy1,
            strandCurve.cx2,
            strandCurve.cy2,
            strandCurve.x1,
            strandCurve.y1
          );
          ctx.strokeStyle = s === 2 ? '#e0f2fe' : strandCurve.color;
          ctx.lineWidth = strandCurve.startWidth;
          ctx.globalAlpha = s === 2 ? 0.92 : 0.55;
          ctx.stroke();

          // 3. 绘制该股微丝上的高速彗星光流脉冲
          synapsePulses
            .filter((sp) => sp.edgeIdx === edgeIdx % 4 && sp.strandIdx === s)
            .forEach((sp) => {
              if (runningRef.current) {
                sp.t += sp.speed;
                if (sp.t > 1.25) sp.t = 0;
              }
              drawCometOnCurve(strandCurve, sp.t, 0.25, sp.color, s === 2 ? 3.4 : 2.2);
            });
        }

        // 绘制起点与终点端口的耀斑星芒
        drawPortFlare(sx, sy, '#38bdf8');
        drawPortFlare(tx, ty, '#00f5d4');

        // 绘制连线上的 延迟 / 置信度 / 选中高亮状态 徽章
        ctx.save();
        ctx.globalCompositeOperation = 'source-over';
        const midX = (sx + tx) / 2;
        const midY = (sy + ty) / 2;

        ctx.font = '600 11px "JetBrains Mono", monospace';
        ctx.fillStyle = '#e2e8f0';
        ctx.fillText(`${edge.latencyMs}ms`, midX - 28, midY - 10);

        // 置信度文字对所有边显示
        ctx.fillStyle = '#94a3b8';
        ctx.fillText(`${edge.confidencePct}%`, midX - 42, midY + 18);

        // 状态徽章仅在边被高亮（与选中节点相连）时绘制，文案取 connectionStatus 字段
        if (edge.highlighted) {
          const bx = midX - 22;
          const by = midY - 30;
          ctx.fillStyle = 'rgba(6, 78, 59, 0.85)';
          ctx.strokeStyle = 'rgba(16, 185, 129, 0.7)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.roundRect(bx, by, 72, 19, 4);
          ctx.fill();
          ctx.stroke();

          ctx.font = '500 10px "PingFang SC", sans-serif';
          ctx.fillStyle = '#6ee7b7';
          ctx.fillText(`状态: ${edge.connectionStatus}`, bx + 7, by + 13);
        }
        ctx.restore();
      });

      ctx.restore();
      // T45：用户偏好减少动态时只渲染一帧静态画面，不进入 60FPS 循环
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      animId = requestAnimationFrame(renderFrame);
    };

    renderFrame();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-10"
    />
  );
};
