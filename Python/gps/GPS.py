"""Adquisición de 10 mediciones GPS con límites de tiempo y guardado seguro.

El archivo mediciones_gps.txt se reemplaza solamente al obtener las
10 mediciones válidas. Un fallo nunca borra el archivo anterior.
"""

import math
import sys
import tempfile
import time
from pathlib import Path

import pynmea2
import serial

PUERTO_GPS = "/dev/serial0"
BAUDRATE = 9600

MEDICIONES_OBJETIVO = 10
INTERVALO_MEDICION = 2.0
SATELITES_MINIMOS = 5
HDOP_MAXIMO = 2.0

# Espera máxima del primer registro que cumpla los criterios de calidad.
TIEMPO_MAX_FIX = 25.0
# Tiempo máximo adicional para completar las otras nueve mediciones.
TIEMPO_MAX_MEDICIONES = 35.0

# Ruta relativa al directorio de ejecución (la interfaz usa cwd=raiz_proyecto).
ARCHIVO_SALIDA = Path("mediciones_gps.txt")


def guardar_mediciones(mediciones: list[str]) -> None:
    """Sustituye el archivo solo tras disponer de diez muestras válidas."""
    ARCHIVO_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        # Archivo temporal en el mismo directorio para reemplazo atómico.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".mediciones_gps_",
            suffix=".tmp",
            dir=ARCHIVO_SALIDA.parent,
            delete=False,
        ) as archivo:
            temporal = Path(archivo.name)
            archivo.write("\n".join(mediciones) + "\n")

        temporal.replace(ARCHIVO_SALIDA)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def main() -> int:
    """Obtiene una posición válida sin bloquear indefinidamente el SEAC."""
    print("Iniciando NEO-6M...", flush=True)
    print("Esperando posición GPS válida (máximo 60 segundos)...", flush=True)

    mediciones: list[str] = []
    ultima_medicion: float | None = None
    inicio = time.monotonic()
    inicio_mediciones: float | None = None
    se_detecto_fix = False

    try:
        with serial.Serial(port=PUERTO_GPS, baudrate=BAUDRATE, timeout=1) as gps:
            while len(mediciones) < MEDICIONES_OBJETIVO:
                ahora = time.monotonic()

                if inicio_mediciones is None and ahora - inicio >= TIEMPO_MAX_FIX:
                    if se_detecto_fix:
                        print(
                            "ERROR GPS: se detectó una posición, pero no cumplió "
                            "los criterios de calidad (5 satélites y HDOP <= 2.0) "
                            "en 60 segundos. Por favor, espere 1 minuto e "
                            "inténtelo nuevamente. Las coordenadas anteriores "
                            "se conservaron.",
                            file=sys.stderr,
                        )
                    else:
                        print(
                            "ERROR GPS: no fue posible encontrar una posición "
                            "válida (GPS Fix) en 60 segundos. Por favor, espere "
                            "1 minuto e inténtelo nuevamente. Las coordenadas "
                            "anteriores se conservaron.",
                            file=sys.stderr,
                        )
                    return 2

                if (
                    inicio_mediciones is not None
                    and ahora - inicio_mediciones >= TIEMPO_MAX_MEDICIONES
                ):
                    print(
                        "ERROR GPS: no se lograron completar las 10 mediciones "
                        f"válidas en el tiempo permitido ({len(mediciones)}/10). "
                        "Por favor, espere 1 minuto e inténtelo nuevamente. "
                        "Las coordenadas anteriores se conservaron.",
                        file=sys.stderr,
                    )
                    return 3

                linea = gps.readline().decode("ascii", errors="ignore").strip()
                if not linea.startswith(("$GPGGA", "$GNGGA")):
                    continue

                try:
                    datos = pynmea2.parse(linea)
                    calidad_fix = int(datos.gps_qual or 0)
                    if calidad_fix <= 0:
                        continue
                    se_detecto_fix = True

                    satelites = int(datos.num_sats or 0)
                    hdop = float(datos.horizontal_dil)
                    latitud = float(datos.latitude)
                    longitud = float(datos.longitude)
                except (pynmea2.ParseError, ValueError, TypeError, AttributeError):
                    continue

                if (
                    satelites < SATELITES_MINIMOS
                    or not math.isfinite(hdop)
                    or hdop > HDOP_MAXIMO
                    or not math.isfinite(latitud)
                    or not math.isfinite(longitud)
                    or not (-90 <= latitud <= 90 and -180 <= longitud <= 180)
                ):
                    continue

                ahora = time.monotonic()
                if ultima_medicion is not None and ahora - ultima_medicion < INTERVALO_MEDICION:
                    continue

                if inicio_mediciones is None:
                    inicio_mediciones = ahora
                    print("Posición GPS válida. Reuniendo 10 mediciones...", flush=True)

                ultima_medicion = ahora
                numero = len(mediciones) + 1
                registro = (
                    f"GPS,{numero},{latitud:.8f},{longitud:.8f},"
                    f"{satelites},{hdop:.2f}"
                )
                mediciones.append(registro)
                print(registro, flush=True)

    except (serial.SerialException, OSError) as error:
        print(
            f"ERROR GPS: no se pudo abrir o leer el puerto {PUERTO_GPS}: {error}. "
            "Las coordenadas anteriores se conservaron.",
            file=sys.stderr,
        )
        return 4
    except KeyboardInterrupt:
        print(
            "ERROR GPS: adquisición cancelada. "
            "Las coordenadas anteriores se conservaron.",
            file=sys.stderr,
        )
        return 130

    try:
        guardar_mediciones(mediciones)
    except OSError as error:
        print(f"ERROR GPS: no se pudieron guardar las nuevas coordenadas: {error}", file=sys.stderr)
        return 5

    print("FIN_MEDICIONES")
    print(f"Mediciones guardadas en: {ARCHIVO_SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
