# -*- coding: utf-8 -*-
"""Achica el xlsx para subirlo a Drive: fórmulas copiadas hacia abajo -> fórmulas
compartidas (como las guarda Excel), sin <v></v> vacíos, texto UTF-8 literal y
compresión máxima. Uso: compactar.py entrada.xlsx salida.xlsx"""
import html, re, sys, zipfile
from openpyxl.formula.translate import Translator

ent, sal = sys.argv[1], sys.argv[2]
CEL = re.compile(r'<c r="([A-Z]+)(\d+)"([^>]*)><f>(.*?)</f><v></v></c>', re.S)
NUMREF = re.compile(r"&#(\d+);")

def utf8(s):
    # &#237; -> í  (deja &amp; &lt; &gt; &quot; como están)
    return NUMREF.sub(lambda m: chr(int(m.group(1))), s)

def compartir(xml):
    celdas = [(m.group(1), int(m.group(2)), html.unescape(m.group(4))) for m in CEL.finditer(xml)]
    por_col = {}
    for col, fila, f in celdas:
        por_col.setdefault(col, []).append((fila, f))
    plan, si = {}, 0                     # (col, fila) -> ("m", ref, si) | ("s", si)
    for col, lst in por_col.items():
        lst.sort()
        i = 0
        while i < len(lst):
            f0r, f0 = lst[i]
            j = i + 1
            while j < len(lst) and lst[j][0] == lst[j - 1][0] + 1:
                esperado = Translator("=" + f0, origin=f"{col}{f0r}").translate_formula(f"{col}{lst[j][0]}")
                if esperado != "=" + lst[j][1]:
                    break
                j += 1
            if j - i > 1:
                plan[(col, f0r)] = ("m", f"{col}{f0r}:{col}{lst[j - 1][0]}", si)
                for k in range(i + 1, j):
                    plan[(col, lst[k][0])] = ("s", si)
                si += 1
            i = j
    def rep(m):
        col, fila, attrs, f = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        p = plan.get((col, fila))
        if p is None:
            return f'<c r="{col}{fila}"{attrs}><f>{f}</f></c>'
        if p[0] == "m":
            return f'<c r="{col}{fila}"{attrs}><f t="shared" ref="{p[1]}" si="{p[2]}">{f}</f></c>'
        return f'<c r="{col}{fila}"{attrs}><f t="shared" si="{p[1]}"/></c>'
    return CEL.sub(rep, xml), si, len(celdas)

# compresión zopfli (deflate más chico, 100 % compatible)
import zlib, zopfli.zopfli as zz
class _Zop:
    def __init__(self): self.buf = []
    def compress(self, d): self.buf.append(d); return b""
    def flush(self): return zz.compress(b"".join(self.buf), numiterations=60)[2:-4]
_orig = zipfile._get_compressor
zipfile._get_compressor = lambda t, l=None: _Zop() if t == zipfile.ZIP_DEFLATED else _orig(t, l)

VACIA = re.compile(r'(<c r="[A-Z]+\d+"(?: s="\d+")?) t="n"></c>')
INL = re.compile(r't="inlineStr"><is><t(?: xml:space="preserve")?>(.*?)</t></is>', re.S)
sst, idx = [], {}
def a_compartido(m):
    t = m.group(1)
    if t not in idx:
        idx[t] = len(sst); sst.append(t)
    return f't="s"><v>{idx[t]}</v>'

zin = zipfile.ZipFile(ent)
partes = {}
for it in zin.infolist():
    if it.filename.startswith("docProps/"):
        continue                                   # metadatos opcionales
    data = zin.read(it.filename).decode("utf-8")
    if it.filename.startswith("xl/worksheets/sheet"):
        data, n, tot = compartir(data)
        data = INL.sub(a_compartido, VACIA.sub(r"\1/>", data))
        print(f"{it.filename}: {tot} fórmulas, {n} grupos compartidos")
    elif it.filename == "xl/styles.xml":           # fuente por defecto: Arial 10
        data = re.sub(r"<fonts count=\"(\d+)\"><font>.*?</font>",
                      lambda m: f'<fonts count="{m.group(1)}"><font><sz val="10"/><name val="Arial"/><family val="2"/></font>',
                      data, count=1, flags=re.S)
    partes[it.filename] = utf8(data)
partes["_rels/.rels"] = re.sub(r'<Relationship[^>]*docProps[^>]*/>', "", partes["_rels/.rels"])
ct = re.sub(r'<Override PartName="/docProps/[^>]*/>', "", partes["[Content_Types].xml"])
ct = ct.replace("</Types>", '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
partes["[Content_Types].xml"] = ct
partes["xl/_rels/workbook.xml.rels"] = partes["xl/_rels/workbook.xml.rels"].replace(
    "</Relationships>", '<Relationship Id="rIdSST" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
def tt(t):
    return f'<si><t xml:space="preserve">{t}</t></si>' if t != t.strip() else f"<si><t>{t}</t></si>"
partes["xl/sharedStrings.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(sst)}" uniqueCount="{len(sst)}">'
    + "".join(tt(utf8(t)) for t in sst) + "</sst>")
orden = ["[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"]
orden += [k for k in partes if k not in orden]
zout = zipfile.ZipFile(sal, "w", zipfile.ZIP_DEFLATED)
for k in orden:
    zout.writestr(k, partes[k].encode("utf-8"))
zout.close()
print("textos compartidos:", len(sst))
