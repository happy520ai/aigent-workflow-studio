// frontend/src/components/NodeMicroWidgets.tsx
import React, { useEffect, useRef } from 'react';

// 1. 【事件捕获】节点内部：60FPS 荧光余晖示波器
// T27：waveform 存在时渲染真实指标（后端 ecg_waveform = 最近一轮 DAG 总耗时，归一化 0~1）；
// 否则回落到本地合成动画（离线仿真模式）。
export const PhosphorECGWidget: React.FC<{ isRunning: boolean; waveform?: number[] }> = ({ isRunning, waveform }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const waveRef = useRef<number[] | undefined>(waveform);
  waveRef.current = waveform;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let phase = 0;
    const width = 132;
    const height = 38;
    const points: number[] = Array(66).fill(height / 2);

    const render = () => {
      const liveWave = waveRef.current;
      if (liveWave && liveWave.length > 0) {
        // 真实数据路径：把 ≤20 个归一化采样线性拉伸到 66 个画布点（0 在中线，1 顶格）
        const src = liveWave.slice(-20);
        points.length = 0;
        for (let i = 0; i < 66; i++) {
          const t = (i / 65) * (src.length - 1);
          const lo = Math.floor(t);
          const hi = Math.ceil(t);
          const vLo = src[lo] ?? 0;
          const vHi = src[hi] ?? vLo;
          const v = Math.max(0, Math.min(1, vLo + (vHi - vLo) * (t - lo)));
          points.push(height - 4 - v * (height - 10));
        }
      } else if (isRunning) {
        phase += 0.22;
        const cycle = phase % (Math.PI * 2);
        // 本地合成模式（离线仿真回落）：QRS 形态脉冲
        let val = Math.sin(phase * 2.5) * 2.2 + (Math.random() - 0.5) * 2.5;
        if (cycle > 2.8 && cycle < 3.1) val = -13; // R 波主尖峰
        else if (cycle >= 3.1 && cycle < 3.35) val = 9; // S 波下探
        else if (cycle >= 3.8 && cycle < 4.3) val = -4.5; // T 波隆起

        points.push(height / 2 + val);
        if (points.length > 66) points.shift();
      }

      ctx.clearRect(0, 0, width, height);

      // 坐标轴线
      ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(2, 2);
      ctx.lineTo(2, height - 2);
      ctx.moveTo(2, height / 2);
      ctx.lineTo(width, height / 2);
      ctx.stroke();

      // 发光波形下方渐变填充
      ctx.save();
      ctx.beginPath();
      points.forEach((py, idx) => {
        const px = 4 + (idx / 65) * (width - 8);
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 1.6;
      ctx.shadowColor = '#10b981';
      ctx.shadowBlur = 8;
      ctx.stroke();

      // 最右侧前导高光扫描点
      const lastY = points[points.length - 1];
      ctx.beginPath();
      ctx.arc(width - 4, lastY, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = '#ffffff';
      ctx.fill();
      ctx.restore();

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [isRunning]);

  return (
    <div className="mt-2 pt-2 border-t border-emerald-500/20 flex items-center space-x-2">
      <div className="text-[9px] text-slate-400 space-y-2.5 leading-none pr-1">
        <div>输入</div>
        <div>输出</div>
      </div>
      <canvas ref={canvasRef} width={132} height={38} className="block" />
    </div>
  );
};

// 2. 【意图识别智能体】节点内部：动态声波频谱柱 + 双环旋转 AI 核心
export const AuraAICoreWidget: React.FC<{ isRunning: boolean }> = ({ isRunning }) => {
  return (
    <div className="mt-2.5 py-2 flex items-center justify-center space-x-2.5 border-t border-indigo-500/20">
      {/* 左侧 4 根动态频谱柱 */}
      <div className="flex items-center space-x-1 h-6">
        {[0.5, 0.9, 0.65, 1.0].map((scale, i) => (
          <span
            key={i}
            style={{
              animation: isRunning ? `eqBar ${0.5 + i * 0.14}s ease-in-out infinite alternate` : 'none',
              height: `${scale * 18}px`,
            }}
            className="w-[2px] rounded-full bg-gradient-to-t from-indigo-500 via-cyan-400 to-white"
          />
        ))}
      </div>

      {/* 中央双层旋转发光 AI 徽章 */}
      <div className="relative w-9 h-9 flex items-center justify-center">
        <div
          className={`absolute inset-0 rounded-full border border-dashed border-cyan-400/70 ${
            isRunning ? 'animate-spin' : ''
          }`}
          style={{ animationDuration: '6s' }}
        />
        <div
          className="w-7 h-7 rounded-full bg-indigo-950/90 border border-indigo-400 flex items-center justify-center text-[11px] font-bold text-cyan-300 shadow-[0_0_12px_rgba(56,189,248,0.65)]"
        >
          AI
        </div>
      </div>

      {/* 右侧 4 根动态频谱柱 */}
      <div className="flex items-center space-x-1 h-6">
        {[1.0, 0.65, 0.9, 0.5].map((scale, i) => (
          <span
            key={i}
            style={{
              animation: isRunning ? `eqBar ${0.55 + i * 0.12}s ease-in-out infinite alternate` : 'none',
              height: `${scale * 18}px`,
            }}
            className="w-[2px] rounded-full bg-gradient-to-t from-indigo-500 via-cyan-400 to-white"
          />
        ))}
      </div>
    </div>
  );
};

// 3. 【前端UI生成】节点内部：带激光扫描线的网页骨架图 + 流光进度条
export const WireframeScannerWidget: React.FC<{ progress: number; isRunning: boolean }> = ({
  progress,
  isRunning,
}) => {
  return (
    <div className="mt-2 space-y-2">
      <div className="grid grid-cols-2 gap-1.5 relative overflow-hidden rounded">
        {/* 左侧亮色网页骨架缩略图 */}
        <div className="h-12 rounded bg-slate-100 p-1.5 flex flex-col justify-between relative overflow-hidden">
          <div className="w-full h-2 bg-slate-800 rounded-sm" />
          <div className="grid grid-cols-2 gap-1">
            <div className="h-5 bg-slate-300 rounded-sm" />
            <div className="h-5 bg-slate-800 rounded-sm" />
          </div>
          {isRunning && (
            <div
              className="absolute inset-x-0 h-3 bg-gradient-to-b from-transparent via-cyan-400/40 to-transparent"
              style={{ animation: 'laserScan 2.2s linear infinite' }}
            />
          )}
        </div>

        {/* 右侧深色组件弹窗缩略图 */}
        <div className="h-12 rounded bg-slate-800/95 border border-slate-700 p-1.5 flex flex-col items-center justify-center relative overflow-hidden">
          <div className="w-4 h-3 bg-slate-300 rounded-sm mb-1" />
          <div className="w-11 h-1.5 bg-slate-500 rounded-sm" />
          {isRunning && (
            <div
              className="absolute inset-x-0 h-3 bg-gradient-to-b from-transparent via-purple-400/35 to-transparent"
              style={{ animation: 'laserScan 2.2s linear infinite 1.1s' }}
            />
          )}
        </div>
      </div>

      {/* 底部 98.6% 流光进度条 */}
      <div className="flex items-center space-x-2">
        <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden relative">
          <div
            style={{ width: `${progress}%` }}
            className="h-full bg-gradient-to-r from-blue-600 via-cyan-400 to-emerald-300 relative"
          />
        </div>
        <span className="text-[10px] font-mono text-cyan-300 font-semibold">{progress}%</span>
      </div>
    </div>
  );
};

// 4. 【右侧属性配置】五边形动态扫描雷达图
export const RadarSweepWidget: React.FC<{
  metrics: number[];
  isRunning: boolean;
}> = ({ metrics, isRunning }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let angleOffset = 0;
    const width = 215;
    const height = 150;
    const cx = width / 2;
    const cy = height / 2 + 4;
    const maxR = 54;

    const render = () => {
      if (isRunning) {
        angleOffset += 0.03;
      }
      ctx.clearRect(0, 0, width, height);

      // 1. 绘制 3 层五边形网格与轴线
      [0.4, 0.7, 1.0].forEach((level) => {
        ctx.beginPath();
        for (let i = 0; i < 5; i++) {
          const ang = (Math.PI * 2 * i) / 5 - Math.PI / 2;
          const x = cx + Math.cos(ang) * (maxR * level);
          const y = cy + Math.sin(ang) * (maxR * level);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.22)';
        ctx.lineWidth = 1;
        ctx.stroke();
      });

      for (let i = 0; i < 5; i++) {
        const ang = (Math.PI * 2 * i) / 5 - Math.PI / 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(ang) * maxR, cy + Math.sin(ang) * maxR);
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.2)';
        ctx.stroke();
      }

      // 2. 绘制动态呼吸的五维能力多边形
      ctx.save();
      ctx.beginPath();
      const vertices: { x: number; y: number }[] = [];
      metrics.forEach((val, i) => {
        const wobble = Math.sin(angleOffset * 1.5 + i) * 2.2;
        const r = Math.min(maxR, Math.max(12, ((val + wobble) / 100) * maxR));
        const ang = (Math.PI * 2 * i) / 5 - Math.PI / 2;
        const vx = cx + Math.cos(ang) * r;
        const vy = cy + Math.sin(ang) * r;
        vertices.push({ x: vx, y: vy });
        if (i === 0) ctx.moveTo(vx, vy);
        else ctx.lineTo(vx, vy);
      });
      ctx.closePath();

      const polyGrad = ctx.createRadialGradient(cx, cy, 4, cx, cy, maxR);
      polyGrad.addColorStop(0, 'rgba(56, 189, 248, 0.65)');
      polyGrad.addColorStop(0.6, 'rgba(59, 130, 246, 0.42)');
      polyGrad.addColorStop(1, 'rgba(168, 85, 247, 0.25)');
      ctx.fillStyle = polyGrad;
      ctx.fill();

      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.8;
      ctx.shadowColor = '#38bdf8';
      ctx.shadowBlur = 10;
      ctx.stroke();

      // 顶点高光光珠
      vertices.forEach((v) => {
        ctx.beginPath();
        ctx.arc(v.x, v.y, 2.8, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
      });
      ctx.restore();

      // 3. 标注五维文字：按指标顺序沿各顶点方向外侧排布，与顶点共用同一角度公式
      ctx.fillStyle = '#94a3b8';
      ctx.font = '10px "PingFang SC", sans-serif';
      const RADAR_LABELS = ['感知', '响应度', '准确度', '并发度', '稳定度'];
      RADAR_LABELS.forEach((label, i) => {
        const ang = (Math.PI * 2 * i) / 5 - Math.PI / 2;
        const lx = cx + Math.cos(ang) * (maxR + 14);
        const ly = cy + Math.sin(ang) * (maxR + 14) + 3;
        ctx.textAlign = Math.cos(ang) > 0.05 ? 'left' : Math.cos(ang) < -0.05 ? 'right' : 'center';
        ctx.fillText(label, lx, ly);
      });
      ctx.textAlign = 'left';

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [metrics, isRunning]);

  return (
    <div className="flex items-center justify-center py-0.5">
      <canvas ref={canvasRef} width={215} height={150} />
    </div>
  );
};
