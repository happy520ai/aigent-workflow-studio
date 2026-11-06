'use strict';
/* 终极版交付件结构校验：perfect_engine.py / perfect_main.py / operator_registry.py / Workbench.tsx 关键锚点 */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
let pass = 0, fail = 0;
function ok(cond, msg) {
  if (cond) { pass++; console.log('  \u2713 ' + msg); }
  else { fail++; console.error('  \u2717 ' + msg); }
}

const engineSrc = fs.readFileSync(path.join(root, 'backend', 'perfect_engine.py'), 'utf8');
const mainSrc = fs.readFileSync(path.join(root, 'backend', 'perfect_main.py'), 'utf8');
const registrySrc = fs.readFileSync(path.join(root, 'backend', 'operator_registry.py'), 'utf8');
const wbSrc = fs.readFileSync(path.join(root, 'frontend', 'src', 'Workbench.tsx'), 'utf8');
const canvasSrc = fs.readFileSync(path.join(root, 'frontend', 'src', 'components', 'BioluminescentCanvas.tsx'), 'utf8');
const widgetsSrc = fs.readFileSync(path.join(root, 'frontend', 'src', 'components', 'NodeMicroWidgets.tsx'), 'utf8');
const configSrc = fs.readFileSync(path.join(root, 'frontend', 'src', 'config.ts'), 'utf8');

console.log('[PERFECT v2.8] 结构校验（终极版三件套）');

/* ---------- backend/perfect_engine.py ---------- */
ok(engineSrc.includes('class CheckpointStore'), 'CheckpointStore（SQLite 时间旅行断点）存在');
ok(engineSrc.includes('CREATE TABLE IF NOT EXISTS checkpoints'), 'checkpoints 表 DDL 存在');
ok(engineSrc.includes('asyncio.to_thread'), '断点写入走 asyncio.to_thread');
ok(engineSrc.includes('list_checkpoints'), '断点查询 list_checkpoints 存在');
ok(engineSrc.includes('class PerfectNeuralEngine'), 'PerfectNeuralEngine 存在');
ok(engineSrc.includes('def compile_topological_layers'), 'Kahn 动态拓扑分层编译器存在');
ok(engineSrc.includes('Cyclic Agent Graph'), '环路兜底（反馈层）逻辑存在');
ok(engineSrc.includes('shared_memory_bus'), '跨节点共享记忆总线存在');
ok(engineSrc.includes('def add_custom_node_from_sidebar'), '算子拖拽注入画布 API 存在');
ok(engineSrc.includes('_default_sandbox_template'), '实时沙盒 HTML/Tailwind 模板存在');
ok(engineSrc.includes('初始化智能体监控面板 v2.8'), '沙盒初始缓存注入');
ok(engineSrc.includes('node_outputs'), '节点输出表（数据沿边流动）存在');
ok(/"event": "node_update"|"node_update"[\s\S]{0,80}node\.model_dump\(\)|node\.model_dump\(\)[\s\S]{0,200}"shared_memory_bus"/.test(engineSrc), 'node_update 事件携带完整节点与沙盒代码');
ok(/node_update[\s\S]{0,400}sandbox_html/.test(engineSrc), 'node_update 事件携带 sandbox_html');
ok(/telemetry_tick[\s\S]{0,600}"edges"/.test(engineSrc) && !/telemetry_tick[\s\S]{0,600}"sandbox_html"/.test(engineSrc), 'telemetry_tick 不含 sandbox_html（A8 遥测瘦身）');

/* ---------- backend/operator_registry.py ---------- */
ok(registrySrc.includes('_ALIASES'), '节点 type 别名归一化表存在');

/* ---------- backend/perfect_main.py ---------- */
ok(mainSrc.includes('@app.post("/api/v1/workflow/nodes"'), 'POST /nodes 算子注入路由存在');
ok(mainSrc.includes('@app.patch("/api/v1/workflow/nodes/{node_id}/position"'), 'PATCH 坐标同步路由存在');
ok(mainSrc.includes('@app.put("/api/v1/workflow/nodes/{node_id}/config"'), 'PUT JSON 热修改路由存在');
ok(mainSrc.includes('@app.get("/api/v1/checkpoints"'), 'GET /checkpoints 时间旅行路由存在');
ok(mainSrc.includes('@app.get("/api/v1/sandbox/preview"'), 'GET /sandbox/preview 路由存在');
ok(mainSrc.includes('2.8.0-ultimate'), '版本号 2.8.0-ultimate');
ok(mainSrc.includes('class AddNodeRequest') && mainSrc.includes('class MoveNodeRequest'), 'AddNode/MoveNode 请求模型存在');
ok(mainSrc.includes('require_admin'), '设置接口管理守卫 require_admin 存在');
ok(mainSrc.includes('validate_llm_api_base'), 'api_base SSRF 校验存在');
ok(mainSrc.includes('Content-Security-Policy'), 'live-app 沙盒 CSP 存在');
ok(mainSrc.includes('@app.get("/api/v1/runs"'), 'GET /runs 运行记录路由存在');
ok(mainSrc.includes('@app.delete("/api/v1/workflow/nodes/{node_id}"'), 'DELETE /nodes/{id} 路由存在');
ok(/workflow_snapshot[\s\S]{0,200}sandbox_html/.test(mainSrc), 'WS 首连消息携带顶层 sandbox_html');

/* ---------- frontend/src ---------- */
ok(wbSrc.includes('API_BASE') && wbSrc.includes('WS_URL'), '前端引用统一 API 配置常量');
ok(configSrc.includes('localhost:8000'), 'src/config.ts 含默认后端地址');
ok(wbSrc.includes('node_update'), '前端处理 node_update 事件');
ok(wbSrc.includes('handleAddComponentNode'), '算子点击注入画布交互存在');
ok(wbSrc.includes('BioluminescentCanvas'), 'Workbench 引用 BioluminescentCanvas 画布引擎');
ok(canvasSrc.includes('globalCompositeOperation'), '加色混合画布（globalCompositeOperation）存在');
ok(canvasSrc.includes('drawOrganicSoma'), '有机神经元胞体绘制存在');
ok(canvasSrc.includes('drawCometOnCurve'), '突触彗星脉冲绘制存在');
ok(wbSrc.includes('radar_perception') && wbSrc.includes('RadarSweepWidget'), '五维雷达图组件接入');
ok(['感知', '响应度', '准确度', '并发度', '稳定度'].every((t) => widgetsSrc.includes(t)), '五维雷达标签齐全且不重复');
ok(wbSrc.includes('PhosphorECGWidget'), '事件捕获节点心电波形存在');
ok(wbSrc.includes('dragOffsetRef') && wbSrc.includes('onMouseDown'), '节点拖拽交互存在');
ok(wbSrc.includes('热更新') && wbSrc.includes('JSON 语法校验未通过'), 'JSON 配置热编辑与校验存在');
ok(wbSrc.includes('showSandboxModal') && wbSrc.includes('SandboxAndTimeTravelModal'), 'DOM 沙盒实时预览弹窗存在');
ok(wbSrc.includes('window.setInterval'), '本地仿真回退内核（后端未启动时驱动动画）存在');
ok(wbSrc.includes('text-amber-400') && wbSrc.includes('text-emerald-400'), 'AI 终端日志分级着色存在');
ok(wbSrc.includes('AIGENT-WORKFLOW STUDIO v2.8'), '顶部标题栏品牌标识存在');
ok(wbSrc.includes('已连接后端') && wbSrc.includes('本地仿真'), 'WS 连接指示灯存在');

console.log(`\n结构校验结果: ${pass} 通过, ${fail} 失败`);
process.exit(fail === 0 ? 0 : 1);
