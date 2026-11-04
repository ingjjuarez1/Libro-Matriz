# -*- coding: utf-8 -*-
"""Libro de Formación Profesional para Google Sheets: Matrícula, Acta de Examen,
Analítico y Catálogo. Solo funciones clásicas (INDEX/MATCH/COUNTIF...) para que
la conversión xlsx -> Google Sheets no cambie resultados."""
import json, re, sys, datetime as dt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter as L

S = "/tmp/claude-0/-home-claude/7993c590-c5c0-5b2b-8c0f-9b1b57cacbe1/scratchpad"
sys.path.insert(0, f"{S}/dc")
import dc
import os as _os
_EXTRA = f"{S}/online/ofertas_extra.json"     # ofertas tomadas de libros existentes (sin DC en el zip)
if _os.path.exists(_EXTRA):
    for _o in json.load(open(_EXTRA, encoding="utf-8")):
        _o["comunes"] = [tuple(m) for m in _o["comunes"]]; _o["especificos"] = [tuple(m) for m in _o["especificos"]]
        dc.OFERTAS.append(_o)

SALIDA = sys.argv[1] if len(sys.argv) > 1 else f"{S}/online/Libro_FP.xlsx"
EJEMPLO = "--sin-ejemplo" not in sys.argv

# ---------- estilo único ----------
FN = "Arial"
AZUL, CELESTE, GRIS = "1F4E78", "DDEBF7", "EDEDED"
AMARILLO = None          # sin relleno en celdas de carga (pedido: sin amarillo)
fino = Side(style="thin", color="A6A6A6")
BORDE = Border(left=fino, right=fino, top=fino, bottom=fino)
LINEA_FIRMA = Border(top=Side(style="thin", color="000000"))

def st(c, v=None, *, b=False, sz=10, col="000000", fill=None, h=None, vert="center",
       wrap=False, it=False, fmt=None, borde=False, rot=0):
    if v is not None:
        c.value = v
    c.font = Font(name=FN, size=sz, bold=b, italic=it, color=col)
    if fill:
        c.fill = PatternFill("solid", fgColor=fill)
    c.alignment = Alignment(horizontal=h, vertical=vert, wrap_text=wrap, text_rotation=rot)
    if fmt:
        c.number_format = fmt
    if borde:
        c.border = BORDE
    return c

def caja(ws, rango, v=None, **kw):
    """Combina un rango y le da estilo a todas sus celdas (bordes incluidos)."""
    ws.merge_cells(rango)
    a, z = rango.split(":")
    celdas = ws[rango]
    for fila in celdas:
        for c in fila:
            st(c, **{k: x for k, x in kw.items() if k != "fmt"})
    return st(ws[a], v, **kw)

def anchos(ws, d):
    for col, w in d.items():
        ws.column_dimensions[col].width = w

def lista(ws, rango, formula, estricta=True):
    dv = DataValidation(type="list", formula1=formula, allow_blank=True,
                        showErrorMessage=estricta)
    dv.add(rango); ws.add_data_validation(dv)

wb = Workbook()
mat = wb.active; mat.title = "RAC"
act = wb.create_sheet("Acta de Examen")
ana = wb.create_sheet("Analítico")
cat = wb.create_sheet("Catálogo")
M, A, C = "'RAC'!", "'Acta de Examen'!", "'Catálogo'!"

# ======================= CATÁLOGO =======================
NOF = len(dc.OFERTAS)                      # 14 ofertas
OF1, OFN = 4, 3 + NOF + 15                 # filas de ofertas + 15 libres para ofertas nuevas
RN = OFN + 2                                # fila de la nota mínima
MOD1, MODN = 4, 150                        # rango de módulos (con margen)
anchos(cat, {"A": 58, "B": 24, "C": 12, "D": 12, "E": 44, "F": 7, "G": 19, "H": 9, "I": 17,
             "J": 10, "K": 12, "L": 12, "M": 3, "N": 44, "O": 5, "P": 16, "Q": 11, "R": 58,
             "S": 9, "T": 9, "U": 13})
st(cat["A1"], "CATÁLOGO DE OFERTAS Y DISEÑOS CURRICULARES", b=True, sz=13, col=AZUL)
st(cat["A2"], "Fuente: Resoluciones de Diseño Curricular Jurisdiccional N° 2104-E a 2115-E, 2133-E y 2148-E/2026, "
              "Ministerio de Educación de Jujuy, 18/09/2026 (archivo drive-download-20261005, subido 05/10/2026). "
              "Editar solo si cambia una resolución.", it=True, sz=9, col="595959")
hdr_of = ["Oferta formativa", "Resolución DC", "Fecha", "Expte.", "Familia profesional", "Nivel",
          "Duración", "Hs reloj", "Hs cátedra", "Módulos", "Inicio (aux.)", "Control hs reloj"]
for j, h in enumerate(hdr_of, 1):
    st(cat.cell(3, j), h, b=True, col="FFFFFF", fill=AZUL, h="center", wrap=True, borde=True)
for r in range(OF1, OFN + 1):
    i = r - OF1
    if i < len(dc.OFERTAS):
        o = dc.OFERTAS[i]
        vals = [o["oferta"], o["res"], o.get("fecha", dc.FECHA_RES), o["expte"], o["familia"], o["nivel"],
                o["duracion"], o["hr"], o["hc"]]
    else:
        vals = [None] * 9
    for j, v in enumerate(vals, 1):
        st(cat.cell(r, j), v, borde=True, wrap=(j == 5), h="center" if j in (2, 3, 4, 6, 8, 9) else None)
    st(cat.cell(r, 10), f'=IF($A{r}="","",COUNTIF($N${MOD1}:$N${MODN},$A{r}))', borde=True, h="center")
    st(cat.cell(r, 11), f'=IF($A{r}="","",MATCH($A{r},$N${MOD1}:$N${MODN},0))', borde=True, h="center", col="7F7F7F")
    st(cat.cell(r, 12), f'=IF($A{r}="","",IF(SUMIF($N${MOD1}:$N${MODN},$A{r},$S${MOD1}:$S${MODN})=$H{r},"OK","Revisar"))',
       borde=True, h="center")

hdr_mod = ["Oferta formativa", "N°", "Período", "Tipo", "Módulo", "Hs reloj", "Hs cátedra",
           "Práctica formativa (hs cát.)"]
for j, h in enumerate(hdr_mod, 14):
    st(cat.cell(3, j), h, b=True, col="FFFFFF", fill=AZUL, h="center", wrap=True, borde=True)
r = MOD1
for o in dc.OFERTAS:
    for (nom, hr, hc, pf, per), tipo in dc.modulos(o):
        st(cat.cell(r, 14), o["oferta"], borde=True)
        st(cat.cell(r, 15), f"=COUNTIF($N${MOD1}:$N{r},$N{r})", borde=True, h="center")
        for j, v in enumerate([per, tipo, nom, hr, hc, pf], 16):
            st(cat.cell(r, j), v, borde=True, h=None if j == 18 else "center")
        r += 1
ULT_MOD = r - 1

# parámetro y listas
st(cat[f"A{RN}"], "Nota mínima de aprobación", b=True)
st(cat[f"B{RN}"], 7, b=True, col="0000FF", fill=AMARILLO, h="center", borde=True)
LS = RN + 3                                               # primera fila de las listas
st(cat[f"A{RN + 1}"], "Listas de los desplegables. Establecimientos: Resolución R210-E-26; CUE: listado de localizaciones enviado por DETP (08/10/2026).",
   it=True, sz=9, col="595959")
for j, h in enumerate(["Establecimiento", "Localidad", "CUE", "Turno", "Estudios que acredita", "Sí / No",
                       "Tipo de documento", "Número", "En letras", "Mes", "Nombre del mes"], 1):
    st(cat.cell(LS - 1, j), h, b=True, col="FFFFFF", fill=AZUL, h="center", borde=True)

r210 = json.load(open(f"{S}/r210.json"))
def partir(nombre):
    n, loc = nombre.rsplit(" - ", 1)
    return re.sub(r'"\s*([^"]*?)\s*"', "“\\1”", n), loc
locs = {}
for inst, *_ in r210:
    n, loc = partir(inst); locs.setdefault(n, set()).add(loc)
import os
ARCH_EST = f"{S}/online/establecimientos.json"          # [nombre, localidad, cue]
if os.path.exists(ARCH_EST):
    establ = [tuple(x) for x in json.load(open(ARCH_EST, encoding="utf-8"))]
else:
    establ = []
    for inst, *_ in r210:
        n, loc = partir(inst)
        k = n if len(locs[n]) == 1 else f"{n} - {loc}"
        if (k, loc, "") not in establ:
            establ.append((k, loc, ""))
NUM = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
       "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
       "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
       "veintiocho", "veintinueve"]
for dec in ("treinta", "cuarenta"):
    NUM += [dec] + [f"{dec} y {u}" for u in NUM[1:10]]
NUM.append("cincuenta")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]
columnas = {1: [e for e, _, _ in establ], 2: [l for _, l, _ in establ], 3: [c for _, _, c in establ],
            4: ["Mañana", "Tarde", "Vespertino", "Noche"],
            5: ["Primario incompleto", "Primario completo", "Secundario incompleto", "Secundario completo",
                "Terciario / Universitario"], 6: ["Sí", "No"],
            7: ["DNI", "Pasaporte", "Cédula de identidad", "Otro"],
            8: list(range(len(NUM))), 9: NUM, 10: list(range(1, 13)), 11: MESES}
for j, vals in columnas.items():
    for i, v in enumerate(vals):
        st(cat.cell(LS + i, j), v, borde=True, h="center" if j in (3, 6, 8, 10) else None)
EST = f"{C}$A${LS}:$A${LS + len(establ) - 1}"
LOC = f"{C}$B${LS}:$B${LS + len(establ) - 1}"
CUEL = f"{C}$C${LS}:$C${LS + len(establ) - 1}"
LET = f"{C}$I${LS}:$I${LS + len(NUM) - 1}"
MES = f"{C}$K${LS}:$K${LS + 11}"
NOTA_MIN = f"{C}$B${RN}"
cat.freeze_panes = "A4"

def oc(col):   # columna de la tabla de ofertas
    return f"{C}${col}${OF1}:${col}${OFN}"
def mc(col):   # columna de la tabla de módulos
    return f"{C}${col}${MOD1}:${col}${MODN}"

# ======================= MATRÍCULA =======================
F1, FN_ = 9, 48                              # 40 estudiantes
NMOD = 8                                     # máximo de módulos de un DC
MCOL = [L(18 + k) for k in range(NMOD)]      # R..Y
NFIN = L(18 + NMOD)                          # Z: nota final (del acta)
FEGR = L(19 + NMOD)                          # AA: fecha de egreso
FOLIO = L(20 + NMOD)                         # AB: folio del libro matriz
SIT = L(21 + NMOD)                           # AC
anchos(mat, {"A": 5, "B": 16, "C": 20, "D": 11, "E": 10, "F": 9, "G": 12, "H": 7, "I": 17, "J": 14,
             "K": 11, "L": 19, "M": 10, "N": 11, "O": 9, "P": 6, "Q": 6, NFIN: 8, FEGR: 11, FOLIO: 8,
             SIT: 18, "AD": 3, "AE": 3, "AF": 3, "AG": 26, "AH": 8})
for c in MCOL:
    mat.column_dimensions[c].width = 8

caja(mat, "A1:H1", "RAC · REGISTRO ANUAL DE CALIFICACIONES", b=True, sz=14, col=AZUL)
caja(mat, "I1:U1", "Establecimiento, oferta y turno se eligen de la lista; localidad, CUE, módulos y horas "
     "salen solos del Catálogo. Los estudiantes se cargan desde la fila 9.",
     it=True, sz=9, col="595959", wrap=True)
mat.row_dimensions[1].height = 30

def etiqueta(ws, rango, txt):
    caja(ws, rango, txt, b=True, fill=CELESTE, borde=True)
def entrada(ws, rango, v=None, **kw):
    return caja(ws, rango, v, col="0000FF", fill=AMARILLO, borde=True, **kw)
def calculo(ws, rango, v, **kw):
    return caja(ws, rango, v, borde=True, **kw)

etiqueta(mat, "A2:B2", "Establecimiento"); entrada(mat, "C2:H2")
etiqueta(mat, "I2:I2", "Localidad")
calculo(mat, "J2:K2", f'=IFERROR(INDEX({LOC},MATCH($C$2,{EST},0))&"","")')
etiqueta(mat, "N2:P2", "Domicilio del establecimiento"); entrada(mat, "Q2:AB2")
etiqueta(mat, "L2:L2", "CUE")
calculo(mat, "M2:M2", f'=IFERROR(INDEX({CUEL},MATCH($C$2,{EST},0))&"","")', h="center")
etiqueta(mat, "A3:B3", "Oferta formativa"); entrada(mat, "C3:H3")
etiqueta(mat, "I3:I3", "Ciclo lectivo"); entrada(mat, "J3:J3", h="center")
etiqueta(mat, "L3:L3", "Libro Matriz N°"); entrada(mat, "M3:M3", h="center")
etiqueta(mat, "A4:B4", "Turno"); entrada(mat, "C4:C4")
etiqueta(mat, "D4:E4", "Matriculados")
calculo(mat, "F4:F4", f'=COUNTIF($C${F1}:$C${FN_},"?*")', h="center")
etiqueta(mat, "I4:I4", "Curso / División"); entrada(mat, "J4:J4", h="center")
etiqueta(mat, "A5:B5", "Diseño curricular")
ix = lambda col: f"INDEX({oc(col)},$AH$2)"
calculo(mat, "C5:U5",
        f'=IF($AH$2="","Elegí la oferta formativa en C3.","Res. "&{ix("B")}&IF({ix("C")}="",""," del "&{ix("C")})'
        f'&"  ·  Familia: "&{ix("E")}&"  ·  Nivel "&{ix("F")}&"  ·  "&{ix("G")}&"  ·  "&{ix("H")}'
        f'&" hs reloj ("&{ix("I")}&" hs cátedra)  ·  "&$AH$3&" módulos")', sz=9)

# auxiliares
st(mat["AG1"], "Auxiliares (no editar)", b=True, sz=9, col="7F7F7F")
aux = [("Fila de la oferta", f'=IFERROR(MATCH($C$3,{oc("A")},0),"")'),
       ("Cantidad de módulos", f'=IF($AH$2="",0,INDEX({oc("J")},$AH$2))'),
       ("Inicio en Catálogo", f'=IF($AH$2="","",INDEX({oc("K")},$AH$2))'),
       ("Nota mínima de aprobación", f"={NOTA_MIN}")]
for i, (t, f) in enumerate(aux, 2):
    st(mat[f"AG{i}"], t, sz=9, col="7F7F7F", borde=True)
    st(mat[f"AH{i}"], f, sz=9, col="7F7F7F", h="center", borde=True)

# encabezados de la tabla
caja(mat, "A6:K6", "DATOS PERSONALES", b=True, col="FFFFFF", fill=AZUL, h="center", borde=True)
caja(mat, "L6:Q6", "ESTUDIOS E INSCRIPCIÓN", b=True, col="FFFFFF", fill=AZUL, h="center", borde=True)
caja(mat, f"R6:{MCOL[-1]}6", "CALIFICACIONES POR MÓDULO (1 a 10, según el diseño curricular)",
     b=True, col="FFFFFF", fill=AZUL, h="center", borde=True)
caja(mat, f"{NFIN}6:{NFIN}8", "Nota final (examen)", b=True, col="FFFFFF", fill=AZUL, h="center", wrap=True, borde=True, rot=90)
caja(mat, f"{FEGR}6:{FEGR}8", "Fecha de egreso", b=True, col="FFFFFF", fill=AZUL, h="center", wrap=True, borde=True)
caja(mat, f"{FOLIO}6:{FOLIO}8", "Folio N°", b=True, col="FFFFFF", fill=AZUL, h="center", wrap=True, borde=True)
caja(mat, f"{SIT}6:{SIT}8", "Situación", b=True, col="FFFFFF", fill=AZUL, h="center", borde=True)
simples = {"A": "N°", "B": "Apellido", "C": "Nombres", "D": "Fecha de nacimiento",
           "E": "Nacionalidad", "F": "Tipo doc.", "G": "N° documento",
           "H": "Teléfono de urgencia", "N": "Fecha de inscripción", "O": "N° solicitud",
           "P": "Con discapacidad", "Q": "Acompañamiento"}
VERTICAL = {"E", "H", "P", "Q"}                 # títulos largos en columnas angostas: texto girado
for col, t in simples.items():
    caja(mat, f"{col}7:{col}8", t, b=True, fill=CELESTE, h="center", wrap=True, borde=True,
         rot=90 if col in VERTICAL else 0)
caja(mat, "I7:K7", "Lugar de nacimiento", b=True, fill=CELESTE, h="center", borde=True)
caja(mat, "L7:M7", "Estudios que acredita", b=True, fill=CELESTE, h="center", borde=True)
for col, t in {"I": "Localidad", "J": "Departamento", "K": "Provincia", "L": "Nivel", "M": "Provincia"}.items():
    st(mat[f"{col}8"], t, b=True, fill=CELESTE, h="center", borde=True)
for c in MCOL:
    k = f"COLUMNS($R$7:{c}7)"
    per = f'SUBSTITUTE(SUBSTITUTE(INDEX({mc("P")},$AH$4+{k}-1),"Cuatrimestre único","C. único"),"Cuatrimestre","C")'
    st(mat[f"{c}7"], f'=IF({k}>$AH$3,"","Mód. "&{k}&" - "&{per})',
       b=True, sz=8, fill=CELESTE, h="center", wrap=True, borde=True)
    k = f"COLUMNS($R$8:{c}8)"
    st(mat[f"{c}8"], f'=IF({k}>$AH$3,"",INDEX({mc("R")},$AH$4+{k}-1))',
       b=True, sz=8, fill=CELESTE, h="center", wrap=True, borde=True, rot=90)
mat.row_dimensions[7].height = 26
mat.row_dimensions[8].height = 120

fechas = {"D", "N"}
for r in range(F1, FN_ + 1):
    st(mat[f"A{r}"], f'=IF($C{r}="","",COUNTIF($C${F1}:$C{r},"?*"))', h="center", borde=True)
    # celdas de carga sin estilo propio (el amarillo lo da un formato condicional): archivo más liviano
    st(mat[f"{NFIN}{r}"], f'=IF($C{r}="","",IF({A}$I{r + 4}="","",{A}$I{r + 4}))', b=True, h="center", borde=True)
    st(mat[f"{FEGR}{r}"], fmt="dd/mm/yyyy", h="center")
    st(mat[f"{FOLIO}{r}"], h="center")
    cuenta = f'COUNTIF($R{r}:${MCOL[-1]}{r},">="&$AH$5)'
    st(mat[f"{SIT}{r}"], f'=IF(OR($C{r}="",$AH$3=0),"",IF({cuenta}>=$AH$3,"Aprobó todos",'
                          f'"Adeuda "&($AH$3-{cuenta})&" módulo(s)"))', borde=True, sz=9)

R = f"{F1}:{{}}{FN_}"
lista(mat, "C2", EST)
lista(mat, "C3", oc("A"))
lista(mat, "C4", f"{C}$D${LS}:$D${LS + 3}")
lista(mat, f"F{F1}:F{FN_}", f"{C}$G${LS}:$G${LS + 3}")
lista(mat, f"L{F1}:L{FN_}", f"{C}$E${LS}:$E${LS + 4}")
lista(mat, f"P{F1}:Q{FN_}", f"{C}$F${LS}:$F${LS + 1}")
dv = DataValidation(type="custom", allow_blank=True, showErrorMessage=True, errorTitle="Nota",
                    error="Nota entera de 1 a 10, o AUS si estuvo ausente.",
                    formula1=f'OR({MCOL[0]}{F1}="AUS",AND(ISNUMBER({MCOL[0]}{F1}),{MCOL[0]}{F1}>=1,{MCOL[0]}{F1}<=10,INT({MCOL[0]}{F1})={MCOL[0]}{F1}))')
dv.add(f"R{F1}:{MCOL[-1]}{FN_}"); mat.add_data_validation(dv)
gris = PatternFill("solid", fgColor=GRIS, bgColor=GRIS)
mat.conditional_formatting.add(f"R{F1}:{MCOL[-1]}{FN_}", FormulaRule(formula=[f'R$8=""'], fill=gris, stopIfTrue=True))
mat.conditional_formatting.add(f"R{F1}:{MCOL[-1]}{FN_}",
                               FormulaRule(formula=[f"AND(ISNUMBER(R{F1}),R{F1}<$AH$5)"], font=Font(color="C00000", bold=True)))
mat.freeze_panes = f"D{F1}"
mat.page_setup.orientation = "landscape"; mat.page_setup.paperSize = mat.PAPERSIZE_A4
mat.page_setup.fitToWidth = 1; mat.page_setup.fitToHeight = 0
mat.sheet_properties.pageSetUpPr.fitToPage = True

# ======================= ACTA DE EXAMEN =======================
A1_ = 13                                      # fila del 1er estudiante en el acta
AN = A1_ + (FN_ - F1)
anchos(act, {"A": 8, "B": 10, "C": 13, "D": 34, "E": 7, "F": 12, "G": 7, "H": 12, "I": 9, "J": 12})
caja(act, "A1:J1", "ACTA DE EXAMEN DE ALUMNOS REGULARES", b=True, sz=13, h="center", col=AZUL)
act.row_dimensions[1].height = 24
etiqueta(act, "A2:B2", "Establecimiento")
calculo(act, "C2:J2", f'={M}$C$2&IF({M}$M$2="",""," · CUE "&{M}$M$2)')
etiqueta(act, "A3:B3", "De")
calculo(act, "C3:J3", f'={M}$C$3&""', b=True)
etiqueta(act, "A4:B4", "Correspondiente al")
calculo(act, "C4:J4", f'=IF({M}$AH$2="","",INDEX({oc("G")},{M}$AH$2))&"  ·  Curso / División: "&{M}$J$4'
                      f'&"  ·  Turno: "&{M}$C$4&"  ·  Ciclo lectivo: "&{M}$J$3')
etiqueta(act, "A5:B5", "Fecha del examen"); entrada(act, "C5:C5", h="center", fmt="dd/mm/yyyy")
caja(act, "A6:J6", f'=IF($C$5="","A los ____ días del mes de __________ de ______",IF(DAY($C$5)=1,"Al 1 día","A los "&DAY($C$5)&" días")'
                   f'&" del mes de "&INDEX({MES},MONTH($C$5))&" de "&YEAR($C$5))&", reunida la comisión '
                   f'examinadora del Trayecto Formativo con asistencia de sus tres miembros señores:"', wrap=True)
act.row_dimensions[6].height = 28
etiqueta(act, "A7:B7", "Presidente/a"); entrada(act, "C7:D7")
etiqueta(act, "E7:F7", "Vocal 1°"); entrada(act, "G7:J7")
etiqueta(act, "A8:B8", "Vocal 2°"); entrada(act, "C8:D8")
caja(act, "A9:J9", "procedió a cumplir su cometido con el resultado que se consigna a continuación:")
caja(act, "A10:J10", "NOTA: Será considerada como fraudulenta toda enmienda o raspadura que no haya sido salvada "
     "expresamente con la firma de todos los miembros de la mesa. El número de alumnos examinados se anotará "
     "con letras y números.", it=True, sz=8, wrap=True)
act.row_dimensions[10].height = 24
H = dict(b=True, sz=9, fill=CELESTE, h="center", wrap=True, borde=True)
for col, t in {"A": "N° de orden", "B": "Permiso de examen N°", "C": "N° doc. de identidad",
               "D": "APELLIDO Y NOMBRE"}.items():
    caja(act, f"{col}11:{col}12", t, **H)
for c1, c2, t in [("E", "F", "EXAMEN TEÓRICO"), ("G", "H", "EXAMEN PRÁCTICO"), ("I", "J", "CALIFICACIÓN DEFINITIVA")]:
    caja(act, f"{c1}11:{c2}11", t, **H)
    st(act[f"{c1}12"], "N°", **H); st(act[f"{c2}12"], "Letras", **H)
act.row_dimensions[11].height = 26

def letras(ref):
    return (f'IF({ref}="","",IF(ISNUMBER({ref}),PROPER(INDEX({LET},{ref}+1)),'
            f'IF({ref}="AUS","AUSENTE",{ref})))')
for i in range(FN_ - F1 + 1):
    r, m = A1_ + i, F1 + i
    st(act[f"A{r}"], f"={M}$A{m}", h="center", borde=True)
    st(act[f"B{r}"], fill=AMARILLO, col="0000FF", h="center", borde=True)
    st(act[f"C{r}"], f'=IF({M}$C{m}="","",{M}$G{m})', h="center", borde=True, fmt="0")
    st(act[f"D{r}"], f'=IF({M}$C{m}="","",{M}$B{m}&", "&{M}$C{m})', borde=True)
    for c in "EG":
        st(act[f"{c}{r}"], fill=AMARILLO, col="0000FF", h="center", borde=True)
    st(act[f"F{r}"], "=" + letras(f"E{r}"), sz=9, borde=True)
    st(act[f"H{r}"], "=" + letras(f"G{r}"), sz=9, borde=True)
    e, g = f"E{r}", f"G{r}"
    st(act[f"I{r}"], f'=IF(OR({e}="",{g}=""),"",IF(OR({e}="AUS",{g}="AUS"),"AUS",IF(AND({e}="AD",{g}="AD"),"AD",'
                     f'IF(AND({e}="AE",{g}="AE"),"AE",IF(AND({e}="AP",{g}="AP"),"AP",'
                     f'IFERROR(ROUNDDOWN(AVERAGE({e},{g}),0),"Revisar"))))))', b=True, h="center", borde=True)
    st(act[f"J{r}"], "=" + letras(f"I{r}"), sz=9, borde=True)
for c in "EG":
    dv = DataValidation(type="custom", allow_blank=True, showErrorMessage=True, errorTitle="Calificación",
                        error="Nota entera de 1 a 10, o AUS (ausente), AD, AE, AP.",
                        formula1=f'OR({c}{A1_}="AUS",{c}{A1_}="AD",{c}{A1_}="AE",{c}{A1_}="AP",'
                                 f'AND(ISNUMBER({c}{A1_}),{c}{A1_}>=1,{c}{A1_}<=10,INT({c}{A1_})={c}{A1_}))')
    dv.add(f"{c}{A1_}:{c}{AN}"); act.add_data_validation(dv)

DEF = f"$I${A1_}:$I${AN}"
c0 = AN + 2                                     # bloque de totales
tot = [("Aprobados", f'=COUNTIF({DEF},">="&{NOTA_MIN})'),
       ("Desaprobados", f'=COUNTIF({DEF},"<"&{NOTA_MIN})'),
       ("Ausentes", f'=COUNTIF({DEF},"AUS")'),
       ("Total", f"=SUM(E{c0}:E{c0 + 2})")]
for i, (t, f) in enumerate(tot):
    st(act[f"D{c0 + i}"], t, b=True, h="right")
    st(act[f"E{c0 + i}"], f, b=True, h="center", borde=True)
num = lambda ref: f'INDEX({LET},{ref}+1)&" ("&{ref}&")"'
caja(act, f"A{c0 + 5}:J{c0 + 6}",
     f'="Se hace constar que sobre un total de "&{num(f"E{c0 + 3}")}&" alumnos/as, resultaron "&{num(f"E{c0}")}'
     f'&" aprobados/as, "&{num(f"E{c0 + 1}")}&" desaprobados/as y "&{num(f"E{c0 + 2}")}&" ausentes."',
     wrap=True, vert="top")
fr = c0 + 10
for rango, t in [(f"A{fr}:B{fr}", "Vocal 2°"), (f"D{fr}:D{fr}", "Presidente/a de mesa"), (f"F{fr}:I{fr}", "Vocal 1°")]:
    caja(act, rango, t, b=True, h="center")
    a, z = rango.split(":")
    for fila in act[rango.replace(str(fr), str(fr))]:
        for c in fila:
            c.border = LINEA_FIRMA
    caja(act, rango.replace(str(fr), str(fr + 1)), "Firma y aclaración", sz=8, h="center", col="595959")
act.print_area = f"A1:J{fr + 1}"
act.page_setup.paperSize = act.PAPERSIZE_A4; act.page_setup.fitToWidth = 1; act.page_setup.fitToHeight = 0
act.sheet_properties.pageSetUpPr.fitToPage = True

# ======================= ANALÍTICO =======================
anchos(ana, {"A": 5, "B": 42, "C": 11, "D": 16, "E": 8, "F": 8, "G": 7, "H": 11, "I": 13, "J": 3, "K": 28, "L": 14})
# panel de control fuera del área de impresión
st(ana["K1"], "Panel (no se imprime)", b=True, sz=9, col="7F7F7F")
etiqueta(ana, "K2:K2", "DNI del/la estudiante (elegir)"); entrada(ana, "L2:L2", h="center", fmt="0")
etiqueta(ana, "K3:K3", "Fecha de emisión"); entrada(ana, "L3:L3", h="center", fmt="dd/mm/yyyy")
etiqueta(ana, "K4:K4", "N° de certificado"); entrada(ana, "L4:L4", h="center")
st(ana["K5"], "Fila en RAC (auxiliar)", sz=9, col="7F7F7F", borde=True)
st(ana["L5"], f'=IFERROR(MATCH($L$2,{M}$G${F1}:$G${FN_},0),"")', sz=9, col="7F7F7F", h="center", borde=True)
lista(ana, "L2", f"{M}$G${F1}:$G${FN_}")

caja(ana, "A1:E1", f'="Libro N° "&IF({M}$M$3="","____",{M}$M$3)&"     Folio N° "&IF($L$5="","____",IF(INDEX({M}${FOLIO}${F1}:${FOLIO}${FN_},$L$5)="","____",INDEX({M}${FOLIO}${F1}:${FOLIO}${FN_},$L$5)))', b=True, sz=11)
caja(ana, "G1:I1", '=$L$4&""', h="right", sz=11)
caja(ana, "A2:I2", "República Argentina", b=True, sz=24, h="center")
ana.row_dimensions[2].height = 36
for i, (t, sz) in enumerate([("LEY DE EDUCACIÓN NACIONAL N° 26.206", 11), ("PROVINCIA DE JUJUY", 11), (None, 6),
                             ("LEY PROVINCIAL N°5807", 11), ("MINISTERIO DE EDUCACIÓN", 11),
                             ("SECRETARIA GESTIÓN EDUCATIVA", 11)], 3):
    if t:
        caja(ana, f"A{i}:I{i}", t, b=True, sz=sz, h="center")

def dato(col):
    return f"INDEX({M}${col}${F1}:${col}${FN_},$L$5)"
def sec(fila, t):
    caja(ana, f"A{fila}:I{fila}", t, b=True, col="FFFFFF", fill=AZUL, borde=True)

fn = dato("D")
dni = dato("G")
dni_fmt = (f'IF(ISNUMBER({dni}),IF({dni}>=1000000,INT({dni}/1000000)&"."&RIGHT("000"&INT(MOD({dni},1000000)/1000),3)'
           f'&"."&RIGHT("000"&MOD({dni},1000),3),{dni}&""),{dni}&"")')
cue_fmt = f'IF(LEN({M}$M$2)=9,LEFT({M}$M$2,7)&"-"&RIGHT({M}$M$2,2),{M}$M$2&"")'
nac_fecha = (f'IF({fn}="","____",RIGHT("0"&DAY({fn}),2)&" de "&UPPER(INDEX({MES},MONTH({fn})))&" de "&YEAR({fn}))')
lugar = f'UPPER({dato("I")}&"")&IF({dato("K")}="",""," ("&UPPER({dato("K")})&")")'
parrafo = ('=IF($L$5="","Elegí el DNI del/la estudiante en el panel de la derecha (celda L2).",'
           f'"La autoridad del establecimiento educativo, "&UPPER({M}$C$2)&" CUE "&{cue_fmt}'
           f'&", ubicado en "&UPPER({M}$Q$2&"")&", de "&UPPER({M}$J$2&"")&", provincia de JUJUY, certifica que "'
           f'&UPPER({dato("B")})&", "&UPPER({dato("C")})&", con lugar de nacimiento en "&{lugar}&", el "&{nac_fecha}'
           f'&", Tipo de Documento "&{dato("F")}&" N° "&{dni_fmt}'
           '&", aprobó los espacios curriculares que con sus respectivas calificaciones a continuación se expresan:")')
caja(ana, "A10:I14", parrafo, wrap=True, vert="top", h="justify", sz=11)

OF = f"{M}$AH$2"
ixa = lambda col: f"INDEX({oc(col)},{OF})"
formacion = (f'=IF({OF}="","","Formación profesional: "&UPPER({M}$C$3)&". Familia profesional: "&{ixa("E")}'
             f'&". Nivel de certificación: "&{ixa("F")}&". Diseño Curricular: Resolución N° "&{ixa("B")}'
             f'&IF({ixa("C")}="",""," del "&{ixa("C")})&". Duración: "&{ixa("G")}&". Ciclo lectivo "&{M}$J$3'
             f'&", turno "&{M}$C$4&".")')
caja(ana, "A16:I18", formacion, wrap=True, vert="top", h="justify", sz=10)
for r in range(10, 15):
    ana.row_dimensions[r].height = 17
for r in (5, 9, 15, 19, 20, 21, 22):
    ana.row_dimensions[r].height = 8

sec(23, "TRAYECTO CURRICULAR")
for j, t in enumerate(["N°", "Módulo", "Tipo", "Período", "Hs reloj", "Hs cát.", "Nota", "En letras", "Condición"], 1):
    st(ana.cell(24, j), t, **H)
T1, TN = 25, 25 + NMOD - 1
for r in range(T1, TN + 1):
    st(ana[f"A{r}"], f'=IF(ROWS($A${T1}:$A{r})>{M}$AH$3,"",ROWS($A${T1}:$A{r}))', h="center", borde=True)
    for col, src in zip("BCDEF", "RQPST"):
        v = f"INDEX({mc(src)},{M}$AH$4+$A{r}-1)"
        st(ana[f"{col}{r}"], f'=IF($A{r}="","",IF({v}="","",{v}))',
           borde=True, wrap=(col == "B"), sz=9, h=None if col == "B" else "center")
    nota = f"INDEX({M}$R${F1}:${MCOL[-1]}${FN_},$L$5,$A{r})"
    st(ana[f"G{r}"], f'=IF(OR($A{r}="",$L$5=""),"",IF({nota}="","",{nota}))', b=True, h="center", borde=True)
    st(ana[f"H{r}"], f'=IF(G{r}="","",IF(ISNUMBER(G{r}),PROPER(INDEX({LET},G{r}+1)),IF(G{r}="AUS","AUSENTE",G{r})))', sz=9, borde=True)
    st(ana[f"I{r}"], f'=IF(OR($A{r}="",$L$5=""),"",IF(G{r}="","Pendiente",IF(G{r}="AUS","Ausente",IF(AND(ISNUMBER(G{r}),G{r}>={NOTA_MIN}),"Aprobado","Desaprobado"))))',
       sz=9, h="center", borde=True)
rt = TN + 1
caja(ana, f"A{rt}:D{rt}", "Carga horaria total", b=True, h="right", borde=True)
st(ana[f"E{rt}"], f'=IF({OF}="","",{ixa("H")})', b=True, h="center", borde=True)
st(ana[f"F{rt}"], f'=IF({OF}="","",{ixa("I")})', b=True, h="center", borde=True)
caja(ana, f"G{rt}:I{rt}", None, borde=True)

rp = rt + 2
etiqueta(ana, f"A{rp}:B{rp}", "Promedio de módulos")
calculo(ana, f"C{rp}:D{rp}", f'=IF(COUNT(G{T1}:G{TN})=0,"",ROUND(AVERAGE(G{T1}:G{TN}),2))', b=True, h="center", fmt="0.00")
etiqueta(ana, f"E{rp}:F{rp}", "Examen final")
calculo(ana, f"G{rp}:G{rp}", f'=IF($L$5="","",INDEX({A}$I${A1_}:$I${AN},$L$5))', b=True, h="center")
calculo(ana, f"H{rp}:I{rp}", f'=IF($L$5="","",INDEX({A}$J${A1_}:$J${AN},$L$5))')
ex = f"$G${rp}"
aprob = f'COUNTIF($I${T1}:$I${TN},"Aprobado")'
etiqueta(ana, f"A{rp + 1}:B{rp + 1}", "Situación")
calculo(ana, f"C{rp + 1}:I{rp + 1}",
        f'=IF(OR($L$5="",{M}$AH$3=0),"",IF({aprob}<{M}$AH$3,"Adeuda "&({M}$AH$3-{aprob})&" módulo(s)",'
        f'IF({ex}="","Módulos aprobados. Examen final pendiente",'
        f'IF(AND(ISNUMBER({ex}),{ex}>={NOTA_MIN}),"Completó y aprobó la formación profesional","Examen final no aprobado"))))', b=True)


rc = rp + 4
caja(ana, f"A{rc}:I{rc + 1}",
     f'="A pedido del/la interesado/a y a los fines que estime corresponder, se extiende el presente en la ciudad de "'
     f'&IF({M}$J$2="","____________",{M}$J$2)&", Provincia de Jujuy, República Argentina, "'
     f'&IF($L$3="","a los ____ días del mes de __________ de ______",IF(DAY($L$3)=1,"al 1 día","a los "&DAY($L$3)&" días")&" del mes de "'
     f'&INDEX({MES},MONTH($L$3))&" de "&YEAR($L$3))&"."', wrap=True, vert="top")
ana.row_dimensions[rc].height = 18; ana.row_dimensions[rc + 1].height = 18
rf = rc + 6
for rango, t in [(f"A{rf}:B{rf}", "Secretario/a Docente"), (f"D{rf}:F{rf}", "Director/a Institucional (firma y sello)"),
                 (f"H{rf}:I{rf}", "Dirección de Títulos")]:
    caja(ana, rango, t, b=True, sz=9, h="center")
    for fila in ana[rango]:
        for c in fila:
            c.border = LINEA_FIRMA
ana.print_area = f"A1:I{rf}"
ana.page_setup.paperSize = ana.PAPERSIZE_A4; ana.page_setup.fitToWidth = 1; ana.page_setup.fitToHeight = 1
ana.sheet_properties.pageSetUpPr.fitToPage = True

# ======================= EJEMPLO =======================
if EJEMPLO:
    mat["C2"] = "Escuela Profesional N° 13 “Damas Mendocinas”"
    mat["C3"] = "Soldador"; mat["C4"] = "Vespertino"; mat["J3"] = 2026; mat["J4"] = "1° A"
    fila = ["EJEMPLO", "Alumna de Prueba", dt.date(2000, 3, 15), "Argentina", "DNI", 99999999,
            None, "Palpalá", "Palpalá", "Jujuy", "Secundario completo",
            "Jujuy", dt.date(2026, 3, 10), 1, None, None,
            8, 7, 9, 8, 7, 8, 9, 7]
    cols = [L(j) for j in range(2, 18)] + MCOL
    for col, v in zip(cols, fila):
        if v is not None:
            mat[f"{col}{F1}"] = v
            if isinstance(v, dt.date):
                mat[f"{col}{F1}"].number_format = "dd/mm/yyyy"
    act[f"B{A1_}"] = 1; act[f"E{A1_}"] = 8; act[f"G{A1_}"] = 9
    act["C5"] = dt.date(2026, 11, 20)
    ana["L2"] = 99999999; ana["L3"] = dt.date(2026, 12, 1); ana["L4"] = "38-00000001-2026"
    mat["Q2"] = "Av. El Congreso esq. Los Paraísos"

for ws in (mat, act, ana, cat):
    ws.sheet_view.showGridLines = ws is cat or ws is mat
    ws.sheet_view.zoomScale = 100
mat.sheet_properties.tabColor = "2E75B6"; act.sheet_properties.tabColor = "548235"
ana.sheet_properties.tabColor = "BF8F00"; cat.sheet_properties.tabColor = "7F7F7F"
cat.sheet_state = "hidden"            # pestaña de apoyo: oculta
wb.active = 0
wb.calculation.fullCalcOnLoad = True
wb.save(SALIDA)
print("guardado", SALIDA, "módulos en catálogo:", ULT_MOD - MOD1 + 1)
