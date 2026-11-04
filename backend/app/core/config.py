"""
Configuración y constantes para Libro Matriz FP.
Migrado directamente de Config.gs.
"""

import os
from typing import Dict, List, Any

# Cargar variables de entorno
PANEL_ID: str = os.getenv("PANEL_ID", "")
CREDENTIALS_FILE: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials/service_account.json")

# Roles del sistema
class Roles:
    DIRECCION = "Dirección DETP"      # ve todas las escuelas, no carga
    DIRECTIVO = "Directivo"           # ve solo su escuela, no carga
    ADMINISTRATIVO = "Administrativo"  # ve y carga solo su escuela
    TITULOS = "titulos"               # nuevo rol: bandeja centralizada de pedidos de todas las instituciones

    ALL = [DIRECCION, DIRECTIVO, ADMINISTRATIVO, TITULOS, "Títulos"]

# Estados del circuito de emisión de certificados
class EstadoCertificado:
    NO_SOLICITADO = "No solicitado"
    PENDIENTE = "Pendiente"
    OBSERVADO = "Observado"
    APROBADO = "Aprobado"

# Posiciones dentro de la pestaña RAC de cada archivo de curso
RAC = {
    "HOJA": "RAC",
    "FILA_1": 9,          # primer estudiante
    "FILA_N": 48,         # último estudiante
    "FILA_MOD_PERIODO": 7,
    "FILA_MOD_NOMBRE": 8,
    "ENCABEZADO": {
        "establecimiento": "C2",
        "localidad": "J2",
        "cue": "M2",
        "domicilio": "Q2",
        "oferta": "C3",
        "ciclo": "J3",
        "libro": "M3",
        "turno": "C4",
        "matriculados": "F4",
        "division": "J4",
        "disenio": "C5"
    },
    "COL": {
        "orden": 1, "apellido": 2, "nombres": 3, "fechaNac": 4, "nacionalidad": 5,
        "tipoDoc": 6, "documento": 7, "telUrgencia": 8,
        "localidad": 9, "departamento": 10, "provincia": 11,
        "nivel": 12, "provEstudios": 13,
        "fechaInsc": 14, "solicitud": 15, "discapacidad": 16, "acompaniamiento": 17,
        "mod1": 18, "modN": 25,           # R..Y: hasta 8 módulos
        "notaFinal": 26,                # Z  (fórmula, la trae el acta)
        "fechaEgreso": 27,              # AA
        "folio": 28,                    # AB
        "situacion": 29                 # AC (fórmula)
    }
}

# Posiciones de la pestaña Acta de Examen
ACTA = {
    "HOJA": "Acta de Examen",
    "FILA_1": 13,
    "COL": {
        "orden": 1, "permiso": 2, "documento": 3, "nombre": 4,
        "teorico": 5, "teoricoLetras": 6, "practico": 7, "practicoLetras": 8,
        "definitiva": 9, "definitivaLetras": 10
    },
    "FECHA": "C5",
    "PRESIDENTE": "C7",
    "VOCAL1": "G7",
    "VOCAL2": "C8"
}

# Posiciones de la pestaña Analítico
ANALITICO = {
    "HOJA": "Analítico",
    "DNI": "L2",
    "FECHA": "L3",
    "CERTIFICADO": "L4"
}

AUSENTE = "AUS"
NOTA_MIN_DEFECTO = 7

# Columnas y configuración de las pestañas del Panel
PANEL = {
    "USUARIOS": {
        "hoja": "Usuarios",
        "cols": ["Email", "Nombre", "Rol", "CUE", "Activo"]
    },
    "CURSOS": {
        "hoja": "Cursos",
        "cols": [
            "CUE", "Institución", "Oferta", "Ciclo", "Turno",
            "Curso / División", "ID del archivo", "Estado"
        ]
    },
    "REGISTRO": {
        "hoja": "Registro",
        "cols": ["Fecha y hora", "Email", "Rol", "Acción", "Curso", "Detalle"]
    },
    "SOLICITUDES": {
        "hoja": "Solicitudes",
        "cols": [
            "ID Solicitud", "ID Curso", "CUE", "Institución", "Oferta", "Ciclo",
            "Documento", "Estudiante", "Fecha Solicitud", "Estado",
            "Motivo Observación", "Número Certificado", "Fecha Aprobación", "Usuario Solicitante"
        ]
    }
}

def col_num_to_letter(col_idx: int) -> str:
    """Convierte un índice de columna numérico (1-based) a letra de Excel (ej: 1->A, 28->AB)."""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

def letter_to_col_num(col_letter: str) -> int:
    """Convierte letra de columna a índice (1-based). Ej: 'A' -> 1, 'AA' -> 27."""
    num = 0
    for char in col_letter.upper():
        num = num * 26 + (ord(char) - ord('A') + 1)
    return num
