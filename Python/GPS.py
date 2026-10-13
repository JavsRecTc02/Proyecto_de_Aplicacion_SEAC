import serial
import pynmea2
import time
from pathlib import Path

PUERTO_GPS = "/dev/serial0"
BAUDRATE = 9600

MEDICIONES_OBJETIVO = 10
INTERVALO_MEDICION = 2.0

ARCHIVO_SALIDA = Path("mediciones_gps.txt")

mediciones_validas = 0
ultima_medicion = 0


def main():
    global mediciones_validas
    global ultima_medicion

    print("Iniciando NEO-6M...")
    print("Esperando mediciones validas...")

    ARCHIVO_SALIDA.parent.mkdir(exist_ok=True)

    gps = serial.Serial(
        port=PUERTO_GPS,
        baudrate=BAUDRATE,
        timeout=1
    )

    with open(ARCHIVO_SALIDA, "w") as archivo:

        while mediciones_validas < MEDICIONES_OBJETIVO:

            try:
                linea = gps.readline().decode(
                    "ascii",
                    errors="ignore"
                ).strip()

                if not linea:
                    continue

                if linea.startswith("$GPGGA") or linea.startswith("$GNGGA"):

                    datos = pynmea2.parse(linea)

                    if not datos.gps_qual:
                        continue

                    satelites = int(datos.num_sats)
                    hdop = float(datos.horizontal_dil)

                    if satelites >= 5 and hdop <= 2.0:

                        tiempo_actual = time.monotonic()

                        if tiempo_actual - ultima_medicion >= INTERVALO_MEDICION:

                            mediciones_validas += 1
                            ultima_medicion = tiempo_actual

                            latitud = float(datos.latitude)
                            longitud = float(datos.longitude)

                            medicion = (
                                f"GPS,{mediciones_validas},"
                                f"{latitud:.8f},"
                                f"{longitud:.8f},"
                                f"{satelites},"
                                f"{hdop:.2f}"
                            )

                            print(medicion)
                            archivo.write(medicion + "\n")
                            archivo.flush()

            except pynmea2.ParseError:
                continue

            except KeyboardInterrupt:
                print("\nAdquisición detenida.")
                break

    print("FIN_MEDICIONES")
    print(f"Mediciones guardadas en: {ARCHIVO_SALIDA}")

    gps.close()


if __name__ == "__main__":
    main()
