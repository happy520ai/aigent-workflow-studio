# tests/test_cors.py —— A6(d)：CORS 白名单默认拒绝陌生 Origin
# CORS 在应用创建时读取配置，因此用独立的最小 FastAPI 复刻同一中间件配置验证
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.testclient import TestClient

DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"


def make_cors_app(origins_env: str = DEFAULT_ORIGINS) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins_env.split(",") if o.strip()],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


def test_preflight_from_allowed_origin_passes():
    client = TestClient(make_cors_app())
    r = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_preflight_from_unknown_origin_rejected():
    client = TestClient(make_cors_app())
    r = client.options(
        "/ping",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    # 不再是 allow_origins=["*"]：陌生来源拿不到放行头
    assert r.headers.get("access-control-allow-origin") is None


def test_plain_request_from_unknown_origin_no_aca_header():
    client = TestClient(make_cors_app())
    r = client.get("/ping", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") is None


def test_credentials_not_allowed():
    client = TestClient(make_cors_app())
    r = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-credentials") != "true"
