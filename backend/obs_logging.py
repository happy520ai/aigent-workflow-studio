# backend/obs_logging.py —— T22：结构化日志（JSON 格式 + run_id/node_id/request_id + 密钥过滤）
"""可观测性日志基建：
- JsonFormatter：每条日志一行 JSON（timestamp/level/logger/message + 动态字段）；
- SecretFilter：在记录落盘前抹除 api_key / 管理令牌 / Bearer / ?token= 等敏感串；
- request_id 走 contextvars，请求中间件生成 X-Request-ID 并注入每条相关日志。
"""
import contextvars
import json
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
run_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("run_id", default="")
node_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("node_id", default="")

# 形态抹除（与具体值无关）：sk- 类密钥、Bearer、X-Admin-Token、URL token 参数
_REDACT_PATTERNS: list[re.Pattern] = [
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(Bearer\s+)[^\s'\"]+", re.IGNORECASE),
    re.compile(r"(X-Admin-Token\s*[:=]\s*)[^\s,;'\"]+", re.IGNORECASE),
    re.compile(r"([?&]token=)[^\s&'\"]+", re.IGNORECASE),
    re.compile(r"((?:api_key|admin_token|password)\s*[:=]\s*)['\"]?[^\s'\",}]+", re.IGNORECASE),
]
_REDACTED = "***REDACTED***"


def redact_secrets(text: str) -> str:
    """按形态抹除敏感串；并对当前配置的真实令牌/key 做精确值抹除兜底"""
    out = text
    for pattern in _REDACT_PATTERNS:
        out = pattern.sub(lambda m: f"{m.group(1)}{_REDACTED}" if m.groups() else _REDACTED, out)
    # 精确值兜底：当前管理令牌与运行时 LLM key 的字面值绝不落日志
    admin_token = os.getenv("AIGENT_ADMIN_TOKEN", "").strip()
    if admin_token and admin_token in out:
        out = out.replace(admin_token, _REDACTED)
    try:
        # 延迟导入避免循环依赖（perfect_engine 不反向依赖本模块的场合也不受影响）
        # 遍历已创建实例成本高，这里只抹模块单例的 key（生产路径即它）
        import perfect_main
        from perfect_engine import PerfectNeuralEngine  # noqa: F401

        api_key = (perfect_main.engine.llm_config.get("api_key") or "").strip()
        if api_key and api_key in out:
            out = out.replace(api_key, _REDACTED)
    except Exception:
        pass
    return out


class SecretFilter(logging.Filter):
    """日志过滤器：message 与 args 格式化后的最终文本统一过 redact_secrets"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            record.msg = redact_secrets(msg)
            record.args = None
        except Exception:
            pass  # 过滤器绝不因异常中断日志链路
        return True


class JsonFormatter(logging.Formatter):
    """一行一条 JSON：ts/level/logger/message + request_id/run_id/node_id"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, var in (("request_id", request_id_var), ("run_id", run_id_var), ("node_id", node_id_var)):
            value = var.get("")
            if value:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """幂等安装：根 logger 挂 JSON handler + SecretFilter（uvicorn 之外的业务日志统一走这里）"""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    root.addFilter(SecretFilter())
    _configured = True


def get_logger(name: str = "aigent") -> logging.Logger:
    return logging.getLogger(name)
