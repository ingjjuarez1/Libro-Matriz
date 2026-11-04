"""
Instalación e importación de cursos desde Google Drive.
Migrado directamente de Instalar.gs.
"""

import logging
from typing import Dict, Any, List
from backend.app.core.config import PANEL, Roles
from backend.app.services.google_service import google_client
from backend.app.services.datos_service import cursos_del_panel, leer_curso

logger = logging.getLogger("libro_matriz.instalador")

def instalar_panel(admin_email: str = "coordinacion@educacion.jujuy.gob.ar") -> Dict[str, Any]:
    """
    Crea la planilla central 'Panel FP · Libro Matriz' con las pestañas
    Usuarios, Cursos y Registro.
    """
    sheet_data = google_client.create_spreadsheet("Panel FP · Libro Matriz (no borrar)")
    panel_id = sheet_data["spreadsheetId"]

    # Agregar pestañas: Usuarios (que es la primera hoja), Cursos y Registro
    # Renombrar primera hoja y agregar las otras dos
    first_sheet_id = sheet_data["sheets"][0]["properties"]["sheetId"]
    requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": first_sheet_id, "title": PANEL["USUARIOS"]["hoja"]},
                "fields": "title"
            }
        },
        {"addSheet": {"properties": {"title": PANEL["CURSOS"]["hoja"]}}},
        {"addSheet": {"properties": {"title": PANEL["REGISTRO"]["hoja"]}}}
    ]
    google_client.batch_update_spreadsheet(panel_id, requests)

    # Cargar encabezados en cada pestaña
    google_client.update_values(panel_id, f"{PANEL['USUARIOS']['hoja']}!A1:E1", [PANEL["USUARIOS"]["cols"]])
    google_client.update_values(panel_id, f"{PANEL['CURSOS']['hoja']}!A1:H1", [PANEL["CURSOS"]["cols"]])
    google_client.update_values(panel_id, f"{PANEL['REGISTRO']['hoja']}!A1:F1", [PANEL["REGISTRO"]["cols"]])

    # Insertar usuario administrador inicial
    google_client.append_row(
        panel_id, PANEL["USUARIOS"]["hoja"],
        [admin_email, "Coordinación DETP", Roles.DIRECCION, "", "Sí"]
    )

    return {
        "panel_id": panel_id,
        "url": f"https://docs.google.com/spreadsheets/d/{panel_id}/edit"
    }

def importar_cursos_de_carpeta(id_carpeta: str, panel_id: str) -> int:
    """
    Recorre una carpeta de Drive y agrega al índice los archivos de curso
    que todavía no estén registrados.
    """
    if not id_carpeta:
        raise ValueError("Debes proporcionar el ID de la carpeta 'Formación Profesional – DETP'.")

    # Identificar cursos ya existentes para evitar duplicados
    cursos_actuales = cursos_del_panel()
    ya_estan = {c["id"]: True for c in cursos_actuales}

    # Listar subcarpetas o archivos de la carpeta
    archivos = google_client.list_files_in_folder(
        id_carpeta, mime_type="application/vnd.google-apps.spreadsheet"
    )

    nuevos_cursos = []
    for f in archivos:
        file_id = f["id"]
        if file_id in ya_estan:
            continue
        try:
            d = leer_curso(file_id)
            enc = d.get("encabezado", {})
            if not enc.get("oferta"):
                continue  # No es una planilla de curso
            
            nuevos_cursos.append([
                enc.get("cue", ""),
                enc.get("establecimiento", ""),
                enc.get("oferta", ""),
                enc.get("ciclo", ""),
                enc.get("turno", ""),
                enc.get("division", ""),
                file_id,
                "Abierto"
            ])
        except Exception as err:
            logger.warning(f"Archivo {file_id} omitido: {err}")

    if nuevos_cursos:
        for c in nuevos_cursos:
            google_client.append_row(panel_id, PANEL["CURSOS"]["hoja"], c)

    return len(nuevos_cursos)
