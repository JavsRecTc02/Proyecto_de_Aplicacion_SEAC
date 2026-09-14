"""Interfaz grafica del Sistema de Estimacion de Ancho de Calles (SEAC).

La interfaz mantiene separada la presentacion de la logica del sistema. Reutiliza
el pipeline existente para ejecutar el procesamiento y posteriormente carga el
reporte JSON y las imagenes generadas en la carpeta de resultados.

Puede ejecutarse de forma remota mediante SSH con reenvio X11.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

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
        self._imagen_analisis_tk: ImageTk.PhotoImage | None = None
        self._ruta_imagen_analisis: Path | None = None

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

        ttk.Label(
            panel_camara,
            text=(
                "Camara no implementada actualmente.\n\n"
                "Este panel queda reservado para la transmision\n"
                "o captura de la escena vial."
            ),
            anchor="center",
            justify="center",
        ).grid(row=0, column=0, sticky="nsew")

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
        self.boton_analisis.grid(row=4, column=0, pady=(4, 10))

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

        self.boton_iniciar = ttk.Button(
            acciones,
            text="Iniciar",
            command=self.iniciar,
            style="Accion.TButton",
        )
        self.boton_iniciar.grid(row=0, column=0, sticky="ew", pady=(10, 12))

        ttk.Button(
            acciones,
            text="Reiniciar",
            command=self.reiniciar,
            style="Accion.TButton",
        ).grid(row=1, column=0, sticky="ew", pady=12)

        ttk.Button(
            acciones,
            text="Acerca de",
            command=self.mostrar_acerca_de,
            style="Accion.TButton",
        ).grid(row=2, column=0, sticky="ew", pady=12)

        ttk.Button(
            acciones,
            text="Salir",
            command=self.destroy,
            style="Accion.TButton",
        ).grid(row=3, column=0, sticky="ew", pady=12)

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
        """Inicia el pipeline en un hilo secundario para no congelar la GUI."""
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
        self.estado_var.set("Procesando datos GPS y descargando imagen satelital...")
        self.ancho_var.set("Procesando...")
        self.confianza_var.set("Confianza: --")
        self.detalle_resultado_var.set("Espere mientras se ejecuta la estimacion.")

        hilo = threading.Thread(target=self._ejecutar_en_segundo_plano, daemon=True)
        hilo.start()

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
            self._ruta_imagen_analisis = carpeta_salida / "06_secciones_transversales.png"
            self.boton_analisis.configure(
                state="normal" if self._ruta_imagen_analisis.exists() else "disabled"
            )

            self.estado_var.set(f"Estimacion completada. Resultados: {carpeta_salida}")
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

    def reiniciar(self) -> None:
        """Limpia la informacion mostrada sin borrar archivos de resultados."""
        self._establecer_texto_gps("Aun no se ha ejecutado una estimacion.")
        self.ancho_var.set("-- m")
        self.confianza_var.set("Confianza: --")
        self.detalle_resultado_var.set("Sin resultados")
        self.estado_var.set("Listo para iniciar.")

        self._imagen_satelital_tk = None
        self._imagen_analisis_tk = None
        self._ruta_imagen_analisis = None
        self.etiqueta_satelital.configure(
            image="",
            text="La imagen de referencia se mostrara despues de iniciar.",
        )
        self.boton_analisis.configure(state="disabled")
        self.boton_iniciar.configure(state="normal")

    def mostrar_acerca_de(self) -> None:
        """Muestra informacion breve del prototipo."""
        messagebox.showinfo(
            "Acerca de SEAC",
            (
                "Sistema de Estimacion de Ancho de Calles (SEAC)\n\n"
                "Utiliza la API Arcgis Esri World Imagery.\n"
                "Integra el procesamiento GPS, la referencia satelital "
                "y la estimacion del ancho de la calle.\n\n"
                "Desarrollado por Javier Tenorio Cervantes para el proyecto de aplicación IIS2026."
            ),
        )

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

    def _mostrar_error(self, error: Exception) -> None:
        """Presenta un error del pipeline y restaura el boton de inicio."""
        self.estado_var.set("La estimacion no pudo completarse.")
        self.ancho_var.set("Error")
        self.detalle_resultado_var.set(str(error))
        self._ruta_imagen_analisis = None
        self.boton_analisis.configure(state="disabled")
        self.boton_iniciar.configure(state="normal")
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
