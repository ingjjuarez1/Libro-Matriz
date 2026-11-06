"""
Rutas API REST para Libro Matriz FP.
Reemplaza todas las llamadas de google.script.run.
"""

import json
import base64
from typing import Dict, Any, Optional
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse
from backend.app.core.auth import (
    sesion, alcanza_cue, AuthException, PermissionDeniedException,
    obtener_usuarios_panel, guardar_usuario_panel, eliminar_usuario_panel
)
from backend.app.services.datos_service import (
    cursos_del_panel, buscar_curso, leer_curso, guardar_notas,
    guardar_estudiante, leer_acta, guardar_acta, obtener_analitico,
    obtener_resumen, importar_excel_en_sistema, crear_curso_manual
)
from backend.app.services.instalador_service import instalar_panel, importar_cursos_de_carpeta
from backend.app.core.config import PANEL_ID

from backend.app.services.titulos_service import (
    listar_solicitudes, crear_o_reingresar_solicitud, aprobar_solicitud,
    observar_solicitud, aprobar_en_lote, validar_certificado_por_numero
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
        return JSONResponse({"ok": True, "fila": res["fila"], "estudiante": res.get("estudiante")})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

async def api_crear_curso(request: Request) -> JSONResponse:
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        curso = crear_curso_manual(body, s)
        return JSONResponse({"ok": True, "curso": curso})
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
        if request.method == "GET":
            usuarios = obtener_usuarios_panel()
            return JSONResponse({"ok": True, "usuarios": usuarios})
        
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()

        if request.method == "POST":
            usr = guardar_usuario_panel(body, s)
            return JSONResponse({"ok": True, "usuario": usr})
        elif request.method == "DELETE":
            email_obj = body.get("Email") or request.query_params.get("email", "")
            eliminar_usuario_panel(email_obj, s)
            return JSONResponse({"ok": True, "eliminado": email_obj})

        return JSONResponse({"ok": False, "error": "Método no soportado"}, status_code=405)
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

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

async def api_importar_excel(request: Request) -> JSONResponse:
    """Recibe un Viejo Excel (.xlsm o .xlsx) en base64 y crea el curso con su nómina y notas."""
    try:
        email = get_current_user_email(request)
        s = sesion(email)
        body = await request.json()
        nombre_archivo = str(body.get("nombreArchivo", "Libro_Matriz.xlsx"))
        b64_str = str(body.get("contenidoBase64", ""))
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        contenido = base64.b64decode(b64_str)
        res = importar_excel_en_sistema(contenido, nombre_archivo, s)
        return JSONResponse({"ok": True, **res})
    except (AuthException, PermissionDeniedException) as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=403)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

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

async def api_validar_certificado(request: Request) -> JSONResponse:
    """Endpoint JSON público para validar un certificado vía QR."""
    nro = request.query_params.get("nro", "")
    dni = request.query_params.get("dni", "")
    res = validar_certificado_por_numero(nro, dni)
    return JSONResponse({"ok": True, "validacion": res})

async def pagina_validar_certificado(request: Request) -> HTMLResponse:
    """Página web pública devuelta al escanear el código QR del certificado."""
    nro = request.query_params.get("nro", "")
    dni = request.query_params.get("dni", "")
    res = validar_certificado_por_numero(nro, dni)
    es_valido = res.get("valido", False)

    if es_valido:
        badge = '<div style="background:#e6f4ea;border:2px solid #34a853;color:#137333;padding:16px;border-radius:8px;font-size:18px;font-weight:bold;text-align:center;margin:16px 0">✅ TÍTULO / CERTIFICADO OFICIAL VÁLIDO</div>'
        detalle = f"""
        <table style="width:100%;border-collapse:collapse;margin-top:16px;font-size:14px">
          <tr style="border-bottom:1px solid #ddd"><td style="padding:8px;color:#555"><b>N° de Certificado:</b></td><td style="padding:8px"><b>{res.get('numeroCertificado')}</b></td></tr>
          <tr style="border-bottom:1px solid #ddd"><td style="padding:8px;color:#555"><b>Estudiante:</b></td><td style="padding:8px">{res.get('estudiante')}</td></tr>
          <tr style="border-bottom:1px solid #ddd"><td style="padding:8px;color:#555"><b>DNI:</b></td><td style="padding:8px">{res.get('documento')}</td></tr>
          <tr style="border-bottom:1px solid #ddd"><td style="padding:8px;color:#555"><b>Oferta Formativa:</b></td><td style="padding:8px">{res.get('oferta')}</td></tr>
          <tr style="border-bottom:1px solid #ddd"><td style="padding:8px;color:#555"><b>Institución:</b></td><td style="padding:8px">{res.get('institucion')} (CUE {res.get('cue')})</td></tr>
          <tr style="border-bottom:1px solid #ddd"><td style="padding:8px;color:#555"><b>Ciclo Lectivo:</b></td><td style="padding:8px">{res.get('ciclo')}</td></tr>
          <tr><td style="padding:8px;color:#555"><b>Fecha de Aprobación:</b></td><td style="padding:8px">{res.get('fechaAprobacion')}</td></tr>
        </table>
        """
    else:
        badge = '<div style="background:#fce8e6;border:2px solid #ea4335;color:#c5221f;padding:16px;border-radius:8px;font-size:18px;font-weight:bold;text-align:center;margin:16px 0">❌ DOCUMENTO NO VÁLIDO / BORRADOR</div>'
        detalle = f'<p style="text-align:center;color:#555;font-size:14px">{res.get("mensaje", "Este documento aún no fue aprobado por la Dirección de Títulos.")}</p>'

    html = f"""<!DOCTYPE html>
    <html lang="es-AR">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Validación Oficial de Certificados · DETP Jujuy</title>
    </head>
    <body style="font-family:Segoe UI,Arial,sans-serif;background:#f6f8fa;margin:0;padding:24px">
      <div style="max-width:520px;margin:20px auto;background:#fff;border:1px solid #c9d3dd;border-radius:10px;padding:28px;box-shadow:0 4px 14px rgba(0,0,0,0.08)">
        <div style="text-align:center;border-bottom:1px solid #eee;padding-bottom:14px">
          <img src="/img/escudo_nacional.png" alt="Escudo" style="height:56px">
          <h2 style="margin:8px 0 2px;color:#1F4E78;font-size:18px">Ministerio de Educación · Provincia de Jujuy</h2>
          <div style="font-size:12px;color:#5b6b7c">Dirección de Educación Técnico Profesional · Dirección de Títulos</div>
        </div>
        {badge}
        {detalle}
        <div style="margin-top:22px;text-align:center;font-size:11px;color:#888">
          Sistema Integrado de Libro Matriz de Formación Profesional
        </div>
      </div>
    </body>
    </html>"""
    return HTMLResponse(html)
