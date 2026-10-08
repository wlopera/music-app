# ESPECIFICACIONES TÉCNICAS: REFACTORIZACIÓN DE INTERFAZ (Navegación Lateral Minimalista)

> **Para:** Equipo de Desarrollo (Antigravity)  
> **De:** Arquitectura & Diseño  
> **Fecha:** Octubre 2026  
> **Proyecto:** Music-App (Navegación Modular v2.0)

---

necesito. hacer un refactor. Del lado izquierdo (un area) crear un menu con las opciones
1) Inicio: Ventana de bienvenida (ya no necesita el boton que llama a la opcion Agrupar temas)
2) Agrupar Temas: Lo programa actualmente 
3) Buscar Canciones: En construcción
Del lado derecho:
1) Vista minimalista de bienvenida 
2) El control de canciones ya programado
3) Un proceso a desarrollar para poder buscar canciones iguales dentro d eun universo de cancionesDE manera minimalista, elegante y bonita


## 1. Objetivo del Refactor
Migrar la interfaz actual de una sola pantalla hacia un patrón **Sidebar Navigation (Navigation Drawer)** 
pantallas de forma modular, minimalista y elegante.

---


Para mantener el diseño desacoplado (MVP ligero), se deben crear/modificar los siguientes archivos en la capa de presentación:

+---------------------------------------------------------------------------------------------------+

|  Music-App                                                                                   _ 口 X |
+---------------------------------------------------------------------------------------------------+

|  | 🏠 Inicio          |  [ QStackedWidget - Panel Derecho Activo ]                                  |
|  |                    |                                                                           |
|  | 🎵 Agrupar Temas   |  VISTA ACTUAL (Se despliega completa aquí al pulsar "Agrupar Temas"):      |
|  |                    |  +---------------------------------------------------------------------+  |
|  | 🔍 Buscar Canción  |  | ▲ ENTRADA - EXPLORADOR Y STAGING                                    |  |
|  |                    |  +---------------------------------------------------------------------+  |
|  |                    |  | ▲ BIBLIOTECA - BASE Y VERSIONES                                     |  |
|  |                    |  +---------------------------------------------------------------------+  |
|  |                    |                                                                           |
|  |                    |  VISTAS ALTERNATIVAS (Conmutadas dinámicamente):                          |
|  |                    |  • Pantalla de Bienvenida Minimalista (Módulo en construcción)             |
|  |                    |  • Motor de Búsqueda de Duplicados (Algoritmo por desarrollar)            |
|  +--------------------+---------------------------------------------------------------------------+

---

## Estado de implementación (v1.081026-3)

Refactor completado en el código fuente:

- **Shell** (`app/ui/main_window.py`, nuevamente orquestador): ventana frameless
  (ventana de título manual en la cabecera, arrastre + doble clic para maximizar,
  botones `_ □ ✕`), menú lateral (`app/ui/sidebar.py`), panel derecho
  `QStackedWidget` con 3 vistas y pie (`app/ui/footer.py`) con estado y firma.
  **Nota técnica:** NO se sobrescribe `nativeEvent` (se demostró que provoca un
  access violation en PyQt6/Windows); el redimensionado se resuelve con un
  `QSizeGrip` en la esquina inferior derecha del pie.
- **Vistas** (`app/ui/views/`): `welcome_view.py` (Inicio, antes era un diálogo
  modal), `agrupar_view.py` (lógica extraída íntegra del antiguo MainWindow,
  emite `statusMessage` hacia el pie), `search_view.py` (placeholder).
- **main.py** arranca directamente en Inicio (se eliminó el diálogo de bienvenida).
- Tema QSS claro/oscuro ampliado (cabecera, sidebar, pie, botones de ventana).
- Smoke tests actualizados (pie en lugar de statusbar; accesos vía `win.agrupar.*`).

### Pendiente (fuera del alcance)
- Motor de búsqueda de duplicados (Fase 2).
- ~~AV al cierre del `.exe` empaquetado~~ **Resuelto (v1.081026-3):** lo disparaba el
  hilo watchdog + `faulthandler` de `app/logs.py` durante el teardown del intérprete.
  `main.py` ahora fuerza `os._exit(code)` tras `app.exec()`: el `.exe` sale con código
  0 y sin crash report (verificado con `MUSICAPP_EXIT_MS`).
- Redimensionado frameless solo por la esquina inferior derecha (`QSizeGrip`); no por
  bordes (sobrescribir `nativeEvent` está descartado por el AV documentado antes).