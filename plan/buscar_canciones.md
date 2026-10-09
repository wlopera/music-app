# ESPECIFICACIONES TÉCNICAS: MOTOR DE DETECCIÓN Y AGRUPACIÓN DE CANCIONES (BOTÓN BUSCAR)

> **Para:** Equipo de Desarrollo (Antigravity)  
> **De:** Arquitectura & Diseño  
> **Fecha:** Octubre 2026  
> **Proyecto:** Music-App (Módulo `SearchPage` / Core de Clasificación)

---

## 1. El Problema del Productor Musical
Un productor genera múltiples versiones, renders y exportaciones de una misma composición en una carpeta temporal. Aunque el ritmo cambie ligeramente, el tempo varíe,
 o se exporte en diferentes formatos (`.wav`, `.mp3`), **la identidad melódica/armónica de la canción es la misma**. 

El sistema debe analizar un universo de canciones sin clasificar y agrupar automáticamente los archivos que corresponden a la misma composición en carpetas únicas. 
Si una canción no tiene duplicados o variantes, se queda en una carpeta individual.

---

## 2. Enfoque Arquitectónico del Dominio (Sin Dependencias de UI)

Para lograr esto de manera robusta sin congelar la interfaz, dividiremos la solución en dos partes: el **Algoritmo de Audio (Dominio)** y la **Presentación (UI)**.

### A. Estrategia de Reconocimiento (Backend de Audio)
Para identificar variaciones de ritmo o tempo de una misma canción, el análisis básico por metadatos (duración, nombre o tamaño) es inútil.
 Antigravity implementará una tubería basada en una de estas dos opciones tecnológicas en `app/processing.py` o un nuevo `app/audio_brain.py`:

1. **Opción Recomendada (Robusta a cambios de ritmo/tempo): Chroma Feature Cross-Correlation**  
   Utilizar `librosa` para extraer la matriz de características de cromatismo (Chroma STFT / CQT), la cual mide la energía de las 12 notas de la escala cromática.
   Las canciones que comparten la misma melodía/armonía tendrán vectores de croma altamente correlacionados, sin importar si una va a 90 BPM y otra a 120 BPM.
2. **Opción Rápida (Huella acústica exacta): Dejavu / AcoustID**  
   Generar hashes basados en los picos de frecuencias del espectrograma. Es ultra veloz, pero más sensible si la estructura musical cambia drásticamente.

### B. El Algoritmo de Clasificación (Clustering)
Una vez que cada archivo de audio se traduce en un vector matemático (huella), aplicaremos un algoritmo de **Clustering no supervisado 
(como Agglomerative Clustering o DBSCAN)** con una distancia umbral (Threshold). 
* Si la distancia entre dos audios es menor al umbral θ, pertenecen al mismo grupo.
* Los archivos que no se parecen a ningún otro forman un clúster unitario (carpeta sola).

---

## 3. Flujo del Pipeline (Plan-then-Execute)

[ Universo de Audios ] ➔ [ Extracción Chroma/Huella ] ➔ [ Matriz de Similitud ] ➔ [ Agrupación/Clustering ] ➔ [ Creación de Carpetas ]

1. **Escanear**: Se leen todos los archivos permitidos de la carpeta temporal/origen.
2. **Procesar**: Se extrae el perfil acústico de cada uno.
3. **Agrupar**: El algoritmo detecta los grupos:
   - `Grupo_A`: `aaa.mp3`, `b.wav` (Misma canción, distinto ritmo/render).
   - `Grupo_B`: `ccc.mp3` (Canción única).
4. **Ejecutar en disco**: Se crean carpetas dinámicas (`Composicion_001`, `Composicion_002`) o se solicita al usuario asignarles un nombre base antes de mover los archivos 
de manera transaccional (reutilizando `fsutil.safe_move`).

---

## 4. Diseño del Componente Visual (`app/ui/pages/search_page.py`)

La interfaz debe ser minimalista, limpia y guiada por estados:

+-----------------------------------------------------------------------+
|  🔍 Buscar Canciones Similares                                        |
+-----------------------------------------------------------------------+
|  Ruta a analizar: [ C:/Proyectos/Musica/Staging               ] [Busc] |
|  Umbral de sensibilidad: Minimalista (Slider: Preciso <-------> Amplio)|
+-----------------------------------------------------------------------+
|  [ BOTÓN PRINCIPAL: ANALIZAR UNIVERSO DE AUDIO ]                      |
+-----------------------------------------------------------------------+
|  Resultados del Análisis (Vista Previa Antes de Aplicar):             |
|                                                                       |
|  📁 Grupo Detectado #1 (2 archivos)                                   |
|     ├── 🎵 aaa.mp3 (Clave armónica detectada / Duración)              |
|     └── 🎵 b.mp3                                                      |
|                                                                       |
|  📁 Canciones Únicas (Se aislarán en carpetas individuales)           |
|     └── 🎵 ccc.mp3                                                    |
+-----------------------------------------------------------------------+
|                                              [ BOTÓN: EJECUTAR ORDEN ]|
+-----------------------------------------------------------------------+


### Directrices para Antigravity en la UI:
* **Uso de Hilos Obligatorio (`QThread` / `QRunnable`):** La extracción de huellas de audio es intensiva en CPU. 
El análisis debe ejecutarse en un hilo secundario para evitar que la UI de PyQt6 muestre el cartel "No responde".
* **Barras de Progreso Sutiles:** Mostrar un `QProgressBar` en modo indeterminado o con porcentaje mientras se analizan los archivos.

---

## 5. Criterios de Aceptación para el Desarrollo
1. **Aislamiento en Carpetas:** El resultado en disco debe crear subcarpetas físicas organizadas de forma limpia. Si la canción no se repite, 
2. **Tolerancia:** Debe emparejar exitosamente un archivo `.wav` sin comprimir con su versión comprimida en `.mp3` si la composición de fondo es la misma.
3. **Seguridad del FS:** Ningún archivo debe ser eliminado o sobrescrito durante el proceso de reubicación; si hay colisiones de nombres dentro de un mismo grupo, 
renombrar agregando un sufijo numérico (ej. `aaa_2.mp3`).

---

## Estado de implementación (v1.081026-4)

**Implementado y verificado.** Esta sección registra las decisiones finales tomadas
al construir la fase.

### Arquitectura final
* **Dominio:** `app/audio_brain.py`. Lazy-import de `librosa` (opcional) con
  degradación elegante: si falta, `availability()` devuelve `(False, motivo)` y la
  vista se deshabilita con un aviso, sin romper la app.
* **Huella:** `extract_profile()` usa chroma CQT sincronizado a beats (mediana por
  beat) o media global si no se detectan beats, con *gates* de duración y
  onsets/beat. Invariante al tempo (una misma melodía a 90/120/150 BPM se agrupa:
  similitud media ≈ 0.977).
* **Agrupación:** `build_plan()` — algoritmo aglomerativo por **enlace completo
  (complete linkage)** con umbral coseno θ (0.975 Flexible … 0.985 Recomendado … 0.995 Estricto).
  Exige que todas las parejas del grupo superen θ, eliminando el efecto cadena
  (single-linkage chaining) donde temas con escalas similares se mezclaban masivamente.
  Los grupos se numeran `carpeta_1, carpeta_2, …` **in-situ** dentro de la carpeta
  analizada. Las canciones únicas permanecen en la raíz sin moverse.
* **UI y Reactividad:** `app/ui/views/search_view.py`. Incorpora:
  - Botón «Copiar» para exportar el resumen de coincidencias al portapapeles.
  - Botón «Limpiar» y auto-limpieza ante cambios de ruta o inicio de análisis.
  - Recálculo matemático al vuelo al mover el slider si los audios ya fueron analizados
    (sin tener que volver a decodificar con librosa).
* **Ejecución:** `execute_group_plan()` reutiliza el patrón transaccional de dos
  fases (temp-rename) + `fsutil.safe_move` + `Sidecar.rebuild`, preservando
  `original_ct` / `original_name`.
* **UI:** `app/ui/views/search_view.py` (NO `app/ui/pages/search_page.py`, ruta
  descartada en el refactor de navegación). Está embebida como página "Buscar" del
  `QStackedWidget` de `app/ui/main_window.py`.
* **Worker:** `app/ui/search_worker.py` — `SearchAnalyzer`, que corre el análisis en
  un `threading.Thread` **plano** (no `QThread`) y emite señales queued hacia el hilo
  GUI. Entrega progreso y mantiene la UI fluida.

### Decisiones
* **Solo audio:** se descartan los vídeos. Extensiones válidas de la app:
  `.mp3, .wav, .opus, .flac, .ogg, .aiff, .aif` (todas decodificables por
  libsndfile). Formatos con MPEG‑4 (`.mp4/.mov/.mkv/.m4a/.aac`) y `.wma` no se
  pueden decodificar sin ffmpeg y quedan fuera.
* **Motor empaquetado:** el `.exe` incluye `librosa` + `soundfile` (vía
  `hiddenimports` en `build.spec`, con los hooks de `pyinstaller-hooks-contrib`),
  de modo que «Buscar Canciones» funciona en el ejecutable. El núcleo sigue sin
  librerías de audio en `requirements.txt`; el motor vive en
  `requirements-audio.txt`.
* **Degradación segura:** si el motor no se puede importar (incluido un fallo
  nativo de DLL), `availability()` captura cualquier excepción, deja la vista
  deshabilitada con aviso y la app nunca se cae por ello.

### Lecciones (crashes investigados)
* **PyQt6 aborta el proceso** (`0xC0000409`) si una excepción escapa de un slot.
  Varios "crashes fantasma" durante el desarrollo eran scripts de diagnóstico que
  referenciaban `view._thread` (ya inexistente). No mezclar refactors con tests que
  accedan a atributos privados.
* Se descartó la hipótesis de "librosa + hilos = crash": tanto `threading.Thread`
  como el bucle de eventos son seguros; el `QThread` nunca fue el problema.
* **Módulo `email` en PyInstaller:** En Python 3.12, `soundfile` e `importlib.metadata`
  importan internamente `email.message`. Si `"email"` está en los `EXCLUDES` de `build.spec`,
  la decodificación de audios falla en tiempo de ejecución con `No module named 'email'`,
  provocando que el 100% de los archivos queden en estado "sin analizar". Se retiró
  `email` de los excludes y se incorporó a `AUDIO_HIDDEN_IMPORTS`.
* **Transparencia en la UI ante fallos de análisis:** `search_view.py` ahora desglosa
  una tarjeta de alerta con los motivos de error (`plan.errors`) y no sugiere de manera
  engañosa mover el slider de sensibilidad cuando la causa es un fallo de procesamiento
  o formato.

---

## 6. Especificaciones de Extensión: Music-App v2.0 (Criterio por Letra y Audición Interactiva)

> **Principio de Diseño:** Extensión puramente aditiva y no destructiva. El motor de similitud acústica actual (enlace completo al 98.5%), la auto-limpieza, el panel de logs y el movimiento transaccional de archivos se mantienen intactos como la base sólida de producción.

### A. Límites de Seguridad y Protección del Sistema
* **Tope de canciones por análisis:** Máximo **100 archivos de audio** por lote.
* **Tope de tamaño por archivo:** Máximo **150 MB** por archivo individual.
* **Comportamiento en UI:**
  - Se visualiza una nota informativa en el panel de análisis:
    `ℹ️ Límite de seguridad: Hasta 100 canciones por lote · Máximo 150 MB por archivo.`
  - Si una carpeta excede 100 audios o contiene algún archivo > 150 MB, el sistema emite una advertencia visual destacada y deshabilita el botón «ANALIZAR» hasta que la selección cumpla los límites, protegiendo la memoria RAM y el procesador de bloqueos.

### B. Criterio Adicional por Letra Nativa (Criterio C)
* **Extracción Ligera y Local:**
  1. Lectura del tag de letra embebido en el archivo (`USLT` en MP3, `LYRICS` / `UNSYNCEDLYRICS` en Vorbis/FLAC/Opus).
  2. Fallback local: Si el tag no existe, busca si hay un archivo de texto acompañante con el mismo nombre en la carpeta (`cancion.txt` o `cancion.lrc`).
  3. No requiere transcripción por IA ni dependencias pesadas; lectura instantánea (< 1 ms).
* **Normalización y Comparación:**
  - Sin traducción: comparación estricta en el idioma nativo de la composición.
  - Normalización: minúsculas, eliminación de signos de puntuación y filtrado de palabras vacías (*stopwords*).
  - Umbral de coincidencia: **$\ge 80\%$** de similitud léxica.
* **Degradación Elegante:**
  - Si las canciones no tienen letra (o son instrumentales), el Criterio C simplemente no interviene y el sistema agrupa al 100% por similitud acústica al 98.5%.
  - Si dos canciones comparten letra con coincidencia $\ge 80\%$, se agrupan automáticamente incluso si la instrumentación o tempo varían sustancialmente.

### C. Resultados Interactivos y Audición en Línea
* **Líneas interactivas en la lista de resultados:**
  Tanto en las carpetas agrupadas como en la sección de canciones únicas, cada fila de canción cuenta con:
  - **Botón `▶` (Play):** Abre de forma síncrona el reproductor cinematográfico `MediaModal` para audicionar el track antes de mover archivos.
  - **Doble Clic:** Hacer doble clic en cualquier fila reproduce la canción inmediatamente.
  - **Botón `📝` (Letra):** Abre un diálogo modal minimalista (`LyricsModal`):
    - Si tiene letra: Muestra el texto original con barra de scroll.
    - Si no tiene letra: Muestra el mensaje: *«Canción sin letra registrada en metadatos (ID3) ni archivo .txt/.lrc acompañante»*.
* **Aislamiento de Canciones Únicas:**
  - Las canciones únicas se listan claramente en una sección dedicada inferior para permitir su escucha.
  - **No se mueven ni se tocan en disco** al presionar «EJECUTAR GRUPOS»; permanecen en su ubicación original en la raíz de la carpeta.