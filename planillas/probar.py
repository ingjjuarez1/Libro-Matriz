import openpyxl, subprocess, sys, json, datetime as dt
B='/tmp/claude-0/-home-claude/7993c590-c5c0-5b2b-8c0f-9b1b57cacbe1/scratchpad/online'
def caso(nombre, cambios):
    wb=openpyxl.load_workbook(f'{B}/Libro_FP.xlsx')
    for hoja, celda, v in cambios: wb[hoja][celda]=v
    p=f'{B}/t/{nombre}.xlsx'; wb.save(p)
    out=json.loads(subprocess.run([sys.executable,'recalc.py',p,'120'],cwd='/mnt/skills/public/xlsx/scripts',capture_output=True,text=True).stdout)
    wb=openpyxl.load_workbook(p,data_only=True); m,a,an=wb['RAC'],wb['Acta de Examen'],wb['Analítico']
    print(f'\n=== {nombre}: {out["status"]} errores={out["total_errors"]} {out.get("error_summary")}')
    print(' C5:',m['C5'].value); print(' hdr8:',[m.cell(8,j).value for j in range(18,26)])
    print(' sit:',[m[f'AC{r}'].value for r in range(9,13)])
    for r in range(13,17): print(' acta',r,[a.cell(r,j).value for j in range(1,11)])
    print(' acta tot:',[a[f'E{r}'].value for r in range(54,58)], a['A59'].value); print(' ', a['A6'].value)
    for r in list(range(11,14))+list(range(25,34))+[35,36,39]:
        v=[an.cell(r,j).value for j in range(1,10) if an.cell(r,j).value not in (None,'')]
        print(' an',r,v)
alumnos=[('B10','PÉREZ'),('C10','Juan Carlos'),('F10','DNI'),('G10',40111222),('D10',dt.date(1998,1,1)),('I10','Perico'),('K10','Jujuy'),
         ('R10',8),('S10',5),('T10',None),('U10',9),('V10',7),
         ('B11','GÓMEZ'),('C11','Ana'),('F11','DNI'),('G11',41222333),('R11',7),('S11',7),('T11',8),('U11',9),('V11',10)]
caso('climatizacion', [('RAC','C3','Instalador y Reparador de Equipos de Climatización')]+[('RAC',c,v) for c,v in alumnos]+
     [('RAC','W9',None),('RAC','X9',None),('RAC','Y9',None),
      ('Acta de Examen','E14','AUS'),('Acta de Examen','G14',6),('Acta de Examen','E15',6),('Acta de Examen','G15',7),
      ('Acta de Examen','C5',dt.date(2026,12,1)),('Analítico','L2',40111222)])
caso('analitico_ana_examen_6', [('RAC','C3','Instalador y Reparador de Equipos de Climatización')]+[('RAC',c,v) for c,v in alumnos]+
     [('Acta de Examen','E15',6),('Acta de Examen','G15',7),('Analítico','L2',41222333)])
caso('dni_inexistente', [('Analítico','L2',12345)])
caso('sin_oferta', [('RAC','C3',None),('RAC','C2',None)])
