"""Obtención y preparación de imágenes satelitales para SEAC.

Este módulo convierte coordenadas GPS a Web Mercator, calcula la
resolución cartográfica, descarga teselas de Esri World Imagery y
construye el mosaico satelital usado por el estimador.
"""

from __future__ import annotations

import math
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw

RADIO_TIERRA_WEB_MERCATOR = 6_378_137.0
TILE_SIZE = 256
URL_TILES_ESRI = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{zoom}/{y}/{x}"
)

__all__ = [
    "crear_mosaico",
    "dibujar_marcador",
    "resolucion_metros_por_pixel",
]

def latlon_a_pixel_global(
    latitud: float, longitud: float, zoom: int
) -> tuple[float, float]:
    """Convierte WGS84 a pixel global de la cuadricula Web Mercator."""
    n = 2**zoom
    pixel_x = (longitud + 180.0) / 360.0 * n * TILE_SIZE
    latitud_rad = math.radians(latitud)
    pixel_y = (
        (1.0 - math.asinh(math.tan(latitud_rad)) / math.pi)
        / 2.0
        * n
        * TILE_SIZE
    )
    return pixel_x, pixel_y


def resolucion_metros_por_pixel(latitud: float, zoom: int) -> float:
    """Calcula la resolucion terrestre local de Web Mercator."""
    circunferencia = 2.0 * math.pi * RADIO_TIERRA_WEB_MERCATOR
    return (
        circunferencia
        * math.cos(math.radians(latitud))
        / (TILE_SIZE * 2**zoom)
    )


def descargar_tile(x: int, y: int, zoom: int) -> Image.Image:
    """Descarga una tesela de Esri World Imagery."""
    cantidad_tiles = 2**zoom
    x = x % cantidad_tiles
    if not 0 <= y < cantidad_tiles:
        raise ValueError(f"Indice vertical de tesela fuera de rango: {y}")

    url = URL_TILES_ESRI.format(zoom=zoom, y=y, x=x)
    solicitud = Request(url, headers={"User-Agent": "SEAC-academic-project/1.0"})

    try:
        with urlopen(solicitud, timeout=30) as respuesta:
            contenido = respuesta.read()
    except (HTTPError, URLError) as error:
        raise RuntimeError(
            f"No se pudo descargar la tesela X={x}, Y={y}, Z={zoom}: {error}"
        ) from error

    return Image.open(BytesIO(contenido)).convert("RGB")


def crear_mosaico(
    latitud: float,
    longitud: float,
    zoom: int,
    radio_teselas: int,
) -> tuple[Image.Image, tuple[float, float]]:
    """Descarga el mosaico y devuelve la posicion GPS dentro de la imagen."""
    pixel_x_global, pixel_y_global = latlon_a_pixel_global(
        latitud, longitud, zoom
    )
    tile_x = int(pixel_x_global // TILE_SIZE)
    tile_y = int(pixel_y_global // TILE_SIZE)

    numero_teselas = 2 * radio_teselas + 1
    tamano_mosaico = numero_teselas * TILE_SIZE
    mosaico = Image.new("RGB", (tamano_mosaico, tamano_mosaico))

    for dy in range(-radio_teselas, radio_teselas + 1):
        for dx in range(-radio_teselas, radio_teselas + 1):
            tile = descargar_tile(tile_x + dx, tile_y + dy, zoom)
            posicion_x = (dx + radio_teselas) * TILE_SIZE
            posicion_y = (dy + radio_teselas) * TILE_SIZE
            mosaico.paste(tile, (posicion_x, posicion_y))

    inicio_x = (tile_x - radio_teselas) * TILE_SIZE
    inicio_y = (tile_y - radio_teselas) * TILE_SIZE
    posicion_gps = (pixel_x_global - inicio_x, pixel_y_global - inicio_y)
    return mosaico, posicion_gps


def dibujar_marcador(
    imagen: Image.Image, posicion_gps: tuple[float, float]
) -> Image.Image:
    """Crea una copia de la imagen con el punto GPS marcado."""
    resultado = imagen.copy()
    x, y = posicion_gps
    dibujo = ImageDraw.Draw(resultado)
    dibujo.ellipse((x - 10, y - 10, x + 10, y + 10), outline="red", width=4)
    dibujo.line((x - 15, y, x + 15, y), fill="red", width=3)
    dibujo.line((x, y - 15, x, y + 15), fill="red", width=3)
    return resultado
