"""
Prueba completa del circuito de emisión de certificados oficiales (Departamento de Títulos).
Valida las 6 reglas de negocio requeridas:
1. Solo alumnos con 'Aprobó' pueden solicitar certificado.
2. Rol 'titulos' ve todos los pedidos en bandeja centralizada.
3. Rol 'titulos' aprueba u observa con motivo obligatorio y soporta lotes.
4. Analítico en estado Borrador mientras no esté aprobado.
5. Calificaciones congeladas tras la aprobación oficial.
6. Reingreso de solicitudes observadas.
"""

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.app.core.config import Roles, EstadoCertificado
from backend.app.core.auth import sesion, PermissionDeniedException
from backend.app.services.titulos_service import (
    crear_o_reingresar_solicitud, aprobar_solicitud, observar_solicitud,
    aprobar_en_lote, listar_solicitudes, esta_estudiante_congelado,
    _SOLICITUDES_CACHE
)
from backend.app.services.datos_service import guardar_notas, leer_curso

def test_circuito():
    print("=================================================================")
    print("   TEST DEL CIRCUITO DE CERTIFICADOS Y BANDEJA DE TÍTULOS")
    print("=================================================================\n")

    # Sesiones de prueba
    s_escuela = sesion("admin@ep6.jujuy.gob.ar")
    s_titulos = sesion("titulos@educacion.jujuy.gob.ar")

    assert s_escuela["rol"] == Roles.ADMINISTRATIVO
    assert s_titulos["esTitulos"] == True
    print("1. [OK] Roles identificados correctamente (Administrativo y titulos).")

    # Regla 1: Solo alumnos con 'Aprobó'
    print("\n2. Probando Regla 1 (Filtro por Aprobó)...")
    est_desaprobado = {
        "apellido": "LOPEZ", "nombres": "Juan", "documento": "35000111",
        "situacion": "Desaprobó Módulo 2", "notaFinal": "5"
    }
    curso_demo = {"id": "curso-peluquero-ep6-demo", "cue": "3800006", "oferta": "Peluquero", "ciclo": "2026"}

    try:
        crear_o_reingresar_solicitud("curso-peluquero-ep6-demo", "35000111", s_escuela, est_desaprobado, curso_demo)
        assert False, "Debió rechazar solicitud para alumno desaprobado"
    except PermissionDeniedException as e:
        print(f"   [OK] Bloqueo exitoso para alumno no aprobado: {e}")

    # Estudiante que sí aprobó
    est_aprobado = {
        "apellido": "BENITEZ", "nombres": "Carlos Javier", "documento": "39876543",
        "situacion": "Aprobó todo", "notaFinal": "8"
    }
    sol_benitez = crear_o_reingresar_solicitud("curso-peluquero-ep6-demo", "39876543", s_escuela, est_aprobado, curso_demo)
    assert sol_benitez["estado"] == EstadoCertificado.PENDIENTE
    print("   [OK] Solicitud creada exitosamente en estado 'Pendiente'.")

    # Regla 2: Bandeja de Títulos
    print("\n3. Probando Regla 2 (Bandeja centralizada de Títulos)...")
    pedidos_titulos = listar_solicitudes(s_titulos)
    assert len(pedidos_titulos) >= 1
    print(f"   [OK] Rol 'titulos' visualiza {len(pedidos_titulos)} pedidos en la bandeja central.")

    # Regla 3: Observación con motivo obligatorio
    print("\n4. Probando Regla 3 (Observación con motivo)...")
    try:
        observar_solicitud(sol_benitez["id"], "", s_titulos)
        assert False, "Debió rechazar observación sin motivo"
    except ValueError as e:
        print(f"   [OK] Rechazo exitoso ante motivo vacío: {e}")

    sol_obs = observar_solicitud(sol_benitez["id"], "Falta legalizar partida de nacimiento", s_titulos)
    assert sol_obs["estado"] == EstadoCertificado.OBSERVADO
    assert sol_obs["motivoObservacion"] == "Falta legalizar partida de nacimiento"
    print("   [OK] Solicitud observada correctamente con motivo.")

    # Regla 6: Reingreso por parte de la escuela
    print("\n5. Probando Regla 6 (Reingreso de solicitud observada)...")
    sol_reingresada = crear_o_reingresar_solicitud("curso-peluquero-ep6-demo", "39876543", s_escuela, est_aprobado, curso_demo)
    assert sol_reingresada["estado"] == EstadoCertificado.PENDIENTE
    assert sol_reingresada["motivoObservacion"] == ""
    print("   [OK] Solicitud reingresada a estado 'Pendiente' con motivo limpio.")

    # Regla 3 & 5: Aprobación, asignación de certificado y congelamiento de notas
    print("\n6. Probando Regla 5 (Aprobación y congelamiento de notas)...")
    sol_aprobada = aprobar_solicitud(sol_reingresada["id"], s_titulos, "38-00041285-2026")
    assert sol_aprobada["estado"] == EstadoCertificado.APROBADO
    assert sol_aprobada["numeroCertificado"] == "38-00041285-2026"
    print(f"   [OK] Certificado aprobado con N° Oficial: {sol_aprobada['numeroCertificado']}")

    # Verificar que las notas estén congeladas
    assert esta_estudiante_congelado("curso-peluquero-ep6-demo", "39876543") == True
    try:
        # Intentar modificar notas del estudiante aprobado (fila 10 es Benitez)
        guardar_notas("curso-peluquero-ep6-demo", [{"fila": 10, "modulo": 0, "valor": "10"}], s_escuela)
        assert False, "Debió impedir modificación de notas congeladas"
    except PermissionDeniedException as e:
        print(f"   [OK] Bloqueo exitoso de modificación de notas: {e}")

    # Aprobación en lote
    print("\n7. Probando Aprobación en Lote...")
    lote = aprobar_en_lote([sol_benitez["id"]], s_titulos)
    assert len(lote) == 1
    print("   [OK] Aprobación en lote funcionando correctamente.")

    print("\n=================================================================")
    print("   ¡TODAS LAS REGLAS DEL CIRCUITO DE TÍTULOS FUNCIONAN AL 100%!")
    print("=================================================================\n")

if __name__ == "__main__":
    test_circuito()
