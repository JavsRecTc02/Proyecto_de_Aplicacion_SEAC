"""Ventana independiente Acerca de SEAC.

Solo depende de Tkinter; se utiliza desde interfaz_seac.py.
No ejecuta GPS, descarga de Esri ni generacion de informes.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def mostrar_ventana_acerca_de(padre: tk.Misc) -> None:
    """Presenta los datos técnicos e institucionales en una ventana propia."""
    existente = getattr(padre, "_ventana_acerca_de", None)
    if existente is not None and existente.winfo_exists():
        existente.lift()
        existente.focus_set()
        return

    ventana = tk.Toplevel(padre)
    padre._ventana_acerca_de = ventana
    ventana.title("Acerca de SEAC")
    ventana.transient(padre)
    ventana.configure(background="#f2f5f8")

    # Se ajusta también a pantallas pequeñas utilizadas con Raspberry Pi.
    ancho = min(700, max(440, ventana.winfo_screenwidth() - 70))
    alto = min(620, max(360, ventana.winfo_screenheight() - 100))
    ventana.geometry(f"{ancho}x{alto}")
    ventana.minsize(min(440, ancho), min(360, alto))

    fondo_cabecera = "#102a43"
    color_acento = "#14a3a5"
    color_texto = "#263746"
    color_secundario = "#536879"
    fondo_contenido = "#ffffff"

    cabecera = tk.Frame(ventana, background=fondo_cabecera, padx=24, pady=18)
    cabecera.pack(fill="x")
    tk.Label(
        cabecera, text="SEAC", font=("TkDefaultFont", 25, "bold"),
        foreground="#ffffff", background=fondo_cabecera, anchor="w",
    ).pack(fill="x")
    tk.Label(
        cabecera, text="Sistema de Estimación de Ancho de Calles",
        font=("TkDefaultFont", 12, "bold"), foreground="#dcecf3",
        background=fondo_cabecera, anchor="w",
    ).pack(fill="x", pady=(2, 0))
    tk.Label(
        cabecera, text="Prototipo académico de ingeniería · II Semestre 2026",
        font=("TkDefaultFont", 9), foreground="#b6cbd7",
        background=fondo_cabecera, anchor="w",
    ).pack(fill="x", pady=(7, 0))

    # El pie se empaca antes del contenido para conservar siempre el botón
    # Cerrar, incluso en pantallas pequeñas de Raspberry Pi.
    pie = ttk.Frame(ventana, padding=(12, 8, 12, 12))
    pie.pack(side="bottom", fill="x")
    ttk.Separator(pie).pack(fill="x", pady=(0, 9))
    ttk.Button(pie, text="Cerrar", command=ventana.destroy).pack(side="right")

    cuerpo = ttk.Frame(ventana, padding=(12, 12, 12, 4))
    cuerpo.pack(fill="both", expand=True)
    cuerpo.rowconfigure(0, weight=1)
    cuerpo.columnconfigure(0, weight=1)

    lienzo = tk.Canvas(
        cuerpo, background=fondo_contenido, highlightthickness=0,
        borderwidth=0, relief="flat",
    )
    barra = ttk.Scrollbar(cuerpo, orient="vertical", command=lienzo.yview)
    lienzo.configure(yscrollcommand=barra.set)
    lienzo.grid(row=0, column=0, sticky="nsew")
    barra.grid(row=0, column=1, sticky="ns")

    contenido = tk.Frame(lienzo, background=fondo_contenido, padx=23, pady=18)
    ventana_contenido = lienzo.create_window((0, 0), window=contenido, anchor="nw")
    contenido.bind(
        "<Configure>",
        lambda _evento: lienzo.configure(scrollregion=lienzo.bbox("all")),
    )
    lienzo.bind(
        "<Configure>",
        lambda evento: lienzo.itemconfigure(ventana_contenido, width=evento.width),
    )

    def encabezado(titulo: str) -> None:
        tk.Frame(contenido, background=color_acento, height=3).pack(
            fill="x", pady=(18, 9)
        )
        tk.Label(
            contenido, text=titulo, font=("TkDefaultFont", 11, "bold"),
            foreground=fondo_cabecera, background=fondo_contenido, anchor="w",
        ).pack(fill="x", pady=(0, 6))

    def parrafo(texto: str) -> None:
        etiqueta = tk.Label(
            contenido, text=texto, font=("TkDefaultFont", 10),
            foreground=color_texto, background=fondo_contenido,
            justify="left", anchor="nw",
        )
        etiqueta.pack(fill="x", pady=(0, 7))
        etiqueta.bind(
            "<Configure>",
            lambda evento: evento.widget.configure(wraplength=max(200, evento.width - 8)),
        )

    def dato(etiqueta: str, valor: str) -> None:
        tk.Label(
            contenido, text=etiqueta, font=("TkDefaultFont", 9, "bold"),
            foreground=color_secundario, background=fondo_contenido,
            anchor="w",
        ).pack(fill="x", pady=(5, 0))
        parrafo(valor)

    # Contenido técnico e información oficial del proyecto.
    encabezado("Descripción del sistema")
    parrafo(
        "SEAC es un prototipo de software para estimar de forma automatizada "
        "el ancho de una calle mediante geolocalización y análisis de imágenes "
        "satelitales. El resultado se expresa en metros y se asocia a la "
        "ubicación utilizada durante el procesamiento."
    )

    encabezado("Funcionamiento y componentes")
    parrafo(
        "El sistema utiliza un receptor GPS NEO-6M para obtener 10 mediciones "
        "válidas y calcular una posición promedio. A partir de esta ubicación, "
        "consulta Esri World Imagery y aplica procesamiento digital de "
        "imágenes para identificar los límites de la calle y estimar su ancho."
    )
    parrafo(
        "Como evidencia complementaria, captura una fotografía de auditoría "
        "con datos de ubicación y permite generar manualmente un informe PDF "
        "que reúne las métricas y las imágenes del análisis."
    )

    encabezado("Alcance y consideraciones")
    parrafo(
        "Los resultados son estimaciones experimentales y pueden variar según "
        "la precisión GPS, la cobertura satelital y las condiciones visuales "
        "de la vía. No sustituyen una medición topográfica de campo. "
        "La fotografía de auditoría documenta la escena; no determina por "
        "sí misma el ancho estimado."
    )
    parrafo(
        "Las imágenes procedentes de Esri World Imagery están sujetas a "
        "los términos de uso y requisitos de atribución de Esri y sus "
        "proveedores de contenido."
    )

    encabezado("Información académica")
    dato("Institución", "Instituto Tecnológico de Costa Rica")
    dato("Unidad académica", "Escuela de Ingeniería en Computadores")
    dato("Modalidad", "Proyecto de Aplicación de la Ingeniería en Computadores (CE-1114)")
    dato("Estudiante desarrollador", "Javier Francisco Tenorio Cervantes")
    dato("Contraparte del proyecto", "Luis Alberto Chavarría Zamora")
    dato("Período", "II Semestre de 2026")

    def desplazar_rueda(evento: tk.Event) -> None:
        if getattr(evento, "num", None) == 4:
            lienzo.yview_scroll(-3, "units")
        elif getattr(evento, "num", None) == 5:
            lienzo.yview_scroll(3, "units")
        elif getattr(evento, "delta", 0):
            lienzo.yview_scroll(-3 if evento.delta > 0 else 3, "units")

    ventana.bind("<MouseWheel>", desplazar_rueda)
    ventana.bind("<Button-4>", desplazar_rueda)
    ventana.bind("<Button-5>", desplazar_rueda)
    ventana.bind("<Escape>", lambda _evento: ventana.destroy())
    ventana.protocol("WM_DELETE_WINDOW", ventana.destroy)
    ventana.grab_set()
    ventana.focus_set()

