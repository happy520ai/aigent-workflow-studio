// frontend/src/components/NeuralWebGLShader.tsx
import React, { useEffect, useRef } from 'react';

interface Props {
  isRunning: boolean;
}

const VERTEX_SHADER_SRC = `
  attribute vec2 a_position;
  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`;

// 片元着色器：实现双神经元胞体次表面辉光、分形噪声神经暗网与鼠标电势场扰动
const FRAGMENT_SHADER_SRC = `
  precision highp float;
  uniform vec2 u_resolution;
  uniform float u_time;
  uniform vec2 u_mouse;

  // 2D 伪随机与平滑噪声
  float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
  }

  // 分形布朗运动 (FBM) 生成有机神经纤维纹理
  float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    mat2 rot = mat2(cos(0.5), sin(0.5), -sin(0.5), cos(0.5));
    for (int i = 0; i < 5; i++) {
      v += a * noise(p);
      p = rot * p * 2.05 + vec2(u_time * 0.08, -u_time * 0.06);
      a *= 0.5;
    }
    return v;
  }

  void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution.xy;
    vec2 aspectUV = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;

    // 两个主神经元胞体中心 (对应画布左下角与右上角)
    vec2 somaLeft = vec2(-0.48, -0.27);
    vec2 somaRight = vec2(0.46, 0.31);

    float dLeft = length(aspectUV - somaLeft);
    float dRight = length(aspectUV - somaRight);

    // 极坐标角度与有机脉动波纹
    float angLeft = atan(aspectUV.y - somaLeft.y, aspectUV.x - somaLeft.x);
    float angRight = atan(aspectUV.y - somaRight.y, aspectUV.x - somaRight.x);

    float raysLeft = sin(angLeft * 9.0 + fbm(aspectUV * 6.0) * 6.0 - u_time * 1.5);
    float raysRight = cos(angRight * 10.0 + fbm(aspectUV * 6.5) * 6.0 + u_time * 1.4);

    // 次表面散射体辉光计算
    float glowLeft = (0.018 / (dLeft + 0.045)) * (1.0 + 0.35 * smoothstep(0.0, 1.0, raysLeft));
    float glowRight = (0.018 / (dRight + 0.045)) * (1.0 + 0.35 * smoothstep(0.0, 1.0, raysRight));

    // 底层微血管神经元暗网
    float webField = fbm(aspectUV * 4.5 + fbm(aspectUV * 9.0));
    float filament = smoothstep(0.48, 0.52, webField) * 0.12;

    // 鼠标生物电场交互波纹
    vec2 mouseNorm = (u_mouse - 0.5 * u_resolution.xy) / u_resolution.y;
    float dMouse = length(aspectUV - mouseNorm);
    float mousePulse = 0.004 / (dMouse + 0.06);

    vec3 colLeft = vec3(0.06, 0.65, 0.95) * glowLeft;
    vec3 colRight = vec3(0.75, 0.25, 0.96) * glowRight;
    vec3 colWeb = vec3(0.22, 0.45, 0.85) * filament;
    vec3 colMouse = vec3(0.0, 0.96, 0.83) * mousePulse;

    vec3 finalColor = colLeft + colRight + colWeb + colMouse;
    gl_FragColor = vec4(finalColor, clamp(length(finalColor) * 0.45, 0.0, 0.65));
  }
`;

export const NeuralWebGLShader: React.FC<Props> = ({ isRunning }) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const mouseRef = useRef<{ x: number; y: number }>({ x: -1000, y: -1000 });
  const runningRef = useRef<boolean>(isRunning);

  useEffect(() => {
    runningRef.current = isRunning;
  }, [isRunning]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl', { alpha: true, premultipliedAlpha: false });
    if (!gl) return;

    const compileShader = (type: number, source: string) => {
      const shader = gl.createShader(type)!;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      return shader;
    };

    const vs = compileShader(gl.VERTEX_SHADER, VERTEX_SHADER_SRC);
    const fs = compileShader(gl.FRAGMENT_SHADER, FRAGMENT_SHADER_SRC);
    const program = gl.createProgram()!;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW
    );

    const posLoc = gl.getAttribLocation(program, 'a_position');
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const resLoc = gl.getUniformLocation(program, 'u_resolution');
    const timeLoc = gl.getUniformLocation(program, 'u_time');
    const mouseLoc = gl.getUniformLocation(program, 'u_mouse');

    const handleResize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    handleResize();
    window.addEventListener('resize', handleResize);

    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseRef.current = {
        x: e.clientX - rect.left,
        y: canvas.height - (e.clientY - rect.top),
      };
    };
    window.addEventListener('mousemove', handleMouseMove);

    let animId: number;
    let t = 0;
    const render = () => {
      if (runningRef.current) t += 0.016;
      gl.uniform2f(resLoc, canvas.width, canvas.height);
      gl.uniform1f(timeLoc, t);
      gl.uniform2f(mouseLoc, mouseRef.current.x, mouseRef.current.y);
      gl.drawArrays(gl.TRIANGLES, 0, 6);
      animId = requestAnimationFrame(render);
    };
    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-0 opacity-85"
    />
  );
};
