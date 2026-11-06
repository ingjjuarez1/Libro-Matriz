"""
Servicio para el circuito de emisión de certificados oficiales y bandeja de Títulos.
Maneja las solicitudes, aprobación con asignación de certificado,
observación con motivo obligatorio y congelamiento de calificaciones.
"""

import datetime
from typing import Dict, List, Any, Optional
from backend.app.core.config import (
    PANEL_ID, PANEL, EstadoCertificado, Roles
)
from backend.app.services.google_service import google_client
from backend.app.core.auth import (
    AuthException, PermissionDeniedException, alcanza_cue, registrar
)

# Almacén en memoria para funcionamiento offline/desarrollo y pruebas
_SOLICITUDES_CACHE: Dict[str, Dict[str, Any]] = {
    "sol-40123456": {
        "id": "sol-40123456",
        "idCurso": "curso-peluquero-ep6-demo",
        "cue": "3800006",
        "institucion": "Escuela Profesional Nº 6",
        "oferta": "Peluquero",
        "ciclo": "2026",
        "documento": "40123456",
        "estudiante": "ALVAREZ, María Belén",
        "calificacionDefinitiva": "9.00",
        "fechaSolicitud": "01/11/2026 10:30:00",
        "estado": EstadoCertificado.PENDIENTE,
        "motivoObservacion": "",
        "numeroCertificado": "",
        "fechaAprobacion": "",
        "usuarioSolicitante": "admin@ep6.jujuy.gob.ar"
    },
    "sol-42111222": {
        "id": "sol-42111222",
        "idCurso": "curso-peluquero-ep6-demo",
        "cue": "3800006",
        "institucion": "Escuela Profesional Nº 6",
        "oferta": "Peluquero",
        "ciclo": "2026",
        "documento": "42111222",
        "estudiante": "CORONEL, Luciana Rocío",
        "calificacionDefinitiva": "10.00",
        "fechaSolicitud": "28/10/2026 15:20:00",
        "estado": EstadoCertificado.OBSERVADO,
        "motivoObservacion": "El documento adjunto en legajo no coincide con la fecha de nacimiento indicada en el RAC. Verificar y corregir antes de emitir certificado.",
        "numeroCertificado": "",
        "fechaAprobacion": "",
        "usuarioSolicitante": "admin@ep6.jujuy.gob.ar"
    }
}

_CORRELATIVO_ACTUAL = 0

def _siguiente_numero_certificado(cue: str = "") -> str:
    global _CORRELATIVO_ACTUAL
    _CORRELATIVO_ACTUAL += 1
    anio = datetime.datetime.now().year
    cue_limpio = "".join(ch for ch in str(cue or "") if ch.isdigit()) or "3800006"
    # Formato oficial: AÑO-CUE-00000001  (ej: 2026-3800006-00000001)
    return f"{anio}-{cue_limpio}-{_CORRELATIVO_ACTUAL:08d}"

def listar_solicitudes(sesion_usr: Dict[str, Any], estado_filtro: Optional[str] = None, id_curso: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista las solicitudes de certificados.
    - El rol 'titulos' y 'Dirección DETP' ven todas las solicitudes.
    - La escuela ve únicamente las solicitudes pertenecientes a sus CUEs.
    """
    es_titulos = sesion_usr.get("esTitulos")
    ver_todo = sesion_usr.get("verTodo") or es_titulos

    solicitudes = list(_SOLICITUDES_CACHE.values())

    resultado = []
    for sol in solicitudes:
        # Filtro de seguridad institucional
        if not ver_todo and not alcanza_cue(sesion_usr, sol.get("cue")):
            continue
        # Filtro por curso opcional
        if id_curso and sol.get("idCurso") != id_curso:
            continue
        # Filtro por estado
        if estado_filtro and sol.get("estado") != estado_filtro:
            continue
        resultado.append(sol)

    # Ordenar por fecha más reciente
    resultado.sort(key=lambda s: s.get("fechaSolicitud", ""), reverse=True)
    return resultado

def obtener_solicitud(id_solicitud: str) -> Optional[Dict[str, Any]]:
    return _SOLICITUDES_CACHE.get(id_solicitud)

def obtener_estado_estudiante(id_curso: str, documento: str) -> Dict[str, Any]:
    """Busca el estado de certificación de un estudiante por su documento."""
    doc_norm = str(documento).strip()
    for sol in _SOLICITUDES_CACHE.values():
        if sol.get("idCurso") == id_curso and str(sol.get("documento")).strip() == doc_norm:
            return {
                "idSolicitud": sol["id"],
                "estado": sol["estado"],
                "numeroCertificado": sol.get("numeroCertificado", ""),
                "fechaAprobacion": sol.get("fechaAprobacion", ""),
                "motivoObservacion": sol.get("motivoObservacion", "")
            }
    return {
        "idSolicitud": None,
        "estado": EstadoCertificado.NO_SOLICITADO,
        "numeroCertificado": "",
        "fechaAprobacion": "",
        "motivoObservacion": ""
    }

def esta_estudiante_congelado(id_curso: str, documento: str) -> bool:
    """Verifica si las calificaciones del estudiante están congeladas por certificado aprobado."""
    estado_data = obtener_estado_estudiante(id_curso, documento)
    return estado_data.get("estado") == EstadoCertificado.APROBADO

def crear_o_reingresar_solicitud(
    id_curso: str,
    documento: str,
    sesion_usr: Dict[str, Any],
    datos_estudiante: Optional[Dict[str, Any]] = None,
    datos_curso: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Crea una nueva solicitud de certificado o reingresa una solicitud previamente observada.
    REGLA: Solo se puede solicitar para alumnos con situación 'Aprobó'.
    """
    doc_norm = str(documento).strip()
    
    # 1. Validar situación académica del estudiante
    situacion = str(datos_estudiante.get("situacion", "") if datos_estudiante else "").strip()
    if not situacion.startswith("Aprobó"):
        raise PermissionDeniedException(
            f"No se puede solicitar certificado para el estudiante {doc_norm} porque su situación es '{situacion or 'No aprobó'}'. "
            "Solo se permite para estudiantes con estado 'Aprobó'."
        )

    # 2. Verificar si ya existe solicitud
    sol_id = f"sol-{doc_norm}"
    sol_existente = _SOLICITUDES_CACHE.get(sol_id)
    if sol_existente and sol_existente.get("estado") == EstadoCertificado.APROBADO:
        raise PermissionDeniedException(
            f"El estudiante ya cuenta con un certificado oficial APROBADO (Nº {sol_existente.get('numeroCertificado')})."
        )

    ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    nombre_completo = f"{datos_estudiante.get('apellido', '')}, {datos_estudiante.get('nombres', '')}".strip()

    nueva_sol = {
        "id": sol_id,
        "idCurso": id_curso,
        "cue": datos_curso.get("cue", "") if datos_curso else "",
        "institucion": datos_curso.get("institucion", "") if datos_curso else "",
        "oferta": datos_curso.get("oferta", "") if datos_curso else "",
        "ciclo": datos_curso.get("ciclo", "") if datos_curso else "",
        "documento": doc_norm,
        "estudiante": nombre_completo,
        "calificacionDefinitiva": str(datos_estudiante.get("notaFinal", "") if datos_estudiante else ""),
        "fechaSolicitud": ahora,
        "estado": EstadoCertificado.PENDIENTE,
        "motivoObservacion": "",  # Se limpia al reingresar
        "numeroCertificado": "",
        "fechaAprobacion": "",
        "usuarioSolicitante": sesion_usr.get("email", "")
    }

    _SOLICITUDES_CACHE[sol_id] = nueva_sol
    registrar(
        sesion_usr,
        "Solicitud Certificado",
        f"{nueva_sol['oferta']} ({nueva_sol['cue']})",
        f"Estudiante: {nombre_completo} - DNI: {doc_norm}"
    )

    return nueva_sol

def aprobar_solicitud(id_solicitud: str, sesion_usr: Dict[str, Any], numero_certificado: Optional[str] = None) -> Dict[str, Any]:
    """
    Aprueba una solicitud de certificado y le asigna el número oficial.
    REGLA: Requiere rol 'titulos'. En ese instante, las notas quedan congeladas.
    """
    if not sesion_usr.get("esTitulos") and sesion_usr.get("rol") != Roles.DIRECCION:
        raise PermissionDeniedException("Solo la Dirección de Títulos tiene permisos para aprobar certificados.")

    sol = _SOLICITUDES_CACHE.get(id_solicitud)
    if not sol:
        raise ValueError(f"No se encontró la solicitud {id_solicitud}.")

    num_cert = str(numero_certificado or "").strip()
    if not num_cert:
        num_cert = _siguiente_numero_certificado(sol.get("cue", ""))

    ahora_fecha = datetime.datetime.now().strftime("%d/%m/%Y")
    sol["estado"] = EstadoCertificado.APROBADO
    sol["numeroCertificado"] = num_cert
    sol["fechaAprobacion"] = ahora_fecha
    sol["motivoObservacion"] = ""

    registrar(
        sesion_usr,
        "Aprobación Certificado",
        f"{sol['oferta']} ({sol['cue']})",
        f"Certificado Nº {num_cert} asignado a {sol['estudiante']} (DNI {sol['documento']})"
    )

    return sol

def observar_solicitud(id_solicitud: str, motivo: str, sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Observa una solicitud requiriendo obligatoriamente el motivo.
    REGLA: Requiere rol 'titulos'. Vuelve al panel de la escuela con el motivo.
    """
    if not sesion_usr.get("esTitulos") and sesion_usr.get("rol") != Roles.DIRECCION:
        raise PermissionDeniedException("Solo la Dirección de Títulos tiene permisos para observar solicitudes.")

    motivo_limpio = str(motivo or "").strip()
    if not motivo_limpio:
        raise ValueError("El motivo de observación es obligatorio para poder devolver la solicitud.")

    sol = _SOLICITUDES_CACHE.get(id_solicitud)
    if not sol:
        raise ValueError(f"No se encontró la solicitud {id_solicitud}.")

    sol["estado"] = EstadoCertificado.OBSERVADO
    sol["motivoObservacion"] = motivo_limpio
    sol["numeroCertificado"] = ""
    sol["fechaAprobacion"] = ""

    registrar(
        sesion_usr,
        "Observación Certificado",
        f"{sol['oferta']} ({sol['cue']})",
        f"Observado {sol['estudiante']}: {motivo_limpio}"
    )

    return sol

def aprobar_en_lote(ids_solicitudes: List[str], sesion_usr: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aprueba múltiples solicitudes a la vez asignando correlativos automáticos."""
    aprobados = []
    for sid in ids_solicitudes:
        try:
            sol = aprobar_solicitud(sid, sesion_usr)
            aprobados.append(sol)
        except Exception:
            pass
    return aprobados

def validar_certificado_por_numero(nro_certificado: str, dni: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifica públicamente (vía QR) si un certificado o título es válido y fue aprobado por Títulos.
    """
    nro_limpio = str(nro_certificado or "").strip()
    dni_limpio = str(dni or "").strip()

    for sol in _SOLICITUDES_CACHE.values():
        match_nro = bool(nro_limpio and sol.get("numeroCertificado") == nro_limpio)
        match_dni = bool(dni_limpio and sol.get("documento") == dni_limpio)
        if match_nro or ( not nro_limpio and match_dni ):
            es_valido = (sol.get("estado") == EstadoCertificado.APROBADO and bool(sol.get("numeroCertificado")))
            return {
                "valido": es_valido,
                "estado": sol.get("estado"),
                "idCurso": sol.get("idCurso", ""),
                "numeroCertificado": sol.get("numeroCertificado", ""),
                "estudiante": sol.get("estudiante", ""),
                "documento": sol.get("documento", ""),
                "oferta": sol.get("oferta", ""),
                "institucion": sol.get("institucion", ""),
                "cue": sol.get("cue", ""),
                "ciclo": sol.get("ciclo", ""),
                "fechaAprobacion": sol.get("fechaAprobacion", "")
            }

    return {
        "valido": False,
        "estado": "No registrado / Borrador",
        "numeroCertificado": nro_limpio,
        "mensaje": "El certificado consultado no figura como aprobado en el Registro Oficial de la Dirección de Títulos."
    }
