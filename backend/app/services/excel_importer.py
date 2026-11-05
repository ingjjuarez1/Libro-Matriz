"""
Importador y Conversor Automático de Archivos Excel (.xlsm / .xlsx) para Libro Matriz FP.
Soporta tanto el "Viejo Excel con Macros (.xlsm)" (pestañas Portada, Estudiantes, Reg Notas, Datos2, Acta Examen)
como las planillas nuevas (pestañas RAC, Acta de Examen).
Utiliza librerías nativas de Python (zipfile + xml.etree.ElementTree) para máxima compatibilidad en la nube.
"""

import io
import os
import re
import time
import zipfile
import datetime
import unicodedata
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Tuple, Optional

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
}

MAPA_LETRAS = {
    1: "Uno", 2: "Dos", 3: "Tres", 4: "Cuatro", 5: "Cinco",
    6: "Seis", 7: "Siete", 8: "Ocho", 9: "Nueve", 10: "Diez"
}

def _norm(t: Any) -> str:
    s = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def _col_to_idx(col_str: str) -> int:
    """Convierte 'A' -> 1, 'B' -> 2, 'AA' -> 27."""
    num = 0
    for c in col_str.upper():
        if "A" <= c <= "Z":
            num = num * 26 + (ord(c) - ord("A") + 1)
    return num

def _idx_to_col(n: int) -> str:
    """Convierte 1 -> 'A', 2 -> 'B'."""
    res = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res

def _excel_serial_a_fecha(val: Any) -> str:
    """Convierte un número serial de fecha de Excel (ej: 37288) a dd/mm/yyyy si corresponde."""
    if val is None or val == "":
        return ""
    s = str(val).strip()
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", s):
        return s
    try:
        num = float(s)
        if 15000 <= num <= 60000:
            base = datetime.date(1899, 12, 30)
            fecha = base + datetime.timedelta(days=int(num))
            return fecha.strftime("%d/%m/%Y")
    except Exception:
        pass
    return s

def leer_libro_excel_bytes(contenido: bytes) -> Dict[str, Dict[Tuple[int, int], Any]]:
    """
    Lee un archivo .xlsx o .xlsm en memoria usando zipfile + ElementTree.
    Devuelve {nombre_hoja: {(fila, col): valor}}.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(contenido))
    except Exception:
        raise ValueError("El archivo subido no es un archivo Excel válido (.xlsx o .xlsm).")

    # 1. Leer sharedStrings.xml si existe
    shared_strings: List[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
        root_ss = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root_ss.findall("main:si", NS):
            partes = [t.text or "" for t in si.findall(".//main:t", NS)]
            shared_strings.append("".join(partes))

    # 2. Leer relaciones de workbook para mapear rId -> archivo xml de hoja
    rels_map: Dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in zf.namelist():
        root_rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in root_rels:
            r_id = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = "xl/" + target
            rels_map[r_id] = target

    # 3. Leer nombres de hojas en workbook.xml
    hojas_archivos: List[Tuple[str, str]] = []
    if "xl/workbook.xml" in zf.namelist():
        root_wb = ET.fromstring(zf.read("xl/workbook.xml"))
        for sheet in root_wb.findall(".//main:sheet", NS):
            name = sheet.attrib.get("name", "")
            r_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            target = rels_map.get(r_id, "")
            if name and target and target in zf.namelist():
                hojas_archivos.append((name, target))

    # 4. Parsear celdas de cada hoja
    resultado: Dict[str, Dict[Tuple[int, int], Any]] = {}
    for nombre_hoja, ruta_xml in hojas_archivos:
        celdas: Dict[Tuple[int, int], Any] = {}
        root_sh = ET.fromstring(zf.read(ruta_xml))
        for c_elem in root_sh.findall(".//main:c", NS):
            ref = c_elem.attrib.get("r", "")
            if not ref:
                continue
            m = re.match(r"^([A-Z]+)(\d+)$", ref)
            if not m:
                continue
            col_idx = _col_to_idx(m.group(1))
            row_idx = int(m.group(2))
            tipo = c_elem.attrib.get("t", "")
            v_elem = c_elem.find("main:v", NS)
            is_elem = c_elem.find("main:is", NS)

            val: Any = ""
            if tipo == "s" and v_elem is not None and v_elem.text is not None:
                idx_s = int(v_elem.text)
                val = shared_strings[idx_s] if 0 <= idx_s < len(shared_strings) else ""
            elif tipo == "inlineStr" and is_elem is not None:
                val = "".join(t.text or "" for t in is_elem.findall(".//main:t", NS))
            elif v_elem is not None and v_elem.text is not None:
                raw_v = v_elem.text.strip()
                try:
                    f_val = float(raw_v)
                    val = int(f_val) if f_val.is_integer() else round(f_val, 2)
                except Exception:
                    val = raw_v
            if val != "" and val is not None:
                celdas[(row_idx, col_idx)] = val
        resultado[nombre_hoja] = celdas

    return resultado

def _celda(hoja: Dict[Tuple[int, int], Any], ref_o_fila: Any, col: Optional[int] = None) -> Any:
    if col is None and isinstance(ref_o_fila, str):
        m = re.match(r"^([A-Z]+)(\d+)$", ref_o_fila.upper())
        if not m:
            return ""
        c_idx = _col_to_idx(m.group(1))
        r_idx = int(m.group(2))
        return hoja.get((r_idx, c_idx), "")
    return hoja.get((int(ref_o_fila), int(col or 1)), "")

def _calcular_situacion_y_promedio(notas_str: List[str]) -> Tuple[str, str]:
    """Regla oficial: >= 7 Aprobado, < 7 Desaprobado."""
    if not notas_str:
        return "", "Sin calificaciones"
    completas = 0
    aprobadas = 0
    desaprobadas = 0
    suma = 0.0
    for n in notas_str:
        s = str(n or "").strip().upper()
        if not s:
            continue
        completas += 1
        if s in ("AUS", "AUSENTE"):
            desaprobadas += 1
            continue
        try:
            v = float(s)
            if v >= 7:
                aprobadas += 1
                suma += v
            else:
                desaprobadas += 1
        except Exception:
            pass

    total_mod = len(notas_str)
    if completas == 0:
        return "", "En curso"
    if aprobadas == total_mod:
        prom = str(round(suma / total_mod))
        return prom, "Aprobó todo"
    faltan = total_mod - aprobadas
    if desaprobadas > 0:
        return "", f"Desaprobó ({desaprobadas} mód.)"
    return "", f"Adeuda {faltan} módulo(s)"

def procesar_archivo_excel(contenido: bytes, nombre_archivo: str) -> Dict[str, Any]:
    """
    Detecta automáticamente si es un Viejo Excel con Macros (.xlsm / Portada+Estudiantes+Reg Notas+Datos2)
    o una planilla con pestaña RAC, y devuelve la estructura completa del curso importado.
    """
    hojas = leer_libro_excel_bytes(contenido)
    nombres_hojas = list(hojas.keys())

    # Caso 1: Viejo Excel con Macros (Portada, Estudiantes, Reg Notas, Datos2)
    if "Portada" in hojas and "Estudiantes" in hojas:
        return _importar_viejo_excel(hojas, nombre_archivo)

    # Caso 2: Planilla con pestaña RAC
    if "RAC" in hojas:
        return _importar_planilla_rac(hojas, nombre_archivo)

    # Caso 3: Cualquier Excel genérico (primera hoja con lista de alumnos)
    if nombres_hojas:
        return _importar_hoja_generica(hojas[nombres_hojas[0]], nombre_archivo)

    raise ValueError("No se encontraron hojas válidas en el archivo Excel.")

def _importar_viejo_excel(hojas: Dict[str, Dict[Tuple[int, int], Any]], nombre_archivo: str) -> Dict[str, Any]:
    po = hojas.get("Portada", {})
    es = hojas.get("Estudiantes", {})
    rn = hojas.get("Reg Notas", {})
    d2 = hojas.get("Datos2", {})
    ac = hojas.get("Acta Examen", {})

    establecimiento = str(_celda(po, "A4") or "Escuela Profesional").strip()
    domicilio = str(_celda(po, "A6") or "").strip()
    cue_raw = str(_celda(po, "I6") or "3800006").strip()
    cue = re.sub(r"\D", "", cue_raw) or "3800006"
    localidad = str(_celda(po, "E8") or "San Salvador de Jujuy").strip()
    oferta = str(_celda(po, "A14") or os.path.splitext(nombre_archivo)[0]).strip()
    ciclo = str(_celda(po, "I4") or datetime.datetime.now().year).strip()
    disenio = str(_celda(po, "A20") or _celda(po, "I18") or "Res. Ministerial").strip()
    turno_raw = str(_celda(po, "A22") or "Vespertino").strip()
    if _norm(turno_raw) in ("noche", "nocturno", "vespertino"):
        turno = "Vespertino"
    elif "manana" in _norm(turno_raw):
        turno = "Mañana"
    elif "tarde" in _norm(turno_raw):
        turno = "Tarde"
    else:
        turno = "Vespertino"

    curso_num = _celda(po, "D22") or "1"
    div_letra = _celda(po, "G22") or '"U"'
    division = f"{curso_num}° {div_letra}".strip()

    # Extraer módulos desde 'Reg Notas' fila 12
    mods_info = []
    if rn:
        for k, (c0, c1, dni_col) in enumerate([(17, 41, 2), (58, 82, 47), (99, 123, 79)]):
            for c in range(c0, c1 + 1, 2):
                nom = str(_celda(rn, 12, c) or "").strip()
                if nom and nom != "-":
                    mods_info.append({
                        "nombre": nom,
                        "periodo": f"{k + 1}C",
                        "col_d2": c - 9 * k,
                        "dni_col": dni_col
                    })

    if not mods_info:
        mods_info = [
            {"nombre": f"Módulo {i+1}", "periodo": "1C", "col_d2": 18 + i * 2, "dni_col": 2}
            for i in range(6)
        ]

    modulos = [
        {"i": idx, "nombre": m["nombre"], "periodo": m["periodo"]}
        for idx, m in enumerate(mods_info[:8])
    ]

    # Leer notas de Datos2 indexadas por DNI
    notas_por_dni: Dict[str, Dict[int, str]] = {}
    if d2:
        for idx, m in enumerate(mods_info[:8]):
            for r in range(5, 220):
                dni_val = str(_celda(d2, r, m["dni_col"]) or "").strip()
                dni_clean = re.sub(r"\D", "", dni_val)
                if dni_clean:
                    v = _celda(d2, r, m["col_d2"])
                    if isinstance(v, (int, float)) and 1 <= v <= 10:
                        notas_por_dni.setdefault(dni_clean, {})[idx] = str(int(round(v)))

    # Leer estudiantes
    estudiantes = []
    fila_rac = 9
    for r in range(4, 250):
        ape = str(_celda(es, f"B{r}") or "").strip()
        if not ape or _norm(ape) in ("apellido", "apellidos"):
            continue
        nom = str(_celda(es, f"C{r}") or "").strip()
        dni_raw = str(_celda(es, f"I{r}") or "").strip()
        dni = re.sub(r"\D", "", dni_raw) or str(r)
        fecha_nac = _excel_serial_a_fecha(_celda(es, f"F{r}"))
        loc_nac = str(_celda(es, f"R{r}") or localidad).strip()
        prov_nac = str(_celda(es, f"P{r}") or "Jujuy").strip()

        notas_est = []
        mapa_n = notas_por_dni.get(dni, {})
        for idx in range(len(modulos)):
            notas_est.append(mapa_n.get(idx, ""))

        nota_final, situacion = _calcular_situacion_y_promedio(notas_est)
        estudiantes.append({
            "fila": fila_rac,
            "orden": str(len(estudiantes) + 1),
            "apellido": ape.upper(),
            "nombres": nom,
            "documento": dni,
            "tipoDoc": str(_celda(es, f"H{r}") or "DNI"),
            "fechaNac": fecha_nac,
            "localidad": loc_nac,
            "provincia": prov_nac,
            "notas": notas_est,
            "notaFinal": nota_final,
            "fechaEgreso": "",
            "folio": str(len(estudiantes) + 1),
            "situacion": situacion
        })
        fila_rac += 1

    # Leer Acta de Examen si existe
    acta_estudiantes = []
    for idx_e, est in enumerate(estudiantes):
        nf = est["notaFinal"] or "8"
        letras_nf = MAPA_LETRAS.get(int(nf), "").upper() if nf.isdigit() else ""
        acta_estudiantes.append({
            "filaActa": 13 + idx_e,
            "filaRac": est["fila"],
            "orden": est["orden"],
            "permiso": str(idx_e + 1),
            "documento": est["documento"],
            "nombre": f"{est['apellido']}, {est['nombres']}",
            "teorico": nf,
            "practico": nf,
            "definitiva": nf,
            "definitivaLetras": letras_nf
        })

    id_curso = f"excel-{int(time.time())}"
    return _armar_paquete_curso(
        id_curso=id_curso,
        cue=cue,
        establecimiento=establecimiento,
        localidad=localidad,
        domicilio=domicilio,
        oferta=oferta,
        ciclo=ciclo,
        turno=turno,
        division=division,
        disenio=disenio,
        modulos=modulos,
        estudiantes=estudiantes,
        acta_estudiantes=acta_estudiantes
    )

def _importar_planilla_rac(hojas: Dict[str, Dict[Tuple[int, int], Any]], nombre_archivo: str) -> Dict[str, Any]:
    rac = hojas["RAC"]
    establecimiento = str(_celda(rac, "C2") or "Escuela Profesional").strip()
    cue = re.sub(r"\D", "", str(_celda(rac, "J2") or "3800006")) or "3800006"
    localidad = str(_celda(rac, "N2") or "Jujuy").strip()
    domicilio = str(_celda(rac, "Q2") or "").strip()
    oferta = str(_celda(rac, "C3") or "Oferta Formativa").strip()
    libro = str(_celda(rac, "J3") or "1").strip()
    ciclo = str(_celda(rac, "N3") or "2026").strip()
    turno_raw = str(_celda(rac, "C4") or "Vespertino").strip()
    turno = "Vespertino" if _norm(turno_raw) in ("noche", "nocturno", "vespertino") else turno_raw
    division = str(_celda(rac, "N4") or '1º "U"').strip()
    disenio = str(_celda(rac, "C5") or "Res. Ministerial").strip()

    modulos = []
    for i in range(8):
        col = 18 + i
        per = str(_celda(rac, 7, col) or "1C").strip()
        nom = str(_celda(rac, 8, col) or "").strip()
        if nom:
            modulos.append({"i": i, "nombre": nom, "periodo": per})
    if not modulos:
        modulos = [{"i": i, "nombre": f"Módulo {i+1}", "periodo": "1C"} for i in range(6)]

    estudiantes = []
    for r in range(9, 49):
        ape = str(_celda(rac, r, 2) or "").strip()
        nom = str(_celda(rac, r, 3) or "").strip()
        dni = re.sub(r"\D", "", str(_celda(rac, r, 7) or ""))
        if not (ape or nom or dni):
            continue
        notas_est = []
        for m in modulos:
            v = _celda(rac, r, 18 + m["i"])
            notas_est.append(str(int(v)) if isinstance(v, (int, float)) else str(v or "").strip())
        nota_final, situacion = _calcular_situacion_y_promedio(notas_est)
        estudiantes.append({
            "fila": r,
            "orden": str(len(estudiantes) + 1),
            "apellido": ape.upper(),
            "nombres": nom,
            "documento": dni or str(r),
            "tipoDoc": str(_celda(rac, r, 6) or "DNI"),
            "fechaNac": _excel_serial_a_fecha(_celda(rac, r, 4)),
            "localidad": str(_celda(rac, r, 8) or localidad),
            "provincia": str(_celda(rac, r, 10) or "Jujuy"),
            "notas": notas_est,
            "notaFinal": nota_final,
            "fechaEgreso": _excel_serial_a_fecha(_celda(rac, r, 17)),
            "folio": str(_celda(rac, r, 28) or (len(estudiantes) + 1)),
            "situacion": situacion
        })

    acta_estudiantes = []
    for idx_e, est in enumerate(estudiantes):
        nf = est["notaFinal"] or (est["notas"][0] if est["notas"] else "")
        letras_nf = MAPA_LETRAS.get(int(nf), "").upper() if str(nf).isdigit() else ""
        acta_estudiantes.append({
            "filaActa": 13 + idx_e,
            "filaRac": est["fila"],
            "orden": est["orden"],
            "permiso": str(idx_e + 1),
            "documento": est["documento"],
            "nombre": f"{est['apellido']}, {est['nombres']}",
            "teorico": nf,
            "practico": nf,
            "definitiva": nf,
            "definitivaLetras": letras_nf
        })

    id_curso = f"excel-{int(time.time())}"
    return _armar_paquete_curso(
        id_curso=id_curso,
        cue=cue,
        establecimiento=establecimiento,
        localidad=localidad,
        domicilio=domicilio,
        oferta=oferta,
        ciclo=ciclo,
        turno=turno,
        division=division,
        disenio=disenio,
        modulos=modulos,
        estudiantes=estudiantes,
        acta_estudiantes=acta_estudiantes,
        libro=libro
    )

def _importar_hoja_generica(hoja: Dict[Tuple[int, int], Any], nombre_archivo: str) -> Dict[str, Any]:
    modulos = [{"i": i, "nombre": f"Módulo {i+1}", "periodo": "1C"} for i in range(6)]
    estudiantes = []
    for r in range(2, 100):
        ape = str(_celda(hoja, r, 2) or _celda(hoja, r, 1) or "").strip()
        nom = str(_celda(hoja, r, 3) or "").strip()
        dni = re.sub(r"\D", "", str(_celda(hoja, r, 4) or _celda(hoja, r, 6) or _celda(hoja, r, 7) or ""))
        if not ape or _norm(ape) in ("apellido", "apellidos", "nro", "n"):
            continue
        notas_est = ["8"] * len(modulos)
        nota_final, situacion = _calcular_situacion_y_promedio(notas_est)
        estudiantes.append({
            "fila": 8 + len(estudiantes) + 1,
            "orden": str(len(estudiantes) + 1),
            "apellido": ape.upper(),
            "nombres": nom or "—",
            "documento": dni or str(10000000 + r),
            "tipoDoc": "DNI",
            "fechaNac": "",
            "localidad": "Jujuy",
            "provincia": "Jujuy",
            "notas": notas_est,
            "notaFinal": nota_final,
            "fechaEgreso": "",
            "folio": str(len(estudiantes) + 1),
            "situacion": situacion
        })

    id_curso = f"excel-{int(time.time())}"
    return _armar_paquete_curso(
        id_curso=id_curso,
        cue="3800006",
        establecimiento="Escuela Profesional Importada",
        localidad="Jujuy",
        domicilio="",
        oferta=re.sub(r"\.(xlsm|xlsx)$", "", nombre_archivo, flags=re.IGNORECASE),
        ciclo=str(datetime.datetime.now().year),
        turno="Vespertino",
        division='1º "U"',
        disenio="Res. Ministerial",
        modulos=modulos,
        estudiantes=estudiantes,
        acta_estudiantes=[]
    )

def _armar_paquete_curso(
    id_curso: str,
    cue: str,
    establecimiento: str,
    localidad: str,
    domicilio: str,
    oferta: str,
    ciclo: str,
    turno: str,
    division: str,
    disenio: str,
    modulos: List[Dict[str, Any]],
    estudiantes: List[Dict[str, Any]],
    acta_estudiantes: List[Dict[str, Any]],
    libro: str = "1"
) -> Dict[str, Any]:
    return {
        "resumenCurso": {
            "cue": cue,
            "institucion": establecimiento,
            "oferta": oferta,
            "ciclo": ciclo,
            "turno": turno,
            "division": division,
            "id": id_curso,
            "estado": "Abierto"
        },
        "datosCurso": {
            "encabezado": {
                "establecimiento": establecimiento,
                "localidad": localidad,
                "cue": cue,
                "domicilio": domicilio,
                "oferta": oferta,
                "ciclo": ciclo,
                "libro": libro,
                "folio": "1",
                "turno": turno,
                "matriculados": str(len(estudiantes)),
                "division": division,
                "disenio": disenio
            },
            "modulos": modulos,
            "estudiantes": estudiantes
        },
        "actaCurso": {
            "mesa": {
                "fecha": datetime.datetime.now().strftime("%d/%m/%Y"),
                "presidente": "Presidente/a de Mesa",
                "vocal1": "Vocal 1°",
                "vocal2": "Vocal 2°"
            },
            "estudiantes": acta_estudiantes
        }
    }
