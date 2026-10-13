"""Reporte PDF ligero del Sistema de Estimación de Ancho de Calles (SEAC).

No realiza procesamiento satelital ni captura de cámara: utiliza el reporte
JSON y las imágenes YA generadas por el pipeline. Reduce el tamaño de las
imágenes SOLO al incrustarlas en el PDF, sin modificar los archivos originales.

Dependencias: reportlab, Pillow.
Uso independiente: python3 reporte.py resultados_seac/reporte.json
"""

from __future__ import annotations

import argparse
from datetime import datetime
from io import BytesIO
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image as PILImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas


# Ajustes sencillos de presentación. No se descargan fuentes ni recursos.
COLOR_PRINCIPAL = colors.HexColor("#102B41")
COLOR_ACENTO = colors.HexColor("#007F8B")
COLOR_TEXTO = colors.HexColor("#213442")
COLOR_SUAVE = colors.HexColor("#566675")
COLOR_FONDO = colors.HexColor("#EFF5F7")
COLOR_BORDE = colors.HexColor("#D8E3E8")
ANCHO_PAGINA, ALTO_PAGINA = A4
MARGEN = 43
ANCHO_CONTENIDO = ANCHO_PAGINA - 2 * MARGEN

# Límite de resolución, aplicado ÚNICAMENTE a imágenes embebidas en el PDF.
MAX_PIXELES_IMAGEN = (1200, 1100)
CALIDAD_JPEG = 78


def _numero(valor: Any, decimales: int = 2, sufijo: str = "") -> str:
    if valor is None or isinstance(valor, bool):
        return "No disponible"
    try:
        numero = float(valor)
        if not math.isfinite(numero):
            return "No disponible"
        return f"{numero:.{decimales}f}{sufijo}"
    except (ValueError, TypeError):
        return "No disponible"


def _cadena(valor: Any, defecto: str = "No disponible") -> str:
    if valor is None or valor == "":
        return defecto
    # Los caracteres de control no deben aparecer en el documento.
    return " ".join(str(valor).split())


def _texto(pdf: canvas.Canvas, contenido: str, x: float, y: float,
           *, tamaño: int = 10, color=COLOR_TEXTO, negrita: bool = False,
           ancho: float = ANCHO_CONTENIDO, interlineado: int | None = None) -> float:
    """Dibuja texto ajustado al ancho y devuelve la siguiente coordenada y."""
    fuente = "Helvetica-Bold" if negrita else "Helvetica"
    pdf.setFont(fuente, tamaño)
    pdf.setFillColor(color)
    paso = interlineado or (tamaño + 5)
    for linea in simpleSplit(str(contenido), fuente, tamaño, ancho) or [""]:
        pdf.drawString(x, y, linea)
        y -= paso
    return y


def _cabecera(pdf: canvas.Canvas, titulo: str, subtitulo: str, numero: int) -> None:
    pdf.setFillColor(COLOR_PRINCIPAL)
    pdf.rect(0, ALTO_PAGINA - 67, ANCHO_PAGINA, 67, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(MARGEN, ALTO_PAGINA - 29, "SEAC  |  INFORME DE ESTIMACIÓN")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(MARGEN, ALTO_PAGINA - 47, subtitulo)

    pdf.setFont("Helvetica-Bold", 19)
    pdf.setFillColor(COLOR_PRINCIPAL)
    pdf.drawString(MARGEN, ALTO_PAGINA - 100, titulo)
    pdf.setStrokeColor(COLOR_BORDE)
    pdf.line(MARGEN, 54, ANCHO_PAGINA - MARGEN, 54)
    pdf.setFillColor(COLOR_SUAVE)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(MARGEN, 37, "SEAC - Sistema de Estimación de Ancho de Calles")
    pdf.drawRightString(ANCHO_PAGINA - MARGEN, 37, f"Página {numero}")


def _etiqueta(pdf: canvas.Canvas, etiqueta: str, valor: str, x: float, y: float,
              ancho: float) -> None:
    pdf.setFillColor(COLOR_SUAVE)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(x, y, etiqueta)
    _texto(pdf, valor, x, y - 20, tamaño=12, negrita=True, ancho=ancho)


def _imagen(pdf: canvas.Canvas, ruta: Path | None, *, x: float, y_superior: float,
            ancho: float, alto_maximo: float, titulo_vacio: str) -> float:
    """Dibuja una imagen reducida para PDF; devuelve la coordenada inferior.

    Transforma las imágenes PNG/JPEG al vuelo a JPEG compacto en memoria.
    La foto y las PNG originales NO cambian.
    """
    pdf.setStrokeColor(COLOR_BORDE)
    pdf.setFillColor(colors.white)
    pdf.roundRect(x, y_superior - alto_maximo, ancho, alto_maximo,
                  9, fill=1, stroke=1)
    if ruta is None or not ruta.is_file():
        pdf.setFont("Helvetica-Oblique", 10)
        pdf.setFillColor(COLOR_SUAVE)
        pdf.drawCentredString(x + ancho / 2, y_superior - alto_maximo / 2,
                              titulo_vacio)
        return y_superior - alto_maximo

    try:
        with PILImage.open(ruta) as original:
            imagen = ImageOps.exif_transpose(original)
            imagen.thumbnail(MAX_PIXELES_IMAGEN, PILImage.Resampling.LANCZOS)
            if imagen.mode != "RGB":
                imagen = imagen.convert("RGB")
            dimensiones = imagen.size
            memoria = BytesIO()
            imagen.save(memoria, format="JPEG", quality=CALIDAD_JPEG)
            memoria.seek(0)

        # Mantener proporciones y dejar margen dentro del rectángulo.
        ancho_usable = ancho - 16
        alto_usable = alto_maximo - 16
        escala = min(ancho_usable / dimensiones[0], alto_usable / dimensiones[1])
        ancho_dibujo = dimensiones[0] * escala
        alto_dibujo = dimensiones[1] * escala
        x_centro = x + (ancho - ancho_dibujo) / 2
        y_centro = y_superior - (alto_maximo + alto_dibujo) / 2
        pdf.drawImage(ImageReader(memoria), x_centro, y_centro,
                      width=ancho_dibujo, height=alto_dibujo, mask="auto")
    except (OSError, ValueError) as exc:
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColor(COLOR_SUAVE)
        pdf.drawCentredString(x + ancho / 2, y_superior - alto_maximo / 2,
                              "No fue posible incluir esta imagen")
        print(f"[reporte] Aviso al incluir {ruta.name}: {exc}")

    return y_superior - alto_maximo


def _ruta_imagen(valor: Any, carpeta: Path) -> Path | None:
    """Resuelve rutas absolutas y relativas guardadas en reporte.json."""
    if not valor:
        return None
    ruta = Path(str(valor)).expanduser()
    if ruta.is_absolute():
        return ruta
    if ruta.exists():
        return ruta.resolve()
    return carpeta / ruta.name


def generar_reporte_pdf(reporte: dict[str, Any], carpeta_salida: str | Path,
                        nombre_archivo: str | None = None) -> Path:
    """Crea un PDF autocontenido a partir del reporte SEAC y sus tres imágenes.

    No modifica el JSON ni el reporte satelital. La imagen de cámara es opcional.
    Devuelve la ruta absoluta del PDF creado.
    """
    salida = Path(carpeta_salida).expanduser().resolve()
    salida.mkdir(parents=True, exist_ok=True)
    if nombre_archivo is None:
        nombre_archivo = "SEAC_reporte_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pdf"
    if Path(nombre_archivo).name != nombre_archivo or not nombre_archivo.lower().endswith(".pdf"):
        raise ValueError("El nombre del reporte debe ser un archivo .pdf sin directorios.")
    ruta_pdf = salida / nombre_archivo

    gps = reporte.get("analisis_gps") or {}
    deteccion = reporte.get("deteccion") or {}
    camara = reporte.get("camara") or {}
    ancho = deteccion.get("ancho_preliminar_m")
    confianza = deteccion.get("confianza")
    nivel = deteccion.get("nivel_confianza")
    latitud = gps.get("latitud_promedio")
    longitud = gps.get("longitud_promedio")
    fecha = datetime.now().strftime("%d/%m/%Y  %H:%M:%S")

    pdf = canvas.Canvas(str(ruta_pdf), pagesize=A4, pageCompression=1)
    pdf.setTitle("SEAC - Reporte de estimación del ancho de calle")
    pdf.setAuthor("Sistema de Estimación de Ancho de Calles (SEAC)")
    pdf.setSubject("Estimación satelital y evidencia fotográfica de auditoría")

    # ----------------------- 1. Portada y resultados ----------------------
    pdf.setFillColor(COLOR_PRINCIPAL)
    pdf.rect(0, ALTO_PAGINA - 258, ANCHO_PAGINA, 258, fill=1, stroke=0)
    pdf.setFillColor(COLOR_ACENTO)
    pdf.rect(MARGEN, ALTO_PAGINA - 82, 78, 5, fill=1, stroke=0)
    _texto(pdf, "SEAC", MARGEN, ALTO_PAGINA - 139,
           tamaño=43, color=colors.white, negrita=True)
    _texto(pdf, "Sistema de Estimación de Ancho de Calles", MARGEN,
           ALTO_PAGINA - 178, tamaño=16, color=colors.white)
    _texto(pdf, "REPORTE TÉCNICO DE ESTIMACIÓN", MARGEN,
           ALTO_PAGINA - 219, tamaño=11, color=colors.HexColor("#BAE6E8"),
           negrita=True)

    _texto(pdf, "RESULTADO PRINCIPAL", MARGEN, 538, tamaño=10,
           color=COLOR_ACENTO, negrita=True)
    _texto(pdf, _numero(ancho, 3, " m") if ancho is not None else "No estimado",
           MARGEN, 483, tamaño=35, negrita=True)
    _texto(pdf, "Ancho de calle estimado mediante imagen satelital",
           MARGEN, 457, tamaño=11, color=COLOR_SUAVE)

    pdf.setFillColor(COLOR_FONDO)
    pdf.roundRect(MARGEN, 253, ANCHO_CONTENIDO, 168, 10, fill=1, stroke=0)
    margen_interno = 19
    izquierda = MARGEN + margen_interno
    derecha = MARGEN + ANCHO_CONTENIDO / 2 + 10
    _etiqueta(pdf, "Latitud promedio", _numero(latitud, 8), izquierda, 393, 210)
    _etiqueta(pdf, "Longitud promedio", _numero(longitud, 8), derecha, 393, 210)
    _etiqueta(pdf, "Mediciones GPS válidas", _cadena(gps.get("cantidad_mediciones")),
              izquierda, 335, 210)
    _etiqueta(pdf, "Confianza del algoritmo",
              f"{_numero(confianza, 3)} ({_cadena(nivel, '--')})",
              derecha, 335, 210)

    _texto(pdf, "Generado automáticamente por SEAC", MARGEN, 205,
           tamaño=11, negrita=True)
    _texto(pdf, f"Fecha de generación: {fecha}", MARGEN, 182,
           tamaño=10, color=COLOR_SUAVE)
    _texto(pdf, "Fuente satelital: Esri World Imagery", MARGEN, 164,
           tamaño=10, color=COLOR_SUAVE)
    _texto(pdf, "Documento de apoyo para revisión y auditoría. La estimación",
           MARGEN, 113, tamaño=9, color=COLOR_SUAVE)
    _texto(pdf, "debe contrastarse con mediciones de referencia cuando corresponda.",
           MARGEN, 99, tamaño=9, color=COLOR_SUAVE)
    pdf.setStrokeColor(COLOR_BORDE)
    pdf.line(MARGEN, 55, ANCHO_PAGINA - MARGEN, 55)
    _texto(pdf, "SEAC  |  Proyecto de Aplicación - Ingeniería en Computadores",
           MARGEN, 38, tamaño=8, color=COLOR_SUAVE)
    pdf.showPage()

    # ----------------------- 2. Imágenes satelitales ----------------------
    _cabecera(pdf, "Evidencia satelital", "Referencia geográfica y estimación geométrica", 2)
    _texto(pdf, "01  IMAGEN DE REFERENCIA CON GPS", MARGEN, 714,
           tamaño=11, color=COLOR_ACENTO, negrita=True)
    _imagen(pdf, salida / "02_imagen_con_gps.png", x=MARGEN,
            y_superior=695, ancho=ANCHO_CONTENIDO, alto_maximo=263,
            titulo_vacio="Imagen con marcador GPS no disponible")

    _texto(pdf, "02  ANÁLISIS DE SECCIONES TRANSVERSALES", MARGEN, 408,
           tamaño=11, color=COLOR_ACENTO, negrita=True)
    _imagen(pdf, salida / "06_secciones_transversales.png", x=MARGEN,
            y_superior=389, ancho=ANCHO_CONTENIDO, alto_maximo=265,
            titulo_vacio="Imagen de análisis no disponible")
    _texto(pdf,
           f"Secciones válidas: {_cadena(deteccion.get('cantidad_secciones_validas'), '--')} "
           f"de {_cadena(deteccion.get('cantidad_secciones_candidatas'), '--')}" 
           f"   |   Orientación: {_numero(deteccion.get('angulo_calle_grados'), 2, '°')}",
           MARGEN, 102, tamaño=9, color=COLOR_SUAVE)
    _texto(pdf, f"Escala cartográfica: "
           f"{_numero(reporte.get('resolucion_cartografica_m_por_pixel'), 4, ' m/píxel')}",
           MARGEN, 83, tamaño=9, color=COLOR_SUAVE)
    pdf.showPage()

    # ----------------------- 3. Cámara y avisos ---------------------------
    _cabecera(pdf, "Auditoría de la escena vial", "Fotografía y condiciones de referencia", 3)
    _texto(pdf, "03  FOTOGRAFÍA DE AUDITORÍA", MARGEN, 712,
           tamaño=11, color=COLOR_ACENTO, negrita=True)
    ruta_foto = (_ruta_imagen(camara.get("ruta_foto_referencia"), salida)
                 if camara.get("disponible") else None)
    _imagen(pdf, ruta_foto, x=MARGEN, y_superior=693,
            ancho=ANCHO_CONTENIDO, alto_maximo=371,
            titulo_vacio="No se capturó fotografía para esta ejecución")

    if ruta_foto and ruta_foto.is_file():
        detalle = "Fotografía de referencia con fecha, posición GPS y ancho estimado."
    else:
        detalle = ("Captura no disponible: " +
                   _cadena(camara.get("motivo"), "no registrada"))
    _texto(pdf, detalle, MARGEN, 306, tamaño=9,
           color=COLOR_SUAVE, ancho=ANCHO_CONTENIDO)

    pdf.setFillColor(COLOR_FONDO)
    pdf.roundRect(MARGEN, 81, ANCHO_CONTENIDO, 194, 8, fill=1, stroke=0)
    x_legal = MARGEN + 15
    ancho_legal = ANCHO_CONTENIDO - 30
    _texto(pdf, "FUENTE Y CONDICIONES DE USO", x_legal, 254,
           tamaño=10, negrita=True, color=COLOR_PRINCIPAL)
    y_legal = _texto(
        pdf,
        "Las imágenes satelitales proceden de Esri World Imagery y están "
        "sujetas a los términos de uso y a las atribuciones aplicables de "
        "Esri y de sus proveedores de datos. Antes de compartir o "
        "redistribuir este documento, verifique dichas condiciones "
        "y los créditos específicos requeridos.",
        x_legal, 235, tamaño=9, interlineado=13, ancho=ancho_legal,
    )
    _texto(pdf, "NOTA METODOLÓGICA", x_legal, y_legal - 6,
           tamaño=10, negrita=True, color=COLOR_PRINCIPAL)
    _texto(
        pdf,
        "El ancho corresponde a una estimación satelital, no a una "
        "medición física certificada. La fotografía de cámara se usa "
        "para auditoría visual; sus coordenadas corresponden al promedio "
        "GPS asociado a esta ejecución, no a una lectura independiente "
        "al instante de captura.",
        x_legal, y_legal - 25, tamaño=9, interlineado=13, ancho=ancho_legal,
    )
    pdf.save()
    return ruta_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera el PDF del SEAC desde reporte.json y sus imágenes."
    )
    parser.add_argument("archivo_json", nargs="?", default="resultados_seac/reporte.json")
    parser.add_argument("--nombre", default=None,
                        help="Nombre opcional del PDF (terminado en .pdf).")
    args = parser.parse_args()
    ruta_json = Path(args.archivo_json).expanduser().resolve()
    with ruta_json.open("r", encoding="utf-8") as archivo:
        datos = json.load(archivo)
    ruta_pdf = generar_reporte_pdf(datos, ruta_json.parent, args.nombre)
    print(f"Reporte PDF generado: {ruta_pdf}")


if __name__ == "__main__":
    main()
