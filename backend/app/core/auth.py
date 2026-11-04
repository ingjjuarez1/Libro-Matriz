"""
Identidad, roles y permisos para Libro Matriz FP.
Migrado directamente de Auth.gs.

REGLA: Toda función que lee o escribe datos verifica primero la sesión y el rol
aquí en el servidor antes de realizar cualquier cambio en Google Drive / Sheets.
"""

import re
import json
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from backend.app.core.config import Roles, PANEL, PANEL_ID
from backend.app.services.google_service import google_client

class AuthException(Exception):
    pass

class PermissionDeniedException(Exception):
    pass

USUARIOS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "usuarios.json"

_USUARIOS_INICIALES: List[Dict[str, Any]] = [
    {
        "Email": "sge.detp.areapedagogica@jujuy.edu.ar",
        "Nombre": "Coordinación Área Pedagógica DETP",
        "Rol": Roles.DIRECCION,
        "CUE": "",
        "Activo": "Sí",
        "Oficial": True
    },
    {
        "Email": "titulos@jujuy.edu.ar",
        "Nombre": "Departamento de Títulos",
        "Rol": Roles.TITULOS,
        "CUE": "",
        "Activo": "Sí",
        "Oficial": True
    },
    {
        "Email": "directivo.ep6@jujuy.edu.ar",
        "Nombre": "Directivo EP Nº 6",
        "Rol": Roles.DIRECTIVO,
        "CUE": "3800006",
        "Activo": "Sí",
        "Oficial": True
    },
    {
        "Email": "admin.ep6@jujuy.edu.ar",
        "Nombre": "Administrativo EP Nº 6",
        "Rol": Roles.ADMINISTRATIVO,
        "CUE": "3800006",
        "Activo": "Sí",
        "Oficial": True
    },
    {
        "Email": "titulos@educacion.jujuy.gob.ar",
        "Nombre": "Departamento de Títulos (Secundario)",
        "Rol": Roles.TITULOS,
        "CUE": "",
        "Activo": "Sí",
        "Oficial": False
    }
]

def _cargar_usuarios_locales() -> List[Dict[str, Any]]:
    if USUARIOS_FILE.exists():
        try:
            with open(USUARIOS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass
    _guardar_usuarios_locales(_USUARIOS_INICIALES)
    return list(_USUARIOS_INICIALES)

def _guardar_usuarios_locales(lista: List[Dict[str, Any]]):
    try:
        USUARIOS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USUARIOS_FILE, "w", encoding="utf-8") as f:
            json.dump(lista, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def normalizar_cue(cue_val: Any) -> str:
    """Extrae únicamente dígitos del CUE."""
    if not cue_val:
        return ""
    return re.sub(r"\D", "", str(cue_val))

def obtener_usuarios_panel() -> List[Dict[str, Any]]:
    """Lee la pestaña 'Usuarios' del Panel FP o el almacén local administrado por DETP/Títulos."""
    if not PANEL_ID or not google_client.is_connected():
        usuarios = _cargar_usuarios_locales()
        for u in usuarios:
            u["Oficial"] = str(u.get("Email", "")).strip().lower().endswith("@jujuy.edu.ar")
        return usuarios

    try:
        valores = google_client.get_values(PANEL_ID, f"{PANEL['USUARIOS']['hoja']}!A1:E200")
        if len(valores) < 2:
            return _cargar_usuarios_locales()
        
        encabezados = [str(col).strip() for col in valores[0]]
        usuarios = []
        for fila in valores[1:]:
            if not fila or not any(str(c).strip() for c in fila):
                continue
            item = {}
            for idx, enc in enumerate(encabezados):
                item[enc] = str(fila[idx]).strip() if idx < len(fila) else ""
            item["Oficial"] = str(item.get("Email", "")).strip().lower().endswith("@jujuy.edu.ar")
            usuarios.append(item)
        return usuarios
    except Exception as e:
        raise RuntimeError(f"Error al leer la hoja Usuarios del Panel FP: {e}")

def guardar_usuario_panel(datos: Dict[str, Any], sesion_usr: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea o actualiza un usuario en la administración centralizada.
    EXCLUSIVO para el rol 'Dirección DETP' (Coordinación).
    """
    if sesion_usr.get("rol") != Roles.DIRECCION:
        raise PermissionDeniedException("Solo los usuarios con rol 'Dirección DETP' pueden crear o modificar usuarios.")

    email = str(datos.get("Email", "")).strip().lower()
    if not email or "@" not in email:
        raise ValueError("Debes ingresar un correo electrónico válido (ej: usuario@jujuy.edu.ar).")

    nombre = str(datos.get("Nombre", "")).strip() or email.split("@")[0]
    rol = str(datos.get("Rol", Roles.ADMINISTRATIVO)).strip()
    if rol not in Roles.ALL:
        raise ValueError(f"Rol inválido '{rol}'. Roles permitidos: {', '.join(Roles.ALL)}.")

    cue = str(datos.get("CUE", "")).strip()
    if rol in [Roles.DIRECTIVO, Roles.ADMINISTRATIVO] and not normalizar_cue(cue):
        raise ValueError("Para los roles Directivo y Administrativo es obligatorio indicar el CUE de la institución.")

    activo = "Sí" if str(datos.get("Activo", "Sí")).strip().lower() not in ["no", "false", "0"] else "No"

    nuevo_item = {
        "Email": email,
        "Nombre": nombre,
        "Rol": rol,
        "CUE": cue,
        "Activo": activo,
        "Oficial": email.endswith("@jujuy.edu.ar")
    }

    usuarios = _cargar_usuarios_locales()
    actualizado = False
    for idx, u in enumerate(usuarios):
        if str(u.get("Email", "")).strip().lower() == email:
            usuarios[idx] = nuevo_item
            actualizado = True
            break
    if not actualizado:
        usuarios.append(nuevo_item)

    _guardar_usuarios_locales(usuarios)

    if PANEL_ID and google_client.is_connected() and not actualizado:
        try:
            google_client.append_row(
                PANEL_ID,
                PANEL["USUARIOS"]["hoja"],
                [email, nombre, rol, cue, activo]
            )
        except Exception:
            pass

    registrar(
        sesion_usr,
        "Actualización Usuario" if actualizado else "Alta Usuario",
        cue,
        f"{email} ({rol}) - Activo: {activo}"
    )
    return nuevo_item

def eliminar_usuario_panel(email_objetivo: str, sesion_usr: Dict[str, Any]) -> bool:
    """Elimina un usuario del registro (EXCLUSIVO para rol Dirección DETP)."""
    if sesion_usr.get("rol") != Roles.DIRECCION:
        raise PermissionDeniedException("Solo los usuarios con rol 'Dirección DETP' pueden borrar usuarios.")

    email_norm = str(email_objetivo or "").strip().lower()
    if email_norm == "sge.detp.areapedagogica@jujuy.edu.ar":
        raise ValueError("No se puede eliminar la cuenta principal de Coordinación DETP.")

    usuarios = _cargar_usuarios_locales()
    nuevos = [u for u in usuarios if str(u.get("Email", "")).strip().lower() != email_norm]
    if len(nuevos) == len(usuarios):
        raise ValueError(f"No se encontró el usuario {email_norm}.")

    _guardar_usuarios_locales(nuevos)
    registrar(sesion_usr, "Baja Usuario", "", f"Eliminado: {email_norm}")
    return True

def sesion(email: Optional[str] = None) -> Dict[str, Any]:
    """
    Verifica la identidad y devuelve {email, nombre, rol, cues, puedeCargar, verTodo, puedeAdministrarUsuarios}.
    Lanza AuthException si la cuenta no está autorizada.
    """
    if not email:
        raise AuthException(
            "No se pudo identificar tu cuenta. Asegúrate de iniciar sesión con tu cuenta de Google."
        )

    email_norm = email.strip().lower()
    usuarios = obtener_usuarios_panel()
    usuario_encontrado = None

    for u in usuarios:
        if str(u.get("Email", "")).strip().lower() == email_norm:
            usuario_encontrado = u
            break

    if not usuario_encontrado:
        raise AuthException(
            f"La cuenta {email_norm} no está habilitada. "
            "Pídele a la Coordinación que te agregue en la pestaña Usuarios del Panel FP."
        )

    if str(usuario_encontrado.get("Activo", "")).strip().lower() in ["no", "false", "0"]:
        raise AuthException(f"La cuenta {email_norm} está dada de baja.")

    rol = str(usuario_encontrado.get("Rol", "")).strip()
    if rol not in Roles.ALL and rol.lower() != "titulos":
        raise AuthException(
            f"El rol '{rol}' no es válido. Debe ser uno de: {', '.join(Roles.ALL)}."
        )

    # Extraer CUEs asignados (pueden ser varios separados por coma)
    raw_cues = str(usuario_encontrado.get("CUE", "")).split(",")
    cues = [normalizar_cue(c) for c in raw_cues if normalizar_cue(c)]

    es_titulos = (rol.lower() in ["titulos", "títulos"])
    ver_todo = (rol == Roles.DIRECCION or es_titulos)
    if not ver_todo and not cues:
        raise AuthException(
            "Tu usuario no tiene ninguna institución asignada. "
            "Pídele a la Coordinación que complete la columna CUE en el Panel FP."
        )

    return {
        "email": email_norm,
        "nombre": str(usuario_encontrado.get("Nombre", email_norm)),
        "rol": rol,
        "cues": cues,
        "verTodo": ver_todo,
        "puedeCargar": (rol == Roles.ADMINISTRATIVO),
        "esTitulos": es_titulos,
        "puedeAdministrarUsuarios": (rol == Roles.DIRECCION)
    }

def alcanza_cue(s: Dict[str, Any], cue: Any) -> bool:
    """Verifica si el usuario tiene permiso para acceder a una institución (CUE)."""
    if s.get("verTodo"):
        return True
    cue_limpio = normalizar_cue(cue)
    return cue_limpio in s.get("cues", [])

def exigir_lectura(s: Dict[str, Any], curso: Dict[str, Any]):
    """Verifica permisos de lectura sobre el curso."""
    if not alcanza_cue(s, curso.get("cue")):
        raise PermissionDeniedException("Ese curso es de otra institución y no tienes acceso.")

def exigir_carga(s: Dict[str, Any], curso: Dict[str, Any]):
    """Verifica permisos de modificación sobre el curso."""
    exigir_lectura(s, curso)
    if not s.get("puedeCargar"):
        raise PermissionDeniedException(f"Tu rol ({s.get('rol')}) es de consulta: no puedes modificar datos.")
    
    estado = str(curso.get("estado", "")).strip().lower()
    if estado == "cerrado":
        raise PermissionDeniedException("El curso está cerrado. Pídele a la Coordinación que lo reabra.")

def registrar(s: Dict[str, Any], accion: str, curso: str, detalle: str):
    """Registra auditoría en la pestaña 'Registro' del Panel FP."""
    if not PANEL_ID or not google_client.is_connected():
        return
    try:
        ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        fila = [ahora, s.get("email"), s.get("rol"), accion, curso or "", detalle or ""]
        google_client.append_row(PANEL_ID, PANEL["REGISTRO"]["hoja"], fila)
    except Exception as e:
        # El registro de auditoría nunca debe frenar el flujo principal
        pass
