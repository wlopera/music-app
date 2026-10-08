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

