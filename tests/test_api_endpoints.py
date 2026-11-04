"""
Prueba unitaria directa de los handlers de la API.
"""

import asyncio
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from starlette.requests import Request
from backend.app.routers.api import (
    api_usuarios, api_inicio
)

def make_request(path="/", method="GET", headers=None, query_string=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": query_string,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope)

async def test_handlers():
    print("1. Probando handler api_usuarios()...")
    req = make_request("/api/usuarios")
    resp = await api_usuarios(req)
    data = json.loads(resp.body.decode("utf-8"))
    print(f"   Status: {resp.status_code}")
    print(f"   Usuarios encontrados: {len(data.get('usuarios', []))}")
    assert resp.status_code == 200

    print("\n2. Probando handler api_inicio()...")
    req_inicio = make_request("/api/inicio", headers=[(b"x-user-email", b"admin@educacion.jujuy.gob.ar")])
    resp_inicio = await api_inicio(req_inicio)
    data_inicio = json.loads(resp_inicio.body.decode("utf-8"))
    print(f"   Status: {resp_inicio.status_code}")
    print(f"   Respuesta: {data_inicio}")
    assert resp_inicio.status_code in [200, 403]

    print("\nTODOS LOS CONTROLADORES DE RUTA FUNCIONAN CORRECTAMENTE.")

if __name__ == "__main__":
    asyncio.run(test_handlers())
