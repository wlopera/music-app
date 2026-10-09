# Guía de Compilación, Instalador y Distribución de Music-App

> **Documento de respaldo técnico:** Describe el ciclo completo de empaquetado, generación del instalador formal en Windows, gestión de permisos para `config.json` y logs, y el proceso de desinstalación limpia.

---

## 1. Arquitectura de Distribución

La distribución de **Music-App** se estructura en dos fases complementarias:

```
[Código Fuente Python + PyQt6]
            │
            ▼  (Paso 1: PyInstaller build.spec)
[dist\Music-App\ (Carpeta Onedir)]
   ├── Music-App.exe (Con icono oficial W ⚡ L)
   ├── PyQt6 / Qt6 / Plugins Multimedia
   ├── assets / (icon.ico, icon.png, QSS temas)
   └── config_template.json
            │
            ▼  (Paso 2: Inno Setup setup.iss)
[dist\installer\MusicApp-Setup.exe]  <── Archivo único de distribución para el usuario final
```

---

## 2. Estrategia de Permisos y Datos de Usuario (Modo Dual)

En Windows, las aplicaciones instaladas en `C:\Program Files\` son de **solo lectura** para usuarios estándar. Intentar escribir archivos de configuración o logs en esa carpeta provoca el error de sistema:
`PermissionError: [Errno 13] Access is denied`

### Solución Implementada: Modo Dual Inteligente
La aplicación en [`main.py`](../main.py) implementa la función `user_data_dir()` con detección automática:

1. **Modo Portable / Desarrollo (Por defecto si la carpeta es editable):**
   * Al ejecutarse desde el código fuente (`C:\2026\Music-App`) o desde una carpeta portátil / pendrive con permisos de escritura, o si existe el archivo testigo `portable` o `portable.dat`.
   * **Ubicación:** `config.json` y `musicapp.log` se mantienen junto al ejecutable.

2. **Modo Instalado (Protegido por UAC en `Program Files`):**
   * Si la app detecta que corre desde `Program Files` o una carpeta sin permisos de escritura.
   * **Configuración:** `%APPDATA%\Music-App\config.json` (aislado por usuario).
   * **Logs:** `%APPDATA%\Music-App\musicapp.log` (permite escritura sin elevación).
   * **Primer Arranque:** Si el archivo `config.json` no existe en AppData, la aplicación lo inicializa automáticamente copiando la plantilla [`config_template.json`](../config_template.json) con los formatos permitidos de audio y video.

---

## 3. Identidad Visual e Iconografía (W ⚡ L)

* **Logo Oficial:** Insignia *squircle* azul oscuro con letras cromadas **W** y **L** unidas por un **rayo eléctrico (⚡)** en amarillo neón brillante, con ondas de audio de fondo.
* **Formatos integrados:**
  * `assets/icon.ico`: Contiene capas multi-resolución (256, 128, 64, 48, 32, 16 px).
  * `assets/icon.png`: Versión en alta definición para interfaz Qt.
* **Puntos de visualización:**
  1. **Ejecutable y Explorador:** Incrustado en el archivo `Music-App.exe` vía [`build.spec`](../build.spec).
  2. **Barra de Tareas de Windows:** Registrado con `SetCurrentProcessExplicitAppUserModelID("MusicApp.WL.1.0")` en [`main.py`](../main.py).
  3. **Cabecera de la Ventana:** Se muestra a 26x26 px justo antes del texto «Music-App» en [`app/ui/header.py`](../app/ui/header.py).
  4. **Instalador:** `MusicApp-Setup.exe` utiliza el mismo icono mediante `SetupIconFile=assets\icon.ico` en [`setup.iss`](../setup.iss).

---

## 4. Prerrequisitos para Generar el Instalador

1. **Python 3.12+** con el entorno virtual `.venv` configurado.
2. **Inno Setup 6:** Compilador de instaladores para Windows.
   * Instalación rápida vía Windows Terminal:
     ```powershell
     winget install JRSoftware.InnoSetup
     ```
   * O descarga directa desde su web oficial: [https://jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php).

---

## 5. Proceso de Compilación Paso a Paso

### Opción A: Compilación Automática (Recomendada)
Se incluye el script automatizado [`build_installer.ps1`](../build_installer.ps1), que realiza todo el proceso en un solo comando:

```powershell
powershell -ExecutionPolicy Bypass -File build_installer.ps1
```

**Lo que hace el script:**
1. Comprueba si existe el binario en `dist\Music-App\Music-App.exe`. Si no existe, invoca primero [`build.ps1`](../build.ps1) para compilar con PyInstaller.
2. Localiza automáticamente el compilador `ISCC.exe` de Inno Setup en el sistema.
3. Compila el script [`setup.iss`](../setup.iss) y genera el archivo final en:
   ```
   dist\installer\MusicApp-Setup.exe
   ```

---

### Opción B: Compilación Manual por Fases

1. **Incrementar versión (Opcional):**
   ```powershell
   python -m app.version bump
   ```

2. **Compilar binarios con PyInstaller:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```

3. **Compilar instalador con Inno Setup:**
   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
   ```

---

## 6. Proceso de Instalación en la Máquina del Usuario

1. El usuario ejecuta `MusicApp-Setup.exe`.
2. Windows solicita confirmación de Administrador (UAC) únicamente para escribir en `C:\Program Files\Music-App`.
3. El instalador:
   * Copia todos los ejecutables, DLLs y componentes de Qt/FFmpeg.
   * Crea el acceso directo en el **Menú Inicio**.
   * Crea el acceso directo opcional en el **Escritorio**.
   * Registra el desinstalador nativo en el Panel de Control y Configuración de Windows.
4. Al abrir la app, esta corre como **usuario normal** (sin pedir permisos de administrador), guardando su configuración y logs en `%APPDATA%\Music-App\`.

---

## 7. Proceso de Desinstalación Limpia

La aplicación se puede desinstalar de forma nativa desde:
* **Configuración de Windows** → *Aplicaciones* → *Aplicaciones instaladas* → *Music-App* → *Desinstalar*.
* O desde el Menú Inicio → *Desinstalar Music-App*.

### Manejo de Datos Residuales:
Durante la desinstalación, el asistente ejecuta el código Pascal configurado en [`setup.iss`](../setup.iss):
1. Elimina todos los archivos del programa en `C:\Program Files\Music-App`.
2. Muestra un cuadro de confirmación:
   > *«¿Deseas eliminar también tus datos de configuración y carpetas guardadas en AppData?»*
   * **Si responde Sí:** Borra `%APPDATA%\Music-App`, dejando el sistema 100% limpio.
   * **Si responde No:** Conserva `config.json` para que, en caso de reinstalar o actualizar, el usuario conserve sus carpetas base y preferencias.

---

## 8. Verificación y Pruebas Rápidas

| Prueba | Comando o Acción | Resultado Esperado |
| :--- | :--- | :--- |
| **Import / Sintaxis** | `python -c "import main; print('OK')"` | Imprime `OK` sin excepciones. |
| **Detección de Rutas** | `python -c "import main; print(main.user_data_dir())"` | Retorna la ruta correspondiente según el modo. |
| **Prueba de Inno Setup** | `powershell -File build_installer.ps1` | Reporta éxito o avisa si falta instalar Inno Setup. |
