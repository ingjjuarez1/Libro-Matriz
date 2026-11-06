"""
Servidor principal para Libro Matriz FP.
Ejecuta la API REST y sirve la interfaz web frontend.
"""

import os
import sys
from pathlib import Path

# Asegurar que el directorio raíz del proyecto esté en el sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse, JSONResponse


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

from backend.app.routers.api import (
    api_inicio, api_curso, api_crear_curso, api_guardar_notas, api_guardar_estudiante,
    api_acta, api_guardar_acta, api_analitico, api_imprimir_analitico, api_resumen,
    api_usuarios, api_instalar_panel, api_importar_cursos, api_importar_excel,
    api_listar_solicitudes, api_crear_solicitud, api_aprobar_solicitud,
    api_observar_solicitud, api_aprobar_lote_solicitudes,
    api_validar_certificado, pagina_validar_certificado
)
from backend.app.services.google_service import google_client
from backend.app.core.config import PANEL_ID

async def home(request):
    index_path = BASE_DIR / "frontend" / "index.html"
    return FileResponse(index_path)

async def health_check(request):
    return JSONResponse({
        "status": "online",
        "google_connected": google_client.is_connected(),
        "panel_configured": bool(PANEL_ID),
        "client_email": google_client.client_email or "No configurado"
    })

routes = [
    Route("/", endpoint=home, methods=["GET"]),
    Route("/health", endpoint=health_check, methods=["GET"]),
    
    # Endpoints de la API
    Route("/api/inicio", endpoint=api_inicio, methods=["GET"]),
    Route("/api/cursos", endpoint=api_crear_curso, methods=["POST"]),
    Route("/api/curso/{id_curso}", endpoint=api_curso, methods=["GET"]),
    Route("/api/curso/{id_curso}/notas", endpoint=api_guardar_notas, methods=["POST"]),
    Route("/api/curso/{id_curso}/estudiante", endpoint=api_guardar_estudiante, methods=["POST"]),
    Route("/api/curso/{id_curso}/acta", endpoint=api_acta, methods=["GET"]),
    Route("/api/curso/{id_curso}/acta", endpoint=api_guardar_acta, methods=["POST"]),
    Route("/api/curso/{id_curso}/analitico", endpoint=api_analitico, methods=["GET"]),
    Route("/api/curso/{id_curso}/analitico/imprimir", endpoint=api_imprimir_analitico, methods=["POST"]),
    Route("/api/resumen", endpoint=api_resumen, methods=["GET"]),
    Route("/api/usuarios", endpoint=api_usuarios, methods=["GET", "POST", "DELETE"]),
    Route("/api/instalar-panel", endpoint=api_instalar_panel, methods=["POST"]),
    Route("/api/importar-cursos", endpoint=api_importar_cursos, methods=["POST"]),
    Route("/api/importar-excel", endpoint=api_importar_excel, methods=["POST"]),
    
    # Endpoints del circuito de emisión de certificados (rol 'titulos' y escuelas)
    Route("/api/solicitudes", endpoint=api_listar_solicitudes, methods=["GET"]),
    Route("/api/solicitudes", endpoint=api_crear_solicitud, methods=["POST"]),
    Route("/api/solicitudes/aprobar-lote", endpoint=api_aprobar_lote_solicitudes, methods=["POST"]),
    Route("/api/solicitudes/{id_solicitud}/aprobar", endpoint=api_aprobar_solicitud, methods=["POST"]),
    Route("/api/solicitudes/{id_solicitud}/observar", endpoint=api_observar_solicitud, methods=["POST"]),
    Route("/api/validar-certificado", endpoint=api_validar_certificado, methods=["GET"]),
    Route("/validar", endpoint=pagina_validar_certificado, methods=["GET"]),
    
    # Archivos estáticos del frontend
    Mount("/css", app=StaticFiles(directory=str(BASE_DIR / "frontend" / "css")), name="css"),
    Mount("/js", app=StaticFiles(directory=str(BASE_DIR / "frontend" / "js")), name="js"),
    Mount("/img", app=StaticFiles(directory=str(BASE_DIR / "frontend" / "img")), name="img"),
]

middleware = [
    Middleware(NoCacheMiddleware),
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(debug=True, routes=routes, middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print("\n========================================================")
    print("   Iniciando Libro Matriz FP · DETP Jujuy")
    print("   Backend REST + Frontend Web")
    print(f"   Estado de Google Drive: {'CONECTADO' if google_client.is_connected() else 'PENDIENTE DE CREDENCIALES'}")
    print(f"   URL local: http://localhost:{port}")
    print("========================================================\n")
    uvicorn.run("backend.main:app", host=host, port=port, reload=False)
