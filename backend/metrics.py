# backend/metrics.py —— T23：进程内指标注册表（Prometheus 文本格式，零依赖）
"""极简指标：节点执行计数/耗时、LLM 成功/失败/降级、DAG 轮次耗时直方图、WS 连接数 gauge。
线程安全性：asyncio 单线程事件循环内更新 + 读端加锁快照，不做跨进程聚合。"""
import threading
import time
from collections import defaultdict, deque
from typing import Dict, List, Tuple

ROUND_LATENCY_BUCKETS_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000)
LLM_OUTCOMES = ("success", "failure", "degraded")


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._node_exec_total: Dict[Tuple[str, str], int] = defaultdict(int)
        self._node_latency_ms_sum: Dict[str, float] = defaultdict(float)
        self._node_latency_ms_count: Dict[str, int] = defaultdict(int)
        self._llm_calls: Dict[str, int] = {o: 0 for o in LLM_OUTCOMES}
        self._round_latencies: deque = deque(maxlen=500)
        self._started_at = time.time()

    # ---- 打点 ----
    def observe_node(self, node_type: str, status: str, latency_ms: int) -> None:
        with self._lock:
            self._node_exec_total[(node_type, status)] += 1
            self._node_latency_ms_sum[node_type] += float(latency_ms)
            self._node_latency_ms_count[node_type] += 1

    def observe_llm(self, outcome: str) -> None:
        if outcome not in LLM_OUTCOMES:
            return
        with self._lock:
            self._llm_calls[outcome] += 1

    def observe_round(self, duration_ms: float) -> None:
        with self._lock:
            self._round_latencies.append(float(duration_ms))

    # ---- 渲染 ----
    def render(self, ws_connections: int = 0) -> str:
        with self._lock:
            node_total = dict(self._node_exec_total)
            lat_sum = dict(self._node_latency_ms_sum)
            lat_cnt = dict(self._node_latency_ms_count)
            llm = dict(self._llm_calls)
            rounds = list(self._round_latencies)

        lines: List[str] = []
        add = lines.append

        add("# HELP aigent_node_exec_total Total node executions by type and status")
        add("# TYPE aigent_node_exec_total counter")
        for (ntype, status), value in sorted(node_total.items()):
            add(f'aigent_node_exec_total{{node_type="{ntype}",status="{status}"}} {value}')

        add("# HELP aigent_node_latency_ms_sum Sum of node execution latency in ms")
        add("# TYPE aigent_node_latency_ms_sum counter")
        for ntype in sorted(set(lat_sum) | set(lat_cnt)):
            add(f'aigent_node_latency_ms_sum{{node_type="{ntype}"}} {lat_sum[ntype]:.3f}')
        add("# TYPE aigent_node_latency_ms_count counter")
        for ntype in sorted(lat_cnt):
            add(f'aigent_node_latency_ms_count{{node_type="{ntype}"}} {lat_cnt[ntype]}')

        add("# HELP aigent_llm_calls_total LLM call outcomes (success/failure/degraded)")
        add("# TYPE aigent_llm_calls_total counter")
        for outcome in LLM_OUTCOMES:
            add(f'aigent_llm_calls_total{{outcome="{outcome}"}} {llm[outcome]}')

        add("# HELP aigent_dag_round_duration_ms DAG round duration histogram (ms)")
        add("# TYPE aigent_dag_round_duration_ms histogram")
        counts_under = {le: 0 for le in ROUND_LATENCY_BUCKETS_MS}
        counts_under["+Inf"] = len(rounds)
        total = 0.0
        for value in rounds:
            total += value
            for le in ROUND_LATENCY_BUCKETS_MS:
                if value <= le:
                    counts_under[le] += 1
        for le in list(ROUND_LATENCY_BUCKETS_MS) + ["+Inf"]:
            add(f'aigent_dag_round_duration_ms_bucket{{le="{le}"}} {counts_under[le]}')
        add(f"aigent_dag_round_duration_ms_sum {total:.3f}")
        add(f"aigent_dag_round_duration_ms_count {len(rounds)}")

        add("# HELP aigent_ws_connections Active WebSocket connections")
        add("# TYPE aigent_ws_connections gauge")
        add(f"aigent_ws_connections {ws_connections}")

        add("# HELP aigent_uptime_seconds Process uptime in seconds")
        add("# TYPE aigent_uptime_seconds gauge")
        add(f"aigent_uptime_seconds {time.time() - self._started_at:.3f}")
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()
