"""
Servicio de comunicación con Google Drive y Google Sheets API v4 / Drive API v3.
Reemplaza las funciones nativas de Apps Script (SpreadsheetApp, DriveApp).
Utiliza google-auth con AuthorizedSession para conexión directa y segura.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

logger = logging.getLogger("libro_matriz.google")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

class GoogleService:
    def __init__(self, credentials_path: Optional[str] = None):
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", 
            os.path.join(os.path.dirname(__file__), "../../../credentials/service_account.json")
        )
        self.session: Optional[AuthorizedSession] = None
        self.client_email: Optional[str] = None
        self._init_session()

    def _init_session(self):
        # 1. Intentar desde variable de entorno con JSON crudo
        raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if raw_json:
            try:
                info = json.loads(raw_json)
                creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
                self.session = AuthorizedSession(creds)
                self.client_email = info.get("client_email")
                logger.info(f"Autenticado con Service Account (env JSON): {self.client_email}")
                return
            except Exception as e:
                logger.warning(f"Error al cargar credenciales desde GOOGLE_SERVICE_ACCOUNT_JSON: {e}")

        # 2. Intentar desde archivo físico
        if os.path.exists(self.credentials_path):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    self.credentials_path, scopes=SCOPES
                )
                self.session = AuthorizedSession(creds)
                with open(self.credentials_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.client_email = data.get("client_email")
                logger.info(f"Autenticado con Service Account ({self.credentials_path}): {self.client_email}")
                return
            except Exception as e:
                logger.error(f"Error al leer credenciales desde {self.credentials_path}: {e}")
        else:
            logger.warning(f"No se encontró archivo de credenciales en {self.credentials_path}.")

    def is_connected(self) -> bool:
        return self.session is not None

    def _ensure_session(self):
        if not self.session:
            raise RuntimeError(
                "No hay credenciales válidas de Google Drive API configuradas. "
                "Coloca tu archivo service_account.json en la carpeta 'credentials/' "
                "o configura la variable de entorno GOOGLE_APPLICATION_CREDENTIALS."
            )

    # ==================== GOOGLE SHEETS API ====================

    def get_spreadsheet_metadata(self, spreadsheet_id: str) -> Dict[str, Any]:
        """Obtiene metadatos de la planilla (pestañas, rangos combinados, propiedades)."""
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        resp = self.session.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al obtener planilla {spreadsheet_id}: {resp.status_code} - {resp.text}")
        return resp.json()

    def get_values(self, spreadsheet_id: str, range_a1: str, render_option: str = "FORMATTED_VALUE") -> List[List[Any]]:
        """Lee un rango de celdas en formato A1 (ej: 'RAC!A9:AC48')."""
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_a1}"
        params = {"valueRenderOption": render_option}
        resp = self.session.get(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al leer rango {range_a1} de {spreadsheet_id}: {resp.status_code} - {resp.text}")
        data = resp.json()
        return data.get("values", [])

    def batch_get_values(self, spreadsheet_id: str, ranges: List[str], render_option: str = "FORMATTED_VALUE") -> Dict[str, List[List[Any]]]:
        """Lee múltiples rangos en una sola petición HTTP."""
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
        params = [("ranges", r) for r in ranges]
        params.append(("valueRenderOption", render_option))
        resp = self.session.get(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"Error batchGet en {spreadsheet_id}: {resp.status_code} - {resp.text}")
        value_ranges = resp.json().get("valueRanges", [])
        result = {}
        for vr in value_ranges:
            result[vr.get("range", "")] = vr.get("values", [])
        return result

    def update_values(self, spreadsheet_id: str, range_a1: str, values: List[List[Any]], input_option: str = "USER_ENTERED") -> Dict[str, Any]:
        """Actualiza un rango de celdas."""
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_a1}"
        params = {"valueInputOption": input_option}
        body = {"range": range_a1, "majorDimension": "ROWS", "values": values}
        resp = self.session.put(url, params=params, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al escribir en {range_a1}: {resp.status_code} - {resp.text}")
        return resp.json()

    def batch_update_values(self, spreadsheet_id: str, data: List[Dict[str, Any]], input_option: str = "USER_ENTERED") -> Dict[str, Any]:
        """
        Actualiza múltiples rangos en una sola llamada (batchUpdate).
        data = [{"range": "RAC!R9", "values": [[8]]}, ...]
        """
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate"
        body = {
            "valueInputOption": input_option,
            "data": data
        }
        resp = self.session.post(url, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"Error en batchUpdate de {spreadsheet_id}: {resp.status_code} - {resp.text}")
        return resp.json()

    def append_row(self, spreadsheet_id: str, sheet_name: str, values: List[Any], input_option: str = "USER_ENTERED") -> Dict[str, Any]:
        """Agrega una fila al final de una hoja (equivalente a appendRow en GAS)."""
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_name}!A1:append"
        params = {"valueInputOption": input_option, "insertDataOption": "INSERT_ROWS"}
        body = {"values": [values]}
        resp = self.session.post(url, params=params, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al agregar fila en {sheet_name}: {resp.status_code} - {resp.text}")
        return resp.json()

    def batch_update_spreadsheet(self, spreadsheet_id: str, requests_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ejecuta operaciones estructurales (crear pestañas, formatos, validación de datos)."""
        self._ensure_session()
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
        body = {"requests": requests_list}
        resp = self.session.post(url, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"Error estructural en {spreadsheet_id}: {resp.status_code} - {resp.text}")
        return resp.json()

    # ==================== GOOGLE DRIVE API ====================

    def list_files_in_folder(self, folder_id: str, mime_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista archivos dentro de una carpeta de Drive."""
        self._ensure_session()
        query = f"'{folder_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": query,
            "fields": "files(id, name, mimeType, webViewLink)",
            "pageSize": 1000
        }
        resp = self.session.get(url, params=params)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al listar carpeta de Drive {folder_id}: {resp.status_code} - {resp.text}")
        return resp.json().get("files", [])

    def create_spreadsheet(self, title: str, parent_folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Crea una nueva planilla en Drive."""
        self._ensure_session()
        url = "https://sheets.googleapis.com/v4/spreadsheets"
        body = {"properties": {"title": title}}
        resp = self.session.post(url, json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"Error al crear planilla '{title}': {resp.status_code} - {resp.text}")
        sheet_data = resp.json()
        file_id = sheet_data["spreadsheetId"]

        # Si se especificó carpeta contenedora, mover el archivo allí
        if parent_folder_id:
            drive_url = f"https://www.googleapis.com/drive/v3/files/{file_id}"
            move_params = {"addParents": parent_folder_id, "fields": "id, parents"}
            self.session.patch(drive_url, params=move_params)

        return sheet_data

# Instancia singleton accesible globalmente
google_client = GoogleService()
