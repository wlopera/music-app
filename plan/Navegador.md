# ESPECIFICACIONES TÉCNICAS: MÓDULO NAVEGADOR DE ARCHIVOS MULTIMEDIA (ESTILO WINDOWS EXPLORER)

> **Para:** Equipo de Desarrollo (Antigravity)  
> **De:** Arquitectura & Diseño  
> **Fecha:** Octubre 2026  
> **Proyecto:** Music-App v2.0 (Módulo `NavigatorPage` / Índice 3 del QStackedWidget)

---

## 1. Objetivo del Módulo
Desarrollar el componente **Navegador** para ofrecer una experiencia idéntica al Explorador de Windows, especializada en la gestión de archivos de audio y video de la biblioteca. La interfaz se dividirá en dos áreas interconectadas que permitirán operaciones avanzadas del sistema de archivos de forma transaccional, segura y fluida.

---

## 2. Arquitectura de Datos y Desacoplamiento (Model/View)

Para evitar operaciones costosas de lectura en el hilo principal de la interfaz gráfica, se utilizará de forma estricta la infraestructura nativa de Qt:

* **Modelo Centralizado (`QFileSystemModel`)**: Se instanciará un único modelo para todo el módulo. Este modelo se ejecutará en un hilo secundario automático de Qt, manejando de forma nativa los filtros de extensión (`.mp3`, `.wav`, `.mp4`, etc.) y optimizando el uso de memoria.
* **Inyección de Utilidades de Dominio (`app/fsutil.py`)**: Las acciones físicas en el disco (crear, renombrar, borrar, mover) no las procesan las vistas. Las vistas capturan la intención del usuario y delegan la validación y ejecución en las funciones puras de `fsutil.py` (usando WinAPI donde sea necesario).

---

## 3. Composición de la Interfaz Visual (Layout Jerárquico)

La página `NavigatorPage(QWidget)` ocupará el espacio completo del contenedor derecho al ser seleccionada en el menú lateral. Su estructura interna se compone de la siguiente manera:

+-----------------------------------------------------------------------------------+
|  🎵 Navegador Multimedia                                                           |
+-----------------------------------------------------------------------------------+
|  [ Barra de Herramientas: 📂 Nueva Carpeta  |  ✂️ Cortar  |  📋 Pegar  |  ❌ Borrar ] |
+-----------------------------------------------------------------------------------+
|  [ QSplitter Horizontal Primario ]                                                |
|                                                                                   |
|  PANEL IZQUIERDO: Árbol de Directorios    | PANEL DERECHO: Vista de Contenido     |
|  Componente: QTreeView                    | Componente: QListView o QTableView     |
|                                           |                                       |
|  • Muestra exclusivamente carpetas.       | • Muestra carpetas y archivos válidos.|
|  • Navegación jerárquica expansible.      | • Modo de visualización en Lista/Icono.|
|  • Operaciones: Crear / Borrar Carpetas.  | • Operaciones: Todo el flujo CRUD.    |
|                                           |                                       |
+-----------------------------------------------------------------------------------+
|  Barra de Estado: 3 archivos seleccionados (142 MB) | Ruta: C:\Musica\Proyecto1   |
+-----------------------------------------------------------------------------------+
---

## 4. Reglas de Negocio e Interacción entre Paneles

### A. Sincronización de Navegación
* Al hacer clic en una carpeta del **Panel Izquierdo (`QTreeView`)**, se emitirá una señal que actualizará el índice raíz (*Root Index*) del **Panel Derecho**. El panel derecho se refrescará instantáneamente mostrando el contenido exclusivo de esa carpeta.

### B. Matriz de Operaciones Permitidas y Validaciones

| Área / Componente | Operación | Validación y Comportamiento Requerido |
| :--- | :--- | :--- |
| **Panel Izquierdo**<br>(Árbol) | **Crear Carpeta** | Solicita nombre mediante diálogo. Valida caracteres ilegales en Windows (`\ / : * ? " < > \|`). |
| | **Borrar Carpeta** | Diálogo de confirmación obligatorio. Valida si la carpeta está vacía; si contiene archivos, advierte explícitamente al usuario antes de proceder. |
| **Panel Derecho**<br>(Contenido) | **Crear Carpeta** | Comportamiento estándar idéntico al panel izquierdo. |
| | **Borrar Elemento** | Si es archivo: Envío seguro a la papelera o borrado definitivo previa confirmación. Si está en reproducción, aborta la operación para evitar `WinError 32` (archivo bloqueado). |
| | **Renombrar** | Doble clic pausado o tecla `F2`. Valida que la extensión del archivo no sea alterada accidentalmente por el usuario (protección del formato multimedia). |
| | **Copiar / Mover** | Soporte de portapapeles interno (`Cortar` / `Copiar` / `Pegar`) y soporte nativo de **Drag & Drop** mediante tipos MIME. El movimiento entre diferentes discos físicos invocará `fsutil.safe_move`. |

### C. Integración Multimedia (Reproducción Dedicada)
* Al hacer doble clic sobre un archivo de audio o video en el **Panel Derecho**, la vista invocará de manera directa al componente **`MediaModal`** que la aplicación ya tiene programado. 
* El diseño debe garantizar que, antes de iniciar la reproducción, se liberen los descriptores de cualquier archivo previo para mantener el sistema libre de bloqueos en el SO.

---

## 5. Directrices de Diseño Estético Minimalista
* **Líneas Divisorias**: El `QSplitter` debe configurarse con un ancho delgado (`handleWidth: 1px`) y un color gris tenue alineado al archivo `theme.qss`.
* **Estilo de Selección**: Los elementos seleccionados en ambos paneles deben usar el color de acento suave del tema de la aplicación, evitando los azules chillones nativos de Windows antiguos.
* **Iconografía**: Uso de iconos vectoriales limpios o emojis unicode estables para diferenciar visualmente carpetas, pistas de audio y archivos de video.

Mantener lo actual de poder oir y ver caciones por icono o por doble click y uso de click derecho dle mouse.
Del lado derecho tabla de archivos:
  Nombre, Fecha, tipo, tamaño. acciones (renombrar, oir o ver, borrar)
Minimalista, practico y bonito.
Los códigos son referenciales 
