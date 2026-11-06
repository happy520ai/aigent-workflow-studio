// frontend/src/components/NeuralBioCanvas.tsx
import React, { useEffect, useRef } from 'react';

interface Props {
  isRunning: boolean;
}

interface DendriteParticle {
  somaIndex: number;
  angle: number;
  distance: number;
  maxDistance: number;
  speed: number;
  size: number;
  color: string;
}

export const NeuralBioCanvas: React.FC<Props> = ({ isRunning }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let tick = 0;

    const resizeCanvas = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = parent.clientHeight;
      }
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // 初始化沿树突向外发射的神经冲动粒子
    const particles: DendriteParticle[] = Array.from({ length: 42 }, (_, idx) => ({
      somaIndex: idx % 2,
      angle: (Math.PI * 2 * (idx % 12)) / 12 + (Math.random() - 0.5) * 0.35,
      distance: Math.random() * 160,
      maxDistance: 150 + Math.random() * 140,
      speed: 0.45 + Math.random() * 0.85,
      size: 1.2 + Math.random() * 1.8,
      color: idx % 2 === 0 ? '#38bdf8' : '#e879f9',
    }));

    // 递归绘制分形生物树突纤维
    const drawFractalBranch = (
      x: number,
      y: number,
      length: number,
      angle: number,
      depth: number,
      strokeColor: string,
      breathOffset: number
    ) => {
      if (depth === 0 || length < 6) return;

      const sway = Math.sin(tick * 0.02 + depth + breathOffset) * 0.04;
      const endX = x + Math.cos(angle + sway) * length;
      const endY = y + Math.sin(angle + sway) * length;

      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.quadraticCurveTo(
        (x + endX) / 2 + Math.sin(angle) * 6,
        (y + endY) / 2 - Math.cos(angle) * 6,
        endX,
        endY
      );
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = Math.max(0.4, depth * 0.55);
      ctx.globalAlpha = Math.min(0.65, depth * 0.11);
      ctx.stroke();

      // 分叉为两条子树突
      drawFractalBranch(
        endX,
        endY,
        length * 0.72,
        angle - 0.32 - sway * 0.5,
        depth - 1,
        strokeColor,
        breathOffset
      );
      drawFractalBranch(
        endX,
        endY,
        length * 0.68,
        angle + 0.36 + sway * 0.5,
        depth - 1,
        strokeColor,
        breathOffset + 1.2
      );
    };

    // 绘制神经元胞体 (Soma) 与细胞核高光
    const drawNeuronSoma = (
      cx: number,
      cy: number,
      coreColor: string,
      glowColor: string,
      branchCount: number,
      seed: number
    ) => {
      const pulseRadius = 115 + Math.sin(tick * 0.03 + seed) * 12;

      // 1. 外部生物电场光晕
      const auraGrad = ctx.createRadialGradient(cx, cy, 8, cx, cy, pulseRadius);
      auraGrad.addColorStop(0, glowColor);
      auraGrad.addColorStop(0.35, 'rgba(99, 102, 241, 0.18)');
      auraGrad.addColorStop(1, 'rgba(7, 10, 18, 0)');
      ctx.globalAlpha = 0.75;
      ctx.fillStyle = auraGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, pulseRadius, 0, Math.PI * 2);
      ctx.fill();

      // 2. 放射状分形树突纤维
      for (let i = 0; i < branchCount; i++) {
        const baseAngle = (Math.PI * 2 * i) / branchCount + seed * 0.4;
        drawFractalBranch(cx, cy, 56, baseAngle, 5, coreColor, i + seed);
      }

      // 3. 神经元细胞核双层环
      ctx.globalAlpha = 0.95;
      ctx.beginPath();
      ctx.arc(cx, cy, 17, 0, Math.PI * 2);
      ctx.fillStyle = '#111827';
      ctx.fill();
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = coreColor;
      ctx.stroke();

      ctx.beginPath();
      ctx.arc(cx, cy, 7.5 + Math.sin(tick * 0.05) * 1.2, 0, Math.PI * 2);
      ctx.fillStyle = '#ffffff';
      ctx.fill();
    };

    const renderLoop = () => {
      if (isRunning) {
        tick += 1;
      }
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const leftSoma = { x: canvas.width * 0.21, y: canvas.height * 0.77 };
      const rightSoma = { x: canvas.width * 0.76, y: canvas.height * 0.19 };

      // 绘制左下角青蓝色神经元胞体与右上角紫粉色神经元胞体
      drawNeuronSoma(leftSoma.x, leftSoma.y, '#38bdf8', 'rgba(56, 189, 248, 0.42)', 9, 1.0);
      drawNeuronSoma(rightSoma.x, rightSoma.y, '#e879f9', 'rgba(232, 121, 249, 0.42)', 10, 3.5);

      // 绘制沿树突游走的动作电位发光微粒
      particles.forEach((p) => {
        if (isRunning) {
          p.distance += p.speed;
          if (p.distance > p.maxDistance) {
            p.distance = 14;
          }
        }
        const origin = p.somaIndex === 0 ? leftSoma : rightSoma;
        const curveOffset = Math.sin(p.distance * 0.04 + p.angle) * 12;
        const px = origin.x + Math.cos(p.angle) * p.distance + curveOffset;
        const py = origin.y + Math.sin(p.angle) * p.distance - curveOffset;

        const alpha = 1 - p.distance / p.maxDistance;
        ctx.globalAlpha = Math.max(0.1, alpha * 0.85);
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();
      });

      ctx.globalAlpha = 1.0;
      animationFrameId = requestAnimationFrame(renderLoop);
    };

    renderLoop();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [isRunning]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-0"
    />
  );
};
