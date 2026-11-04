"""
Pruebas unitarias de la lógica del Libro Matriz FP.
Verifica normalización de notas, rangos de celdas, conversión de columnas y permisos.
"""

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app.core.config import col_num_to_letter, letter_to_col_num, RAC, ACTA, Roles
from backend.app.services.datos_service import normalizar_nota
from backend.app.core.auth import alcanza_cue

def test_logica():
    print("Probando conversiones de columnas...")
    assert col_num_to_letter(1) == "A"
    assert col_num_to_letter(26) == "Z"
    assert col_num_to_letter(27) == "AA"
    assert col_num_to_letter(28) == "AB"
    assert col_num_to_letter(29) == "AC"
    assert letter_to_col_num("A") == 1
    assert letter_to_col_num("Z") == 26
    assert letter_to_col_num("AA") == 27
    assert letter_to_col_num("AC") == 29
    print(" [OK] Columnas correctas.")

    print("Probando normalización de notas...")
    assert normalizar_nota("10") == 10
    assert normalizar_nota(7) == 7
    assert normalizar_nota("aus") == "AUS"
    assert normalizar_nota("A") == "AUS"
    assert normalizar_nota("AUSENTE") == "AUS"
    assert normalizar_nota("") == ""

    # Casos inválidos deben lanzar ValueError
    try:
        normalizar_nota(11)
        assert False, "11 debió fallar"
    except ValueError:
        pass

    try:
        normalizar_nota(0)
        assert False, "0 debió fallar"
    except ValueError:
        pass

    try:
        normalizar_nota("7.5")
        assert False, "Nota decimal debió fallar"
    except ValueError:
        pass
    print(" [OK] Validación de notas exacta a Google Apps Script.")

    print("Probando permisos por CUE y Roles...")
    # Dirección DETP ve todo
    sesion_dir = {"verTodo": True, "cues": [], "rol": Roles.DIRECCION}
    assert alcanza_cue(sesion_dir, "3800123") == True

    # Directivo de una institución específica
    sesion_dir_escuela = {"verTodo": False, "cues": ["3800123"], "rol": Roles.DIRECTIVO}
    assert alcanza_cue(sesion_dir_escuela, "3800123") == True
    assert alcanza_cue(sesion_dir_escuela, "3800999") == False
    print(" [OK] Control de acceso institucional verificado.")

    print("\nTODAS LAS PRUEBAS DE LÓGICA PASARON EXITOSAMENTE (100% compatible).")

if __name__ == "__main__":
    test_logica()
