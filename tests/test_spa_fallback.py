"""测试 SPA fallback 路由"""
import os
import tempfile

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope
from fastapi.testclient import TestClient


class _SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to index.html for SPA routing."""

    async def get_response(self, path: str, scope: Scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def _create_spa_app(frontend_dir: str) -> FastAPI:
    """创建带 SPA fallback 的 FastAPI 应用（使用 _SPAStaticFiles，与 main.py 一致）"""
    app = FastAPI()

    # 模拟一个 API 路由
    @app.get("/api/v1/health")
    def health():
        return {"status": "healthy"}

    # SPA fallback — 使用 _SPAStaticFiles(html=True)
    app.mount("/", _SPAStaticFiles(directory=frontend_dir, html=True), name="spa")

    return app


def test_spa_fallback_serves_index_html():
    """非 API 路径返回 index.html"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "SPA" in response.text


def test_spa_fallback_serves_static_file():
    """已有静态文件直接返回对应文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        assets_dir = os.path.join(tmpdir, "assets")
        os.makedirs(assets_dir)
        js_path = os.path.join(assets_dir, "main.js")
        with open(js_path, "w") as f:
            f.write("console.log('hello');")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        response = client.get("/assets/main.js")
        assert response.status_code == 200
        assert "hello" in response.text


def test_api_routes_take_priority():
    """API 路由优先于 SPA fallback"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


def test_path_traversal_blocked():
    """路径遍历攻击应被阻止"""
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "index.html")
        with open(index_path, "w") as f:
            f.write("<html><body>SPA</body></html>")

        app = _create_spa_app(tmpdir)
        client = TestClient(app)

        # Attempt path traversal — should NOT return /etc/passwd
        response = client.get("/..%2F..%2F..%2Fetc%2Fpasswd")
        assert response.status_code != 200 or "root:" not in response.text
