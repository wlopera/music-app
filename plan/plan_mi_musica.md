# Especificación de Requerimientos: Gestor Organizador de Versiones Musicales

Este documento contiene la especificación de diseño, lógica y comportamiento acordada para el desarrollo de la aplicación de escritorio destinada a organizar las versiones musicales de audio y video.

---

## 1. Arquitectura y Tecnologías Base
* **Plataforma Objetivo:** Windows (Escritorio).
* **Lenguaje de Programación:** Python.
* **Framework de Interfaz Gráfica (GUI):** PyQt6 (permite manejo fluido de componentes avanzados, estilos modernos y personalizables).
* **Almacenamiento de Ajustes:** Archivo `config.json` ubicado en la misma raíz que el ejecutable para asegurar portabilidad.

---

## 2. Archivo de Configuración (`config.json`)
El programa debe leer, actualizar y auto-generar (en caso de no existir) un archivo de configuración estructurado de la siguiente manera:
```json
{
    "carpeta_base": "",
    "carpeta_temporal": "",
    "extensiones_permitidas": [".mp3", ".wav", ".mp4"]
}
```
* **carpeta_base:** Directorio final de almacenamiento de las canciones organizadas.
* **carpeta_temporal:** Directorio puente utilizado para acumular y preparar las canciones de manera inmediata.
* **extensiones_permitidas:** Filtro estricto que controla qué tipos de archivos procesará la app (ignora metadatos extraños, imágenes o archivos de texto ajenos a la producción musical).

---

## 3. Diseño Visual e Interfaz de Usuario (UI)
Inspirado en una cuadrícula simétrica de 2 columnas, el diseño debe ser **bonito, moderno y minimalista**, preferentemente adaptado a un **Modo Oscuro** (estilo estaciones de trabajo de audio digital / DAWs) con bordes suavizados y espaciado estratégico.

### Estructura de Paneles Plegables
La pantalla se dividirá en dos grandes regiones (Superior e Inferior) que pueden maximizarse o colapsarse mediante botones de flecha (`▲` / `▼`) para optimizar el espacio visual de trabajo en pantallas compactas.

#### A. FILA SUPERIOR (Área de Captura y Entrada - Colapsable)
* **Cuadrante Izquierdo (Buscador Global del Disco):** 
  * Un cuadro de texto superior funciona como **Filtro de búsqueda**.
  * Una lista estilo árbol muestra archivos que coincidan en todo el disco duro o directorio seleccionado, restringido a las `extensiones_permitidas`.
* **Cuadrante Derecho (La Carpeta Temporal):**
  * Representa visualmente el estado del directorio `carpeta_temporal`.
  * **Soporte Drag and Drop:** Debe permitir arrastrar múltiples archivos simultáneamente directamente desde el Explorador de Windows y soltarlos aquí.

#### B. FILA INFERIOR (Área de Biblioteca y Destino - Colapsable)
* **Cuadrante Izquierdo (Carpeta Base / Historial):**
  * Un cuadro de texto superior funciona como **Filtro de búsqueda de carpetas organizadas**.
  * Muestra la estructura de la `carpeta_base`.
* **Cuadrante Derecho (Contenido Interno / Historial de Versiones):**
  * Muestra de forma detallada los archivos que pertenecen a la carpeta seleccionada en el cuadrante izquierdo.

#### C. COMPORTAMIENTO ESTILO EXPLORADOR DE WINDOWS
Todas las listas de archivos dentro de los cuadrantes deben estructurarse en columnas ordenables mediante sus encabezados, mostrando de manera idéntica al Explorador de Windows la siguiente metadata:
1. **Nombre del Archivo**
2. **Fecha de Generación Original** (`Creation Time` del sistema operativo Windows, asegurando el momento real en que el archivo nació).
3. **Fecha Actual / Última Modificación** (`Modification Time`).
4. **Tamaño del Archivo** (con sufijos legibles como KB, MB).

---

## 4. Flujo de Trabajo y Lógica Musical (Procesamiento)

### Barra de Control Central (Minimalista)
* Un campo de texto editable (**Campo Edit / Nombre Base**) para corregir el nombre definitivo de la canción.
* **Botón 1:** "Crear Nueva Carpeta de Trabajo". Prepara la carpeta en el destino final.
* **Botón 2:** "Proceder al Proceso (Temp a Definitiva)". Ejecuta la transferencia de archivos.

### Interacciones de Usuario
* **Un clic:** Selecciona el archivo para interactuar o extraer metadatos. Al seleccionar un archivo de cualquier lista, el programa extraerá su nombre (sin extensión) y lo colocará automáticamente en el **Campo Edit** para su posterior corrección.
* **Doble clic o Clic Derecho Contextual:** Abre la Ventana Modal Multimedia.

### Lógica de Re-numeración Cronológica Inteligente
Cuando el usuario presiona "Proceder al Proceso", el programa ejecuta las siguientes instrucciones lógicas:
1. Reúne todos los archivos acumulados en la carpeta `temp` asignados a esa canción. Si se están añadiendo archivos a una carpeta existente, se extraen también los archivos actuales de la carpeta final.
2. Lee la **Fecha de Generación Original** de la totalidad de los archivos recolectados.
3. Ordena toda la lista cronológicamente, desde el archivo más antiguo hasta el más nuevo.
4. Realiza una **Fusión y Re-numeración limpia desde cero**: cada archivo es renombrado dinámicamente con la estructura `[Nombre Base]_v[Índice Secuencial].[Extensión Original]` (Ejemplo: `CancionIdeal_v1.mp3`, `CancionIdeal_v2.wav`, `CancionIdeal_v3.mp4`). Si un nuevo archivo insertado es cronológicamente más viejo que los existentes, tomará de manera transparente la posición correspondiente (`_v1`) y desplazará el resto numéricamente.

---

## 5. Ventana Modal Multimedia Integrada
Al activar un archivo (mediante doble clic o menú contextual), se debe desplegar una ventana flotante (Modal) al frente de la pantalla principal con las siguientes especificaciones:
* **Foco y Bloqueo:** Bloquea la interacción con la ventana de fondo hasta que sea cerrada.
* **Adaptación de Tipo:**
  * **Si es MP4:** Muestra un contenedor visual centrado para renderizar el video, junto con la barra de reproducción inferior.
  * **Si es MP3 o WAV:** Modifica su geometría a una dimensión compacta y minimalista de solo audio (mostrando un diseño limpio, barra de reproducción u onda gráfica representativa).
* **Controles Integrados:** Dispone de botones táctiles independientes para:
  * ▶️ **Play / Continuar**
  * ⏸️ **Pause**
  * ⏹️ **Stop**
  * ❌ **Salir / Cerrar** (Cierra la modal e interrumpe de forma inmediata todo consumo de hilos de audio o video en segundo plano para evitar fugas de sonido).

---

## 6. Decisiones Técnicas Acordadas (Implementadas)

* **Procesamiento:** el botón "Procesar" mueve TODOS los archivos del staging, fusionándolos
  con los existentes en la carpeta `[Base]` y re-numerándolos cronológicamente (`v1..vN`,
  ordenados por fecha original / sidecar). El staging se vacía al terminar.
* **Seguridad de originales:** los originales NUNCA se mueven ni se borran. El staging
  contiene copias (`carpeta_base\_staging`). Permitimos archivos duplicados.
* **Sidecar** `.musicapp.json` por canción: conserva la "Fecha de Generación Original"
  (Windows resetea Creation Time al copiar entre volúmenes).
* **Búsqueda:** estilo navegación de carpetas con raíz seleccionable + filtro de nombre.
  La búsqueda es **recursiva** sobre el directorio raíz seleccionado (máx. 4000 entradas;
  con aviso si se alcanza el tope).
* **Drag & drop:** los archivos pueden soltarse sobre el panel de staging **o sobre la propia
  tabla** (el área de la tabla era un punto ciego previo). Los drops se procesan por
  `pathsDropped`/`dropEvent` y se filtran por extensiones permitidas.
* **Logging:** módulo `app/logs.py` — escribe `musicapp.log` junto al .exe, hooks de
  excepción/Qt/faulthandler y un *watchdog* que vuelca el traceback de todos los hilos si la
  UI no responde más de 20 s. La ventana principal y el reproductor están instrumentados.
* **Backend multimedia:** PyQt6 6.6.0 incluye `QtMultimedia.pyd` y el plugin
  `ffmpegmediaplugin.dll` con **FFmpeg embebido estáticamente** (15,5 MB): NO se necesitan
  DLLs externas. Regla de robustez: nunca llamar a `QMediaPlayer.stop()/setSource(QUrl())`
  desde la UI (pueden bloquearse con medios reales en Windows); se pausa y el backend se
  cierra al destruir el QMediaPlayer junto al diálogo.
* **Empaquetado:** PyInstaller *onedir* (`build.spec`), `console=False`, plugin de
  multimedia incluido, módulos Qt pesados excluidos. Resultado: `dist\Music-App\
  (≈110 MB)` con auto-generación de `config.json` junto al .exe.

## 7. Estado

| Fase | Descripción                                   | Estado      |
|------|-----------------------------------------------|-------------|
| 1    | Config + fsutil + sidecar + tema              | ✅ Verificado |
| 2    | UI (navegador, tablas, staging, ajustes)     | ✅ Verificado |
| 3    | Procesamiento (fusión + re-numeración)       | ✅ Verificado |
| 4    | Ventana modal multimedia                      | ✅ Verificado |
| 5    | Empaquetado .exe portable                     | ✅ Construido |
| Fix  | Búsqueda recursiva + DnD sobre tabla + logs  | ✅ Verificado |

Smoke tests: `tests\smoke_fase1.py`, `tests\smoke_fases23.py`, `tests\smoke_fase4.py`.
Construcción: `build.ps1` o `python -m PyInstaller build.spec`.