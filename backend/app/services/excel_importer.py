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

def _normalizar_acredita_o_referencial(val: Any) -> str:
    """Normaliza el texto de Referencial de Ingreso o Acredita con desde el Excel."""
    s = str(val or "").strip()
    if not s:
        return "Primaria Completa"
    n = _norm(s)
    partes = []
    if "primari" in n:
        partes.append("Primaria Completa")
    if "secundari" in n:
        partes.append("Secundaria Completa")
    if "ciclo basico" in n or "cb " in f"{n} " or "c b" in n:
        partes.append("CB Completo")
    if "superior" in n or "terciari" in n or "universitari" in n:
        partes.append("Superior Completa")
    if "montador" in n:
        partes.append("Montador Electricista Domiciliario")
    if partes:
        return " / ".join(partes)
    return s

def _normalizar_pais(val: Any) -> str:
    """Normaliza abreviaturas de nacionalidad/país (ej: 'Arg' -> 'Argentina')."""
    s = str(val or "").strip()
    if not s:
        return "Argentina"
    n = _norm(s)
    if n.startswith("arg"):
        return "Argentina"
    if n.startswith("bol"):
        return "Bolivia"
    if n.startswith("per"):
        return "Perú"
    if n.startswith("par"):
        return "Paraguay"
    if n.startswith("chi"):
        return "Chile"
    if n.startswith("uru"):
        return "Uruguay"
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
    lm = hojas.get("L Matriz", {})

    establecimiento = str(_celda(po, "A4") or _celda(rn, "G4") or "Escuela Profesional").strip()
    domicilio = str(_celda(po, "A6") or "").strip()
    cue_raw = str(_celda(po, "I6") or "3800006").strip()
    cue = re.sub(r"\D", "", cue_raw) or "3800006"
    localidad = str(_celda(po, "E8") or _celda(lm, "E4") or "San Salvador de Jujuy").strip()
    oferta = str(_celda(po, "A14") or _celda(rn, "H5") or os.path.splitext(nombre_archivo)[0]).strip()
    familia_profesional = str(_celda(po, "A16") or _celda(po, "B16") or _celda(lm, "D9") or "—").strip()
    ciclo = str(_celda(po, "I4") or _celda(rn, "C6") or datetime.datetime.now().year).strip()

    # Datos de la tabla de Portada / Reg Notas / L Matriz:
    # - Horas Cátedras, Nivel, Certificación, Norma Jurisdiccional de Aprobación Res. N°,
    #   Resolución Diseño Curricular y/o Plan de Estudio Jurisdiccional N°, Validez Nacional R.M.E N°, Disposición
    hs_cat_raw = str(_celda(rn, "AK6") or _celda(po, "A18") or _celda(po, "B18") or "510").strip()
    hs_cat_total = hs_cat_raw if re.match(r"^\d+$", hs_cat_raw) else "510"
    nivel_curso = str(_celda(rn, "AC6") or _celda(po, "C18") or _celda(po, "D18") or "II").strip()
    certificacion = str(_celda(po, "E18") or _celda(po, "F18") or "Diseño Curricular Jurisdiccional").strip()
    if certificacion in ("I", "II", "III"):
        certificacion = "Diseño Curricular Jurisdiccional"
    norma_aprobacion = str(_celda(rn, "I7") or _celda(lm, "E10") or _celda(po, "I18") or _celda(po, "H18") or _celda(po, "G18") or "—").strip()
    resolucion_disenio = str(_celda(rn, "W7") or _celda(lm, "P10") or _celda(po, "A20") or _celda(po, "B20") or "—").strip()
    validez_nacional = str(_celda(rn, "AI7") or _celda(lm, "G11") or _celda(po, "E20") or _celda(po, "F20") or _celda(po, "D20") or "—").strip()
    disposicion = str(_celda(lm, "O11") or _celda(po, "H20") or _celda(po, "I20") or _celda(po, "G20") or "-").strip()
    referencial_ingreso = _normalizar_acredita_o_referencial(
        _celda(po, "I14") or _celda(po, "H14") or _celda(po, "G14") or _celda(lm, "E6") or "Primaria Completa"
    )
    libro_nro = str(_celda(lm, "C1") or "1").strip()

    disenio = resolucion_disenio if resolucion_disenio != "—" else (norma_aprobacion if norma_aprobacion != "—" else "Res. Ministerial")
    turno_raw = str(_celda(po, "A22") or _celda(rn, "S6") or "Vespertino").strip()
    if _norm(turno_raw) in ("noche", "nocturno", "vespertino"):
        turno = "Vespertino"
    elif "manana" in _norm(turno_raw):
        turno = "Mañana"
    elif "tarde" in _norm(turno_raw):
        turno = "Tarde"
    else:
        turno = "Vespertino"

    curso_num = str(_celda(po, "D22") or "1°").strip()
    if curso_num and not curso_num.endswith("°") and not curso_num.endswith("º"):
        curso_num = f"{curso_num}°"
    div_letra = str(_celda(po, "G22") or _celda(rn, "L6") or '"U"').strip()
    division = f"{curso_num} {div_letra}".strip()

    # Determinar si la oferta es de 1 cuatrimestre o de 2/3 cuatrimestres
    duracion_rn = str(_celda(rn, "AD8") or _celda(po, "A18") or "").strip().lower()
    es_cuat_unico = "1 cuatrimestre" in duracion_rn

    # Extraer módulos desde 'Reg Notas' fila 12 (1° Cuatrimestre, 2° Cuatrimestre, 3° Cuatrimestre)
    # En Reg Notas:
    # - 1° Cuatrimestre: DNI en col 2 (B), Nombre en col 6 (F), módulos en cols 17..40 (Q..AN; 17..28 Comunes, 29..40 Específicos)
    # - 2° Cuatrimestre: DNI en col 43 (AQ), Nombre en col 47 (AU), módulos en cols 58..81 (BF..CC; 58..69 Comunes, 70..81 Específicos)
    # - 3° Cuatrimestre: DNI en col 84 (CF), Nombre en col 88 (CJ), módulos en cols 99..122 (CU..DR; 99..110 Comunes, 111..122 Específicos)
    mods_info = []
    if rn:
        bloques = [
            (0, 17, 40, 29, 2, 6, 2),
            (1, 58, 81, 70, 43, 47, 47),
            (2, 99, 122, 111, 84, 88, 79),
        ]
        for k, c0, c1, col_esp_inicio, dni_col_rn, nom_col_rn, dni_col_d2 in bloques:
            etiqueta_per = "Cuatrimestre único" if (es_cuat_unico and k == 0) else f"{k + 1}° Cuatrimestre"
            etiqueta_corta = "1C" if (es_cuat_unico and k == 0) else f"{k + 1}°C"
            for c in range(c0, c1 + 1, 2):
                nom = str(_celda(rn, 12, c) or "").strip()
                if nom and nom != "-":
                    tipo_mod = "Específico" if c >= col_esp_inicio else "Común"
                    mods_info.append({
                        "nombre": nom,
                        "periodo": etiqueta_per,
                        "periodoCorto": etiqueta_corta,
                        "cuatrimestre": k + 1,
                        "tipo": tipo_mod,
                        "col_rn_t": c,
                        "col_rn_p": c + 1,
                        "dni_col_rn": dni_col_rn,
                        "nom_col_rn": nom_col_rn,
                        "col_d2": c - 9 * k,
                        "dni_col_d2": dni_col_d2
                    })

    if not mods_info:
        mods_info = [
            {
                "nombre": f"Módulo {i+1}",
                "periodo": "1° Cuatrimestre",
                "periodoCorto": "1°C",
                "cuatrimestre": 1,
                "tipo": "Común" if i < 2 else "Específico",
                "col_rn_t": 17 + i * 2,
                "col_rn_p": 18 + i * 2,
                "dni_col_rn": 2,
                "nom_col_rn": 6,
                "col_d2": 17 + i * 2,
                "dni_col_d2": 2
            }
            for i in range(6)
        ]

    modulos = [
        {
            "i": idx,
            "nombre": m["nombre"],
            "periodo": m["periodo"],
            "periodoCorto": m["periodoCorto"],
            "cuatrimestre": m["cuatrimestre"],
            "tipo": m["tipo"]
        }
        for idx, m in enumerate(mods_info[:12])
    ]

    # 1) Leer notas desde 'Reg Notas' (Teórico y Práctico de 1° y 2° Cuatrimestre) indexadas por DNI y por Nombre
    notas_por_dni: Dict[str, Dict[int, str]] = {}
    notas_por_nombre: Dict[str, Dict[int, str]] = {}

    if rn:
        for idx, m in enumerate(mods_info[:12]):
            for r in range(14, 240):
                dni_val = re.sub(r"\D", "", str(_celda(rn, r, m["dni_col_rn"]) or ""))
                nom_val = _norm(_celda(rn, r, m["nom_col_rn"]))
                if not dni_val and not nom_val:
                    continue
                vt = _celda(rn, r, m["col_rn_t"])
                vp = _celda(rn, r, m["col_rn_p"])
                nota_calc = ""
                vals_num = []
                for vx in (vt, vp):
                    if isinstance(vx, (int, float)) and 1 <= vx <= 10:
                        vals_num.append(float(vx))
                    elif str(vx or "").strip().upper() in ("AUS", "AUSENTE"):
                        nota_calc = "AUS"
                if vals_num:
                    prom_mod = sum(vals_num) / len(vals_num)
                    # En el viejo Excel si el promedio da entero o decimal se redondea a entero en la libreta
                    nota_calc = str(int(round(prom_mod)))
                if nota_calc:
                    if dni_val:
                        notas_por_dni.setdefault(dni_val, {})[idx] = nota_calc
                    if nom_val:
                        notas_por_nombre.setdefault(nom_val, {})[idx] = nota_calc

    # 2) Completar o sobreescribir con notas de 'Datos2' si existen valores calculados válidos (1..10)
    if d2:
        for idx, m in enumerate(mods_info[:12]):
            for r in range(5, 240):
                dni_val = re.sub(r"\D", "", str(_celda(d2, r, m["dni_col_d2"]) or ""))
                if dni_val:
                    v = _celda(d2, r, m["col_d2"])
                    if isinstance(v, (int, float)) and 1 <= v <= 10:
                        notas_por_dni.setdefault(dni_val, {})[idx] = str(int(round(v)))

    # 3) Respaldo adicional desde 'Historial Módulos' si existe en el libro
    hm = hojas.get("Historial Módulos", {})
    if hm:
        mapa_nom_mod = {_norm(m["nombre"]): idx for idx, m in enumerate(modulos)}
        for r in range(5, 600):
            dni_hm = re.sub(r"\D", "", str(_celda(hm, r, 3) or ""))
            mod_hm = _norm(_celda(hm, r, 11))
            cal_hm = _celda(hm, r, 12)
            if dni_hm and mod_hm in mapa_nom_mod and isinstance(cal_hm, (int, float)) and 1 <= cal_hm <= 10:
                idx_m = mapa_nom_mod[mod_hm]
                if idx_m not in notas_por_dni.get(dni_hm, {}):
                    notas_por_dni.setdefault(dni_hm, {})[idx_m] = str(int(round(cal_hm)))

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
        loc_nac = str(_celda(es, f"O{r}") or localidad).strip()
        prov_nac = str(_celda(es, f"Q{r}") or _celda(es, f"L{r}") or "Jujuy").strip()
        pais_nac = _normalizar_pais(_celda(es, f"G{r}"))
        acredita_est = _normalizar_acredita_o_referencial(_celda(es, f"K{r}") or "Primaria Completa")

        notas_est = []
        mapa_n = notas_por_dni.get(dni, {})
        mapa_nom = notas_por_nombre.get(_norm(f"{ape} {nom}"), {})
        for idx in range(len(modulos)):
            val_m = mapa_n.get(idx, "") or mapa_nom.get(idx, "")
            notas_est.append(val_m)

        nota_final_mod, situacion = _calcular_situacion_y_promedio(notas_est)
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
            "pais": pais_nac,
            "acreditaCon": acredita_est,
            "nivel": acredita_est,
            "notas": notas_est,
            "promedioModulos": nota_final_mod,
            "notaFinal": "",
            "libroActa": "",
            "fechaEgreso": "",
            "folio": "",
            "situacion": situacion
        })
        fila_rac += 1

    # Leer Acta de Examen real desde la pestaña 'Acta Examen' y alimentar el RAC
    meses_nombres = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
        "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12
    }
    fecha_acta_str = ""
    presidente_acta = "Presidente/a de Mesa"
    vocal1_acta = "Vocal 1°"
    vocal2_acta = "Vocal 2°"
    folio_acta_str = str(_celda(ac, "W2") or _celda(lm, "R1") or "1").strip()
    notas_acta_por_dni: Dict[str, Tuple[str, str, str]] = {}

    if ac:
        dia_ac = str(_celda(ac, "C8") or "").strip()
        mes_ac = _norm(_celda(ac, "H8"))
        anio_ac = str(_celda(ac, "P8") or "").strip()
        if dia_ac.isdigit() and mes_ac in meses_nombres and anio_ac.isdigit():
            fecha_acta_str = f"{int(dia_ac):02d}/{meses_nombres[mes_ac]:02d}/{int(anio_ac)}"
        mesa_txt = str(_celda(ac, "A10") or "").strip()
        m_mesa = re.search(r"Presidente:\s*(.*?)\s*-\s*Vocal\s*1[°º]?\s*(.*?)\s*-\s*Vocal\s*2[°º]?\s*(.*)", mesa_txt, re.IGNORECASE)
        if m_mesa:
            presidente_acta = m_mesa.group(1).strip() or presidente_acta
            vocal1_acta = m_mesa.group(2).strip() or vocal1_acta
            vocal2_acta = m_mesa.group(3).strip() or vocal2_acta

        for r_ac in range(15, 150):
            dni_ac = re.sub(r"\D", "", str(_celda(ac, f"E{r_ac}") or ""))
            if not dni_ac:
                continue
            vt_raw = _celda(ac, f"P{r_ac}")
            vp_raw = _celda(ac, f"S{r_ac}")
            vd_raw = _celda(ac, f"V{r_ac}")

            def _fmt_nota_acta(v_in: Any) -> str:
                if v_in is None or v_in == "":
                    return ""
                s_in = str(v_in).strip().upper()
                if s_in in ("A", "AUS", "AUSENTE"):
                    return "AUS"
                try:
                    n_f = float(s_in)
                    if 1 <= n_f <= 10:
                        return str(int(round(n_f)))
                except Exception:
                    pass
                return ""

            teo_s = _fmt_nota_acta(vt_raw)
            prac_s = _fmt_nota_acta(vp_raw)
            def_s = _fmt_nota_acta(vd_raw)
            if not def_s and teo_s and prac_s:
                if teo_s == "AUS" or prac_s == "AUS":
                    def_s = "AUS"
                elif teo_s.isdigit() and prac_s.isdigit():
                    def_s = str(int(round((int(teo_s) + int(prac_s)) / 2.0)))
            if teo_s or prac_s or def_s:
                notas_acta_por_dni[dni_ac] = (teo_s, prac_s, def_s)

    acta_estudiantes = []
    for idx_e, est in enumerate(estudiantes):
        teo_s, prac_s, def_s = notas_acta_por_dni.get(est["documento"], ("", "", ""))
        letras_nf = "AUSENTE" if def_s == "AUS" else (MAPA_LETRAS.get(int(def_s), "").upper() if def_s.isdigit() else "")
        # El Acta alimenta la información de Calificación Final, Libro, Folio y Fecha en el RAC
        if def_s:
            est["notaFinal"] = def_s
            est["libroActa"] = libro_nro
            est["folio"] = folio_acta_str
            est["fechaEgreso"] = fecha_acta_str
        acta_estudiantes.append({
            "filaActa": 13 + idx_e,
            "filaRac": est["fila"],
            "orden": est["orden"],
            "permiso": str(idx_e + 1),
            "documento": est["documento"],
            "nombre": f"{est['apellido']}, {est['nombres']}",
            "teorico": teo_s,
            "practico": prac_s,
            "definitiva": def_s,
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
        libro=libro_nro,
        folio=folio_acta_str,
        fecha_acta=fecha_acta_str,
        presidente_acta=presidente_acta,
        vocal1_acta=vocal1_acta,
        vocal2_acta=vocal2_acta,
        hs_cat_total=hs_cat_total,
        nivel_curso=nivel_curso,
        certificacion=certificacion,
        norma_aprobacion=norma_aprobacion,
        resolucion_disenio=resolucion_disenio,
        validez_nacional=validez_nacional,
        disposicion=disposicion,
        referencial_ingreso=referencial_ingreso,
        familia_profesional=familia_profesional,
        curso_anio=curso_num,
        division_letra=div_letra
    )

def _importar_planilla_rac(hojas: Dict[str, Dict[Tuple[int, int], Any]], nombre_archivo: str) -> Dict[str, Any]:
    rac = hojas["RAC"]
    establecimiento = str(_celda(rac, "C2") or "Escuela Profesional").strip()
    # Soportar tanto versión donde CUE está en M2 y Localidad en J2 como donde CUE está en J2
    val_j2 = str(_celda(rac, "J2") or "").strip()
    val_m2 = str(_celda(rac, "M2") or "").strip()
    if re.search(r"\d{5,}", val_m2):
        cue = re.sub(r"\D", "", val_m2)[:7] or "3800006"
        localidad = val_j2 or "Jujuy"
    else:
        cue = re.sub(r"\D", "", val_j2)[:7] or "3800006"
        localidad = str(_celda(rac, "N2") or "Jujuy").strip()
    domicilio = str(_celda(rac, "Q2") or "").strip()
    oferta = str(_celda(rac, "C3") or "Oferta Formativa").strip()
    val_j3 = str(_celda(rac, "J3") or "").strip()
    val_m3 = str(_celda(rac, "M3") or "").strip()
    if re.match(r"^20\d{2}$", val_j3):
        ciclo = val_j3
        libro = val_m3 or "1"
    else:
        libro = val_j3 or "1"
        ciclo = str(_celda(rac, "N3") or "2026").strip()
    turno_raw = str(_celda(rac, "C4") or "Vespertino").strip()
    turno = "Vespertino" if _norm(turno_raw) in ("noche", "nocturno", "vespertino") else turno_raw
    division = str(_celda(rac, "J4") or _celda(rac, "N4") or '1º "U"').strip()
    disenio = str(_celda(rac, "C5") or "Res. Ministerial").strip()

    modulos = []
    for i in range(10):
        col = 18 + i
        per_raw = str(_celda(rac, 7, col) or "1C").strip()
        nom = str(_celda(rac, 8, col) or "").strip()
        if nom:
            p_low = per_raw.lower()
            if "2" in p_low:
                periodo = "2° Cuatrimestre"
                periodo_corto = "2°C"
                cuat = 2
            elif "3" in p_low:
                periodo = "3° Cuatrimestre"
                periodo_corto = "3°C"
                cuat = 3
            elif "unico" in _norm(p_low):
                periodo = "Cuatrimestre único"
                periodo_corto = "1C"
                cuat = 1
            else:
                periodo = "1° Cuatrimestre"
                periodo_corto = "1°C"
                cuat = 1
            modulos.append({
                "i": len(modulos),
                "col_rac": col,
                "nombre": nom,
                "periodo": periodo,
                "periodoCorto": periodo_corto,
                "cuatrimestre": cuat,
                "tipo": "Común" if len(modulos) < 3 else "Específico"
            })
    if not modulos:
        modulos = [
            {
                "i": i,
                "col_rac": 18 + i,
                "nombre": f"Módulo {i+1}",
                "periodo": "1° Cuatrimestre",
                "periodoCorto": "1°C",
                "cuatrimestre": 1,
                "tipo": "Común" if i < 2 else "Específico"
            }
            for i in range(6)
        ]

    estudiantes = []
    for r in range(9, 60):
        ape = str(_celda(rac, r, 2) or "").strip()
        nom = str(_celda(rac, r, 3) or "").strip()
        dni = re.sub(r"\D", "", str(_celda(rac, r, 7) or ""))
        if not (ape or nom or dni):
            continue
        notas_est = []
        for m in modulos:
            v = _celda(rac, r, m.get("col_rac", 18 + m["i"]))
            notas_est.append(str(int(round(v))) if isinstance(v, (int, float)) else str(v or "").strip())
        nota_final, situacion = _calcular_situacion_y_promedio(notas_est)
        estudiantes.append({
            "fila": r,
            "orden": str(len(estudiantes) + 1),
            "apellido": ape.upper(),
            "nombres": nom,
            "documento": dni or str(r),
            "tipoDoc": str(_celda(rac, r, 6) or "DNI"),
            "fechaNac": _excel_serial_a_fecha(_celda(rac, r, 4)),
            "localidad": str(_celda(rac, r, 9) or localidad),
            "provincia": str(_celda(rac, r, 11) or "Jujuy"),
            "pais": _normalizar_pais(_celda(rac, r, 5)),
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
            "fechaNac": _excel_serial_a_fecha(_celda(hoja, r, 5) or _celda(hoja, r, 6)),
            "localidad": "Jujuy",
            "provincia": str(_celda(hoja, r, 8) or "Jujuy").strip(),
            "pais": _normalizar_pais(_celda(hoja, r, 9) or "Argentina"),
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
    libro: str = "1",
    folio: str = "1",
    fecha_acta: str = "",
    presidente_acta: str = "Presidente/a de Mesa",
    vocal1_acta: str = "Vocal 1°",
    vocal2_acta: str = "Vocal 2°",
    hs_cat_total: str = "510",
    nivel_curso: str = "II",
    certificacion: str = "Diseño Curricular Jurisdiccional",
    norma_aprobacion: str = "—",
    resolucion_disenio: str = "",
    validez_nacional: str = "—",
    disposicion: str = "-",
    referencial_ingreso: str = "Primaria Completa",
    familia_profesional: str = "—",
    curso_anio: str = "1°",
    division_letra: str = '"U"'
) -> Dict[str, Any]:
    fecha_mesa_final = fecha_acta or datetime.datetime.now().strftime("%d/%m/%Y")
    return {
        "resumenCurso": {
            "cue": cue,
            "institucion": establecimiento,
            "oferta": oferta,
            "familiaProfesional": familia_profesional,
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
                "familiaProfesional": familia_profesional,
                "ciclo": ciclo,
                "libro": libro,
                "folio": folio,
                "fechaActa": fecha_mesa_final,
                "turno": turno,
                "cursoAnio": curso_anio,
                "divisionLetra": division_letra,
                "matriculados": str(len(estudiantes)),
                "division": division,
                "disenio": disenio,
                "hsCatTotal": hs_cat_total,
                "nivelCurso": nivel_curso,
                "certificacion": certificacion,
                "normaAprobacion": norma_aprobacion if norma_aprobacion != "—" else disenio,
                "resolucionDisenio": resolucion_disenio or disenio,
                "validezNacional": validez_nacional,
                "disposicion": disposicion,
                "referencialIngreso": referencial_ingreso
            },
            "modulos": modulos,
            "estudiantes": estudiantes
        },
        "actaCurso": {
            "mesa": {
                "fecha": fecha_mesa_final,
                "presidente": presidente_acta,
                "vocal1": vocal1_acta,
                "vocal2": vocal2_acta
            },
            "estudiantes": acta_estudiantes
        }
    }
