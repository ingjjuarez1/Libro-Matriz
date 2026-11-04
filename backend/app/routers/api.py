"""
Rutas API REST para Libro Matriz FP.
Reemplaza todas las llamadas de google.script.run.
"""

import json
from typing import Dict, Any, Optional
from starlette.requests import Request
from starlette.responses import JSONResponse
from backend.app.core.auth import (
    sesion, alcanza_cue, AuthException, PermissionDeniedException, obtener_usuarios_panel
)
from backend.app.services.datos_service import (
    cursos_del_panel, buscar_curso, leer_curso, guardar_notas,
    guardar_estudiante, leer_acta, guardar_acta, obtener_analitico,
    obtener_resumen
)
from backend.app.services.instalador_service import instalar_panel, importar_cursos_de_carpeta
from backend.app.core.config import PANEL_ID

from backend.app.services.titulos_service import (
    listar_solicitudes, crear_o_reingresar_solicitud, aprobar_solicitud,
    observar_solicitud, aprobar_en_lote
)

def get_current_user_email(request: Request) -> str:
    """
    Obtiene el email del usuario desde:
    1. Header 'X-User-Email'
    2. Header 'Authorization: Bearer <email_o_token>'
    3. Query parameter '?email=...'
    4. Por defecto para pruebas: primer usuario activo del Panel
    """
    email = request.headers.get("x-user-email")
    if not email:
        email = request.query_params.get("email")
    if not email:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            email = auth_header.split(" ", 1)[1]
    
    if not email:
        usuarios = obtener_usuarios_panel()
        if usuarios:
            email = usuarios[0].get("Email", "")
    
    return str(email or "").strip().lower()

async def api_inicio(request: Request) -> JSONResponse:
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        todos_cursos = cursos_del_panel()
        cursos_visibles = [c for c in todos_cursos if alcanza_cue(s, c.get("cue"))]
        
        return JSONResponse({
            "ok": True,
            "sesion": {
                "nombre": s["nombre"],
                "email": s["email"],
                "rol": s["rol"],
                "puedeCargar": s["puedeCargar"],
                "verTodo": s["verTodo"],
                "esTitulos": bool(s.get("esTitulos"))
            },
            "cursos": cursos_visibles
        })
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_curso(request: Request) -> JSONResponse:
    try:
        id_curso = request.path_params.get("id_curso", "")
        email = get_current_user_email(request)
        s = sesion(email)
        curso = buscar_curso(id_curso)
        if not curso:
            return JSONResponse({"ok": False, "error": "Curso no encontrado."}, status_code=404)
        
        if not alcanza_cue(s, curso.get("cue")):
            return JSONResponse({"ok": False, "error": "Acceso denegado a esta institución."}, status_code=403)
        
        datos = leer_curso(curso["id"])
        datos["curso"] = curso
        datos["puedeCargar"] = bool(s["puedeCargar"] and str(curso.get("estado")).lower() != "cerrado")
        
        return JSONResponse({"ok": True, "datos": datos})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_guardar_notas(request: Request) -> JSONResponse:
    try:
        id_curso = request.path_params.get("id_curso", "")
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        cambios = body.get("cambios", [])
        
        res = guardar_notas(id_curso, cambios, s)
        return JSONResponse({"ok": True, "guardados": res["guardados"]})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_guardar_estudiante(request: Request) -> JSONResponse:
    try:
        id_curso = request.path_params.get("id_curso", "")
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        
        res = guardar_estudiante(id_curso, body, s)
        return JSONResponse({"ok": True, "fila": res["fila"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_acta(request: Request) -> JSONResponse:
    try:
        id_curso = request.path_params.get("id_curso", "")
        email = get_current_user_email(request)
        s = sesion(email)
        
        datos_acta = leer_acta(id_curso, s)
        return JSONResponse({"ok": True, "acta": datos_acta})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_guardar_acta(request: Request) -> JSONResponse:
    try:
        id_curso = request.path_params.get("id_curso", "")
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        
        mesa = body.get("mesa")
        cambios = body.get("cambios", [])
        res = guardar_acta(id_curso, mesa, cambios, s)
        return JSONResponse({"ok": True, "guardados": res["guardados"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_analitico(request: Request) -> JSONResponse:
    try:
        id_curso = request.path_params.get("id_curso", "")
        email = get_current_user_email(request)
        s = sesion(email)
        
        documento = request.query_params.get("documento", "")
        fecha = request.query_params.get("fecha")
        certificado = request.query_params.get("certificado")
        
        res = obtener_analitico(id_curso, documento, fecha, certificado, s)
        return JSONResponse({"ok": True, "analitico": res})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_resumen(request: Request) -> JSONResponse:
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        resumen = obtener_resumen(s)
        return JSONResponse({"ok": True, "resumen": resumen})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_usuarios(request: Request) -> JSONResponse:
    try:
        usuarios = obtener_usuarios_panel()
        return JSONResponse({"ok": True, "usuarios": usuarios})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_instalar_panel(request: Request) -> JSONResponse:
    try:
        email = get_current_user_email(request)
        body = await request.json() if request.method == "POST" else {}
        admin = body.get("adminEmail", email)
        res = instalar_panel(admin)
        return JSONResponse({"ok": True, "panel": res})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_importar_cursos(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        folder_id = body.get("folderId")
        panel_id = body.get("panelId", PANEL_ID)
        cantidad = importar_cursos_de_carpeta(folder_id, panel_id)
        return JSONResponse({"ok": True, "importados": cantidad})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ==================== MÓDULO CIRCUITO DE CERTIFICADOS (TÍTULOS) ====================

async def api_listar_solicitudes(request: Request) -> JSONResponse:
    """Lista pedidos de certificados según permisos de rol."""
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        estado_filtro = request.query_params.get("estado")
        id_curso = request.query_params.get("id_curso")
        
        solicitudes = listar_solicitudes(s, estado_filtro=estado_filtro, id_curso=id_curso)
        return JSONResponse({"ok": True, "solicitudes": solicitudes})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

async def api_crear_solicitud(request: Request) -> JSONResponse:
    """La escuela solicita la emisión de certificado para un estudiante aprobado."""
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        id_curso = body.get("idCurso", "")
        documento = body.get("documento", "")

        curso = buscar_curso(id_curso)
        if not curso:
            return JSONResponse({"ok": False, "error": "Curso no encontrado."}, status_code=404)

        if not s.get("verTodo") and not alcanza_cue(s, curso.get("cue")):
            return JSONResponse({"ok": False, "error": "No tienes permiso para solicitar certificados en esta institución."}, status_code=403)

        datos = leer_curso(curso["id"])
        estudiante_encontrado = None
        for est in datos.get("estudiantes", []):
            if str(est.get("documento")).strip() == str(documento).strip():
                estudiante_encontrado = est
                break

        if not estudiante_encontrado:
            return JSONResponse({"ok": False, "error": f"No se encontró al estudiante con DNI {documento} en este curso."}, status_code=404)

        # Crear o reingresar
        sol = crear_o_reingresar_solicitud(
            id_curso=id_curso,
            documento=documento,
            sesion_usr=s,
            datos_estudiante=estudiante_encontrado,
            datos_curso=curso
        )
        return JSONResponse({"ok": True, "solicitud": sol})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_aprobar_solicitud(request: Request) -> JSONResponse:
    """El rol 'titulos' aprueba la solicitud y asigna el número oficial."""
    try:
        id_solicitud = request.path_params.get("id_solicitud", "")
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json() if request.method == "POST" else {}
        num_cert = body.get("numeroCertificado")

        sol = aprobar_solicitud(id_solicitud, s, numero_certificado=num_cert)
        return JSONResponse({"ok": True, "solicitud": sol})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_observar_solicitud(request: Request) -> JSONResponse:
    """El rol 'titulos' observa la solicitud indicando motivo obligatorio."""
    try:
        id_solicitud = request.path_params.get("id_solicitud", "")
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        motivo = body.get("motivo", "")

        sol = observar_solicitud(id_solicitud, motivo, s)
        return JSONResponse({"ok": True, "solicitud": sol})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_aprobar_lote_solicitudes(request: Request) -> JSONResponse:
    """El rol 'titulos' aprueba múltiples solicitudes en bloque."""
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        ids = body.get("ids", [])

        aprobados = aprobar_en_lote(ids, s)
        return JSONResponse({"ok": True, "aprobados": aprobados, "cantidad": len(aprobados)})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
