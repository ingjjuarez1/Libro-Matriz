"""
Lógica de datos y manipulación de planillas Google Sheets.
Migrado de Datos.gs y Api.gs.
Preserva la lógica exacta de Libro Matriz FP:
- RAC (Registro Anual de Calificaciones)
- Acta de Examen
- Certificado Analítico
- Panel FP (Usuarios, Cursos, Registro)
"""

import os
import re
import json
import time
import uuid
import tempfile
import datetime
import threading
from pathlib import Path
from typing import Dict, List, Any, Optional
from backend.app.core.config import (
    PANEL_ID, RAC, ACTA, ANALITICO, PANEL, AUSENTE,
    col_num_to_letter, letter_to_col_num
)
from backend.app.services.google_service import google_client
from backend.app.core.auth import (
    normalizar_cue, exigir_lectura, exigir_carga, registrar, alcanza_cue, PermissionDeniedException,
    asegurar_usuarios_escuela
)
from backend.app.services.titulos_service import (
    obtener_estado_estudiante, esta_estudiante_congelado, EstadoCertificado
)
from backend.app.services.excel_importer import (
    procesar_archivo_excel, _calcular_situacion_y_promedio, _generar_id_curso_excel
)

_RUTA_CURSOS_DISCO = Path(__file__).resolve().parent.parent.parent / "data" / "cursos_importados.json"
_RUTA_INSTITUCIONES = Path(__file__).resolve().parent.parent.parent.parent / "planillas" / "instituciones.json"
_CURSOS_IMPORTADOS: Dict[str, Dict[str, Any]] = {}
_INSTITUCIONES_CACHE: Optional[List[Dict[str, Any]]] = None
_MANUAL_ID_LOCK = threading.Lock()
_MANUAL_ID_SEQ = 0


def _generar_id_curso_manual() -> str:
    global _MANUAL_ID_SEQ
    with _MANUAL_ID_LOCK:
        _MANUAL_ID_SEQ += 1
        seq = _MANUAL_ID_SEQ
    cid = f"curso-{int(time.time() * 1000)}-{seq}-{uuid.uuid4().hex[:4]}"
    while cid in _CURSOS_IMPORTADOS:
        cid = f"curso-{int(time.time() * 1000)}-{seq}-{uuid.uuid4().hex[:6]}"
    return cid


def _cargar_instituciones() -> List[Dict[str, Any]]:
    global _INSTITUCIONES_CACHE
    if _INSTITUCIONES_CACHE is not None:
        return _INSTITUCIONES_CACHE
    try:
        if _RUTA_INSTITUCIONES.exists():
            data = json.loads(_RUTA_INSTITUCIONES.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _INSTITUCIONES_CACHE = data
                return _INSTITUCIONES_CACHE
    except Exception:
        pass
    _INSTITUCIONES_CACHE = []
    return _INSTITUCIONES_CACHE


def _buscar_institucion_por_cue(cue: Any) -> Optional[Dict[str, Any]]:
    cue_dig = normalizar_cue(cue)
    if not cue_dig:
        return None
    candidatos = {cue_dig}
    if len(cue_dig) == 7:
        candidatos.add(cue_dig + "00")
    elif len(cue_dig) == 9 and cue_dig.endswith("00"):
        candidatos.add(cue_dig[:7])
    for inst in _cargar_instituciones():
        inst_cue = normalizar_cue(inst.get("cue"))
        locs = [normalizar_cue(l) for l in (inst.get("localizaciones") or [])]
        if inst_cue in candidatos or any(l in candidatos for l in locs if l):
            return inst
    return None


def obtener_institucion_usuario(sesion_usr: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resuelve el nombre completo de la escuela activa para la barra superior."""
    cues = sesion_usr.get("cues") or []
    if cues:
        cue_u = normalizar_cue(cues[0])
        inst = _buscar_institucion_por_cue(cue_u)
        if inst:
            return {
                "cue": cue_u,
                "nombre": inst.get("nombre", ""),
                "localidad": inst.get("localidad", "")
            }
        # Fallback: buscar en cursos disponibles
        for c in cursos_del_panel():
            c_cue = normalizar_cue(c.get("cue"))
            if c_cue == cue_u or (len(cue_u) == 7 and c_cue == cue_u + "00") or (len(c_cue) == 7 and cue_u == c_cue + "00"):
                return {
                    "cue": cue_u,
                    "nombre": c.get("institucion", ""),
                    "localidad": ""
                }
        if cue_u == "3800006":
            return {
                "cue": "3800006",
                "nombre": "Escuela Profesional Nº 6",
                "localidad": "San Salvador de Jujuy"
            }
    return None


def _cargar_cursos_disco() -> None:
    """Carga en memoria los cursos importados o creados previamente desde disco."""
    global _CURSOS_IMPORTADOS
    try:
        if _RUTA_CURSOS_DISCO.exists():
            contenido = json.loads(_RUTA_CURSOS_DISCO.read_text(encoding="utf-8"))
            if isinstance(contenido, dict):
                _CURSOS_IMPORTADOS.update(contenido)
    except Exception:
        pass


def _guardar_cursos_disco() -> None:
    """Persiste atómicamente en disco los cursos importados/creados para que no se pierdan al actualizar."""
    try:
        _RUTA_CURSOS_DISCO.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="cursos_tmp_",
            suffix=".json",
            dir=str(_RUTA_CURSOS_DISCO.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(_CURSOS_IMPORTADOS, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, _RUTA_CURSOS_DISCO)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
    except Exception:
        pass


def sincronizar_cursos_locales(paquetes: Dict[str, Any], sesion_usr: Optional[Dict[str, Any]] = None) -> int:
    """Restaura paquetes de cursos guardados en el navegador si el contenedor se reinició."""
    if sesion_usr is not None and not sesion_usr.get("puedeCargar"):
        raise PermissionDeniedException(
            f"Tu rol ({sesion_usr.get('rol')}) es de consulta: no puedes sincronizar cursos."
        )
    if not isinstance(paquetes, dict):
        return 0

    paquetes_validos: List[tuple] = []
    for id_c, paq in paquetes.items():
        if not (isinstance(paq, dict) and "resumenCurso" in paq and "datosCurso" in paq):
            continue
        res_c = paq.get("resumenCurso")
        datos_c = paq.get("datosCurso")
        if not isinstance(res_c, dict) or not isinstance(datos_c, dict):
            continue
        enc_c = datos_c.get("encabezado") if isinstance(datos_c.get("encabezado"), dict) else {}
        if sesion_usr is not None and not sesion_usr.get("verTodo"):
            pkg_cue = normalizar_cue(res_c.get("cue") or enc_c.get("cue"))
            if not pkg_cue:
                cues_usr = sesion_usr.get("cues") or []
                if not cues_usr:
                    raise PermissionDeniedException("No tienes un CUE asignado para sincronizar cursos.")
                res_c["cue"] = cues_usr[0]
                if isinstance(datos_c.get("encabezado"), dict):
                    datos_c["encabezado"]["cue"] = cues_usr[0]
            elif not alcanza_cue(sesion_usr, pkg_cue):
                raise PermissionDeniedException(
                    f"No tienes permiso para sincronizar cursos de otra institución (CUE {pkg_cue})."
                )
        paquetes_validos.append((id_c, paq))

    restaurados = 0
    for id_c, paq in paquetes_validos:
        if id_c not in _CURSOS_IMPORTADOS:
            _CURSOS_IMPORTADOS[id_c] = paq
            restaurados += 1
    if restaurados > 0:
        _guardar_cursos_disco()
    return restaurados


_cargar_cursos_disco()

def texto(v: Any) -> str:
    """Normaliza un valor de celda a string limpio."""
    if v is None:
        return ""
    return str(v).strip()

def normalizar_nota(valor: Any) -> Any:
    """Valida y normaliza una nota: vacío, AUS, o entero de 1 a 10."""
    v = texto(valor).upper()
    if v == "":
        return ""
    if v in ["A", "AUS", "AUSENTE"]:
        return AUSENTE
    
    # Manejar comas decimales si vinieran
    v_clean = v.replace(",", ".")
    try:
        n = float(v_clean)
        if not (1 <= n <= 10) or n != int(n):
            raise ValueError()
        return int(n)
    except (ValueError, TypeError):
        raise ValueError(
            f"'{valor}' no es una nota válida. Ingresa un número entero de 1 a 10, o AUS si estuvo ausente."
        )

# ==================== DATOS DEMO / FALLBACK ====================

_CURSOS_DEMO = [
    {
        "cue": "3800006",
        "institucion": "Escuela Profesional Nº 6",
        "oferta": "Peluquero",
        "ciclo": "2026",
        "turno": "Vespertino",
        "division": '1º "U"',
        "id": "curso-peluquero-ep6-demo",
        "estado": "Abierto"
    }
]

_ESTUDIANTES_DEMO = [
    {
        "fila": 9,
        "orden": "1",
        "apellido": "AMANTE",
        "nombres": "Sergio David",
        "documento": "44645553",
        "tipoDoc": "DNI",
        "fechaNac": "01/02/2002",
        "localidad": "S S DE JUJUY (JUJUY)",
        "provincia": "Jujuy",
        "notas": ["8", "9", "10", "7", "8", ""],
        "notaFinal": "",
        "fechaEgreso": "",
        "folio": "11",
        "situacion": "Adeuda 1 módulo(s)"
    },
    {
        "fila": 10,
        "orden": "2",
        "apellido": "ALVAREZ",
        "nombres": "María Belén",
        "documento": "40123456",
        "tipoDoc": "DNI",
        "fechaNac": "15/04/1998",
        "localidad": "San Salvador de Jujuy",
        "provincia": "Jujuy",
        "notas": ["8", "9", "8", "10", "9", "9"],
        "notaFinal": "9",
        "fechaEgreso": "10/12/2026",
        "folio": "12",
        "situacion": "Aprobó todo"
    },
    {
        "fila": 11,
        "orden": "3",
        "apellido": "BENITEZ",
        "nombres": "Carlos Javier",
        "documento": "39876543",
        "tipoDoc": "DNI",
        "fechaNac": "22/08/1996",
        "localidad": "Palpalá",
        "provincia": "Jujuy",
        "notas": ["7", "8", "7", "8", "8", "7"],
        "notaFinal": "8",
        "fechaEgreso": "10/12/2026",
        "folio": "13",
        "situacion": "Aprobó todo"
    },
    {
        "fila": 12,
        "orden": "4",
        "apellido": "CORONEL",
        "nombres": "Luciana Rocío",
        "documento": "42111222",
        "tipoDoc": "DNI",
        "fechaNac": "05/11/2000",
        "localidad": "San Salvador de Jujuy",
        "provincia": "Jujuy",
        "notas": ["9", "10", "9", "9", "10", "10"],
        "notaFinal": "10",
        "fechaEgreso": "15/12/2026",
        "folio": "14",
        "situacion": "Aprobó todo"
    }
]

_ENCABEZADO_DEMO = {
    "establecimiento": "Escuela Profesional Nº 6",
    "localidad": "San Salvador de Jujuy",
    "cue": "3800006",
    "domicilio": "Av. Fascio 1050",
    "oferta": "Peluquero",
    "familiaProfesional": "Estética Profesional",
    "ciclo": "2026",
    "libro": "1",
    "folio": "1",
    "fechaActa": "15/12/2026",
    "turno": "Vespertino",
    "matriculados": "4",
    "cursoAnio": "1°",
    "divisionLetra": '"U"',
    "division": '1° "U"',
    "duracion": "1 Cuatrimestre",
    "docente": "Prof. Martín Gomez",
    "fechaFin1C": "15/12/2026",
    "fechaFin2C": "",
    "hsCatTotal": "510",
    "nivelCurso": "II",
    "certificacion": "Diseño Curricular Jurisdiccional",
    "normaAprobacion": "4006-E/2023",
    "resolucionDisenio": "661-E/2022",
    "validezNacional": "530/23",
    "disposicion": "-",
    "referencialIngreso": "Primaria Completa",
    "disenio": "661-E/2022"
}

_ACTA_DEMO_MESA = {
    "fecha": "15/12/2026",
    "presidente": "Prof. Martín Gomez",
    "vocal1": "Prof. Ana Torres",
    "vocal2": "Prof. Luis Pérez"
}

_ACTA_DEMO_ESTUDIANTES = [
    {
        "filaActa": 13,
        "filaRac": 9,
        "orden": "1",
        "documento": "44645553",
        "nombre": "AMANTE, Sergio David",
        "teorico": "",
        "practico": "",
        "definitiva": "",
        "definitivaLetras": ""
    },
    {
        "filaActa": 14,
        "filaRac": 10,
        "orden": "2",
        "documento": "40123456",
        "nombre": "ALVAREZ, María Belén",
        "teorico": "9",
        "practico": "9",
        "definitiva": "9",
        "definitivaLetras": "NUEVE"
    },
    {
        "filaActa": 15,
        "filaRac": 11,
        "orden": "3",
        "documento": "39876543",
        "nombre": "BENITEZ, Carlos Javier",
        "teorico": "8",
        "practico": "8",
        "definitiva": "8",
        "definitivaLetras": "OCHO"
    },
    {
        "filaActa": 16,
        "filaRac": 12,
        "orden": "4",
        "documento": "42111222",
        "nombre": "CORONEL, Luciana Rocío",
        "teorico": "10",
        "practico": "10",
        "definitiva": "10",
        "definitivaLetras": "DIEZ"
    }
]

# ==================== CURSOS DEL PANEL ====================

def _mezclar_cursos_importados(base: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Agrega todos los cursos importados o creados manualmente sin duplicar IDs."""
    resultado = list(base)
    ids_existentes = {c.get("id") for c in resultado if c.get("id")}
    for id_c, paq in _CURSOS_IMPORTADOS.items():
        res_c = paq.get("resumenCurso")
        if isinstance(res_c, dict) and res_c.get("id") and res_c["id"] not in ids_existentes:
            resultado.append(dict(res_c))
            ids_existentes.add(res_c["id"])
    return resultado


def cursos_del_panel() -> List[Dict[str, Any]]:
    """Lee y normaliza el índice de cursos desde la pestaña 'Cursos' del Panel FP."""
    if not PANEL_ID or not google_client.is_connected():
        return _mezclar_cursos_importados(_CURSOS_DEMO)

    try:
        rango = f"{PANEL['CURSOS']['hoja']}!A1:H1000"
        valores = google_client.get_values(PANEL_ID, rango)
        if len(valores) < 2:
            return _mezclar_cursos_importados(_CURSOS_DEMO)

        encabezados = [texto(col) for col in valores[0]]
        cursos = []
        for fila in valores[1:]:
            if not fila or not any(texto(c) for c in fila):
                continue
            item = {}
            for idx, enc in enumerate(encabezados):
                item[enc] = fila[idx] if idx < len(fila) else ""
            
            file_id = texto(item.get("ID del archivo"))
            if not file_id:
                continue

            cursos.append({
                "cue": normalizar_cue(item.get("CUE")),
                "institucion": texto(item.get("Institución")),
                "oferta": texto(item.get("Oferta")),
                "ciclo": texto(item.get("Ciclo")),
                "turno": texto(item.get("Turno")),
                "division": texto(item.get("Curso / División")),
                "id": file_id,
                "estado": texto(item.get("Estado")) or "Abierto"
            })
        base = cursos if cursos else list(_CURSOS_DEMO)
        return _mezclar_cursos_importados(base)
    except Exception:
        return _mezclar_cursos_importados(_CURSOS_DEMO)

def buscar_curso(id_curso: str) -> Optional[Dict[str, Any]]:
    """Busca un curso por su ID de archivo en Drive."""
    for c in cursos_del_panel():
        if c["id"] == id_curso:
            return c
    return None

# ==================== LECTURA DE CURSO (RAC) ====================

def leer_curso(id_archivo: str) -> Dict[str, Any]:
    """
    Lee encabezado, módulos y lista de estudiantes desde la pestaña RAC del curso.
    Optimizado en batch: lee metadatos y rangos en mínimas llamadas.
    """
    if id_archivo in _CURSOS_IMPORTADOS:
        datos_imp = _CURSOS_IMPORTADOS[id_archivo]["datosCurso"]
        est_copia = []
        for est in datos_imp.get("estudiantes", []):
            e = dict(est)
            notas_e = list(e.get("notas", []))
            prom_recalc, sit_recalc = _calcular_situacion_y_promedio(notas_e)
            if prom_recalc and not e.get("promedioModulos"):
                e["promedioModulos"] = prom_recalc
            nf_e = texto(e.get("notaFinal"))
            if nf_e == "AUS":
                e["situacion"] = "Ausente examen final"
            elif nf_e and nf_e.isdigit() and int(nf_e) < 7:
                e["situacion"] = "Desaprobó examen final"
            elif sit_recalc.startswith("Aprobó") or sit_recalc.startswith("Desaprobó"):
                e["situacion"] = sit_recalc
            sol_info = obtener_estado_estudiante(id_archivo, e.get("documento", ""))
            e["solicitudCertificado"] = sol_info
            e["notasCongeladas"] = (sol_info.get("estado") == EstadoCertificado.APROBADO)
            est_copia.append(e)
        return {
            "encabezado": datos_imp["encabezado"],
            "modulos": datos_imp["modulos"],
            "estudiantes": est_copia
        }

    if id_archivo == "curso-peluquero-ep6-demo" or not google_client.is_connected():
        est_copia = []
        for est in _ESTUDIANTES_DEMO:
            e = dict(est)
            sol_info = obtener_estado_estudiante(id_archivo, e.get("documento", ""))
            e["solicitudCertificado"] = sol_info
            e["notasCongeladas"] = (sol_info.get("estado") == EstadoCertificado.APROBADO)
            est_copia.append(e)

        return {
            "encabezado": dict(_ENCABEZADO_DEMO),
            "modulos": [
                {"i": 0, "nombre": "Relaciones Laborales", "periodo": "1C", "hsReloj": 24, "hsCat": 36},
                {"i": 1, "nombre": "Piel y Anexos", "periodo": "1C", "hsReloj": 24, "hsCat": 36},
                {"i": 2, "nombre": "Gestión del Trabajo", "periodo": "1C", "hsReloj": 20, "hsCat": 30},
                {"i": 3, "nombre": "Peinado", "periodo": "1C", "hsReloj": 80, "hsCat": 120},
                {"i": 4, "nombre": "Corte", "periodo": "1C", "hsReloj": 85, "hsCat": 128},
                {"i": 5, "nombre": "Coloración", "periodo": "1C", "hsReloj": 107, "hsCat": 160}
            ],
            "estudiantes": est_copia
        }

    # 1. Leer encabezados principales (C2:Q5)
    # 2. Leer módulos (R7:Y8)
    # 3. Leer estudiantes (A9:AC48)
    rangos = [
        f"{RAC['HOJA']}!A1:Q5",
        f"{RAC['HOJA']}!R7:Y8",
        f"{RAC['HOJA']}!A9:AC48"
    ]
    batch_data = google_client.batch_get_values(id_archivo, rangos)

    # Procesar encabezados
    vals_enc = batch_data.get(f"{RAC['HOJA']}!A1:Q5", [])
    def get_cell(cell_ref: str) -> str:
        col_letter = re.sub(r"\d", "", cell_ref)
        row_num = int(re.sub(r"\D", "", cell_ref))
        col_idx = letter_to_col_num(col_letter) - 1
        row_idx = row_num - 1
        if row_idx < len(vals_enc) and col_idx < len(vals_enc[row_idx]):
            return texto(vals_enc[row_idx][col_idx])
        return ""

    encabezado = {}
    for clave, celda in RAC["ENCABEZADO"].items():
        encabezado[clave] = get_cell(celda)

    # Procesar módulos (R7:Y8)
    vals_mod = batch_data.get(f"{RAC['HOJA']}!R7:Y8", [])
    periodos = vals_mod[0] if len(vals_mod) > 0 else []
    nombres = vals_mod[1] if len(vals_mod) > 1 else []
    
    ancho_mod = RAC["COL"]["modN"] - RAC["COL"]["mod1"] + 1  # 8 módulos máx
    modulos = []
    for i in range(ancho_mod):
        nom = texto(nombres[i]) if i < len(nombres) else ""
        per = texto(periodos[i]) if i < len(periodos) else ""
        if nom:
            modulos.append({
                "i": i,
                "nombre": nom,
                "periodo": per
            })

    # Procesar estudiantes (A9:AC48)
    vals_est = batch_data.get(f"{RAC['HOJA']}!A9:AC48", [])
    estudiantes = []
    for r_idx, fila in enumerate(vals_est):
        fila_num = RAC["FILA_1"] + r_idx
        def col_v(c_idx: int) -> str:
            return texto(fila[c_idx - 1]) if (c_idx - 1) < len(fila) else ""

        ap = col_v(RAC["COL"]["apellido"])
        nom = col_v(RAC["COL"]["nombres"])
        if not ap and not nom:
            continue

        notas = []
        for m in modulos:
            col_nota = RAC["COL"]["mod1"] + m["i"]
            notas.append(col_v(col_nota))

        estudiantes.append({
            "fila": fila_num,
            "orden": col_v(RAC["COL"]["orden"]),
            "apellido": ap,
            "nombres": nom,
            "documento": col_v(RAC["COL"]["documento"]),
            "tipoDoc": col_v(RAC["COL"]["tipoDoc"]),
            "fechaNac": col_v(RAC["COL"]["fechaNac"]),
            "localidad": col_v(RAC["COL"]["localidad"]),
            "provincia": col_v(RAC["COL"]["provincia"]) or "Jujuy",
            "pais": col_v(RAC["COL"].get("nacionalidad", 5)) or "Argentina",
            "notas": notas,
            "notaFinal": col_v(RAC["COL"]["notaFinal"]),
            "fechaEgreso": col_v(RAC["COL"]["fechaEgreso"]),
            "folio": col_v(RAC["COL"]["folio"]),
            "situacion": col_v(RAC["COL"]["situacion"])
        })

    for est in estudiantes:
        sol_info = obtener_estado_estudiante(id_archivo, est.get("documento", ""))
        est["solicitudCertificado"] = sol_info
        est["notasCongeladas"] = (sol_info.get("estado") == EstadoCertificado.APROBADO)

    return {
        "encabezado": encabezado,
        "modulos": modulos,
        "estudiantes": estudiantes
    }

# ==================== GUARDAR NOTAS (RAC) ====================

def guardar_notas(id_curso: str, cambios: List[Dict[str, Any]], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Guarda las calificaciones de los módulos.
    cambios = [{"fila": 9, "modulo": 0, "valor": "8"}, ...]
    REGLA: Si el estudiante ya tiene certificado APROBADO por Títulos, sus notas están CONGELADAS.
    """
    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError("Curso no encontrado en el Panel.")
    exigir_carga(sesion_usr, curso)

    if not cambios:
        return {"guardados": 0}

    # Validar congelamiento de notas antes de procesar cambios
    datos_actuales = leer_curso(curso["id"])
    mapa_est_fila = {e["fila"]: e for e in datos_actuales.get("estudiantes", [])}
    for c in cambios:
        f = int(c.get("fila", 0))
        est_obj = mapa_est_fila.get(f)
        if est_obj and est_obj.get("notasCongeladas"):
            raise PermissionDeniedException(
                f"Las notas de {est_obj.get('apellido')}, {est_obj.get('nombres')} (DNI {est_obj.get('documento')}) "
                "están congeladas porque su certificado oficial ya fue APROBADO por el Departamento de Títulos."
            )

    if curso["id"] in _CURSOS_IMPORTADOS:
        est_lista = _CURSOS_IMPORTADOS[curso["id"]]["datosCurso"]["estudiantes"]
        for c in cambios:
            f = int(c.get("fila", 0))
            if c.get("campo") == "acreditaCon" or "acreditaCon" in c:
                val_acr = texto(c.get("acreditaCon") if "acreditaCon" in c else c.get("valor"))
                for est in est_lista:
                    if est["fila"] == f:
                        est["acreditaCon"] = val_acr
                        est["nivel"] = val_acr
                continue
            m = int(c.get("modulo", 0))
            v_norm = normalizar_nota(c.get("valor"))
            for est in est_lista:
                if est["fila"] == f and m < len(est["notas"]):
                    est["notas"][m] = str(v_norm)
                    nf, sit = _calcular_situacion_y_promedio(est["notas"])
                    est["promedioModulos"] = nf
                    nf_act = str(est.get("notaFinal", "")).strip().upper()
                    if sit.startswith("Aprobó") and nf_act == "AUS":
                        est["situacion"] = "Ausente examen final"
                    elif sit.startswith("Aprobó") and nf_act.isdigit() and int(nf_act) < 7:
                        est["situacion"] = "Desaprobó examen final"
                    else:
                        est["situacion"] = sit
        _guardar_cursos_disco()
        return {"guardados": len(cambios), "paquete": _CURSOS_IMPORTADOS.get(curso["id"])}

    if curso["id"] == "curso-peluquero-ep6-demo" or not google_client.is_connected():
        for c in cambios:
            f = int(c.get("fila", 0))
            if c.get("campo") == "acreditaCon" or "acreditaCon" in c:
                val_acr = texto(c.get("acreditaCon") if "acreditaCon" in c else c.get("valor"))
                for est in _ESTUDIANTES_DEMO:
                    if est["fila"] == f:
                        est["acreditaCon"] = val_acr
                        est["nivel"] = val_acr
                continue
            m = int(c.get("modulo", 0))
            v_norm = normalizar_nota(c.get("valor"))
            for est in _ESTUDIANTES_DEMO:
                if est["fila"] == f and m < len(est["notas"]):
                    est["notas"][m] = str(v_norm)
                    nf, sit = _calcular_situacion_y_promedio(est["notas"])
                    est["promedioModulos"] = nf
                    nf_act = str(est.get("notaFinal", "")).strip().upper()
                    if sit.startswith("Aprobó") and nf_act == "AUS":
                        est["situacion"] = "Ausente examen final"
                    elif sit.startswith("Aprobó") and nf_act.isdigit() and int(nf_act) < 7:
                        est["situacion"] = "Desaprobó examen final"
                    else:
                        est["situacion"] = sit
        _guardar_cursos_disco()
        return {"guardados": len(cambios), "paquete": _CURSOS_IMPORTADOS.get(curso["id"])}

    updates = []
    detalle = []
    for c in cambios:
        fila = int(c.get("fila", 0))
        mod_idx = int(c.get("modulo", 0))
        if not (RAC["FILA_1"] <= fila <= RAC["FILA_N"]):
            raise ValueError(f"Fila {fila} fuera de rango permitido ({RAC['FILA_1']}-{RAC['FILA_N']}).")
        if not (0 <= mod_idx <= (RAC["COL"]["modN"] - RAC["COL"]["mod1"])):
            raise ValueError(f"Módulo {mod_idx} fuera de rango.")

        val_norm = normalizar_nota(c.get("valor"))
        col_idx = RAC["COL"]["mod1"] + mod_idx
        col_letra = col_num_to_letter(col_idx)
        rango_celda = f"{RAC['HOJA']}!{col_letra}{fila}"

        updates.append({
            "range": rango_celda,
            "values": [[val_norm]]
        })
        detalle.append(f"f{fila} m{mod_idx + 1}={val_norm if val_norm != '' else 'vacío'}")

    google_client.batch_update_values(curso["id"], updates)
    registrar(sesion_usr, "Notas", f"{curso['oferta']} {curso['ciclo']}", " ".join(detalle))

    return {"guardados": len(updates)}

# ==================== GUARDAR ESTUDIANTE (RAC) ====================

def guardar_estudiante(id_curso: str, est_data: Dict[str, Any], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """Guarda o agrega un estudiante en la primera fila disponible del RAC."""
    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError("Curso no encontrado en el Panel.")
    exigir_carga(sesion_usr, curso)

    apellido = texto(est_data.get("apellido")).upper()
    nombres = texto(est_data.get("nombres"))
    if not apellido or not nombres:
        raise ValueError("El apellido y los nombres no pueden quedar vacíos.")
    documento_str = re.sub(r"\D", "", texto(est_data.get("documento"))) or texto(est_data.get("documento"))
    if not documento_str:
        raise ValueError("El número de documento (DNI) es obligatorio.")

    if curso["id"] in _CURSOS_IMPORTADOS:
        paq = _CURSOS_IMPORTADOS[curso["id"]]
        lista_est = paq["datosCurso"]["estudiantes"]
        cant_mods = len(paq["datosCurso"].get("modulos", [])) or 6
        nueva_fila = (max([e["fila"] for e in lista_est], default=8) + 1)
        nuevo_orden = str(len(lista_est) + 1)
        acredita_val = texto(est_data.get("acreditaCon") or est_data.get("nivel")) or "Primaria Completa"
        nuevo_est = {
            "fila": nueva_fila,
            "orden": nuevo_orden,
            "apellido": apellido,
            "nombres": nombres,
            "documento": documento_str,
            "tipoDoc": texto(est_data.get("tipoDoc")) or "DNI",
            "fechaNac": texto(est_data.get("fechaNac")),
            "localidad": texto(est_data.get("localidad")) or paq["datosCurso"]["encabezado"].get("localidad", "Jujuy"),
            "provincia": texto(est_data.get("provincia")) or "Jujuy",
            "pais": texto(est_data.get("pais")) or "Argentina",
            "acreditaCon": acredita_val,
            "nivel": acredita_val,
            "notas": [""] * cant_mods,
            "notaFinal": "",
            "fechaEgreso": "",
            "folio": texto(est_data.get("folio")) or nuevo_orden,
            "situacion": "En curso"
        }
        lista_est.append(nuevo_est)
        paq["datosCurso"]["encabezado"]["matriculados"] = str(len(lista_est))
        paq["actaCurso"]["estudiantes"].append({
            "filaActa": 12 + len(lista_est),
            "filaRac": nueva_fila,
            "orden": nuevo_orden,
            "permiso": nuevo_orden,
            "documento": documento_str,
            "nombre": f"{apellido}, {nombres}",
            "teorico": "",
            "practico": "",
            "definitiva": "",
            "definitivaLetras": ""
        })
        registrar(sesion_usr, "Alta Estudiante", f"{curso['oferta']} {curso['ciclo']}", f"{apellido}, {nombres} (DNI {documento_str})")
        _guardar_cursos_disco()
        return {"fila": nueva_fila, "estudiante": nuevo_est, "paquete": paq}

    if curso["id"] == "curso-peluquero-ep6-demo" or not google_client.is_connected():
        nueva_fila = (max([e["fila"] for e in _ESTUDIANTES_DEMO], default=8) + 1)
        nuevo_orden = str(len(_ESTUDIANTES_DEMO) + 1)
        acredita_val = texto(est_data.get("acreditaCon") or est_data.get("nivel")) or "Primaria Completa"
        nuevo_est = {
            "fila": nueva_fila,
            "orden": nuevo_orden,
            "apellido": apellido,
            "nombres": nombres,
            "documento": documento_str,
            "tipoDoc": texto(est_data.get("tipoDoc")) or "DNI",
            "fechaNac": texto(est_data.get("fechaNac")),
            "localidad": texto(est_data.get("localidad")) or "Jujuy",
            "provincia": texto(est_data.get("provincia")) or "Jujuy",
            "pais": texto(est_data.get("pais")) or "Argentina",
            "acreditaCon": acredita_val,
            "nivel": acredita_val,
            "notas": [""] * 6,
            "notaFinal": "",
            "fechaEgreso": "",
            "folio": texto(est_data.get("folio")) or nuevo_orden,
            "situacion": "En curso"
        }
        _ESTUDIANTES_DEMO.append(nuevo_est)
        _ACTA_DEMO_ESTUDIANTES.append({
            "filaActa": 12 + len(_ESTUDIANTES_DEMO),
            "filaRac": nueva_fila,
            "orden": nuevo_orden,
            "permiso": nuevo_orden,
            "documento": documento_str,
            "nombre": f"{apellido}, {nombres}",
            "teorico": "",
            "practico": "",
            "definitiva": "",
            "definitivaLetras": ""
        })
        registrar(sesion_usr, "Alta Estudiante", f"{curso['oferta']} {curso['ciclo']}", f"{apellido}, {nombres} (DNI {documento_str})")
        return {"fila": nueva_fila, "estudiante": nuevo_est}

    fila = int(est_data.get("fila") or 0)
    if not fila:
        apellidos_vals = google_client.get_values(
            curso["id"], f"{RAC['HOJA']}!B{RAC['FILA_1']}:B{RAC['FILA_N']}"
        )
        for idx in range(RAC["FILA_N"] - RAC["FILA_1"] + 1):
            val = apellidos_vals[idx][0] if idx < len(apellidos_vals) and len(apellidos_vals[idx]) > 0 else ""
            if not texto(val):
                fila = RAC["FILA_1"] + idx
                break
        if not fila:
            max_est = RAC["FILA_N"] - RAC["FILA_1"] + 1
            raise ValueError(f"El curso ya tiene {max_est} estudiantes, que es el máximo permitido en la planilla.")

    if not (RAC["FILA_1"] <= fila <= RAC["FILA_N"]):
        raise ValueError(f"Fila {fila} fuera de rango.")

    mapa = {
        "apellido": apellido, "nombres": nombres,
        "tipoDoc": est_data.get("tipoDoc"), "documento": est_data.get("documento"),
        "fechaNac": est_data.get("fechaNac"), "nacionalidad": est_data.get("nacionalidad"),
        "localidad": est_data.get("localidad"), "departamento": est_data.get("departamento"),
        "provincia": est_data.get("provincia"), "nivel": est_data.get("nivel"),
        "telUrgencia": est_data.get("telUrgencia"), "folio": est_data.get("folio"),
        "fechaEgreso": est_data.get("fechaEgreso")
    }

    updates = []
    for k, v in mapa.items():
        if v is not None and k in RAC["COL"]:
            col_idx = RAC["COL"][k]
            col_letra = col_num_to_letter(col_idx)
            updates.append({
                "range": f"{RAC['HOJA']}!{col_letra}{fila}",
                "values": [[texto(v)]]
            })

    google_client.batch_update_values(curso["id"], updates)
    registrar(
        sesion_usr, "Estudiante", f"{curso['oferta']} {curso['ciclo']}",
        f"{apellido}, {nombres} (fila {fila})"
    )

    return {"fila": fila}

# ==================== ACTA DE EXAMEN ====================

def leer_acta(id_curso: str, sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """Lee el acta de examen y sus notas."""
    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError("Curso no encontrado en el Panel.")
    exigir_lectura(sesion_usr, curso)

    puede_cargar_curso = bool(sesion_usr.get("puedeCargar") and str(curso.get("estado", "")).lower() != "cerrado")

    if curso["id"] in _CURSOS_IMPORTADOS:
        acta_imp = _CURSOS_IMPORTADOS[curso["id"]]["actaCurso"]
        return {
            "curso": curso,
            "puedeCargar": puede_cargar_curso,
            "mesa": acta_imp["mesa"],
            "estudiantes": acta_imp["estudiantes"]
        }

    if curso["id"] == "curso-peluquero-ep6-demo" or not google_client.is_connected():
        return {
            "curso": curso,
            "puedeCargar": puede_cargar_curso,
            "mesa": dict(_ACTA_DEMO_MESA),
            "estudiantes": [dict(x) for x in _ACTA_DEMO_ESTUDIANTES]
        }

    rangos = [
        f"{ACTA['HOJA']}!C5:G8",
        f"{ACTA['HOJA']}!A13:J52"
    ]
    batch_data = google_client.batch_get_values(curso["id"], rangos)
    
    # Mesa examinadora
    mesa_vals = batch_data.get(f"{ACTA['HOJA']}!C5:G8", [])
    def m_val(r_idx, c_idx):
        if r_idx < len(mesa_vals) and c_idx < len(mesa_vals[r_idx]):
            return texto(mesa_vals[r_idx][c_idx])
        return ""

    fecha_mesa = m_val(0, 0)
    presidente = m_val(2, 0)
    vocal1 = m_val(2, 4)
    vocal2 = m_val(3, 0)

    # Estudiantes del acta
    est_vals = batch_data.get(f"{ACTA['HOJA']}!A13:J52", [])
    filas = RAC["FILA_N"] - RAC["FILA_1"] + 1
    estudiantes = []
    for i in range(min(filas, len(est_vals))):
        fila = est_vals[i]
        def c_val(c_idx):
            return texto(fila[c_idx - 1]) if (c_idx - 1) < len(fila) else ""

        nombre = c_val(ACTA["COL"]["nombre"])
        if not nombre:
            continue

        estudiantes.append({
            "filaActa": ACTA["FILA_1"] + i,
            "filaRac": RAC["FILA_1"] + i,
            "orden": c_val(ACTA["COL"]["orden"]),
            "documento": c_val(ACTA["COL"]["documento"]),
            "nombre": nombre,
            "teorico": c_val(ACTA["COL"]["teorico"]),
            "practico": c_val(ACTA["COL"]["practico"]),
            "definitiva": c_val(ACTA["COL"]["definitiva"]),
            "definitivaLetras": c_val(ACTA["COL"]["definitivaLetras"])
        })

    puede_cargar = sesion_usr.get("puedeCargar") and str(curso.get("estado")).lower() != "cerrado"
    return {
        "curso": curso,
        "puedeCargar": puede_cargar,
        "mesa": {
            "fecha": fecha_mesa,
            "presidente": presidente,
            "vocal1": vocal1,
            "vocal2": vocal2
        },
        "estudiantes": estudiantes
    }

def guardar_acta(id_curso: str, mesa: Optional[Dict[str, Any]], cambios: List[Dict[str, Any]], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """Guarda mesa examinadora (docentes y fecha) y notas del examen (teórico / práctico)."""
    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError("Curso no encontrado en el Panel.")
    exigir_carga(sesion_usr, curso)

    letras_acta = {
        1: "UNO", 2: "DOS", 3: "TRES", 4: "CUATRO", 5: "CINCO",
        6: "SEIS", 7: "SIETE", 8: "OCHO", 9: "NUEVE", 10: "DIEZ"
    }

    if curso["id"] in _CURSOS_IMPORTADOS or curso["id"] == "curso-peluquero-ep6-demo" or not google_client.is_connected():
        if curso["id"] in _CURSOS_IMPORTADOS:
            acta_obj = _CURSOS_IMPORTADOS[curso["id"]]["actaCurso"]
            mesa_dest = acta_obj["mesa"]
            est_list = acta_obj["estudiantes"]
            enc_dest = _CURSOS_IMPORTADOS[curso["id"]]["datosCurso"]["encabezado"]
            rac_est_list = _CURSOS_IMPORTADOS[curso["id"]]["datosCurso"]["estudiantes"]
        else:
            mesa_dest = _ACTA_DEMO_MESA
            est_list = _ACTA_DEMO_ESTUDIANTES
            enc_dest = _ENCABEZADO_DEMO
            rac_est_list = _ESTUDIANTES_DEMO

        est_por_fila = {int(es.get("filaActa", 0)): es for es in est_list}
        for c in (cambios or []):
            fila_a = int(c.get("filaActa", 0))
            campo = c.get("campo")
            if campo not in ("teorico", "practico"):
                raise ValueError(f"Campo del acta no válido: '{campo}'.")
            val_norm = str(normalizar_nota(c.get("valor")))
            es = est_por_fila.get(fila_a)
            if es and val_norm != texto(es.get(campo, "")):
                doc_est = texto(es.get("documento"))
                if doc_est and esta_estudiante_congelado(curso["id"], doc_est):
                    raise PermissionDeniedException(
                        f"Las notas de {es.get('nombre') or doc_est} (DNI {doc_est}) "
                        "están congeladas porque su certificado oficial ya fue APROBADO por la Dirección de Títulos."
                    )

        if mesa:
            for k in ("fecha", "presidente", "vocal1", "vocal2"):
                if k in mesa:
                    mesa_dest[k] = texto(mesa[k])
            if enc_dest is not None:
                if "libro" in mesa:
                    enc_dest["libro"] = texto(mesa["libro"])
                if "folio" in mesa:
                    enc_dest["folio"] = texto(mesa["folio"])
                if "fecha" in mesa and texto(mesa["fecha"]):
                    enc_dest["fechaActa"] = texto(mesa["fecha"])

        for c in (cambios or []):
            fila_a = int(c.get("filaActa", 0))
            campo = c.get("campo")
            val_norm = str(normalizar_nota(c.get("valor")))
            for es in est_list:
                if int(es.get("filaActa", 0)) == fila_a:
                    if campo in ("teorico", "practico"):
                        es[campo] = val_norm
                        vt = texto(es.get("teorico", ""))
                        vp = texto(es.get("practico", ""))
                        if vt == "AUS" or vp == "AUS":
                            es["definitiva"] = "AUS"
                            es["definitivaLetras"] = "AUSENTE"
                        elif vt == "" or vp == "":
                            es["definitiva"] = ""
                            es["definitivaLetras"] = ""
                        else:
                            try:
                                nt = float(vt)
                                np = float(vp)
                                prom = int(round((nt + np) / 2.0))
                                es["definitiva"] = str(prom)
                                es["definitivaLetras"] = letras_acta.get(prom, str(prom))
                            except Exception:
                                es["definitiva"] = ""
                                es["definitivaLetras"] = ""
                    break

        # Sincronizar todo lo cargado en el Acta de Examen con el Registro Anual de Calificaciones (RAC)
        libro_acta_actual = enc_dest.get("libro", "1") if enc_dest else "1"
        folio_acta_actual = enc_dest.get("folio", "1") if enc_dest else "1"
        fecha_acta_actual = mesa_dest.get("fecha", "")
        for es_acta in est_list:
            doc_a = str(es_acta.get("documento", "")).strip()
            if doc_a and esta_estudiante_congelado(curso["id"], doc_a):
                continue
            fila_r = int(es_acta.get("filaRac", 0))
            def_val = str(es_acta.get("definitiva", "")).strip()
            for est_rac in rac_est_list:
                if (doc_a and str(est_rac.get("documento", "")).strip() == doc_a) or (fila_r and int(est_rac.get("fila", 0)) == fila_r):
                    est_rac["notaFinal"] = def_val
                    if def_val:
                        est_rac["libroActa"] = libro_acta_actual
                        est_rac["folio"] = folio_acta_actual or est_rac.get("folio", "1")
                        est_rac["fechaEgreso"] = fecha_acta_actual
                        if def_val == "AUS":
                            est_rac["situacion"] = "Ausente examen final"
                        elif def_val.isdigit():
                            if int(def_val) >= 7:
                                _, sit_mods = _calcular_situacion_y_promedio(est_rac.get("notas", []))
                                if sit_mods.startswith("Aprobó") or not est_rac.get("notas"):
                                    est_rac["situacion"] = "Aprobó todo"
                                else:
                                    est_rac["situacion"] = sit_mods
                            else:
                                est_rac["situacion"] = "Desaprobó examen final"
                    else:
                        est_rac["libroActa"] = ""
                        est_rac["fechaEgreso"] = ""
                        _, sit_mods = _calcular_situacion_y_promedio(est_rac.get("notas", []))
                        est_rac["situacion"] = sit_mods
                    break

        if curso["id"] in _CURSOS_IMPORTADOS:
            _guardar_cursos_disco()
        return {"guardados": len(cambios or []) + (1 if mesa else 0), "paquete": _CURSOS_IMPORTADOS.get(curso["id"])}

    acta_actual = leer_acta(curso["id"], sesion_usr)
    est_por_fila_gs = {int(es.get("filaActa", 0)): es for es in acta_actual.get("estudiantes", [])}
    for c in (cambios or []):
        fila_a = int(c.get("filaActa", 0))
        campo = c.get("campo")
        if campo not in ("teorico", "practico"):
            raise ValueError(f"Campo del acta no válido: '{campo}'.")
        val_norm = str(normalizar_nota(c.get("valor")))
        es = est_por_fila_gs.get(fila_a)
        if es and val_norm != texto(es.get(campo, "")):
            doc_est = texto(es.get("documento"))
            if doc_est and esta_estudiante_congelado(curso["id"], doc_est):
                raise PermissionDeniedException(
                    f"Las notas de {es.get('nombre') or doc_est} (DNI {doc_est}) "
                    "están congeladas porque su certificado oficial ya fue APROBADO por la Dirección de Títulos."
                )

    updates = []
    if mesa:
        if "fecha" in mesa:
            updates.append({"range": f"{ACTA['HOJA']}!{ACTA['FECHA']}", "values": [[texto(mesa['fecha'])]]})
        if "presidente" in mesa:
            updates.append({"range": f"{ACTA['HOJA']}!{ACTA['PRESIDENTE']}", "values": [[texto(mesa['presidente'])]]})
        if "vocal1" in mesa:
            updates.append({"range": f"{ACTA['HOJA']}!{ACTA['VOCAL1']}", "values": [[texto(mesa['vocal1'])]]})
        if "vocal2" in mesa:
            updates.append({"range": f"{ACTA['HOJA']}!{ACTA['VOCAL2']}", "values": [[texto(mesa['vocal2'])]]})

    n_notas = 0
    for c in (cambios or []):
        fila = int(c.get("filaActa", 0))
        max_fila = ACTA["FILA_1"] + (RAC["FILA_N"] - RAC["FILA_1"])
        if not (ACTA["FILA_1"] <= fila <= max_fila):
            raise ValueError("Fila del acta fuera de rango.")
        campo = c.get("campo")
        if campo == "teorico":
            col_idx = ACTA["COL"]["teorico"]
        elif campo == "practico":
            col_idx = ACTA["COL"]["practico"]
        else:
            raise ValueError(f"Campo del acta no válido: '{campo}'.")

        col_letra = col_num_to_letter(col_idx)
        val_norm = normalizar_nota(c.get("valor"))
        updates.append({
            "range": f"{ACTA['HOJA']}!{col_letra}{fila}",
            "values": [[val_norm]]
        })
        n_notas += 1

    if updates:
        google_client.batch_update_values(curso["id"], updates)

    registrar(sesion_usr, "Acta", f"{curso['oferta']} {curso['ciclo']}", f"{n_notas} nota(s) guardadas")
    return {"guardados": n_notas}

# ==================== CERTIFICADO ANALÍTICO ====================

def obtener_analitico(id_curso: str, documento: str, fecha_emision: Optional[str], certificado: Optional[str], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simula e interactúa con la pestaña Analítico para emitir el certificado
    manteniendo la fórmula de la planilla como única fuente de verdad.
    """
    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError("Curso no encontrado en el Panel.")
    exigir_lectura(sesion_usr, curso)

    sol_info = obtener_estado_estudiante(curso["id"], documento)
    es_aprobado = (sol_info.get("estado") == EstadoCertificado.APROBADO)
    es_borrador = not es_aprobado
    num_cert_final = sol_info.get("numeroCertificado") if es_aprobado else ""

    # Buscar datos del estudiante
    datos_curso = leer_curso(curso["id"])
    est_seleccionado = None
    for e in datos_curso.get("estudiantes", []):
        if str(e.get("documento")).strip() == str(documento).strip():
            est_seleccionado = e
            break

    situacion_est = est_seleccionado.get("situacion", "") if est_seleccionado else ""
    aprobo_todo = str(situacion_est).startswith("Aprobó")

    # Mapeo de notas a letras
    letras_map = {
        "1": "Uno", "2": "Dos", "3": "Tres", "4": "Cuatro", "5": "Cinco",
        "6": "Seis", "7": "Siete", "8": "Ocho", "9": "Nueve", "10": "Diez",
        "AUS": "Ausente"
    }

    # Trayecto curricular oficial de Peluquero (Res. 2114-E-2026) o dinámico para cursos importados
    enc_curso = datos_curso.get("encabezado", {})
    mods_curso = datos_curso.get("modulos", [])

    if curso["id"] == "curso-peluquero-ep6-demo" or not mods_curso:
        trayecto_base = [
            {"nro": 1, "modulo": "Relaciones Laborales y Orientación Profesional", "tipo": "Común", "periodo": "Cuatrimestre único", "hsReloj": 24, "hsCat": 36},
            {"nro": 2, "modulo": "Piel y anexos cutáneos", "tipo": "Común", "periodo": "Cuatrimestre único", "hsReloj": 24, "hsCat": 36},
            {"nro": 3, "modulo": "Gestión del proceso de trabajo en estética profesional", "tipo": "Común", "periodo": "Cuatrimestre único", "hsReloj": 20, "hsCat": 30},
            {"nro": 4, "modulo": "Peinado", "tipo": "Específico", "periodo": "Cuatrimestre único", "hsReloj": 80, "hsCat": 120},
            {"nro": 5, "modulo": "Corte", "tipo": "Específico", "periodo": "Cuatrimestre único", "hsReloj": 85, "hsCat": 128},
            {"nro": 6, "modulo": "Coloración y cambio de estructura del cabello", "tipo": "Específico", "periodo": "Cuatrimestre único", "hsReloj": 107, "hsCat": 160}
        ]
        carga_total = {"reloj": 340, "cat": 510}
    else:
        trayecto_base = []
        tot_reloj = 0
        tot_cat = 0
        for idx_m, m in enumerate(mods_curso):
            per_str = str(m.get("periodo", "1° Cuatrimestre")).strip()
            if per_str == "1C":
                per_str = "1° Cuatrimestre"
            elif per_str == "2C":
                per_str = "2° Cuatrimestre"
            elif per_str == "3C":
                per_str = "3° Cuatrimestre"
            tipo_str = m.get("tipo") or ("Común" if idx_m < 3 else "Específico")
            hs_r = int(m.get("hsReloj") or (32 if tipo_str == "Común" else 96))
            hs_c = int(m.get("hsCat") or round(hs_r * 1.5))
            tot_reloj += hs_r
            tot_cat += hs_c
            trayecto_base.append({
                "nro": idx_m + 1,
                "modulo": m.get("nombre", f"Módulo {idx_m + 1}"),
                "tipo": tipo_str,
                "periodo": per_str,
                "hsReloj": hs_r,
                "hsCat": hs_c
            })
        carga_total = {"reloj": tot_reloj, "cat": tot_cat}

    def _extraer_mes_anio(fecha_str: Any) -> str:
        s_f = texto(fecha_str)
        if not s_f:
            return ""
        m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s_f)
        if m_iso:
            return f"{m_iso.group(2)}/{m_iso.group(1)}"
        m_lat = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s_f)
        if m_lat:
            return f"{int(m_lat.group(2)):02d}/{m_lat.group(3)}"
        m_my = re.match(r"^(\d{1,2})/(\d{4})$", s_f)
        if m_my:
            return f"{int(m_my.group(1)):02d}/{m_my.group(2)}"
        return ""

    notas_est = est_seleccionado.get("notas", []) if est_seleccionado else []
    trayecto_final = []
    cohorte_mod = str(enc_curso.get("ciclo") or curso.get("ciclo") or "2026")
    mes_anio_1c = _extraer_mes_anio(enc_curso.get("fechaFin1C"))
    mes_anio_2c = _extraer_mes_anio(enc_curso.get("fechaFin2C"))
    mes_anio_egr = _extraer_mes_anio(est_seleccionado.get("fechaEgreso") if est_seleccionado else "")

    for idx, mod in enumerate(trayecto_base):
        val_nota = notas_est[idx] if idx < len(notas_est) else ""
        if val_nota == "" or val_nota is None:
            cond = "Pendiente"
            en_letra = ""
        elif val_nota == "AUS":
            cond = "Ausente"
            en_letra = "Ausente"
        else:
            try:
                n_num = int(float(val_nota))
                cond = "Aprobado" if n_num >= 7 else "Desaprobado"
                en_letra = letras_map.get(str(n_num), str(n_num))
            except Exception:
                cond = "Pendiente"
                en_letra = ""

        mes_anio_mod = ""
        if cond == "Aprobado":
            per_low = str(mod.get("periodo", "")).lower()
            if "2" in per_low or "3" in per_low:
                mes_anio_mod = mes_anio_2c or mes_anio_egr or f"12/{cohorte_mod}"
            else:
                mes_anio_mod = mes_anio_1c or mes_anio_egr or f"12/{cohorte_mod}"

        trayecto_final.append({
            **mod,
            "nota": val_nota,
            "enLetras": en_letra,
            "condicion": cond,
            "mesAnio": mes_anio_mod
        })

    # Formatear DNI con puntos (ej: 44.645.553)
    doc_digits = re.sub(r"\D", "", str(documento))
    if len(doc_digits) >= 7:
        dni_formateado = f"{int(doc_digits):,}".replace(",", ".")
    else:
        dni_formateado = str(documento)

    es_demo_ep6 = (curso["id"] == "curso-peluquero-ep6-demo")
    prov_est = (est_seleccionado.get("provincia") or "Jujuy").strip() if est_seleccionado else "Jujuy"
    pais_est = (est_seleccionado.get("pais") or "Argentina").strip() if est_seleccionado else "Argentina"
    lugar_nac_str = f"{prov_est} ({pais_est})".upper()

    prom_trayectoria, _ = _calcular_situacion_y_promedio(notas_est)
    prom_trayectoria_letras = letras_map.get(str(prom_trayectoria), "")
    nota_final_rac = str((est_seleccionado.get("notaFinal") if est_seleccionado else "") or "").strip()
    nota_final_letras = letras_map.get(nota_final_rac, nota_final_rac)
    fecha_egreso_rac = str((est_seleccionado.get("fechaEgreso") if est_seleccionado else "") or enc_curso.get("fechaActa") or "").strip()
    libro_rac = str((est_seleccionado.get("libroActa") if est_seleccionado else "") or enc_curso.get("libro") or "1").strip()
    folio_rac = str((est_seleccionado.get("folio") if est_seleccionado else "") or enc_curso.get("folio") or "1").strip()
    acredita_rac = str(((est_seleccionado.get("acreditaCon") or est_seleccionado.get("nivel")) if est_seleccionado else "") or "Primaria Completa").strip()

    documento_oficial = {
        "libro": libro_rac,
        "folio": folio_rac,
        "certNro": num_cert_final if not es_borrador else "",
        "establecimiento": "ESCUELA PROFESIONAL Nº 6" if es_demo_ep6 else str(enc_curso.get("establecimiento") or curso.get("institucion") or "ESCUELA PROFESIONAL").upper(),
        "cue": "3800612-00" if es_demo_ep6 else str(enc_curso.get("cue") or curso.get("cue") or "3800006"),
        "domicilio": "PTO ARGENTINO Nº 705- Bº MALVINAS ARG." if es_demo_ep6 else str(enc_curso.get("domicilio") or "S/D").upper(),
        "localidad": "PERICO" if es_demo_ep6 else str(enc_curso.get("localidad") or "JUJUY").upper(),
        "provincia": "JUJUY",
        "oferta": str(enc_curso.get("oferta") or curso.get("oferta") or "Peluquero").upper(),
        "familiaProfesional": str(enc_curso.get("familiaProfesional") or "—"),
        "cohorte": str(enc_curso.get("ciclo") or curso.get("ciclo") or "2026"),
        "normaJurisdiccional": str(enc_curso.get("normaAprobacion") or enc_curso.get("disenio") or "Res. N° 2114-E-2026"),
        "resolucionDisenio": str(enc_curso.get("resolucionDisenio") or enc_curso.get("disenio") or "—"),
        "validezNacional": str(enc_curso.get("validezNacional") or "—"),
        "fechaEmision": fecha_emision or "",
        "fechaEgreso": fecha_egreso_rac,
        "fechaFin1C": str(enc_curso.get("fechaFin1C") or ""),
        "fechaFin2C": str(enc_curso.get("fechaFin2C") or ""),
        "duracion": str(enc_curso.get("duracion") or ""),
        "docente": str(enc_curso.get("docente") or ""),
        "fechaAprobacion": sol_info.get("fechaAprobacion") or "",
        "estudianteNombre": f"{est_seleccionado.get('apellido', '')}, {est_seleccionado.get('nombres', '')}".strip() if est_seleccionado else "AMANTE, SERGIO DAVID",
        "lugarNac": lugar_nac_str,
        "fechaNac": est_seleccionado.get("fechaNac", "01/02/2002") if est_seleccionado else "01/02/2002",
        "tipoDoc": est_seleccionado.get("tipoDoc", "DNI") if est_seleccionado else "DNI",
        "dniFormateado": dni_formateado,
        "acreditaCon": acredita_rac,
        "promedioTrayectoria": prom_trayectoria,
        "promedioTrayectoriaLetras": prom_trayectoria_letras,
        "notaFinal": nota_final_rac,
        "notaFinalLetras": nota_final_letras,
        "trayecto": trayecto_final,
        "cargaHorariaTotal": carga_total,
        "esBorrador": es_borrador,
        "aprobo": aprobo_todo,
        "situacion": situacion_est,
        "mensajeEstado": "" if aprobo_todo else "Este estudiante todavía no aprobó: no se puede solicitar su certificado."
    }

    if curso["id"] == "curso-peluquero-ep6-demo" or curso["id"] in _CURSOS_IMPORTADOS or not google_client.is_connected():
        return {
            "documentoOficial": documento_oficial,
            "curso": curso,
            "esBorrador": es_borrador,
            "numeroCertificado": num_cert_final,
            "solicitudCertificado": sol_info
        }

    # 1. Leer valores previos para no sobreescribir permanentemente
    previo = google_client.batch_get_values(curso["id"], [
        f"{ANALITICO['HOJA']}!{ANALITICO['DNI']}",
        f"{ANALITICO['HOJA']}!{ANALITICO['FECHA']}",
        f"{ANALITICO['HOJA']}!{ANALITICO['CERTIFICADO']}"
    ])
    prev_dni = previo.get(f"{ANALITICO['HOJA']}!{ANALITICO['DNI']}", [[""]])[0][0]
    prev_fecha = previo.get(f"{ANALITICO['HOJA']}!{ANALITICO['FECHA']}", [[""]])[0][0]
    prev_cert = previo.get(f"{ANALITICO['HOJA']}!{ANALITICO['CERTIFICADO']}", [[""]])[0][0]

    # 2. Cargar los datos del estudiante solicitado
    updates = [
        {"range": f"{ANALITICO['HOJA']}!{ANALITICO['DNI']}", "values": [[documento]]}
    ]
    if fecha_emision:
        updates.append({"range": f"{ANALITICO['HOJA']}!{ANALITICO['FECHA']}", "values": [[fecha_emision]]})
    if certificado is not None:
        updates.append({"range": f"{ANALITICO['HOJA']}!{ANALITICO['CERTIFICADO']}", "values": [[certificado]]})
    google_client.batch_update_values(curso["id"], updates)

    # 3. Leer la cuadrícula renderizada (columnas A..I) y metadatos de celdas combinadas
    metadata = google_client.get_spreadsheet_metadata(curso["id"])
    celdas = google_client.get_values(curso["id"], f"{ANALITICO['HOJA']}!A1:I50")

    combinadas = []
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("title") == ANALITICO["HOJA"]:
            for m in sheet.get("merges", []):
                combinadas.append({
                    "f": m.get("startRowIndex", 0) + 1,
                    "c": m.get("startColumnIndex", 0) + 1,
                    "nf": m.get("endRowIndex", 0) - m.get("startRowIndex", 0),
                    "nc": m.get("endColumnIndex", 0) - m.get("startColumnIndex", 0)
                })
            break

    # 4. Restaurar valores previos
    restore = [
        {"range": f"{ANALITICO['HOJA']}!{ANALITICO['DNI']}", "values": [[prev_dni]]},
        {"range": f"{ANALITICO['HOJA']}!{ANALITICO['FECHA']}", "values": [[prev_fecha]]},
        {"range": f"{ANALITICO['HOJA']}!{ANALITICO['CERTIFICADO']}", "values": [[prev_cert]]}
    ]
    google_client.batch_update_values(curso["id"], restore)

    registrar(sesion_usr, "Analítico", f"{curso['oferta']} {curso['ciclo']}", f"doc {documento}")
    return {
        "celdas": celdas,
        "combinadas": combinadas,
        "documentoOficial": documento_oficial,
        "curso": curso,
        "esBorrador": es_borrador,
        "numeroCertificado": num_cert_final,
        "solicitudCertificado": sol_info
    }

# ==================== RESUMEN Y DASHBOARD DE ESTADÍSTICAS (DIRECCIÓN Y TÍTULOS) ====================

def _parse_fecha_dt(val: Any) -> Optional[datetime.date]:
    s = texto(val)
    if not s:
        return None
    s_date = s.split(" ")[0].strip()
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s_date)
    if m_iso:
        try:
            return datetime.date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        except Exception:
            return None
    m_lat = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s_date)
    if m_lat:
        try:
            return datetime.date(int(m_lat.group(3)), int(m_lat.group(2)), int(m_lat.group(1)))
        except Exception:
            return None
    return None


def obtener_estadisticas(sesion_usr: Dict[str, Any], filtros: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Calcula y devuelve las estadísticas completas para el Dashboard de Gestión
    (accesible tanto a Dirección DETP como a Dirección de Títulos).
    """
    es_directivo_escuela = (str(sesion_usr.get("rol", "")).strip().lower() == "directivo")
    if not (sesion_usr.get("verTodo") or sesion_usr.get("esTitulos") or sesion_usr.get("puedeVerDashboard") or es_directivo_escuela):
        raise PermissionDeniedException("Este dashboard es exclusivo para la Dirección DETP, la Dirección de Títulos y el Directivo de la Escuela.")

    filtros = filtros or {}
    f_escuela = texto(filtros.get("escuela")).lower()
    f_cue = normalizar_cue(filtros.get("cue"))
    f_desde = _parse_fecha_dt(filtros.get("desde"))
    f_hasta = _parse_fecha_dt(filtros.get("hasta"))
    f_estado = texto(filtros.get("estado")).lower() or "todos"

    def _mismo_cue_str(c1: Any, c2: Any) -> bool:
        a = normalizar_cue(c1)
        b = normalizar_cue(c2)
        if not a or not b:
            return False
        if a == b:
            return True
        if len(a) == 7 and b == a + "00":
            return True
        if len(b) == 7 and a == b + "00":
            return True
        return False

    cursos_todos = cursos_del_panel()
    if not (sesion_usr.get("verTodo") or sesion_usr.get("esTitulos")):
        cursos_todos = [c for c in cursos_todos if alcanza_cue(sesion_usr, c.get("cue"))]
    escuelas_disp_map: Dict[str, str] = {}
    cues_disp_set = set()
    for c in cursos_todos:
        inst_n = texto(c.get("institucion"))
        cue_n = texto(c.get("cue"))
        if inst_n:
            escuelas_disp_map[inst_n] = inst_n
        if cue_n:
            cues_disp_set.add(cue_n)

    por_institucion: Dict[str, Dict[str, Any]] = {}
    por_oferta: Dict[str, Dict[str, Any]] = {}
    por_familia: Dict[str, Dict[str, Any]] = {}
    por_turno: Dict[str, Dict[str, Any]] = {}
    niveles_base_orden = ["Primaria", "Secundaria", "Ciclo Básico", "Superior"]
    por_acreditacion: Dict[str, Dict[str, Any]] = {
        niv: {
            "acreditacion": niv,
            "matriculados": 0,
            "aprobados": 0,
            "desaprobados": 0,
            "ausentes": 0,
            "certificadosAprobados": 0,
            "certificadosObservados": 0
        }
        for niv in niveles_base_orden
    }
    obs_detalle: List[Dict[str, Any]] = []
    obs_por_escuela_map: Dict[str, Dict[str, Any]] = {}

    def _categorizar_acreditacion(val_acr: Any) -> str:
        s_a = texto(val_acr).lower()
        if "secundar" in s_a:
            return "Secundaria"
        if "ciclo" in s_a or "cb" in s_a or "básico" in s_a or "basico" in s_a:
            return "Ciclo Básico"
        if "superior" in s_a or "terciar" in s_a or "universitar" in s_a:
            return "Superior"
        if "primar" in s_a or not s_a:
            return "Primaria"
        return texto(val_acr)

    tot_cursos = 0
    tot_matriculados = 0
    tot_aprobados = 0
    tot_desaprobados = 0
    tot_ausentes = 0
    tot_cert_aprobados = 0
    tot_cert_pendientes = 0
    tot_cert_observados = 0
    tot_consultas_qr = 0
    tot_cert_consultados_qr = 0
    qr_detalle: List[Dict[str, Any]] = []

    for c in cursos_todos:
        try:
            d = leer_curso(c["id"])
        except Exception:
            continue

        enc = d.get("encabezado", {})
        inst_c = texto(enc.get("establecimiento") or c.get("institucion") or "Sin Institución")
        cue_c = texto(enc.get("cue") or c.get("cue") or "")
        oferta_c = texto(enc.get("oferta") or c.get("oferta") or "Sin Oferta")
        familia_c = texto(enc.get("familiaProfesional") or "Sin Familia")
        if familia_c in ("", "—", "-"):
            familia_c = "Sin especificar"
        turno_c = texto(enc.get("turno") or c.get("turno") or "Sin especificar")
        fecha_curso_dt = _parse_fecha_dt(enc.get("fechaActa")) or _parse_fecha_dt(enc.get("fechaFin2C")) or _parse_fecha_dt(enc.get("fechaFin1C"))

        if f_escuela and f_escuela not in inst_c.lower():
            continue
        if f_cue and not _mismo_cue_str(cue_c, f_cue):
            continue

        estudiantes_filtrados = []
        for e in d.get("estudiantes", []):
            sol = e.get("solicitudCertificado") or {}
            st_cert = texto(sol.get("estado") or EstadoCertificado.NO_SOLICITADO)
            sit = texto(e.get("situacion"))
            nf_str = texto(e.get("notaFinal")).upper()

            nf_ok = True
            if nf_str:
                if nf_str == "AUS":
                    nf_ok = False
                else:
                    try:
                        nf_ok = float(nf_str.replace(",", ".")) >= 7
                    except Exception:
                        nf_ok = False

            es_aprobado = sit.startswith("Aprobó") and nf_ok
            es_ausente = (nf_str == "AUS") or ("ausente" in sit.lower())

            # Filtro por fecha (usa fechaEgreso, fechaAprobacion, fechaSolicitud o fechaActa)
            if f_desde or f_hasta:
                dt_est = (
                    _parse_fecha_dt(e.get("fechaEgreso"))
                    or _parse_fecha_dt(sol.get("fechaAprobacion"))
                    or _parse_fecha_dt(sol.get("fechaSolicitud"))
                    or fecha_curso_dt
                )
                if dt_est is None:
                    ciclo_str = texto(enc.get("ciclo") or c.get("ciclo"))
                    if ciclo_str.isdigit():
                        dt_est = datetime.date(int(ciclo_str), 12, 31)
                if dt_est is not None:
                    if f_desde and dt_est < f_desde:
                        continue
                    if f_hasta and dt_est > f_hasta:
                        continue

            # Filtro por estado académico / certificación
            if f_estado == "aprobados" and not es_aprobado:
                continue
            elif f_estado in ("desaprobados", "desaprobados_en_curso") and es_aprobado:
                continue
            elif f_estado in ("cert_aprobados", "certificados_aprobados") and st_cert != EstadoCertificado.APROBADO:
                continue
            elif f_estado in ("observados", "certificados_observados") and st_cert != EstadoCertificado.OBSERVADO:
                continue

            estudiantes_filtrados.append((e, es_aprobado, es_ausente, st_cert))

        if not estudiantes_filtrados:
            if f_estado != "todos":
                continue
            if f_desde or f_hasta:
                if len(d.get("estudiantes", [])) > 0:
                    continue
                if fecha_curso_dt is None:
                    continue
                if f_desde and fecha_curso_dt < f_desde:
                    continue
                if f_hasta and fecha_curso_dt > f_hasta:
                    continue

        tot_cursos += 1
        k_inst = f"{cue_c}||{inst_c}"
        if k_inst not in por_institucion:
            por_institucion[k_inst] = {
                "cue": cue_c,
                "institucion": inst_c,
                "cursos": 0,
                "estudiantes": 0,
                "matriculados": 0,
                "aprobados": 0,
                "desaprobados": 0,
                "ausentes": 0,
                "certificadosAprobados": 0,
                "certificadosPendientes": 0,
                "certificadosObservados": 0,
                "consultasQr": 0
            }
        por_institucion[k_inst]["cursos"] += 1

        for grp_map, grp_key, grp_label in (
            (por_oferta, oferta_c, "oferta"),
            (por_familia, familia_c, "familiaProfesional"),
            (por_turno, turno_c, "turno")
        ):
            if grp_key not in grp_map:
                grp_map[grp_key] = {
                    grp_label: grp_key,
                    "cursos": 0,
                    "matriculados": 0,
                    "aprobados": 0,
                    "desaprobados": 0,
                    "ausentes": 0,
                    "certificadosAprobados": 0,
                    "certificadosObservados": 0
                }
            grp_map[grp_key]["cursos"] += 1

        for e, es_aprobado, es_ausente, st_cert in estudiantes_filtrados:
            sol_e = e.get("solicitudCertificado") or {}
            cant_qr_est = int(sol_e.get("consultasQr") or 0)
            tot_matriculados += 1
            if es_aprobado:
                tot_aprobados += 1
            else:
                tot_desaprobados += 1
            if es_ausente:
                tot_ausentes += 1
            if cant_qr_est > 0:
                tot_consultas_qr += cant_qr_est
                tot_cert_consultados_qr += 1
                qr_detalle.append({
                    "cue": cue_c,
                    "institucion": inst_c,
                    "oferta": oferta_c,
                    "ciclo": texto(enc.get("ciclo") or c.get("ciclo")),
                    "documento": texto(e.get("documento")),
                    "estudiante": f"{texto(e.get('apellido')).upper()}, {texto(e.get('nombres'))}".strip(", "),
                    "numeroCertificado": texto(sol_e.get("numeroCertificado")),
                    "consultasQr": cant_qr_est,
                    "ultimaConsultaQr": texto(sol_e.get("ultimaConsultaQr"))
                })
            if st_cert == EstadoCertificado.APROBADO:
                tot_cert_aprobados += 1
            elif st_cert == EstadoCertificado.PENDIENTE:
                tot_cert_pendientes += 1
            elif st_cert == EstadoCertificado.OBSERVADO:
                tot_cert_observados += 1
                obs_detalle.append({
                    "id": sol_e.get("idSolicitud") or "",
                    "idCurso": c["id"],
                    "cue": cue_c,
                    "institucion": inst_c,
                    "oferta": oferta_c,
                    "ciclo": texto(enc.get("ciclo") or c.get("ciclo")),
                    "documento": texto(e.get("documento")),
                    "estudiante": f"{texto(e.get('apellido')).upper()}, {texto(e.get('nombres'))}".strip(", "),
                    "fechaSolicitud": texto(sol_e.get("fechaSolicitud")),
                    "motivoObservacion": texto(sol_e.get("motivoObservacion")),
                    "observadoPor": texto(sol_e.get("observadoPor") or sol_e.get("observadoEmail") or "Dirección de Títulos"),
                    "observadoEmail": texto(sol_e.get("observadoEmail")),
                    "fechaObservacion": texto(sol_e.get("fechaObservacion"))
                })
                if k_inst not in obs_por_escuela_map:
                    obs_por_escuela_map[k_inst] = {"cue": cue_c, "institucion": inst_c, "cantidad": 0}
                obs_por_escuela_map[k_inst]["cantidad"] += 1

            row_inst = por_institucion[k_inst]
            row_inst["estudiantes"] += 1
            row_inst["matriculados"] += 1
            if es_aprobado:
                row_inst["aprobados"] += 1
            else:
                row_inst["desaprobados"] += 1
            if es_ausente:
                row_inst["ausentes"] += 1
            if st_cert == EstadoCertificado.APROBADO:
                row_inst["certificadosAprobados"] += 1
            elif st_cert == EstadoCertificado.PENDIENTE:
                row_inst["certificadosPendientes"] += 1
            elif st_cert == EstadoCertificado.OBSERVADO:
                row_inst["certificadosObservados"] += 1
            row_inst["consultasQr"] = int(row_inst.get("consultasQr") or 0) + cant_qr_est

            for grp_map, grp_key in ((por_oferta, oferta_c), (por_familia, familia_c), (por_turno, turno_c)):
                g = grp_map[grp_key]
                g["matriculados"] += 1
                if es_aprobado:
                    g["aprobados"] += 1
                else:
                    g["desaprobados"] += 1
                if es_ausente:
                    g["ausentes"] += 1
                if st_cert == EstadoCertificado.APROBADO:
                    g["certificadosAprobados"] += 1
                elif st_cert == EstadoCertificado.OBSERVADO:
                    g["certificadosObservados"] += 1

            raw_acr = e.get("acreditaCon") or e.get("nivel") or enc.get("acreditaCon") or enc.get("referencialIngreso") or "Primaria Completa"
            cat_acr = _categorizar_acreditacion(raw_acr)
            if cat_acr not in por_acreditacion:
                por_acreditacion[cat_acr] = {
                    "acreditacion": cat_acr,
                    "matriculados": 0,
                    "aprobados": 0,
                    "desaprobados": 0,
                    "ausentes": 0,
                    "certificadosAprobados": 0,
                    "certificadosObservados": 0
                }
            g_acr = por_acreditacion[cat_acr]
            g_acr["matriculados"] += 1
            if es_aprobado:
                g_acr["aprobados"] += 1
            else:
                g_acr["desaprobados"] += 1
            if es_ausente:
                g_acr["ausentes"] += 1
            if st_cert == EstadoCertificado.APROBADO:
                g_acr["certificadosAprobados"] += 1
            elif st_cert == EstadoCertificado.OBSERVADO:
                g_acr["certificadosObservados"] += 1

    def _enriquecer_pct(lista_items: List[Dict[str, Any]], sort_key: str) -> List[Dict[str, Any]]:
        for item in lista_items:
            mat = item.get("matriculados", 0)
            apr = item.get("aprobados", 0)
            cert_a = item.get("certificadosAprobados", 0)
            item["pctAprobacion"] = round((apr * 100.0) / mat, 1) if mat > 0 else 0.0
            item["tasaTitulacion"] = round((cert_a * 100.0) / apr, 1) if apr > 0 else 0.0
        lista_items.sort(key=lambda x: str(x.get(sort_key, "")))
        return lista_items

    obs_detalle.sort(key=lambda x: x.get("fechaSolicitud", ""), reverse=True)

    pct_aprobacion = round((tot_aprobados * 100.0) / tot_matriculados, 1) if tot_matriculados > 0 else 0.0
    pct_desaprobacion = round((tot_desaprobados * 100.0) / tot_matriculados, 1) if tot_matriculados > 0 else 0.0
    tasa_titulacion = round((tot_cert_aprobados * 100.0) / tot_aprobados, 1) if tot_aprobados > 0 else 0.0

    lista_acreditacion = []
    for k_acr in niveles_base_orden + [k for k in por_acreditacion.keys() if k not in niveles_base_orden]:
        it_a = dict(por_acreditacion[k_acr])
        mat_a = it_a.get("matriculados", 0)
        apr_a = it_a.get("aprobados", 0)
        cert_a = it_a.get("certificadosAprobados", 0)
        it_a["pctAprobacion"] = round((apr_a * 100.0) / mat_a, 1) if mat_a > 0 else 0.0
        it_a["tasaTitulacion"] = round((cert_a * 100.0) / apr_a, 1) if apr_a > 0 else 0.0
        lista_acreditacion.append(it_a)

    return {
        "kpis": {
            "totalCursos": tot_cursos,
            "totalMatriculados": tot_matriculados,
            "totalAprobados": tot_aprobados,
            "pctAprobacion": pct_aprobacion,
            "totalDesaprobados": tot_desaprobados,
            "pctDesaprobacion": pct_desaprobacion,
            "totalAusentes": tot_ausentes,
            "totalCertificadosAprobados": tot_cert_aprobados,
            "tasaTitulacion": tasa_titulacion,
            "totalPendientesTitulos": tot_cert_pendientes,
            "totalObservados": tot_cert_observados,
            "totalConsultasQr": tot_consultas_qr,
            "certificadosConsultadosQr": tot_cert_consultados_qr
        },
        "porEscuela": _enriquecer_pct(list(por_institucion.values()), "institucion"),
        "porAcreditacion": lista_acreditacion,
        "porOferta": _enriquecer_pct(list(por_oferta.values()), "oferta"),
        "porFamilia": _enriquecer_pct(list(por_familia.values()), "familiaProfesional"),
        "porTurno": _enriquecer_pct(list(por_turno.values()), "turno"),
        "observacionesPorEscuela": sorted(list(obs_por_escuela_map.values()), key=lambda x: x["institucion"]),
        "observacionesDetalle": obs_detalle,
        "consultasQrDetalle": sorted(qr_detalle, key=lambda x: x.get("consultasQr", 0), reverse=True),
        "escuelasDisponibles": sorted(list(escuelas_disp_map.keys())),
        "cuesDisponibles": sorted(list(cues_disp_set))
    }


def obtener_resumen(sesion_usr: Dict[str, Any], filtros: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Calcula y devuelve el resumen institucional para Dirección DETP y Dirección de Títulos."""
    return obtener_estadisticas(sesion_usr, filtros=filtros)["porEscuela"]

# ==================== IMPORTADOR DE VIEJO EXCEL (.XLSM / .XLSX) ====================

def importar_excel_en_sistema(contenido: bytes, nombre_archivo: str, sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un archivo Excel (.xlsm o .xlsx), extrae la nómina de estudiantes,
    calificaciones y acta de examen, y lo registra inmediatamente en el sistema.
    """
    if not sesion_usr.get("puedeCargar"):
        raise PermissionDeniedException(
            f"Tu rol ({sesion_usr.get('rol')}) es de consulta: no puedes importar cursos."
        )
    paquete = procesar_archivo_excel(contenido, nombre_archivo)
    resumen = paquete["resumenCurso"]
    enc_imp = paquete["datosCurso"]["encabezado"]

    # Para usuarios de escuela (no verTodo), validar CUE o vincular al CUE propio si falta
    if not sesion_usr.get("verTodo"):
        cue_excel = normalizar_cue(resumen.get("cue") or enc_imp.get("cue"))
        if not cue_excel:
            cues_usr = sesion_usr.get("cues") or []
            if not cues_usr:
                raise PermissionDeniedException("No tienes un CUE asignado para importar cursos.")
            resumen["cue"] = cues_usr[0]
            enc_imp["cue"] = cues_usr[0]
        elif not alcanza_cue(sesion_usr, cue_excel):
            raise PermissionDeniedException(
                f"El archivo Excel pertenece a otra institución (CUE {cue_excel}) y no tienes permiso para importarlo."
            )

    inst_info = _buscar_institucion_por_cue(resumen.get("cue"))
    if inst_info:
        if not enc_imp.get("establecimiento") or enc_imp.get("establecimiento") in ("Escuela Profesional", "Escuela Profesional Importada"):
            enc_imp["establecimiento"] = inst_info.get("nombre") or enc_imp.get("establecimiento")
            resumen["institucion"] = enc_imp["establecimiento"]
        if not enc_imp.get("localidad") or enc_imp.get("localidad") == "Jujuy":
            enc_imp["localidad"] = inst_info.get("localidad") or enc_imp.get("localidad")

    id_curso = resumen["id"]
    while id_curso in _CURSOS_IMPORTADOS:
        id_curso = _generar_id_curso_excel()
    resumen["id"] = id_curso
    _CURSOS_IMPORTADOS[id_curso] = paquete
    _guardar_cursos_disco()
    asegurar_usuarios_escuela(resumen.get("cue", ""), resumen.get("institucion", ""))

    registrar(
        sesion_usr,
        "Importación Excel",
        f"{resumen['oferta']} ({resumen['cue']})",
        f"Archivo '{nombre_archivo}' importado con {len(paquete['datosCurso']['estudiantes'])} estudiantes"
    )
    return {
        "curso": resumen,
        "paquete": paquete,
        "cantidadEstudiantes": len(paquete["datosCurso"]["estudiantes"]),
        "cantidadModulos": len(paquete["datosCurso"]["modulos"])
    }

def crear_curso_manual(datos: Dict[str, Any], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """Registra un nuevo curso en el sistema listo para que el Administrativo cargue alumnos."""
    if not sesion_usr.get("puedeCargar"):
        raise PermissionDeniedException(
            f"Tu rol ({sesion_usr.get('rol')}) es de consulta: no puedes crear cursos."
        )
    id_solicitado = texto(datos.get("id"))
    if id_solicitado and id_solicitado not in _CURSOS_IMPORTADOS:
        id_curso = id_solicitado
    else:
        id_curso = _generar_id_curso_manual()
    cue_raw = texto(datos.get("cue"))
    if not sesion_usr.get("verTodo"):
        if not normalizar_cue(cue_raw):
            cues_usr = sesion_usr.get("cues") or []
            if not cues_usr:
                raise PermissionDeniedException("No tienes un CUE asignado para crear cursos.")
            cue = cues_usr[0]
        elif not alcanza_cue(sesion_usr, cue_raw):
            raise PermissionDeniedException("No tienes permiso para crear cursos en otra institución (CUE).")
        else:
            cue = cue_raw
    else:
        cue = cue_raw or (sesion_usr["cues"][0] if sesion_usr.get("cues") else "3800006")
    inst_info = _buscar_institucion_por_cue(cue)
    institucion = texto(datos.get("institucion")) or (inst_info.get("nombre") if inst_info else "") or "Escuela Profesional"
    localidad = texto(datos.get("localidad")) or (inst_info.get("localidad") if inst_info else "") or "San Salvador de Jujuy"
    domicilio = texto(datos.get("domicilio")) or (inst_info.get("domicilio") if inst_info else "") or "S/D"
    oferta = texto(datos.get("oferta")) or "Oferta Formativa"
    ciclo = texto(datos.get("ciclo")) or str(datetime.datetime.now().year)
    turno_raw = texto(datos.get("turno")) or "Vespertino"
    turno = "Vespertino" if turno_raw.lower() in ("noche", "nocturno", "vespertino") else turno_raw
    division = texto(datos.get("division")) or '1º "U"'
    duracion = texto(datos.get("duracion")) or "2 Cuatrimestres"
    docente = texto(datos.get("docente")) or "—"
    fecha_fin_1c = texto(datos.get("fechaFin1C"))
    fecha_fin_2c = texto(datos.get("fechaFin2C"))

    resumen = {
        "cue": cue,
        "institucion": institucion,
        "oferta": oferta,
        "ciclo": ciclo,
        "turno": turno,
        "division": division,
        "id": id_curso,
        "estado": "Abierto",
        "fechaFin1C": fecha_fin_1c,
        "fechaFin2C": fecha_fin_2c
    }
    modulos = [
        {"i": 0, "nombre": "Relaciones Laborales y Orientación Profesional", "periodo": "1° Cuatrimestre", "periodoCorto": "1°C", "cuatrimestre": 1, "tipo": "Común"},
        {"i": 1, "nombre": "Seguridad e Higiene", "periodo": "1° Cuatrimestre", "periodoCorto": "1°C", "cuatrimestre": 1, "tipo": "Común"},
        {"i": 2, "nombre": "Gestión del Proceso de Trabajo", "periodo": "1° Cuatrimestre", "periodoCorto": "1°C", "cuatrimestre": 1, "tipo": "Común"},
        {"i": 3, "nombre": "Módulo Específico I", "periodo": "1° Cuatrimestre", "periodoCorto": "1°C", "cuatrimestre": 1, "tipo": "Específico"},
        {"i": 4, "nombre": "Módulo Específico II", "periodo": "2° Cuatrimestre", "periodoCorto": "2°C", "cuatrimestre": 2, "tipo": "Específico"},
        {"i": 5, "nombre": "Práctica Profesionalizante", "periodo": "2° Cuatrimestre", "periodoCorto": "2°C", "cuatrimestre": 2, "tipo": "Específico"},
    ]
    _CURSOS_IMPORTADOS[id_curso] = {
        "resumenCurso": resumen,
        "datosCurso": {
            "encabezado": {
                "establecimiento": institucion,
                "localidad": localidad,
                "cue": cue,
                "domicilio": domicilio,
                "oferta": oferta,
                "familiaProfesional": texto(datos.get("familiaProfesional")) or "—",
                "ciclo": ciclo,
                "libro": "1",
                "folio": "1",
                "turno": turno,
                "matriculados": "0",
                "cursoAnio": texto(datos.get("cursoAnio")) or "1°",
                "divisionLetra": texto(datos.get("divisionLetra")) or '"U"',
                "division": division,
                "duracion": duracion,
                "docente": docente,
                "fechaFin1C": fecha_fin_1c,
                "fechaFin2C": fecha_fin_2c,
                "disenio": texto(datos.get("resolucionDisenio")) or texto(datos.get("disenio")) or "661-E/2022",
                "hsCatTotal": texto(datos.get("hsCatTotal")) or "510",
                "nivelCurso": texto(datos.get("nivelCurso")) or "II",
                "certificacion": texto(datos.get("certificacion")) or "Diseño Curricular Jurisdiccional",
                "normaAprobacion": texto(datos.get("normaAprobacion")) or "4006-E/2023",
                "resolucionDisenio": texto(datos.get("resolucionDisenio")) or texto(datos.get("disenio")) or "661-E/2022",
                "validezNacional": texto(datos.get("validezNacional")) or "530/23",
                "disposicion": texto(datos.get("disposicion")) or "-",
                "referencialIngreso": texto(datos.get("referencialIngreso")) or "Primaria Completa",
                "acreditaCon": texto(datos.get("acreditaCon")) or "Primaria Completa"
            },
            "modulos": modulos,
            "estudiantes": []
        },
        "actaCurso": {
            "mesa": {
                "fecha": datetime.datetime.now().strftime("%d/%m/%Y"),
                "presidente": docente if docente and docente != "—" else "Presidente/a de Mesa",
                "vocal1": "Vocal 1°",
                "vocal2": "Vocal 2°"
            },
            "estudiantes": []
        }
    }
    _guardar_cursos_disco()
    registrar(sesion_usr, "Nuevo Curso", f"{oferta} ({cue})", f"Turno {turno}")
    return resumen


def actualizar_encabezado_curso(id_curso: str, datos_enc: Dict[str, Any], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """Actualiza metadatos del encabezado del curso (fechaFin1C, fechaFin2C, domicilio, duracion, docente, etc.)."""
    curso = buscar_curso(id_curso)
    if not curso:
        raise ValueError("Curso no encontrado en el Panel.")
    exigir_carga(sesion_usr, curso)

    campos_permitidos = (
        "establecimiento", "domicilio", "localidad", "oferta", "duracion",
        "division", "normaAprobacion", "resolucionDisenio", "validezNacional",
        "disposicion", "docente", "turno", "ciclo", "fechaFin1C", "fechaFin2C",
        "libro", "folio", "hsCatTotal", "nivelCurso", "certificacion", "familiaProfesional"
    )

    if curso["id"] in _CURSOS_IMPORTADOS:
        paq = _CURSOS_IMPORTADOS[curso["id"]]
        enc_dest = paq["datosCurso"]["encabezado"]
        res_dest = paq["resumenCurso"]
        for k in campos_permitidos:
            if k in datos_enc and datos_enc[k] is not None:
                val = texto(datos_enc[k])
                enc_dest[k] = val
                if k in ("oferta", "ciclo", "turno", "division", "fechaFin1C", "fechaFin2C"):
                    res_dest[k] = val
                elif k == "establecimiento":
                    res_dest["institucion"] = val
        _guardar_cursos_disco()
        return {"encabezado": dict(enc_dest), "paquete": paq}

    if curso["id"] == "curso-peluquero-ep6-demo":
        for k in campos_permitidos:
            if k in datos_enc and datos_enc[k] is not None:
                _ENCABEZADO_DEMO[k] = texto(datos_enc[k])
        return {"encabezado": dict(_ENCABEZADO_DEMO)}

    raise ValueError("La actualización directa de encabezado solo está disponible para cursos locales o importados.")


def obtener_nomina_egresados(
    cue: Optional[str] = None,
    id_curso: Optional[str] = None,
    ciclo: Optional[str] = None,
    filtro: str = "todos",
    sesion_usr: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Construye la Planilla por Escuela ('NOMINA DE EGRESADOS Ciclo Lectivo ...')
    con encabezado institucional y filas filtradas según estado académico / Títulos.
    """
    cue_norm = normalizar_cue(cue)
    ciclo_norm = texto(ciclo)
    filtro_norm = texto(filtro).lower() or "todos"
    if filtro_norm not in ("con_certificados", "aprobados", "pendientes", "todos"):
        filtro_norm = "todos"

    if sesion_usr and not sesion_usr.get("verTodo"):
        if cue_norm and not alcanza_cue(sesion_usr, cue_norm):
            raise PermissionDeniedException("No tienes acceso a la nómina de otra institución.")

    todos_cursos = cursos_del_panel()
    if sesion_usr and not sesion_usr.get("verTodo"):
        todos_cursos = [c for c in todos_cursos if alcanza_cue(sesion_usr, c.get("cue"))]

    def _mismo_cue(c1: Any, c2: Any) -> bool:
        a = normalizar_cue(c1)
        b = normalizar_cue(c2)
        if not a or not b:
            return False
        if a == b:
            return True
        if len(a) == 7 and b == a + "00":
            return True
        if len(b) == 7 and a == b + "00":
            return True
        return False

    seleccionados: List[Dict[str, Any]] = []
    if id_curso:
        c_match = next((c for c in todos_cursos if c.get("id") == id_curso), None)
        if not c_match:
            raise ValueError(f"Curso '{id_curso}' no encontrado o sin acceso.")
        seleccionados = [c_match]
    else:
        for c in todos_cursos:
            if cue_norm and not _mismo_cue(c.get("cue"), cue_norm):
                continue
            if ciclo_norm and texto(c.get("ciclo")) != ciclo_norm:
                continue
            seleccionados.append(c)
        if not seleccionados and not cue_norm and not ciclo_norm and todos_cursos:
            seleccionados = [todos_cursos[0]]

    encabezado_nomina = {
        "establecimiento": "",
        "domicilio": "",
        "localidad": "",
        "cue": cue_norm or "",
        "oferta": "",
        "duracion": "",
        "division": "",
        "normaAprobacion": "",
        "resolucionDisenio": "",
        "docente": "",
        "turno": "",
        "ciclo": ciclo_norm or str(datetime.datetime.now().year)
    }

    todas_filas: List[Dict[str, Any]] = []
    totales = {"todos": 0, "aprobados": 0, "con_certificados": 0, "pendientes": 0}

    for idx_c, c in enumerate(seleccionados):
        datos_c = leer_curso(c["id"])
        enc_c = datos_c.get("encabezado", {})
        inst_ref = _buscar_institucion_por_cue(enc_c.get("cue") or c.get("cue"))
        docente_c = texto(enc_c.get("docente"))
        if not docente_c:
            try:
                if c["id"] in _CURSOS_IMPORTADOS:
                    pres = _CURSOS_IMPORTADOS[c["id"]]["actaCurso"]["mesa"].get("presidente", "")
                    if pres and pres != "Presidente/a de Mesa":
                        docente_c = pres
                elif c["id"] == "curso-peluquero-ep6-demo":
                    docente_c = _ACTA_DEMO_MESA.get("presidente", "")
            except Exception:
                pass

        if idx_c == 0:
            encabezado_nomina = {
                "establecimiento": texto(enc_c.get("establecimiento") or c.get("institucion") or (inst_ref.get("nombre") if inst_ref else "")),
                "domicilio": texto(enc_c.get("domicilio") or (inst_ref.get("domicilio") if inst_ref else "") or "S/D"),
                "localidad": texto(enc_c.get("localidad") or (inst_ref.get("localidad") if inst_ref else "") or "Jujuy"),
                "cue": texto(enc_c.get("cue") or c.get("cue") or ""),
                "oferta": texto(enc_c.get("oferta") or c.get("oferta") or ""),
                "duracion": texto(enc_c.get("duracion") or (f"{enc_c.get('hsCatTotal')} hs cátedra" if enc_c.get("hsCatTotal") else "") or "Anual"),
                "division": texto(enc_c.get("division") or c.get("division") or ""),
                "normaAprobacion": texto(enc_c.get("normaAprobacion") or "—"),
                "resolucionDisenio": texto(enc_c.get("resolucionDisenio") or enc_c.get("disenio") or "—"),
                "docente": docente_c or "—",
                "turno": texto(enc_c.get("turno") or c.get("turno") or ""),
                "ciclo": texto(enc_c.get("ciclo") or c.get("ciclo") or ciclo_norm or str(datetime.datetime.now().year))
            }
        elif len(seleccionados) > 1:
            ofertas_prev = encabezado_nomina.get("oferta", "")
            of_cur = texto(enc_c.get("oferta") or c.get("oferta"))
            if of_cur and of_cur not in ofertas_prev:
                encabezado_nomina["oferta"] = f"{ofertas_prev} / {of_cur}".strip(" /")

        for est in datos_c.get("estudiantes", []):
            sol_info = est.get("solicitudCertificado") or obtener_estado_estudiante(c["id"], est.get("documento", ""))
            situacion = texto(est.get("situacion"))
            nf_str = texto(est.get("notaFinal"))
            nf_ok = True
            if nf_str:
                try:
                    nf_ok = float(nf_str.replace(",", ".")) >= 7
                except Exception:
                    nf_ok = False
            es_egresado = situacion.startswith("Aprobó") and nf_ok
            estado_cert = sol_info.get("estado") or EstadoCertificado.NO_SOLICITADO
            num_cert = texto(sol_info.get("numeroCertificado"))

            totales["todos"] += 1
            if es_egresado:
                totales["aprobados"] += 1
            if estado_cert == EstadoCertificado.APROBADO:
                totales["con_certificados"] += 1
            else:
                totales["pendientes"] += 1

            incluir = (
                filtro_norm == "todos"
                or (filtro_norm == "con_certificados" and estado_cert == EstadoCertificado.APROBADO)
                or (filtro_norm == "aprobados" and es_egresado)
                or (filtro_norm == "pendientes" and estado_cert != EstadoCertificado.APROBADO)
            )
            if not incluir:
                continue

            apellido = texto(est.get("apellido")).upper()
            nombres = texto(est.get("nombres"))
            ape_nom = f"{apellido}, {nombres}".strip(", ")
            fecha_fila = texto(est.get("fechaEgreso") or sol_info.get("fechaAprobacion") or enc_c.get("fechaActa"))
            if num_cert:
                obs_fila = f"Cert. N° {num_cert}"
            elif estado_cert in (EstadoCertificado.PENDIENTE, EstadoCertificado.OBSERVADO):
                obs_fila = estado_cert
            else:
                obs_fila = situacion or "En curso"

            todas_filas.append({
                "orden": str(len(todas_filas) + 1),
                "apellido": apellido,
                "nombres": nombres,
                "apellidoNombres": ape_nom,
                "documento": texto(est.get("documento")),
                "fecha": fecha_fila,
                "observaciones": obs_fila,
                "situacion": situacion,
                "estadoCertificado": estado_cert,
                "numeroCertificado": num_cert,
                "esEgresado": es_egresado,
                "idCurso": c["id"],
                "oferta": texto(enc_c.get("oferta") or c.get("oferta")),
                "division": texto(enc_c.get("division") or c.get("division"))
            })

    return {
        "encabezado": encabezado_nomina,
        "filtro": filtro_norm,
        "totales": totales,
        "filas": todas_filas
    }
