# scripts/ws_smoke.py —— T61：经 nginx 反代握手 WS（带令牌与 Origin），打印首帧事件名后退出
# 用法：backend/.venv/Scripts/python scripts/ws_smoke.py ws://127.0.0.1:3000/ws/telemetry?token=XXX http://127.0.0.1:3000
import asyncio
import sys

import websockets


async def main() -> int:
    url = sys.argv[1]
    origin = sys.argv[2]
    try:
        async with websockets.connect(url, origin=origin, open_timeout=10) as ws:
            first = await asyncio.wait_for(ws.recv(), timeout=10)
            print("WS_UPGRADE_OK first_event=", first[:60])
            return 0
    except Exception as exc:
        print("WS_FAIL", type(exc).__name__, str(exc)[:160])
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
