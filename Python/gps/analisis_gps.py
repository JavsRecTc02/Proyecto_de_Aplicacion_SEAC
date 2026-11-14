"""Procesamiento de mediciones GPS para SEAC.

Este módulo lee las mediciones GPS, valida sus valores y calcula la
posición promedio y las estadísticas de dispersión utilizadas por el
resto del sistema.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["leer_mediciones", "analizar_mediciones"]

def leer_mediciones(archivo: Path) -> list[dict[str, float | int]]:
    """Lee registros GPS,numero,latitud,longitud,satelites,hdop."""
    mediciones: list[dict[str, float | int]] = []

    with archivo.open("r", encoding="utf-8") as entrada:
        for numero_linea, linea in enumerate(entrada, start=1):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if linea == "FIN_MEDICIONES":
                break

            partes = [parte.strip() for parte in linea.split(",")]
            if partes[0] != "GPS":
                continue
            if len(partes) != 6:
                raise ValueError(
                    f"Linea {numero_linea}: se esperaban 6 campos y se "
                    f"encontraron {len(partes)}."
                )

            try:
                medicion = {
                    "numero": int(partes[1]),
                    "latitud": float(partes[2]),
                    "longitud": float(partes[3]),
                    "satelites": int(partes[4]),
                    "hdop": float(partes[5]),
                }
            except ValueError as error:
                raise ValueError(
                    f"Linea {numero_linea}: contiene un valor numerico invalido."
                ) from error

            latitud = float(medicion["latitud"])
            longitud = float(medicion["longitud"])
            if not -85.05112878 <= latitud <= 85.05112878:
                raise ValueError(
                    f"Linea {numero_linea}: la latitud queda fuera del rango "
                    "admitido por Web Mercator."
                )
            if not -180.0 <= longitud <= 180.0:
                raise ValueError(f"Linea {numero_linea}: longitud invalida.")

            mediciones.append(medicion)

    if not mediciones:
        raise ValueError("No se encontraron mediciones GPS validas en el archivo.")

    return mediciones


def distancia_haversine(
    latitud_1: float,
    longitud_1: float,
    latitud_2: float,
    longitud_2: float,
) -> float:
    """Calcula en metros la distancia entre dos coordenadas WGS84."""
    radio_tierra = 6_371_000.0
    lat_1 = math.radians(latitud_1)
    lat_2 = math.radians(latitud_2)
    delta_latitud = math.radians(latitud_2 - latitud_1)
    delta_longitud = math.radians(longitud_2 - longitud_1)

    a = (
        math.sin(delta_latitud / 2.0) ** 2
        + math.cos(lat_1)
        * math.cos(lat_2)
        * math.sin(delta_longitud / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radio_tierra * c


def analizar_mediciones(
    mediciones: list[dict[str, float | int]],
) -> dict[str, Any]:
    """Obtiene la posicion promedio y estadisticas de dispersion."""
    latitudes = np.array([m["latitud"] for m in mediciones], dtype=float)
    longitudes = np.array([m["longitud"] for m in mediciones], dtype=float)

    latitud_promedio = float(np.mean(latitudes))
    longitud_promedio = float(np.mean(longitudes))
    latitud_rad = math.radians(latitud_promedio)

    metros_por_grado_latitud = (
        111_132.92
        - 559.82 * math.cos(2.0 * latitud_rad)
        + 1.175 * math.cos(4.0 * latitud_rad)
    )
    metros_por_grado_longitud = (
        111_412.84 * math.cos(latitud_rad)
        - 93.5 * math.cos(3.0 * latitud_rad)
    )

    distancias = [
        distancia_haversine(
            latitud_promedio,
            longitud_promedio,
            float(m["latitud"]),
            float(m["longitud"]),
        )
        for m in mediciones
    ]
    ddof = 1 if len(mediciones) > 1 else 0

    return {
        "cantidad_mediciones": len(mediciones),
        "latitud_promedio": latitud_promedio,
        "longitud_promedio": longitud_promedio,
        "latitud_minima": float(np.min(latitudes)),
        "latitud_maxima": float(np.max(latitudes)),
        "longitud_minima": float(np.min(longitudes)),
        "longitud_maxima": float(np.max(longitudes)),
        "desviacion_latitud_grados": float(np.std(latitudes, ddof=ddof)),
        "desviacion_longitud_grados": float(np.std(longitudes, ddof=ddof)),
        "rango_latitud_m": float(
            (np.max(latitudes) - np.min(latitudes)) * metros_por_grado_latitud
        ),
        "rango_longitud_m": float(
            (np.max(longitudes) - np.min(longitudes))
            * metros_por_grado_longitud
        ),
        "distancias_al_promedio_m": distancias,
        "distancia_promedio_m": float(np.mean(distancias)),
        "distancia_maxima_m": float(np.max(distancias)),
    }
