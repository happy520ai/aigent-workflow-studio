# tests/test_telemetry_real.py —— T27：ECG 波形改为真实 DAG 轮延迟指标（契约同步）
import asyncio

from perfect_engine import ConnectionManager, PerfectNeuralEngine


def run(coro):
    return asyncio.run(coro)


def test_ecg_source_is_real_round_latency():
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())
    run(eng._run_dag_round())
    assert eng.last_round_latency_ms > 0
    expected = min(1.0, eng.last_round_latency_ms / 2000.0)
    assert abs(eng._telemetry_sample() - expected) < 1e-9


def test_ecg_waveform_values_within_real_range():
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())

    async def scenario():
        for _ in range(3):
            await eng._run_dag_round()
            # 模拟若干次遥测采样（值 = 归一化轮延迟，无轮时重复上一值）
            for _ in range(25):
                eng.ecg_waveform = (eng.ecg_waveform + [eng._telemetry_sample()])[-20:]

    run(scenario())
    assert len(eng.ecg_waveform) == 20
    assert all(0.0 <= v <= 1.0 for v in eng.ecg_waveform)
    # 波形末值与最新轮延迟一致
    assert abs(eng.ecg_waveform[-1] - min(1.0, eng.last_round_latency_ms / 2000.0)) < 1e-9


def test_ecg_contract_still_in_snapshot_and_tick():
    # 契约：ecg_waveform 键仍在 snapshot telemetry 中（telemetry_tick 同字段）
    eng = PerfectNeuralEngine(ws_manager=ConnectionManager())
    snap = eng.get_snapshot()
    assert isinstance(snap.telemetry.ecg_waveform, list)
