"""
Lógica de datos y manipulación de planillas Google Sheets.
Migrado de Datos.gs y Api.gs.
Preserva la lógica exacta de Libro Matriz FP:
- RAC (Registro Anual de Calificaciones)
- Acta de Examen
- Certificado Analítico
- Panel FP (Usuarios, Cursos, Registro)
"""

import re
from typing import Dict, List, Any, Optional
from backend.app.core.config import (
    PANEL_ID, RAC, ACTA, ANALITICO, PANEL, AUSENTE,
    col_num_to_letter, letter_to_col_num
)
from backend.app.services.google_service import google_client
from backend.app.core.auth import (
    normalizar_cue, exigir_lectura, exigir_carga, registrar, PermissionDeniedException
)
from backend.app.services.titulos_service import (
    obtener_estado_estudiante, esta_estudiante_congelado, EstadoCertificado
)
from backend.app.services.excel_importer import (
    procesar_archivo_excel, _calcular_situacion_y_promedio
)

_CURSOS_IMPORTADOS: Dict[str, Dict[str, Any]] = {}

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

def cursos_del_panel() -> List[Dict[str, Any]]:
    """Lee y normaliza el índice de cursos desde la pestaña 'Cursos' del Panel FP."""
    if not PANEL_ID or not google_client.is_connected():
        return list(_CURSOS_DEMO)

    try:
        rango = f"{PANEL['CURSOS']['hoja']}!A1:H1000"
        valores = google_client.get_values(PANEL_ID, rango)
        if len(valores) < 2:
            return list(_CURSOS_DEMO)

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
        return cursos if cursos else list(_CURSOS_DEMO)
    except Exception:
        return list(_CURSOS_DEMO)

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
                    est["notaFinal"] = nf
                    est["situacion"] = sit
        return {"guardados": len(cambios)}

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
                    est["notaFinal"] = nf
                    est["situacion"] = sit
        return {"guardados": len(cambios)}

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
        return {"fila": nueva_fila, "estudiante": nuevo_est}

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

    if curso["id"] in _CURSOS_IMPORTADOS:
        acta_imp = _CURSOS_IMPORTADOS[curso["id"]]["actaCurso"]
        return {
            "curso": curso,
            "puedeCargar": bool(sesion_usr.get("puedeCargar") or sesion_usr.get("verTodo")),
            "mesa": acta_imp["mesa"],
            "estudiantes": acta_imp["estudiantes"]
        }

    if curso["id"] == "curso-peluquero-ep6-demo" or not google_client.is_connected():
        return {
            "curso": curso,
            "puedeCargar": True,
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
                        vt = es.get("teorico", "")
                        vp = es.get("practico", "")
                        if vt == "AUS" or vp == "AUS":
                            es["definitiva"] = "AUS"
                            es["definitivaLetras"] = "AUSENTE"
                        else:
                            try:
                                nt = float(vt)
                                np = float(vp)
                                prom = int(round((nt + np) / 2.0))
                                es["definitiva"] = str(prom)
                                es["definitivaLetras"] = letras_acta.get(prom, str(prom))
                            except Exception:
                                pass
                    break

        # Sincronizar todo lo cargado en el Acta de Examen con el Registro Anual de Calificaciones (RAC)
        libro_acta_actual = enc_dest.get("libro", "1") if enc_dest else "1"
        folio_acta_actual = enc_dest.get("folio", "") if enc_dest else ""
        fecha_acta_actual = mesa_dest.get("fecha", "")
        for es_acta in est_list:
            doc_a = str(es_acta.get("documento", "")).strip()
            fila_r = int(es_acta.get("filaRac", 0))
            def_val = str(es_acta.get("definitiva", "")).strip()
            for est_rac in rac_est_list:
                if (doc_a and str(est_rac.get("documento", "")).strip() == doc_a) or (fila_r and int(est_rac.get("fila", 0)) == fila_r):
                    if def_val:
                        est_rac["notaFinal"] = def_val
                        if def_val.isdigit() and int(def_val) >= 7:
                            est_rac["situacion"] = "Aprobó todo"
                    if est_rac.get("notaFinal") or def_val:
                        est_rac["libroActa"] = libro_acta_actual
                        if folio_acta_actual:
                            est_rac["folio"] = folio_acta_actual
                        if fecha_acta_actual:
                            est_rac["fechaEgreso"] = fecha_acta_actual
                    break

        return {"guardados": len(cambios or []) + (1 if mesa else 0)}

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

    notas_est = est_seleccionado.get("notas", []) if est_seleccionado else []
    trayecto_final = []
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

        cohorte_mod = str(enc_curso.get("ciclo") or curso.get("ciclo") or "2026")
        mes_anio_mod = f"12/{cohorte_mod}" if val_nota and val_nota != "AUS" else ""
        if est_seleccionado and est_seleccionado.get("fechaEgreso") and val_nota and val_nota != "AUS":
            partes_fe = str(est_seleccionado.get("fechaEgreso")).split("/")
            if len(partes_fe) == 3:
                mes_anio_mod = f"{partes_fe[1]}/{partes_fe[2]}"

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

    documento_oficial = {
        "libro": str(enc_curso.get("libro") or "1"),
        "folio": est_seleccionado.get("folio", "1") if est_seleccionado else "1",
        "certNro": num_cert_final if not es_borrador else "",
        "establecimiento": "ESCUELA PROFESIONAL Nº 6" if es_demo_ep6 else str(enc_curso.get("establecimiento") or curso.get("institucion") or "ESCUELA PROFESIONAL").upper(),
        "cue": "3800612-00" if es_demo_ep6 else str(enc_curso.get("cue") or curso.get("cue") or "3800006"),
        "domicilio": "PTO ARGENTINO Nº 705- Bº MALVINAS ARG." if es_demo_ep6 else str(enc_curso.get("domicilio") or "S/D").upper(),
        "localidad": "PERICO" if es_demo_ep6 else str(enc_curso.get("localidad") or "JUJUY").upper(),
        "provincia": "JUJUY",
        "oferta": str(enc_curso.get("oferta") or curso.get("oferta") or "Peluquero").upper(),
        "cohorte": str(enc_curso.get("ciclo") or curso.get("ciclo") or "2026"),
        "normaJurisdiccional": str(enc_curso.get("disenio") or "Res. N° 2114-E-2026"),
        "fechaEmision": fecha_emision or "",
        "fechaAprobacion": sol_info.get("fechaAprobacion") or "",
        "estudianteNombre": f"{est_seleccionado.get('apellido', '')}, {est_seleccionado.get('nombres', '')}".strip() if est_seleccionado else "AMANTE, SERGIO DAVID",
        "lugarNac": lugar_nac_str,
        "fechaNac": est_seleccionado.get("fechaNac", "01/02/2002") if est_seleccionado else "01/02/2002",
        "tipoDoc": est_seleccionado.get("tipoDoc", "DNI") if est_seleccionado else "DNI",
        "dniFormateado": dni_formateado,
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

# ==================== RESUMEN POR INSTITUCIÓN (DIRECCIÓN) ====================

def obtener_resumen(sesion_usr: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Calcula y devuelve el resumen institucional para el rol Dirección DETP."""
    if not sesion_usr.get("verTodo"):
        raise PermissionDeniedException("Este resumen es exclusivo para la Dirección DETP.")

    por_institucion = {}
    for c in cursos_del_panel():
        try:
            d = leer_curso(c["id"])
            aprobados = sum(
                1 for e in d.get("estudiantes", []) if str(e.get("situacion", "")).startswith("Aprobó")
            )
            k = c["cue"] or c["institucion"]
            if k not in por_institucion:
                por_institucion[k] = {
                    "cue": c["cue"],
                    "institucion": c["institucion"],
                    "cursos": 0,
                    "estudiantes": 0,
                    "aprobados": 0
                }
            por_institucion[k]["cursos"] += 1
            por_institucion[k]["estudiantes"] += len(d.get("estudiantes", []))
            por_institucion[k]["aprobados"] += aprobados
        except Exception:
            continue

    lista = list(por_institucion.values())
    lista.sort(key=lambda x: x["institucion"])
    return lista

# ==================== IMPORTADOR DE VIEJO EXCEL (.XLSM / .XLSX) ====================

def importar_excel_en_sistema(contenido: bytes, nombre_archivo: str, sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un archivo Excel (.xlsm o .xlsx), extrae la nómina de estudiantes,
    calificaciones y acta de examen, y lo registra inmediatamente en el sistema.
    """
    paquete = procesar_archivo_excel(contenido, nombre_archivo)
    resumen = paquete["resumenCurso"]

    # Si el usuario pertenece a una escuela con CUE específico, asignar su CUE si el Excel no tenía uno válido
    if not sesion_usr.get("verTodo") and sesion_usr.get("cues"):
        resumen["cue"] = sesion_usr["cues"][0]
        paquete["datosCurso"]["encabezado"]["cue"] = sesion_usr["cues"][0]

    id_curso = resumen["id"]
    _CURSOS_IMPORTADOS[id_curso] = paquete
    _CURSOS_DEMO.append(resumen)

    registrar(
        sesion_usr,
        "Importación Excel",
        f"{resumen['oferta']} ({resumen['cue']})",
        f"Archivo '{nombre_archivo}' importado con {len(paquete['datosCurso']['estudiantes'])} estudiantes"
    )
    return {
        "curso": resumen,
        "cantidadEstudiantes": len(paquete["datosCurso"]["estudiantes"]),
        "cantidadModulos": len(paquete["datosCurso"]["modulos"])
    }

def crear_curso_manual(datos: Dict[str, Any], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """Registra un nuevo curso en el sistema listo para que el Administrativo cargue alumnos."""
    import time
    import datetime
    id_curso = texto(datos.get("id")) or f"curso-{int(time.time())}"
    cue = texto(datos.get("cue")) or (sesion_usr["cues"][0] if sesion_usr.get("cues") else "3800006")
    institucion = texto(datos.get("institucion")) or "Escuela Profesional"
    oferta = texto(datos.get("oferta")) or "Oferta Formativa"
    ciclo = texto(datos.get("ciclo")) or str(datetime.datetime.now().year)
    turno_raw = texto(datos.get("turno")) or "Vespertino"
    turno = "Vespertino" if turno_raw.lower() in ("noche", "nocturno", "vespertino") else turno_raw
    division = texto(datos.get("division")) or '1º "U"'

    resumen = {
        "cue": cue,
        "institucion": institucion,
        "oferta": oferta,
        "ciclo": ciclo,
        "turno": turno,
        "division": division,
        "id": id_curso,
        "estado": "Abierto"
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
                "localidad": "San Salvador de Jujuy",
                "cue": cue,
                "domicilio": "S/D",
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
                "presidente": "Presidente/a de Mesa",
                "vocal1": "Vocal 1°",
                "vocal2": "Vocal 2°"
            },
            "estudiantes": []
        }
    }
    _CURSOS_DEMO.append(resumen)
    registrar(sesion_usr, "Nuevo Curso", f"{oferta} ({cue})", f"Turno {turno}")
    return resumen
