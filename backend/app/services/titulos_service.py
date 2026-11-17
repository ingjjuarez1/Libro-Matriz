"""
Servicio para el circuito de emisión de certificados oficiales y bandeja de Títulos.
Maneja las solicitudes, aprobación con asignación de certificado,
observación con motivo obligatorio y congelamiento de calificaciones.
"""

import os
import re
import json
import tempfile
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from backend.app.core.config import (
    PANEL_ID, PANEL, EstadoCertificado, Roles
)
from backend.app.services.google_service import google_client
from backend.app.core.auth import (
    AuthException, PermissionDeniedException, alcanza_cue, registrar
)

_RUTA_SOLICITUDES_DISCO = Path(__file__).resolve().parent.parent.parent / "data" / "solicitudes_titulos.json"

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
        "usuarioSolicitante": "admin.ep6@jujuy.edu.ar"
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
        "usuarioSolicitante": "admin.ep6@jujuy.edu.ar"
    }
}

_CORRELATIVO_POR_ANIO: Dict[int, int] = {}


def _reconstruir_correlativos() -> None:
    """Reconstruye los contadores correlativos por año desde los números de certificado guardados."""
    for sol in _SOLICITUDES_CACHE.values():
        nro = str(sol.get("numeroCertificado", "")).strip()
        m = re.match(r"^(\d{4})-.*-(\d+)$", nro)
        if m:
            try:
                anio = int(m.group(1))
                seq = int(m.group(2))
                if seq > _CORRELATIVO_POR_ANIO.get(anio, 0):
                    _CORRELATIVO_POR_ANIO[anio] = seq
            except Exception:
                pass


def _cargar_solicitudes_disco() -> None:
    """Carga solicitudes y contadores correlativos desde disco si existen."""
    try:
        if _RUTA_SOLICITUDES_DISCO.exists():
            data = json.loads(_RUTA_SOLICITUDES_DISCO.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                sols = data.get("solicitudes")
                if isinstance(sols, dict):
                    _SOLICITUDES_CACHE.clear()
                    _SOLICITUDES_CACHE.update(sols)
                corrs = data.get("correlativos")
                if isinstance(corrs, dict):
                    _CORRELATIVO_POR_ANIO.clear()
                    for k, v in corrs.items():
                        try:
                            _CORRELATIVO_POR_ANIO[int(k)] = int(v)
                        except Exception:
                            pass
    except Exception:
        pass
    _reconstruir_correlativos()


def _guardar_solicitudes_disco() -> None:
    """Persiste atómicamente _SOLICITUDES_CACHE y _CORRELATIVO_POR_ANIO en disco."""
    try:
        _RUTA_SOLICITUDES_DISCO.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "solicitudes": _SOLICITUDES_CACHE,
            "correlativos": {str(k): int(v) for k, v in _CORRELATIVO_POR_ANIO.items()}
        }
        fd, tmp_path = tempfile.mkstemp(
            prefix="sol_tmp_",
            suffix=".json",
            dir=str(_RUTA_SOLICITUDES_DISCO.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, _RUTA_SOLICITUDES_DISCO)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except Exception:
        pass


_cargar_solicitudes_disco()

def _siguiente_numero_certificado(cue: str = "") -> str:
    anio = datetime.datetime.now().year
    actual = _CORRELATIVO_POR_ANIO.get(anio, 0) + 1
    _CORRELATIVO_POR_ANIO[anio] = actual
    cue_limpio = "".join(ch for ch in str(cue or "") if ch.isdigit()) or "380000600"
    if len(cue_limpio) == 7:
        cue_limpio = cue_limpio + "00"
    # Formato oficial: AÑO-CUE-00001 (se reinicia a 00001 automáticamente al comenzar cada nuevo año)
    return f"{anio}-{cue_limpio}-{actual:05d}"

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
                "motivoObservacion": sol.get("motivoObservacion", ""),
                "impreso": bool(sol.get("impreso", False)),
                "fechaImpresion": sol.get("fechaImpresion", ""),
                "impresoPor": sol.get("impresoPor", "")
            }
    return {
        "idSolicitud": None,
        "estado": EstadoCertificado.NO_SOLICITADO,
        "numeroCertificado": "",
        "fechaAprobacion": "",
        "motivoObservacion": "",
        "impreso": False,
        "fechaImpresion": "",
        "impresoPor": ""
    }

def esta_estudiante_congelado(id_curso: str, documento: str) -> bool:
    """Verifica si las calificaciones del estudiante están congeladas por certificado aprobado."""
    estado_data = obtener_estado_estudiante(id_curso, documento)
    return estado_data.get("estado") == EstadoCertificado.APROBADO

def _buscar_solicitud_por_curso_doc(id_curso: str, documento: str) -> Optional[Dict[str, Any]]:
    doc_norm = str(documento or "").strip()
    for sol in _SOLICITUDES_CACHE.values():
        if sol.get("idCurso") == id_curso and str(sol.get("documento", "")).strip() == doc_norm:
            return sol
    return None


def _es_estudiante_elegible_titulos(datos_estudiante: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Regla académica oficial: el estudiante es elegible SOLO si su situación
    comienza con 'Aprobó' y (si notaFinal no está vacía) notaFinal es numérica >= 7.
    """
    if not datos_estudiante:
        return False, "No se encontraron datos académicos del estudiante."
    nombre_est = f"{datos_estudiante.get('apellido', '')}, {datos_estudiante.get('nombres', '')}".strip(", ") or "Estudiante"
    doc_norm = str(datos_estudiante.get("documento", "")).strip()
    situacion = str(datos_estudiante.get("situacion", "")).strip()
    if not situacion.startswith("Aprobó"):
        return (
            False,
            f"El estudiante {nombre_est} (DNI {doc_norm}) no está aprobado académicamente "
            f"(situación actual: '{situacion or 'No aprobó'}')."
        )
    nf_raw = str(datos_estudiante.get("notaFinal", "")).strip()
    if nf_raw:
        try:
            nf_val = float(nf_raw.replace(",", "."))
            if nf_val < 7:
                return (
                    False,
                    f"El estudiante {nombre_est} (DNI {doc_norm}) tiene calificación final '{nf_raw}' menor a 7."
                )
        except Exception:
            return (
                False,
                f"El estudiante {nombre_est} (DNI {doc_norm}) tiene calificación final '{nf_raw}' no aprobatoria."
            )
    return True, ""


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
    elegible, motivo_no = _es_estudiante_elegible_titulos(datos_estudiante)
    if not elegible:
        raise PermissionDeniedException(
            f"No se puede solicitar certificado para el estudiante {doc_norm}: {motivo_no}"
        )

    # 2. Verificar si ya existe solicitud para este (idCurso, documento)
    sol_existente = _buscar_solicitud_por_curso_doc(id_curso, doc_norm)
    if sol_existente and sol_existente.get("estado") == EstadoCertificado.APROBADO:
        raise PermissionDeniedException(
            f"El estudiante ya cuenta con un certificado oficial APROBADO (Nº {sol_existente.get('numeroCertificado')})."
        )

    sol_id = sol_existente["id"] if sol_existente else f"sol-{id_curso}-{doc_norm}"
    ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    nombre_completo = f"{datos_estudiante.get('apellido', '')}, {datos_estudiante.get('nombres', '')}".strip(", ")

    nueva_sol = {
        "id": sol_id,
        "idCurso": id_curso,
        "cue": datos_curso.get("cue", "") if datos_curso else "",
        "institucion": datos_curso.get("institucion", "") if datos_curso else "",
        "oferta": datos_curso.get("oferta", "") if datos_curso else "",
        "ciclo": datos_curso.get("ciclo", "") if datos_curso else "",
        "documento": doc_norm,
        "estudiante": nombre_completo,
        "calificacionDefinitiva": str((datos_estudiante.get("notaFinal") or datos_estudiante.get("promedioModulos") or "") if datos_estudiante else ""),
        "fechaSolicitud": ahora,
        "estado": EstadoCertificado.PENDIENTE,
        "motivoObservacion": "",  # Se limpia al reingresar
        "numeroCertificado": "",
        "fechaAprobacion": "",
        "usuarioSolicitante": sesion_usr.get("email", "")
    }

    _SOLICITUDES_CACHE[sol_id] = nueva_sol
    _guardar_solicitudes_disco()
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
    Idempotente: si ya está Aprobado, no sobreescribe el número de certificado ni el estado de impresión.
    """
    if not sesion_usr.get("esTitulos") and sesion_usr.get("rol") != Roles.DIRECCION:
        raise PermissionDeniedException("Solo la Dirección de Títulos tiene permisos para aprobar certificados.")

    sol = _SOLICITUDES_CACHE.get(id_solicitud)
    if not sol:
        raise ValueError(f"No se encontró la solicitud {id_solicitud}.")

    if sol.get("estado") == EstadoCertificado.APROBADO:
        return sol

    num_cert = str(numero_certificado or "").strip()
    if not num_cert:
        num_cert = _siguiente_numero_certificado(sol.get("cue", ""))

    ahora_fecha = datetime.datetime.now().strftime("%d/%m/%Y")
    sol["estado"] = EstadoCertificado.APROBADO
    sol["numeroCertificado"] = num_cert
    sol["fechaAprobacion"] = ahora_fecha
    sol["motivoObservacion"] = ""
    sol["impreso"] = False
    sol["fechaImpresion"] = ""
    sol["impresoPor"] = ""
    _guardar_solicitudes_disco()

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
    _guardar_solicitudes_disco()

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


def aprobar_estudiantes_curso(
    id_curso: str,
    documentos: Optional[List[str]],
    sesion_usr: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Permite a Dirección de Títulos aprobar directamente desde el curso/RAC a uno o varios
    estudiantes elegibles (o a todos los egresados aprobados del curso si documentos es None/vacío).
    """
    if not sesion_usr.get("esTitulos") and sesion_usr.get("rol") != Roles.DIRECCION:
        raise PermissionDeniedException("Solo la Dirección de Títulos tiene permisos para aprobar certificados.")

    from backend.app.services.datos_service import buscar_curso, leer_curso

    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError(f"Curso '{id_curso}' no encontrado.")

    datos = leer_curso(curso["id"])
    enc = datos.get("encabezado", {})
    estudiantes = datos.get("estudiantes", [])
    ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    def _crear_si_no_existe(est_obj: Dict[str, Any]) -> Dict[str, Any]:
        doc_n = str(est_obj.get("documento", "")).strip()
        sol_ex = _buscar_solicitud_por_curso_doc(curso["id"], doc_n)
        if sol_ex:
            return sol_ex
        sol_id_n = f"sol-{curso['id']}-{doc_n}"
        nom_comp = f"{est_obj.get('apellido', '')}, {est_obj.get('nombres', '')}".strip(", ")
        nueva = {
            "id": sol_id_n,
            "idCurso": curso["id"],
            "cue": enc.get("cue") or curso.get("cue", ""),
            "institucion": enc.get("establecimiento") or curso.get("institucion", ""),
            "oferta": enc.get("oferta") or curso.get("oferta", ""),
            "ciclo": enc.get("ciclo") or curso.get("ciclo", ""),
            "documento": doc_n,
            "estudiante": nom_comp,
            "calificacionDefinitiva": str(est_obj.get("notaFinal") or est_obj.get("promedioModulos") or ""),
            "fechaSolicitud": ahora,
            "estado": EstadoCertificado.PENDIENTE,
            "motivoObservacion": "",
            "numeroCertificado": "",
            "fechaAprobacion": "",
            "usuarioSolicitante": sesion_usr.get("email", "")
        }
        _SOLICITUDES_CACHE[sol_id_n] = nueva
        return nueva

    aprobados: List[Dict[str, Any]] = []
    ya_aprobados: List[Dict[str, Any]] = []
    omitidos: List[Dict[str, Any]] = []

    docs_objetivo = [str(d).strip() for d in (documentos or []) if str(d or "").strip()]
    if docs_objetivo:
        mapa_est = {str(e.get("documento", "")).strip(): e for e in estudiantes}
        for doc_n in docs_objetivo:
            est_obj = mapa_est.get(doc_n)
            if not est_obj:
                raise ValueError(f"No se encontró al estudiante con DNI {doc_n} en el curso.")
            elegible, motivo_no = _es_estudiante_elegible_titulos(est_obj)
            if not elegible:
                raise ValueError(motivo_no)
        for doc_n in docs_objetivo:
            est_obj = mapa_est[doc_n]
            sol = _crear_si_no_existe(est_obj)
            if sol.get("estado") == EstadoCertificado.APROBADO:
                ya_aprobados.append(sol)
            else:
                sol_apr = aprobar_solicitud(sol["id"], sesion_usr)
                aprobados.append(sol_apr)
    else:
        for est_obj in estudiantes:
            doc_n = str(est_obj.get("documento", "")).strip()
            nom_comp = f"{est_obj.get('apellido', '')}, {est_obj.get('nombres', '')}".strip(", ")
            elegible, motivo_no = _es_estudiante_elegible_titulos(est_obj)
            if not elegible:
                omitidos.append({"documento": doc_n, "estudiante": nom_comp, "motivo": motivo_no})
                continue
            sol = _crear_si_no_existe(est_obj)
            if sol.get("estado") == EstadoCertificado.APROBADO:
                ya_aprobados.append(sol)
            else:
                sol_apr = aprobar_solicitud(sol["id"], sesion_usr)
                aprobados.append(sol_apr)

    _guardar_solicitudes_disco()
    return {
        "idCurso": curso["id"],
        "aprobados": aprobados,
        "cantidadAprobados": len(aprobados),
        "yaAprobados": ya_aprobados,
        "omitidos": omitidos
    }


def registrar_impresion_certificado(id_curso: str, documento: str, sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra la impresión única del certificado oficial por parte del Administrativo (o Directivo)
    y bloquea el certificado para que no pueda volver a imprimirse.
    """
    rol_usr = str(sesion_usr.get("rol", "")).strip().lower()
    if rol_usr not in ("administrativo", "directivo"):
        raise PermissionDeniedException("Solo el Administrativo o el Directivo de la institución puede imprimir el certificado.")

    doc_norm = str(documento).strip()
    sol_encontrada = _buscar_solicitud_por_curso_doc(id_curso, doc_norm)

    if not sol_encontrada or sol_encontrada.get("estado") != EstadoCertificado.APROBADO:
        raise PermissionDeniedException("El certificado aún no fue aprobado por la Dirección de Títulos.")

    if sol_encontrada.get("impreso"):
        raise PermissionDeniedException(
            f"Este certificado ya fue impreso el {sol_encontrada.get('fechaImpresion')} y se encuentra bloqueado."
        )

    ahora_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    sol_encontrada["impreso"] = True
    sol_encontrada["fechaImpresion"] = ahora_str
    sol_encontrada["impresoPor"] = sesion_usr.get("email", "")
    _guardar_solicitudes_disco()

    registrar(
        sesion_usr,
        "Impresión Única Certificado",
        f"{sol_encontrada.get('oferta', '')} ({sol_encontrada.get('cue', '')})",
        f"Certificado Nº {sol_encontrada.get('numeroCertificado')} impreso y bloqueado (DNI {doc_norm})"
    )
    return sol_encontrada

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
