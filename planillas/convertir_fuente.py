# -*- coding: utf-8 -*-
"""
CONVERTIDOR DE LIBRO MATRIZ FP  ->  PLANILLA PARA GOOGLE DRIVE
Dirección de Educación Técnico Profesional - Jujuy

Toma el libro matriz original de un curso (.xlsm o .xlsx, el que tiene las pestañas
Portada, Estudiantes, Reg Notas, Datos2, Acta Examen y L Matriz) y genera la planilla
nueva (RAC, Acta de Examen, Analítico y Catálogo) lista para subir a Drive.

USO
  1) Una sola vez:   pip install openpyxl
  2) Convertir:      python convertir_libro.py "Confeccionista a Medida - T Vesp - 2025.xlsm"
     (se pueden pasar varios archivos juntos, o arrastrarlos sobre el .py en Windows)
  3) Se crea "<nombre original> - Drive.xlsx" en la misma carpeta. Arrastrarlo a la
     carpeta de la escuela en Drive: se convierte solo en Hoja de cálculo de Google.

Qué hace
  - Datos del curso: establecimiento (lo busca por CUE), oferta, turno, año, curso/división, libro.
  - Estudiantes: datos personales (sin edad ni sexo).
  - Notas finales de cada módulo (de la hoja Datos2).
  - Acta de examen: fecha, mesa, permiso y notas teórica y práctica.
  - Si la oferta no está en el Catálogo, la agrega con sus módulos (las horas por módulo
    quedan en blanco para completar a mano).
Al terminar muestra un resumen y avisa lo que no pudo pasar.
"""
import base64, io, os, re, sys, unicodedata, datetime as dt

try:
    import openpyxl
except ImportError:
    sys.exit("Falta openpyxl. Instalalo con:  pip install openpyxl")

PLANTILLA_B64 = "__PLANTILLA__"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
F1, FN = 9, 48                      # filas de estudiantes en Matrícula
A1 = 13                             # primera fila de estudiantes en el Acta
NMOD = 8                            # módulos por oferta en la planilla
COL_NOTA1 = 18                      # columna R = Módulo 1
NIVELES = {"primario completo": "Primario completo", "primario incompleto": "Primario incompleto",
           "secundario completo": "Secundario completo", "secundario incompleto": "Secundario incompleto"}


def norm(t):
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def limpio(v):
    return v.strip() if isinstance(v, str) else v


def nota_valida(v):
    return v if isinstance(v, (int, float)) and 1 <= v <= 10 else None


def convertir(ruta):
    avisos = []
    src = openpyxl.load_workbook(ruta, data_only=True)
    for h in ("Portada", "Estudiantes", "Reg Notas", "Datos2"):
        if h not in src.sheetnames:
            raise ValueError(f"no tiene la pestaña '{h}'; no parece un libro matriz FP")
    po, es, rn, d2 = src["Portada"], src["Estudiantes"], src["Reg Notas"], src["Datos2"]

    wb = openpyxl.load_workbook(io.BytesIO(base64.b64decode(PLANTILLA_B64)))
    mat, act, ana, cat = wb["RAC"], wb["Acta de Examen"], wb["Analítico"], wb["Catálogo"]

    # ---------- ubicar tablas del Catálogo ----------
    fila_nota = next(r for r in range(4, 200) if cat[f"A{r}"].value == "Nota mínima de aprobación")
    of_filas = range(4, fila_nota - 1)
    ls = fila_nota + 3                                   # primera fila de las listas
    est_filas = [r for r in range(ls, ls + 200) if cat[f"A{r}"].value]
    turnos = [cat[f"D{r}"].value for r in range(ls, ls + 10) if cat[f"D{r}"].value]

    # ---------- módulos del libro original (Reg Notas, fila 12) ----------
    bloques = []   # (desplazamiento a Datos2, col DNI en Datos2, período)
    mods = []      # (nombre, tipo, período, columna de la nota en Datos2, col DNI en Datos2)
    for k, (c0, c1, dni_col) in enumerate([(17, 41, 2), (58, 82, 47), (99, 123, 79)]):
        esp = next((c for c in range(c0, c1 + 1) if norm(rn.cell(11, c).value) == "especificos"), c1 + 1)
        for c in range(c0, c1 + 1, 2):
            nom = limpio(rn.cell(12, c).value)
            if nom and nom != "-":
                mods.append([nom, "Común" if c < esp else "Específico", k, c - 9 * k, dni_col])
    if not mods:
        raise ValueError("no encontré módulos en la fila 12 de 'Reg Notas'")
    usados = sorted({m[2] for m in mods})
    nombres_per = {0: "1° Cuatrimestre", 1: "2° Cuatrimestre", 2: "3° Cuatrimestre"}
    for m in mods:
        m[2] = "Cuatrimestre único" if len(usados) == 1 else nombres_per[m[2]]
    if len(mods) > NMOD:
        avisos.append(f"la oferta tiene {len(mods)} módulos; la planilla muestra los primeros {NMOD}")

    # ---------- oferta ----------
    oferta = limpio(po["A14"].value) or ""
    fila_of = next((r for r in of_filas if norm(cat[f"A{r}"].value) == norm(oferta)), None)
    if fila_of is None:
        fila_of = next((r for r in of_filas if not cat[f"A{r}"].value), None)
        if fila_of is None:
            raise ValueError("el Catálogo no tiene filas libres para agregar la oferta")
        hc = po["A18"].value if isinstance(po["A18"].value, (int, float)) else None
        for col, v in zip("ABCDEFGHI", [oferta, limpio(po["A20"].value), "", "", limpio(po["A16"].value),
                                        limpio(po["C18"].value), limpio(po["I14"].value),
                                        round(hc * 2 / 3) if hc else None, hc]):
            cat[f"{col}{fila_of}"] = v
        ult = max(r for r in range(4, 400) if cat[f"N{r}"].value)
        for i, (nom, tipo, per, _, _) in enumerate(mods, 1):
            r = ult + i
            for c in "NOPQRSTU":
                cat[f"{c}{r}"]._style = cat[f"{c}{ult}"]._style
            cat[f"N{r}"] = oferta
            cat[f"O{r}"] = f"=COUNTIF($N$4:$N{r},$N{r})"
            cat[f"P{r}"], cat[f"Q{r}"], cat[f"R{r}"] = per, tipo, nom
        avisos.append(f"la oferta '{oferta}' no estaba en el Catálogo: se agregó con {len(mods)} módulos "
                      "(completar en el Catálogo las horas de cada módulo y la fecha de la resolución)")
        orden = list(range(len(mods)))
    else:
        oferta = cat[f"A{fila_of}"].value
        cat_mods = [cat[f"R{r}"].value for r in range(4, 400) if cat[f"N{r}"].value == oferta]
        orden = []
        for cm in cat_mods:
            j = next((i for i, m in enumerate(mods) if norm(m[0]) == norm(cm)), None)
            orden.append(j)
        if None in orden:
            avisos.append("algunos módulos no coinciden por nombre con el Catálogo; se tomaron en el mismo orden")
            orden = list(range(min(len(mods), len(cat_mods))))

    # ---------- encabezado del curso ----------
    cue = re.sub(r"\D", "", str(po["I6"].value or ""))
    nombre_est = limpio(po["A4"].value)
    fila_est = next((r for r in est_filas if cue and str(cat[f"C{r}"].value or "") == cue), None) \
        or next((r for r in est_filas if norm(cat[f"A{r}"].value) == norm(nombre_est)), None)
    if fila_est:
        mat["C2"] = cat[f"A{fila_est}"].value
        if not cat[f"B{fila_est}"].value and limpio(po["E8"].value):
            cat[f"B{fila_est}"] = limpio(po["E8"].value)      # localidad que faltaba en el Catálogo
    else:
        mat["C2"] = nombre_est
        avisos.append(f"el establecimiento '{nombre_est}' (CUE {cue}) no está en el Catálogo: elegilo de la lista")
    mat["C3"] = oferta
    if limpio(po["A6"].value):
        mat["Q2"] = limpio(po["A6"].value)
    turno = limpio(po["A22"].value)
    mat["C4"] = next((t for t in turnos if norm(t) == norm(turno)), turno)
    mat["J3"] = po["I4"].value
    curso = po["D22"].value
    if isinstance(curso, (int, float)):
        curso = f"{int(curso)}°"
    mat["J4"] = " ".join(str(limpio(x)) for x in (curso, po["G22"].value) if x)
    if "L Matriz" in src.sheetnames and src["L Matriz"]["C1"].value:
        mat["M3"] = src["L Matriz"]["C1"].value

    # ---------- notas finales (Datos2) ----------
    notas = {}                     # dni -> {índice de módulo: nota}
    for i, (_, _, _, col, dni_col) in enumerate(mods):
        for r in range(5, 200):
            dni = d2.cell(r, dni_col).value
            if isinstance(dni, (int, float)):
                v = nota_valida(d2.cell(r, col).value)
                if v is not None:
                    notas.setdefault(int(dni), {})[i] = v

    # ---------- estudiantes ----------
    fila, pos, sin_nota = F1, {}, 0
    for r in range(4, 300):
        ape = limpio(es[f"B{r}"].value)
        if not ape or not isinstance(ape, str) or norm(ape) in ("apellido",):
            continue
        if fila > FN:
            avisos.append(f"hay más de {FN - F1 + 1} estudiantes; se pasaron los primeros {FN - F1 + 1}")
            break
        g = lambda c: limpio(es[f"{c}{r}"].value)
        dni = g("I")
        nac = g("G")
        if isinstance(nac, str) and norm(nac) in ("arg", "argentina", "argentino", "argentina o"):
            nac = "Argentina"
        datos = {"B": ape, "C": g("C"), "D": g("F"), "E": nac, "F": g("H"), "G": dni, "H": g("R"),
                 "I": g("O"), "J": g("P"), "K": g("Q"),
                 "L": NIVELES.get(norm(g("K")), g("K")), "M": g("L"), "N": g("S"), "O": g("T"),
                 "P": "Sí" if g("U") else None, "Q": "Sí" if g("V") else None, "AA": g("X")}
        for c, v in datos.items():
            if v not in (None, ""):
                mat[f"{c}{fila}"] = v
                if isinstance(v, (dt.datetime, dt.date)):
                    mat[f"{c}{fila}"].number_format = "dd/mm/yyyy"
        n = notas.get(int(dni), {}) if isinstance(dni, (int, float)) else {}
        if not n:
            sin_nota += 1
        for k, j in enumerate(orden[:NMOD]):
            if j is not None and j in n:
                mat.cell(fila, COL_NOTA1 + k, n[j])
        if isinstance(dni, (int, float)):
            pos[int(dni)] = fila - F1
        fila += 1
    n_est = fila - F1

    # ---------- acta de examen ----------
    n_acta = 0
    if "Acta Examen" in src.sheetnames:
        ac = src["Acta Examen"]
        try:
            mes = MESES.index(norm(ac["H8"].value)) + 1
            act["C5"] = dt.date(int(ac["P8"].value), mes, int(ac["C8"].value))
            act["C5"].number_format = "dd/mm/yyyy"
        except Exception:
            avisos.append("no pude leer la fecha del acta: cargala a mano")
        mesa = str(ac["A10"].value or "")
        m = re.search(r"Presidente:\s*(.*?)\s*-\s*Vocal\s*1°\s*(.*?)\s*-\s*Vocal\s*2°\s*(.*)", mesa)
        partes = [x.strip(" .-") for x in re.split(r"[;\n]", mesa) if x.strip(" .-")]
        if m:
            act["C7"], act["G7"], act["C8"] = (x.strip() for x in m.groups())
        elif len(partes) == 3:                       # "Presidente; Vocal 1°; Vocal 2°"
            act["C7"], act["G7"], act["C8"] = partes
        elif mesa.strip():
            avisos.append("no pude separar la mesa examinadora del acta: cargala a mano")
        for r in range(15, 120):
            dni = ac[f"E{r}"].value
            if not isinstance(dni, (int, float)):
                continue
            if int(dni) not in pos:
                avisos.append(f"el DNI {int(dni)} está en el acta pero no en Estudiantes")
                continue
            rr = A1 + pos[int(dni)]
            if ac[f"C{r}"].value:
                act[f"B{rr}"] = ac[f"C{r}"].value
            for src_c, dst_c in (("P", "E"), ("S", "G")):
                v = ac[f"{src_c}{r}"].value
                if isinstance(v, str) and v.strip().upper() in ("A", "AUS", "AUSENTE"):
                    v = "AUS"
                if v not in (None, "", " "):
                    act[f"{dst_c}{rr}"] = v
            n_acta += 1

    if pos:                                              # el Analítico arranca mostrando al primer estudiante
        ana["L2"] = next(iter(pos))
    wb.calculation.fullCalcOnLoad = True                 # que Excel/Sheets recalculen todo al abrir
    if "L Matriz" in src.sheetnames:                     # folio del estudiante que muestra el L Matriz
        lm = src["L Matriz"]
        if isinstance(lm["Q3"].value, (int, float)) and int(lm["Q3"].value) in pos and lm["R1"].value:
            mat.cell(F1 + pos[int(lm["Q3"].value)], 28, lm["R1"].value)
    salida = os.path.splitext(ruta)[0] + " - Drive.xlsx"
    wb.save(salida)
    return salida, n_est, n_acta, sin_nota, avisos


def main():
    archivos = sys.argv[1:]
    if not archivos:
        print(__doc__)
        input("Enter para salir...")
        return
    for a in archivos:
        print(f"\n== {os.path.basename(a)}")
        try:
            sal, n_est, n_acta, sin_nota, avisos = convertir(a)
            print(f"   Listo: {sal}")
            print(f"   {n_est} estudiantes, {n_acta} en el acta, {sin_nota} sin notas cargadas")
            for x in avisos:
                print("   AVISO:", x)
        except Exception as e:
            print("   ERROR:", e)
    if os.name == "nt":
        input("\nEnter para salir...")


if __name__ == "__main__":
    main()
