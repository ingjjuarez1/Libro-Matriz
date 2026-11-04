"""
Script de verificación de conexión a Google Drive API y Google Sheets API.
Valida credenciales de Service Account y permisos sobre el Panel FP.
"""

import os
import sys
from pathlib import Path

# Agregar raíz al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app.core.config import PANEL_ID, CREDENTIALS_FILE
from backend.app.services.google_service import GoogleService

def test_google_connection():
    print("=================================================================")
    print("   PRUEBA DE CONEXIÓN A GOOGLE DRIVE Y GOOGLE SHEETS API")
    print("=================================================================\n")

    # 1. Verificar archivo de credenciales
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", CREDENTIALS_FILE)
    print(f"1. Verificando archivo de credenciales: '{cred_path}'")
    if not os.path.exists(cred_path):
        print(f"   [AVISO] No se encontró el archivo '{cred_path}'.")
        print("\n   PASOS PARA CONFIGURAR LA AUTENTICACIÓN:")
        print("   1. Entra a Google Cloud Console (https://console.cloud.google.com).")
        print("   2. Crea o selecciona tu proyecto institucional.")
        print("   3. Habilita las APIs: 'Google Drive API' y 'Google Sheets API'.")
        print("   4. Ve a 'IAM y administración' > 'Cuentas de servicio' > 'Crear cuenta de servicio'.")
        print("   5. Crea una clave en formato JSON y descárgala.")
        print("   6. Guárdala como 'credentials/service_account.json' en este proyecto.")
        print("   7. Comparte tu carpeta de Drive y tu planilla 'Panel FP' con el email de la Service Account (con rol Editor).")
        return False
    else:
        print("   [OK] Archivo de credenciales encontrado.")

    # 2. Inicializar cliente y validar token
    print("\n2. Probando autenticación con Google...")
    try:
        service = GoogleService(cred_path)
        if not service.is_connected():
            print("   [ERROR] No se pudo inicializar la sesión autenticada.")
            return False
        print(f"   [OK] Autenticado exitosamente como: {service.client_email}")
    except Exception as e:
        print(f"   [ERROR] Falló la autenticación: {e}")
        return False

    # 3. Probar llamada a Google Drive API
    print("\n3. Probando consulta a Google Drive API...")
    try:
        # Intentar consultar archivos accesibles
        url = "https://www.googleapis.com/drive/v3/files"
        resp = service.session.get(url, params={"pageSize": 5, "fields": "files(id, name, mimeType)"})
        if resp.status_code == 200:
            archivos = resp.json().get("files", [])
            print(f"   [OK] Google Drive API responde correctamente. Archivos visibles: {len(archivos)}")
            for a in archivos:
                print(f"        - {a.get('name')} (ID: {a.get('id')})")
        else:
            print(f"   [ERROR] Respuesta HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"   [ERROR] Error al contactar Google Drive API: {e}")
        return False

    # 4. Probar acceso al Panel FP (Google Sheets API)
    print("\n4. Verificando acceso a la planilla central 'Panel FP'...")
    panel_id = os.getenv("PANEL_ID", PANEL_ID)
    if not panel_id:
        print("   [INFO] PANEL_ID no está configurado en .env.")
        print("   Puedes crear uno nuevo ejecutando el instalador o ingresando su ID.")
    else:
        print(f"   Consultando ID de planilla: {panel_id}")
        try:
            meta = service.get_spreadsheet_metadata(panel_id)
            titulo = meta.get("properties", {}).get("title", "")
            pestanias = [s.get("properties", {}).get("title") for s in meta.get("sheets", [])]
            print(f"   [OK] Planilla encontrada: '{titulo}'")
            print(f"        Pestañas detectadas: {', '.join(pestanias)}")
        except Exception as e:
            print(f"   [ERROR] No se pudo leer la planilla {panel_id}: {e}")
            print(f"   Asegúrate de haber compartido la planilla con: {service.client_email}")
            return False

    print("\n=================================================================")
    print("   ¡CONEXIÓN VERIFICADA EXITOSAMENTE!")
    print("=================================================================\n")
    return True

if __name__ == "__main__":
    test_google_connection()
