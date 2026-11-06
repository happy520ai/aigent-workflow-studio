// frontend/src/components/HeaderMiniOscilloscope.tsx —— T40：顶栏 60FPS 迷你示波器（原样迁出）
import React, { useEffect, useRef } from 'react';

export const HeaderMiniOscilloscope: React.FC<{
  series: number[];
  strokeColor: string;
  fillColor: string;
  showDashedBaseline?: boolean;
}> = ({ series, strokeColor, fillColor, showDashedBaseline }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (showDashedBaseline) {
      ctx.save();
      ctx.strokeStyle = 'rgba(16, 185, 129, 0.75)';
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2]);
      ctx.beginPath();
      ctx.moveTo(0, h * 0.72);
      ctx.lineTo(w, h * 0.72);
      ctx.stroke();
      ctx.restore();
    }

    if (series.length < 2) return;

    const coords = series.map((val, idx) => {
      const x = (idx / (series.length - 1)) * w;
      const norm = Math.max(0.08, Math.min(0.92, (val - 15) / 80));
      const y = h - norm * h;
      return { x, y };
    });

    // 绘制曲线下方荧光渐变填充
    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, fillColor);
    grad.addColorStop(1, 'rgba(7, 10, 18, 0)');

    ctx.beginPath();
    ctx.moveTo(coords[0].x, h);
    coords.forEach((pt) => ctx.lineTo(pt.x, pt.y));
    ctx.lineTo(coords[coords.length - 1].x, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // 绘制高亮平滑曲线
    ctx.save();
    ctx.beginPath();
    coords.forEach((pt, idx) => {
      if (idx === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1.6;
    ctx.shadowColor = strokeColor;
    ctx.shadowBlur = 6;
    ctx.stroke();
    ctx.restore();
  }, [series, strokeColor, fillColor, showDashedBaseline]);

  return <canvas ref={canvasRef} width={82} height={24} className="block" />;
};
