"""Interfaz grafica del Sistema de Estimacion de Ancho de Calles (SEAC).

La interfaz mantiene separada la presentacion de la logica del sistema. Reutiliza
el pipeline existente para ejecutar el procesamiento y posteriormente carga el
reporte JSON y las imagenes generadas en la carpeta de resultados.

Puede ejecutarse de forma remota mediante SSH con reenvio X11.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from acerca_de import mostrar_ventana_acerca_de

from seac_pipeline import crear_parser, ejecutar_pipeline, validar_argumentos


class InterfazSEAC(tk.Tk):
    """Ventana principal del prototipo grafico del SEAC."""

    def __init__(self, args: Any) -> None:
        super().__init__()
        self.args = args
        self.args.mostrar = False

        self.title("Sistema de Estimacion de Ancho de Calles (SEAC)")
        self.geometry("1100x650")
        self.minsize(950, 580)

        self._imagen_satelital_tk: ImageTk.PhotoImage | None = None
        self._imagen_camara_tk: ImageTk.PhotoImage | None = None
        self._ruta_foto_camara: Path | None = None
        self._imagen_analisis_tk: ImageTk.PhotoImage | None = None
        self._ruta_imagen_analisis: Path | None = None
        self._carpeta_resultados: Path | None = None
        self._ruta_reporte_pdf: Path | None = None

        self.estado_var = tk.StringVar(value="Listo para iniciar.")
        self.ancho_var = tk.StringVar(value="-- m")
        self.confianza_var = tk.StringVar(value="Confianza: --")
        self.detalle_resultado_var = tk.StringVar(value="Sin resultados")

        self._configurar_estilo()
        self._crear_interfaz()

    def _configurar_estilo(self) -> None:
        """Configura un estilo sencillo basado en ttk."""
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass

        estilo.configure("Titulo.TLabel", font=("TkDefaultFont", 15, "bold"))
        estilo.configure("Subtitulo.TLabel", font=("TkDefaultFont", 11, "bold"))
        estilo.configure("Resultado.TLabel", font=("TkDefaultFont", 24, "bold"))
        estilo.configure("Accion.TButton", padding=(10, 8))
        estilo.configure("Accion.TMenubutton", padding=(10, 8))

    def _crear_interfaz(self) -> None:
        """Construye los paneles de acuerdo con el mockup del proyecto."""
        contenedor = ttk.Frame(self, padding=12)
        contenedor.pack(fill="both", expand=True)

        contenedor.columnconfigure(0, weight=4)
        contenedor.columnconfigure(1, weight=4)
        contenedor.columnconfigure(2, weight=1)
        contenedor.rowconfigure(1, weight=1)

        titulo = ttk.Label(
            contenedor,
            text="Sistema de Estimacion de Ancho de Calles (SEAC)",
            style="Titulo.TLabel",
            anchor="center",
        )
        titulo.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 12))

        # --------------------------------------------------------------
        # Columna izquierda: GPS + imagen satelital.
        # --------------------------------------------------------------
        izquierda = ttk.LabelFrame(contenedor, text="Ubicacion y referencia satelital", padding=12)
        izquierda.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        izquierda.columnconfigure(0, weight=1)
        izquierda.rowconfigure(1, weight=1)

        panel_gps = ttk.LabelFrame(izquierda, text="Panel 1: Ubicacion y metricas", padding=10)
        panel_gps.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        panel_gps.columnconfigure(0, weight=1)

        self.texto_gps = tk.Text(
            panel_gps,
            height=10,
            width=45,
            wrap="word",
            state="disabled",
            relief="flat",
            borderwidth=0,
        )
        self.texto_gps.grid(row=0, column=0, sticky="ew")
        self._establecer_texto_gps("Aun no se ha ejecutado una estimacion.")

        panel_satelital = ttk.LabelFrame(izquierda, text="Panel 2: Imagen satelital", padding=10)
        panel_satelital.grid(row=1, column=0, sticky="nsew")
        panel_satelital.columnconfigure(0, weight=1)
        panel_satelital.rowconfigure(0, weight=1)

        self.etiqueta_satelital = ttk.Label(
            panel_satelital,
            text="La imagen de referencia se mostrara despues de iniciar.",
            anchor="center",
            justify="center",
        )
        self.etiqueta_satelital.grid(row=0, column=0, sticky="nsew")

        # --------------------------------------------------------------
        # Columna central: camara + resultado.
        # --------------------------------------------------------------
        centro = ttk.LabelFrame(contenedor, text="Analisis", padding=12)
        centro.grid(row=1, column=1, sticky="nsew", padx=8)
        centro.columnconfigure(0, weight=1)
        centro.rowconfigure(0, weight=1)
        centro.rowconfigure(1, weight=1)

        panel_camara = ttk.LabelFrame(centro, text="Panel 3: Imagen de camara", padding=10)
        panel_camara.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        panel_camara.columnconfigure(0, weight=1)
        panel_camara.rowconfigure(0, weight=1)

        self.etiqueta_camara = ttk.Label(
            panel_camara,
            text="La foto de auditoría aparecerá al finalizar la estimación.",
            anchor="center",
            justify="center",
            wraplength=370,
        )
        self.etiqueta_camara.grid(row=0, column=0, sticky="nsew")

        self.boton_ampliar_camara = ttk.Button(
            panel_camara,
            text="Ampliar foto de auditoría",
            command=self.mostrar_foto_camara,
            state="disabled",
        )
        self.boton_ampliar_camara.grid(row=1, column=0, pady=(6, 0))

        panel_resultado = ttk.LabelFrame(centro, text="Panel 4: Resultado", padding=14)
        panel_resultado.grid(row=1, column=0, sticky="nsew")
        panel_resultado.columnconfigure(0, weight=1)

        ttk.Label(
            panel_resultado,
            text="Ancho estimado de la calle",
            style="Subtitulo.TLabel",
            anchor="center",
        ).grid(row=0, column=0, sticky="ew", pady=(10, 8))

        self.boton_analisis = ttk.Button(
            panel_resultado,
            text="Análisis satelital",
            command=self.mostrar_imagen_analisis,
            style="Accion.TButton",
            state="disabled",
        )
        self.boton_analisis.grid(row=4, column=0, pady=(4, 5))

        ttk.Label(
            panel_resultado,
            textvariable=self.ancho_var,
            style="Resultado.TLabel",
            anchor="center",
        ).grid(row=1, column=0, sticky="ew", pady=8)

        ttk.Label(
            panel_resultado,
            textvariable=self.confianza_var,
            anchor="center",
        ).grid(row=2, column=0, sticky="ew", pady=(4, 2))

        ttk.Label(
            panel_resultado,
            textvariable=self.detalle_resultado_var,
            anchor="center",
            justify="center",
            wraplength=360,
        ).grid(row=3, column=0, sticky="ew", pady=(2, 10))

        # --------------------------------------------------------------
        # Columna derecha: acciones.
        # --------------------------------------------------------------
        acciones = ttk.LabelFrame(contenedor, text="Acciones", padding=12)
        acciones.grid(row=1, column=2, sticky="nsew", padx=(8, 0))
        acciones.columnconfigure(0, weight=1)

        self.boton_iniciar = ttk.Menubutton(
            acciones,
            text="Iniciar",
            style="Accion.TMenubutton",
        )

        self.menu_iniciar = tk.Menu(self.boton_iniciar, tearoff=False)
        self.menu_iniciar.add_command(
            label="Usar ultimas coordenadas",
            command=self.iniciar,
        )
        self.menu_iniciar.add_command(
            label="Actualizar coordenadas",
            command=self.actualizar_coordenadas,
        )
        self.boton_iniciar.configure(menu=self.menu_iniciar)
        self.boton_iniciar.grid(row=0, column=0, sticky="ew", pady=(10, 12))

        self.boton_reiniciar = ttk.Button(
            acciones,
            text="Reiniciar",
            command=self.reiniciar,
            style="Accion.TButton",
        )
        self.boton_reiniciar.grid(row=1, column=0, sticky="ew", pady=12)

        self.boton_pdf = ttk.Button(
            acciones,
            text="Generar informe",
            command=self.generar_informe,
            style="Accion.TButton",
            state="disabled",  # Se habilita al finalizar una estimación
        )
        self.boton_pdf.grid(row=2, column=0, sticky="ew", pady=12)

        ttk.Button(
            acciones,
            text="Acerca de",
            command=self.mostrar_acerca_de,
            style="Accion.TButton",
        ).grid(row=3, column=0, sticky="ew", pady=12)

        ttk.Button(
            acciones,
            text="Salir",
            command=self.destroy,
            style="Accion.TButton",
        ).grid(row=4, column=0, sticky="ew", pady=12)

        # Barra inferior de estado.
        ttk.Separator(contenedor).grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 6),
        )
        ttk.Label(
            contenedor,
            textvariable=self.estado_var,
            anchor="w",
        ).grid(row=3, column=0, columnspan=3, sticky="ew")

    def iniciar(self) -> None:
        """Ejecuta el pipeline utilizando el ultimo archivo de coordenadas."""
        try:
            validar_argumentos(self.args)
        except ValueError as error:
            messagebox.showerror("Parametros invalidos", str(error))
            return

        archivo = Path(self.args.archivo).expanduser().resolve()
        if not archivo.exists():
            messagebox.showerror(
                "Archivo no encontrado",
                f"No se encontro el archivo de mediciones:\n{archivo}",
            )
            return

        self.boton_iniciar.configure(state="disabled")
        self.boton_pdf.configure(state="disabled")
        self._carpeta_resultados = None
        self._ruta_reporte_pdf = None
        self._limpiar_camara()
        self.estado_var.set("Procesando datos GPS y descargando imagen satelital...")
        self.ancho_var.set("Procesando...")
        self.confianza_var.set("Confianza: --")
        self.detalle_resultado_var.set("Espere mientras se ejecuta la estimacion.")

        hilo = threading.Thread(target=self._ejecutar_en_segundo_plano, daemon=True)
        hilo.start()

    def actualizar_coordenadas(self) -> None:
        """Obtiene nuevas coordenadas con GPS.py antes de ejecutar el pipeline."""
        try:
            validar_argumentos(self.args)
        except ValueError as error:
            messagebox.showerror("Parametros invalidos", str(error))
            return

        self.boton_iniciar.configure(state="disabled")
        self.boton_analisis.configure(state="disabled")
        self.boton_pdf.configure(state="disabled")
        self._carpeta_resultados = None
        self._ruta_reporte_pdf = None
        self._limpiar_camara()
        self.estado_var.set(
            "Actualizando coordenadas GPS. Esperando 10 mediciones validas..."
        )
        self.ancho_var.set("Esperando GPS...")
        self.confianza_var.set("Confianza: --")
        self.detalle_resultado_var.set(
            "El NEO-6M esta adquiriendo una nueva ubicacion."
        )
        self._establecer_texto_gps(
            "Adquiriendo nuevas coordenadas GPS...\n\n"
            "Se esperaran 10 mediciones validas del modulo NEO-6M.\n"
            "Al finalizar, el SEAC continuara automaticamente."
        )

        hilo = threading.Thread(
            target=self._actualizar_gps_y_ejecutar,
            daemon=True,
        )
        hilo.start()

    def _actualizar_gps_y_ejecutar(self) -> None:
        """Ejecuta GPS.py, valida su salida y luego ejecuta el pipeline."""
        try:
            directorio = Path(__file__).resolve().parent

            # En el proyecto normal el archivo debe llamarse GPS.py.
            # El segundo nombre permite probar directamente una copia descargada.
            candidatos = (
                directorio / "GPS.py",
                directorio / "GPS(1).py",
            )
            ruta_gps = next(
                (ruta for ruta in candidatos if ruta.exists()),
                None,
            )

            if ruta_gps is None:
                raise FileNotFoundError(
                    "No se encontro GPS.py en la misma carpeta que interfaz_seac.py."
                )

            resultado = subprocess.run(
                [sys.executable, str(ruta_gps)],
                cwd=directorio,
                capture_output=True,
                text=True,
                check=False,
            )

            if resultado.returncode != 0:
                detalle = (resultado.stderr or resultado.stdout).strip()
                if len(detalle) > 1500:
                    detalle = detalle[-1500:]
                raise RuntimeError(
                    "GPS.py termino con un error."
                    + (f"\n\n{detalle}" if detalle else "")
                )

            archivo_gps = directorio / "mediciones_gps.txt"

            if not archivo_gps.exists():
                raise FileNotFoundError(
                    "GPS.py termino, pero no genero "
                    "mediciones_gps.txt."
                )

            lineas_validas = [
                linea
                for linea in archivo_gps.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ).splitlines()
                if linea.strip()
            ]

            if len(lineas_validas) < 10:
                raise RuntimeError(
                    "La adquisicion GPS finalizo sin completar las 10 "
                    f"mediciones requeridas. Se encontraron {len(lineas_validas)}."
                )

            # Desde este punto, las nuevas mediciones se convierten en la
            # entrada oficial del pipeline y tambien quedan como las
            # "ultimas coordenadas" para ejecuciones posteriores.
            self.args.archivo = str(archivo_gps.resolve())

            self.after(
                0,
                self.estado_var.set,
                "Coordenadas actualizadas. Iniciando estimacion SEAC...",
            )

            carpeta_salida = ejecutar_pipeline(self.args)

        except Exception as error:
            self.after(0, self._mostrar_error_gps, error)
            return

        self.after(0, self._cargar_resultados, carpeta_salida)

    def _ejecutar_en_segundo_plano(self) -> None:
        """Ejecuta el pipeline y devuelve el control a Tkinter al finalizar."""
        try:
            carpeta_salida = ejecutar_pipeline(self.args)
        except Exception as error:  # La GUI debe poder informar cualquier fallo del pipeline.
            self.after(0, self._mostrar_error, error)
            return

        self.after(0, self._cargar_resultados, carpeta_salida)

    def _cargar_resultados(self, carpeta_salida: Path) -> None:
        """Carga reporte e imagenes generadas por el pipeline."""
        try:
            reporte_path = carpeta_salida / "reporte.json"
            with reporte_path.open("r", encoding="utf-8") as archivo:
                reporte = json.load(archivo)

            self._actualizar_metricas(reporte)
            self._actualizar_resultado(reporte)
            self._mostrar_imagen_satelital(carpeta_salida / "02_imagen_con_gps.png")
            self._mostrar_imagen_camara(reporte.get("camara", {}), carpeta_salida)
            self._ruta_imagen_analisis = carpeta_salida / "06_secciones_transversales.png"
            self.boton_analisis.configure(
                state="normal" if self._ruta_imagen_analisis.exists() else "disabled"
            )

            # Los resultados ya están listos, pero aún NO se crea ningún PDF.
            self._carpeta_resultados = carpeta_salida
            self._ruta_reporte_pdf = None
            self.boton_pdf.configure(state="normal")
            self.estado_var.set(
                "Estimación completada. Pulsa «Generar informe» si deseas crear el PDF."
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            self._mostrar_error(error)
            return

        self.boton_iniciar.configure(state="normal")

    def _actualizar_metricas(self, reporte: dict[str, Any]) -> None:
        """Muestra las metricas GPS principales del reporte."""
        gps = reporte.get("analisis_gps", {})

        lineas = [
            f"Mediciones validas: {gps.get('cantidad_mediciones', '--')}",
            f"Latitud promedio: {self._formatear(gps.get('latitud_promedio'), 8)}",
            f"Longitud promedio: {self._formatear(gps.get('longitud_promedio'), 8)}",
            (
                "Distancia GPS promedio: "
                f"{self._formatear(gps.get('distancia_promedio_m'), 3)} m"
            ),
            (
                "Distancia GPS maxima: "
                f"{self._formatear(gps.get('distancia_maxima_m'), 3)} m"
            ),
            (
                "Resolucion cartografica: "
                f"{self._formatear(reporte.get('resolucion_cartografica_m_por_pixel'), 4)} m/px"
            ),
        ]

        # Se agregan metricas adicionales solo si el modulo GPS las proporciona.
        opcionales = (
            ("Promedio de satelites", "satelites_promedio", 2),
            ("HDOP promedio", "hdop_promedio", 2),
            ("Desviacion", "desviacion_m", 3),
            ("Dispersion", "dispersion_m", 3),
        )
        for etiqueta, clave, decimales in opcionales:
            if clave in gps:
                lineas.append(
                    f"{etiqueta}: {self._formatear(gps.get(clave), decimales)}"
                )

        self._establecer_texto_gps("\n".join(lineas))

    def _actualizar_resultado(self, reporte: dict[str, Any]) -> None:
        """Actualiza el panel del ancho estimado y su confianza."""
        deteccion = reporte.get("deteccion", {})
        ancho = deteccion.get("ancho_preliminar_m")

        if ancho is None:
            self.ancho_var.set("No estimado")
        else:
            self.ancho_var.set(f"{float(ancho):.3f} m")

        confianza = deteccion.get("confianza")
        nivel = deteccion.get("nivel_confianza", "--")
        if confianza is None:
            self.confianza_var.set(f"Confianza: {nivel}")
        else:
            self.confianza_var.set(
                f"Confianza: {float(confianza):.3f} ({nivel})"
            )

        angulo = deteccion.get("angulo_calle_grados")
        validas = deteccion.get("cantidad_secciones_validas", "--")
        candidatas = deteccion.get("cantidad_secciones_candidatas", "--")

        if angulo is None:
            angulo_texto = "no estimada"
        else:
            angulo_texto = f"{float(angulo):.2f} grados"

        self.detalle_resultado_var.set(
            f"Orientacion: {angulo_texto}\n"
            f"Secciones validas: {validas} de {candidatas}"
        )

    def _mostrar_imagen_satelital(self, ruta: Path) -> None:
        """Carga la imagen satelital con GPS en el panel correspondiente."""
        imagen = Image.open(ruta)
        imagen.thumbnail((420, 300), Image.Resampling.LANCZOS)

        self._imagen_satelital_tk = ImageTk.PhotoImage(imagen)
        self.etiqueta_satelital.configure(
            image=self._imagen_satelital_tk,
            text="",
        )

    def _limpiar_camara(self) -> None:
        """Limpia la fotografía previa y evita mostrar auditorías antiguas."""
        self._imagen_camara_tk = None
        self._ruta_foto_camara = None
        self.etiqueta_camara.configure(
            image="",
            text="La foto de auditoría aparecerá al finalizar la estimación.",
        )
        self.boton_ampliar_camara.configure(state="disabled")

    def _mostrar_imagen_camara(self, auditoria: dict[str, Any], carpeta_salida: Path) -> None:
        """Muestra la foto registrada por el módulo camara.py, si existe."""
        self._limpiar_camara()
        if not auditoria.get("disponible", False):
            motivos = {
                "captura_deshabilitada": "Captura de cámara desactivada para esta ejecución.",
                "no_se_pudo_capturar_imagen": "No se pudo obtener una imagen de la cámara.",
                "error_captura": "La cámara tuvo un error; la estimación satelital sí finalizó.",
            }
            motivo = auditoria.get("motivo", "no_disponible")
            texto = motivos.get(motivo, "No hay foto de auditoría disponible.")
            if auditoria.get("detalle"):
                texto += f"\n{auditoria['detalle']}"
            self.etiqueta_camara.configure(text=texto)
            return

        nombre = auditoria.get("ruta_foto_referencia")
        if not nombre:
            self.etiqueta_camara.configure(text="El reporte no incluye la ruta de la foto.")
            return

        ruta = Path(nombre).expanduser()
        if not ruta.is_absolute():
            ruta = carpeta_salida / ruta
        if not ruta.is_file():
            self.etiqueta_camara.configure(text=f"No se encontró la foto guardada:\n{ruta}")
            return

        try:
            with Image.open(ruta) as fuente:
                imagen = fuente.convert("RGB")
                imagen.thumbnail((420, 230), Image.Resampling.LANCZOS)
            self._imagen_camara_tk = ImageTk.PhotoImage(imagen)
        except (OSError, ValueError) as error:
            self.etiqueta_camara.configure(text=f"No se pudo abrir la foto: {error}")
            return

        self._ruta_foto_camara = ruta
        self.etiqueta_camara.configure(image=self._imagen_camara_tk, text="")
        self.boton_ampliar_camara.configure(state="normal")

    def mostrar_foto_camara(self) -> None:
        """Abre la foto de auditoría a mayor tamaño para leer sus metadatos."""
        if self._ruta_foto_camara is None or not self._ruta_foto_camara.is_file():
            messagebox.showwarning("Foto no disponible", "Todavía no se ha capturado una foto.")
            return

        ventana = tk.Toplevel(self)
        ventana.title("Foto de auditoría SEAC")
        ventana.geometry("950x750")
        marco = ttk.Frame(ventana, padding=12)
        marco.pack(fill="both", expand=True)
        with Image.open(self._ruta_foto_camara) as fuente:
            imagen = fuente.convert("RGB")
            imagen.thumbnail((920, 680), Image.Resampling.LANCZOS)
        ventana._imagen_tk = ImageTk.PhotoImage(imagen)
        ttk.Label(marco, image=ventana._imagen_tk).pack(fill="both", expand=True)
        ttk.Label(marco, text=str(self._ruta_foto_camara),
                  anchor="center", wraplength=900).pack(pady=(8, 0))

    def generar_informe(self) -> None:
        """Genera el PDF solo cuando se solicita, sin repetir el análisis."""
        carpeta = self._carpeta_resultados
        if carpeta is None or not (carpeta / "reporte.json").is_file():
            messagebox.showwarning(
                "Generar informe", "Primero debes completar una estimación."
            )
            return

        self.boton_pdf.configure(state="disabled")
        self.boton_iniciar.configure(state="disabled")
        self.boton_reiniciar.configure(state="disabled")
        self.estado_var.set("Generando informe PDF con las evidencias disponibles...")
        hilo = threading.Thread(
            target=self._generar_informe_en_segundo_plano,
            args=(carpeta,),
            daemon=True,
        )
        hilo.start()

    def _generar_informe_en_segundo_plano(self, carpeta: Path) -> None:
        """Construye el PDF sin bloquear la interfaz Tkinter."""
        try:
            from reporte import generar_reporte_pdf

            ruta_json = carpeta / "reporte.json"
            with ruta_json.open("r", encoding="utf-8") as archivo:
                datos = json.load(archivo)

            ruta_pdf = generar_reporte_pdf(datos, carpeta)

            # Registrar la ruta para que el JSON siga siendo trazable al PDF.
            datos["reporte_pdf"] = str(ruta_pdf)
            datos["estado_pdf"] = "generado"
            temporal = ruta_json.with_name("reporte.json.tmp")
            try:
                with temporal.open("w", encoding="utf-8") as archivo:
                    json.dump(datos, archivo, indent=2, ensure_ascii=False)
                temporal.replace(ruta_json)
            finally:
                temporal.unlink(missing_ok=True)
        except Exception as error:
            self.after(0, self._error_generar_informe, error)
            return

        self.after(0, self._informe_generado, ruta_pdf)

    def _informe_generado(self, ruta_pdf: Path) -> None:
        """Confirma al usuario dónde quedó guardado el PDF."""
        self._ruta_reporte_pdf = ruta_pdf
        self.boton_pdf.configure(state="normal")
        self.boton_iniciar.configure(state="normal")
        self.boton_reiniciar.configure(state="normal")
        self.estado_var.set(f"Informe PDF generado: {ruta_pdf.name}")
        self._mostrar_dialogo_informe(ruta_pdf)

    def _mostrar_dialogo_informe(self, ruta_pdf: Path) -> None:
        """Ofrece abrir el PDF inmediatamente o cerrar la confirmación."""
        ventana = tk.Toplevel(self)
        ventana.title("Informe generado")
        ventana.resizable(False, False)
        ventana.transient(self)

        contenido = ttk.Frame(ventana, padding=18)
        contenido.pack(fill="both", expand=True)
        ttk.Label(
            contenido,
            text="El PDF se guardó correctamente en:",
            font=("TkDefaultFont", 10, "bold"),
            anchor="center",
        ).pack(fill="x", pady=(0, 10))
        ttk.Label(
            contenido,
            text=str(ruta_pdf),
            wraplength=460,
            justify="center",
            anchor="center",
        ).pack(fill="x", pady=(0, 15))

        botones = ttk.Frame(contenido)
        botones.pack()

        def ver_informe() -> None:
            ventana.destroy()
            try:
                self._abrir_archivo_pdf(ruta_pdf)
            except OSError as error:
                messagebox.showerror(
                    "No se pudo abrir el informe",
                    f"El PDF está guardado en:\n{ruta_pdf}\n\nDetalle: {error}",
                    parent=self,
                )

        boton_ver = ttk.Button(botones, text="Ver informe", command=ver_informe)
        boton_ver.pack(side="left", padx=(0, 8))
        ttk.Button(botones, text="Cerrar", command=ventana.destroy).pack(side="left")

        ventana.protocol("WM_DELETE_WINDOW", ventana.destroy)
        ventana.bind("<Escape>", lambda _evento: ventana.destroy())
        ventana.grab_set()
        boton_ver.focus_set()

    @staticmethod
    def _abrir_archivo_pdf(ruta_pdf: Path) -> None:
        """Abre el PDF con el visor predeterminado sin bloquear Tkinter."""
        ruta_pdf = Path(ruta_pdf).expanduser().resolve()
        if not ruta_pdf.is_file():
            raise FileNotFoundError(f"No se encontró el PDF: {ruta_pdf}")

        if sys.platform == "win32":
            os.startfile(str(ruta_pdf))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ruta_pdf)])
        else:
            # Raspberry Pi OS / Linux: utiliza el visor PDF configurado.
            subprocess.Popen(["xdg-open", str(ruta_pdf)])

    def _error_generar_informe(self, error: Exception) -> None:
        """Un error del PDF no altera la estimación ya calculada."""
        self.boton_pdf.configure(state="normal")
        self.boton_iniciar.configure(state="normal")
        self.boton_reiniciar.configure(state="normal")
        self.estado_var.set("No se pudo generar el PDF; la estimación está disponible.")
        messagebox.showerror("Error al generar el informe", str(error))

    def reiniciar(self) -> None:
        """Limpia la informacion mostrada sin borrar archivos de resultados."""
        self._establecer_texto_gps("Aun no se ha ejecutado una estimacion.")
        self.ancho_var.set("-- m")
        self.confianza_var.set("Confianza: --")
        self.detalle_resultado_var.set("Sin resultados")
        self.estado_var.set("Listo para iniciar.")

        self._imagen_satelital_tk = None
        self._limpiar_camara()
        self._imagen_analisis_tk = None
        self._ruta_imagen_analisis = None
        self._carpeta_resultados = None
        self._ruta_reporte_pdf = None
        self.boton_pdf.configure(state="disabled")
        self.etiqueta_satelital.configure(
            image="",
            text="La imagen de referencia se mostrara despues de iniciar.",
        )
        self.boton_analisis.configure(state="disabled")
        self.boton_iniciar.configure(state="normal")

    def mostrar_acerca_de(self) -> None:
        """Muestra la ventana informativa definida en acerca_de.py."""
        mostrar_ventana_acerca_de(self)

    def mostrar_imagen_analisis(self) -> None:
        """Abre la imagen 06_secciones_transversales en una ventana aparte."""
        if self._ruta_imagen_analisis is None or not self._ruta_imagen_analisis.exists():
            messagebox.showwarning(
                "Imagen no disponible",
                "Todavia no existe la imagen 06_secciones_transversales.png.",
            )
            return

        ventana = tk.Toplevel(self)
        ventana.title("Analisis de la imagen")
        ventana.geometry("900x700")

        marco = ttk.Frame(ventana, padding=10)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)

        imagen = Image.open(self._ruta_imagen_analisis)
        imagen.thumbnail((860, 620), Image.Resampling.LANCZOS)

        self._imagen_analisis_tk = ImageTk.PhotoImage(imagen)
        etiqueta = ttk.Label(marco, image=self._imagen_analisis_tk, anchor="center")
        etiqueta.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            marco,
            text=str(self._ruta_imagen_analisis),
            anchor="center",
            justify="center",
            wraplength=820,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _mostrar_error_gps(self, error: Exception) -> None:
        """Informa una falla durante la actualizacion de coordenadas."""
        self.estado_var.set("No fue posible actualizar las coordenadas GPS.")
        self.ancho_var.set("-- m")
        self.confianza_var.set("Confianza: --")
        self.detalle_resultado_var.set("La estimacion no fue iniciada.")
        self.boton_analisis.configure(state="disabled")
        self.boton_pdf.configure(state="disabled")
        self._carpeta_resultados = None
        self._ruta_reporte_pdf = None
        self.boton_iniciar.configure(state="normal")
        self._limpiar_camara()

        messagebox.showerror(
            "Error durante la adquisicion GPS",
            str(error),
        )

    def _mostrar_error(self, error: Exception) -> None:
        """Presenta un error del pipeline y restaura el boton de inicio."""
        self.estado_var.set("La estimacion no pudo completarse.")
        self.ancho_var.set("Error")
        self.detalle_resultado_var.set(str(error))
        self._ruta_imagen_analisis = None
        self._carpeta_resultados = None
        self._ruta_reporte_pdf = None
        self.boton_analisis.configure(state="disabled")
        self.boton_pdf.configure(state="disabled")
        self.boton_iniciar.configure(state="normal")
        self._limpiar_camara()
        messagebox.showerror("Error durante la estimacion", str(error))

    def _establecer_texto_gps(self, texto: str) -> None:
        """Actualiza el widget de metricas manteniendolo de solo lectura."""
        self.texto_gps.configure(state="normal")
        self.texto_gps.delete("1.0", tk.END)
        self.texto_gps.insert("1.0", texto)
        self.texto_gps.configure(state="disabled")

    @staticmethod
    def _formatear(valor: Any, decimales: int) -> str:
        """Convierte un valor numerico a texto sin fallar si esta ausente."""
        if valor is None:
            return "--"
        try:
            return f"{float(valor):.{decimales}f}"
        except (TypeError, ValueError):
            return str(valor)


def main() -> None:
    """Inicia la interfaz reutilizando los mismos argumentos del pipeline."""
    parser = crear_parser()
    parser.description = (
        "Interfaz grafica del SEAC. Acepta los mismos parametros que "
        "seac_pipeline.py."
    )
    args = parser.parse_args()
    args.mostrar = False

    app = InterfazSEAC(args)
    app.mainloop()


if __name__ == "__main__":
    main()