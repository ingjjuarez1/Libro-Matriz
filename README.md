# Libro Matriz FP · DETP Jujuy (Migración Antigravity)

Sistema para que las escuelas de Formación Profesional de Jujuy carguen la matrícula y calificaciones, emitan el acta de examen y generen el certificado analítico oficial, conectado directamente a Google Drive y Google Sheets.

Este proyecto ha sido migrado de **Google Apps Script** a una arquitectura moderna desacoplada en **Python (Starlette / REST API)** y **Frontend Web SPA (HTML5 / CSS / JavaScript)**.

---

## 📁 Estructura del Proyecto

```text
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py             # Constantes, mapeo de celdas de RAC/Acta/Analítico y roles
│   │   │   └── auth.py               # Control de acceso, roles y permisos institucionales por CUE
│   │   ├── services/
│   │   │   ├── google_service.py     # Cliente de Google Drive y Sheets API v4 (Service Account / OAuth2)
│   │   │   ├── datos_service.py      # Lógica de lectura/escritura de RAC, Actas y Analíticos
│   │   │   ├── titulos_service.py    # Circuito oficial de certificados y bandeja central de Títulos
│   │   │   └── instalador_service.py # Instalación de Panel FP e importación automática de carpetas Drive
│   │   └── routers/
│   │       └── api.py                # Endpoints REST (reemplazo de google.script.run)
│   └── main.py                       # Servidor web local y punto de entrada
├── frontend/
│   ├── index.html                    # Interfaz web principal
│   ├── css/
│   │   └── estilos.css               # Estilos responsivos, marca de agua de borrador e impresión
│   └── js/
│       └── app.js                    # Cliente SPA con soporte para bandeja de Títulos y congelamiento
├── credentials/
│   ├── service_account.json.ejemplo  # Plantilla de credenciales de Google Cloud
│   └── service_account.json          # Tu clave privada descargada (protegida por .gitignore)
├── tests/
│   ├── test_connection.py            # Validador de conexión y permisos a Google Drive y Sheets
│   ├── test_circuito_titulos.py      # Pruebas del circuito de Títulos (congelamiento, borrador, estados)
│   └── test_logic.py                 # Pruebas unitarias de conversión de celdas, notas y roles
├── planillas/                        # Catálogos JSON y utilidades de conversión
├── .env.ejemplo                      # Variables de entorno de configuración
└── requirements.txt                  # Dependencias del backend
```

---

## 🔐 1. Configuración de Credenciales de Google Drive

En lugar de las autorizaciones nativas de Apps Script, el backend utiliza una **Cuenta de Servicio (Service Account)** de Google Cloud:

1. Ingresa a [Google Cloud Console](https://console.cloud.google.com).
2. Crea o selecciona tu proyecto institucional.
3. En **APIs y servicios** > **Biblioteca**, habilita:
   - **Google Drive API**
   - **Google Sheets API**
4. Ve a **IAM y administración** > **Cuentas de servicio** > **Crear cuenta de servicio**.
5. En la pestaña **Claves**, selecciona **Agregar clave** > **Crear clave nueva** > **JSON**.
6. Guarda el archivo descargado como:
   ```text
   credentials/service_account.json
   ```
7. **Paso fundamental de permisos en Google Drive:**
   Copia el email de la Service Account (ej: `libro-matriz-fp@tu-proyecto.iam.gserviceaccount.com`) y **compártelo con permiso de "Editor"** en:
   - La carpeta de Drive donde están las planillas de los cursos.
   - La planilla central **Panel FP**.

---

## ⚙️ 2. Variables de Entorno

Copia el archivo `.env.ejemplo` a `.env` y configura el ID de tu planilla central:

```bash
cp .env.ejemplo .env
```

Contenido de `.env`:
```ini
PANEL_ID=1abc...tu_id_de_panel_fp_aqui
GOOGLE_APPLICATION_CREDENTIALS=credentials/service_account.json
```

---

## 🧪 3. Verificación de la Conexión

Ejecuta el script de diagnóstico para comprobar que la conexión a Google Drive y Sheets funciona:

```bash
python tests/test_connection.py
```

Para validar las reglas de negocio (conversión de notas, columnas RAC, permisos por CUE):
```bash
python tests/test_logic.py
```

---

## 📜 5. Circuito Oficial de Emisión de Certificados (Departamento de Títulos)

El sistema incorpora el flujo de control para la emisión de analíticos oficiales:

1. **Filtro de Escuela:** La escuela únicamente puede solicitar certificados para estudiantes cuya situación figure como **"Aprobó"**. Quienes no aprobaron tienen el botón bloqueado.
2. **Rol `titulos` y Bandeja Central:** Los usuarios con rol `titulos` disponen de una bandeja con todos los pedidos de todas las instituciones de la provincia (con Institución, CUE, Curso, Estudiante y Fecha).
3. **Aprobación u Observación:** 
   - **Aprobar:** Asigna el número oficial de registro (individual o en lote).
   - **Observar:** Requiere obligatoriamente ingresar el motivo de rechazo.
4. **Marca de Agua Borrador vs Oficial:**
   - Mientras no esté aprobado, el analítico exhibe una marca de agua diagonal **"BORRADOR - no válido"** y el botón de impresión permanece bloqueado.
   - Al aprobarse, se elimina la marca de agua y se habilita la impresión oficial con el número de certificado.
5. **Congelamiento de Calificaciones:** Al aprobarse el certificado, las notas del estudiante en el RAC y en el Acta de examen quedan **bloqueadas/congeladas permanentemente** para asegurar la inmutabilidad del documento.
6. **Reingreso de Observados:** Si una solicitud es observada, regresa a la escuela mostrando el motivo. Tras la corrección, la escuela reenvía la solicitud a Títulos.

Para validar este circuito en consola:
```bash
python tests/test_circuito_titulos.py
```

Para iniciar el servidor local:

```bash
python backend/main.py
```

Abre tu navegador en:
👉 **`http://localhost:8000`**

### Roles y Pruebas en el Frontend:
El encabezado cuenta con un selector de usuario para alternar entre:
* **Dirección DETP:** visualiza todas las instituciones y el resumen general.
* **Directivo:** visualiza únicamente los cursos de su CUE asignado.
* **Administrativo:** visualiza y tiene permisos de edición sobre las notas de su CUE.
