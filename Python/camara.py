import argparse
import json
import os
import platform
import subprocess
import time
from datetime import datetime
import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------
def fijar_parametros_camara(indice_camara: int,
                             exposicion_manual: int = None,
                             balance_blancos_manual: int = None,
                             ganancia_manual: int = None) -> None:

    if platform.system() != "Linux":
        return

    dispositivo = f"/dev/video{indice_camara}"
    comandos = []
    if exposicion_manual is not None:
        comandos.append(["--set-ctrl=auto_exposure=1"])  # 1 = manual
        comandos.append([f"--set-ctrl=exposure_time_absolute={exposicion_manual}"])

    if balance_blancos_manual is not None:
        comandos.append(["--set-ctrl=white_balance_temperature_auto=0"])
        comandos.append(
            [f"--set-ctrl=white_balance_temperature={balance_blancos_manual}"]
        )

    if ganancia_manual is not None:
        comandos.append([f"--set-ctrl=gain={ganancia_manual}"])

    for args_extra in comandos:
        try:
            subprocess.run(
                ["v4l2-ctl", "-d", dispositivo] + args_extra,
                check=True,
                capture_output=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            print(f"[camara] Aviso: no se pudo fijar parámetro ({args_extra}): {error}")


def capturar_imagen(indice_camara: int = 0,
                     resolucion: tuple = (640, 480),
                     descartar_primeros_frames: int = 35):

    backend = cv2.CAP_V4L2 if platform.system() == "Linux" else cv2.CAP_ANY
    captura = cv2.VideoCapture(indice_camara, backend)
    if not captura.isOpened():
        print(f"[camara] Error: no se pudo abrir la cámara índice {indice_camara}")
        return None

    captura.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    captura.set(cv2.CAP_PROP_FRAME_WIDTH, resolucion[0])
    captura.set(cv2.CAP_PROP_FRAME_HEIGHT, resolucion[1])

    imagen = None
    for indice_frame in range(descartar_primeros_frames + 1):
        ok, frame = captura.read()
        if ok:
            imagen = frame

    captura.release()

    if imagen is None:
        print("[camara] Error: no se obtuvo ningún frame válido")
    elif not imagen.any():
        print("[camara] Aviso: el frame capturado está completamente en negro "
              "(revisar backend de captura, permisos de /dev/video*, o tapa del lente)")

    return imagen

def incrustar_metadatos_auditoria(imagen: np.ndarray,
                                   latitud: float = None,
                                   longitud: float = None,
                                   ancho_estimado_metros: float = None) -> np.ndarray:

    imagen_con_texto = imagen.copy()
    alto, ancho = imagen_con_texto.shape[:2]

    marca_tiempo = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lineas = [f"Fecha: {marca_tiempo}"]

    if latitud is not None and longitud is not None:
        lineas.append(f"GPS: {latitud:.6f}, {longitud:.6f}")
    if ancho_estimado_metros is not None:
        lineas.append(f"Ancho estimado (metros): {ancho_estimado_metros:.2f} m")

    fuente = cv2.FONT_HERSHEY_SIMPLEX
    escala_fuente = 0.4
    grosor = 1
    alto_linea = 16
    margen = 6

    alto_banda = margen * 2 + alto_linea * len(lineas)
    overlay = imagen_con_texto.copy()
    cv2.rectangle(
        overlay,
        (0, alto - alto_banda),
        (ancho, alto),
        (0, 0, 0),
        thickness=-1,
    )

    cv2.addWeighted(overlay, 0.55, imagen_con_texto, 0.45, 0, imagen_con_texto)

    for indice, linea in enumerate(lineas):
        posicion_y = alto - alto_banda + margen + (indice + 1) * alto_linea - 4
        cv2.putText(
            imagen_con_texto, linea, (margen, posicion_y),
            fuente, escala_fuente, (255, 255, 255), grosor, cv2.LINE_AA,
        )

    return imagen_con_texto

def guardar_foto_referencia(imagen: np.ndarray,
                             carpeta_salida: str,
                             indice_medicion: int = None,
                             latitud: float = None,
                             longitud: float = None,
                             ancho_estimado_metros: float = None) -> str:

    imagen_final = incrustar_metadatos_auditoria(
        imagen, latitud=latitud, longitud=longitud,
        ancho_estimado_metros=ancho_estimado_metros,
    )

    os.makedirs(carpeta_salida, exist_ok=True)
    marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
    sufijo = f"_med{indice_medicion}" if indice_medicion is not None else ""
    nombre_archivo = f"camara_referencia{sufijo}_{marca_tiempo}.jpg"
    ruta_completa = os.path.join(carpeta_salida, nombre_archivo)
    if not cv2.imwrite(ruta_completa, imagen_final):
        raise OSError(f"No se pudo guardar la foto de auditoría: {ruta_completa}")
    return ruta_completa


def _medir_brillo_promedio(imagen: np.ndarray) -> float:
    """Brillo promedio de la imagen en escala de grises (0-255)."""
    gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gris))


def _abrir_captura_configurada(indice_camara: int, resolucion: tuple):
    """
    Abre y configura la cámara (backend, formato YUYV, resolución),
    sin leer ningún frame todavía. Uso interno.
    """
    backend = cv2.CAP_V4L2 if platform.system() == "Linux" else cv2.CAP_ANY
    captura = cv2.VideoCapture(indice_camara, backend)
    if not captura.isOpened():
        print(f"[camara] Error: no se pudo abrir la cámara índice {indice_camara}")
        return None

    captura.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
    captura.set(cv2.CAP_PROP_FRAME_WIDTH, resolucion[0])
    captura.set(cv2.CAP_PROP_FRAME_HEIGHT, resolucion[1])
    return captura


def _leer_ultimo_frame(captura, cantidad_frames: int):
    """Lee cantidad_frames frames reales y devuelve el último. Uso interno."""
    imagen = None
    for _ in range(cantidad_frames):
        ok, frame = captura.read()
        if ok:
            imagen = frame
    return imagen

def capturar_imagen_con_autoexposicion(indice_camara: int = 0,
                                        resolucion: tuple = (640, 480),
                                        candidatos_exposicion: tuple = (150, 40, 15, 5),
                                        objetivo_brillo: float = 130.0,
                                        margen_aceptable: float = 25.0,
                                        frames_calentamiento_inicial: int = 35,
                                        frames_asentamiento_cambio: int = 8):

    if not candidatos_exposicion:
        return None, None

    fijar_parametros_camara(indice_camara, exposicion_manual=candidatos_exposicion[0])
    captura = _abrir_captura_configurada(indice_camara, resolucion)
    if captura is None:
        return None, None

    mejor_imagen = None
    mejor_valor = None
    mejor_diferencia = None

    for indice, valor in enumerate(candidatos_exposicion):
        if indice > 0:
            fijar_parametros_camara(indice_camara, exposicion_manual=valor)

        cantidad_frames = frames_calentamiento_inicial if indice == 0 else frames_asentamiento_cambio
        imagen = _leer_ultimo_frame(captura, cantidad_frames)

        if imagen is None or not imagen.any():
            if imagen is not None:
                print(f"[camara] Aviso: frame en negro con exposición={valor}, probando siguiente candidato")
            continue

        brillo = _medir_brillo_promedio(imagen)
        diferencia = abs(brillo - objetivo_brillo)

        if mejor_diferencia is None or diferencia < mejor_diferencia:
            mejor_diferencia = diferencia
            mejor_imagen = imagen
            mejor_valor = valor

        if diferencia <= margen_aceptable:
            break  # ya es suficientemente bueno, no seguimos probando

    captura.release()
    return mejor_imagen, mejor_valor
# ---------------------------------------------------------------------------
# Integración con el reporte del pipeline (reporte.json)
# ---------------------------------------------------------------------------

def generar_bloque_reporte(indice_camara: int,
                            carpeta_salida: str,
                            indice_medicion: int = None,
                            latitud: float = None,
                            longitud: float = None,
                            ancho_estimado_metros: float = None,
                            ganancia_manual: int = None,
                            usar_autoexposicion: bool = True) -> dict:

    if usar_autoexposicion:
        imagen, exposicion_usada = capturar_imagen_con_autoexposicion(indice_camara)
    else:
        fijar_parametros_camara(indice_camara, ganancia_manual=ganancia_manual)
        imagen = capturar_imagen(indice_camara)
        exposicion_usada = None

    if imagen is None:
        return {
            "disponible": False,
            "motivo": "no_se_pudo_capturar_imagen",
        }

    ruta_foto = guardar_foto_referencia(
        imagen, carpeta_salida, indice_medicion,
        latitud=latitud, longitud=longitud,
        ancho_estimado_metros=ancho_estimado_metros,
    )

    return {
        "disponible": True,
        "ruta_foto_referencia": ruta_foto,
        "exposicion_utilizada": exposicion_usada,
    }

# ---------------------------------------------------------------------------
# Ejecución independiente (para probar el módulo por separado)
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Captura una foto de referencia (auditoría) desde la webcam (SEAC)."
    )
    parser.add_argument("--indice-camara", type=int, default=0,
                         help="Índice del dispositivo de video (default: 0)")
    parser.add_argument("--salida", type=str, default="resultados_seac",
                         help="Carpeta donde guardar la foto de referencia")
    parser.add_argument("--indice-medicion", type=int, default=None,
                         help="Índice de la medición GPS asociada, si aplica")
    parser.add_argument("--latitud", type=float, default=None,
                         help="Latitud de la medición, para incrustar en la foto (prueba)")
    parser.add_argument("--longitud", type=float, default=None,
                         help="Longitud de la medición, para incrustar en la foto (prueba)")
    parser.add_argument("--ancho-estimado", type=float, default=None,
                         help="Ancho estimado por vía satelital en metros, para incrustar en la foto (prueba)")
    parser.add_argument("--ganancia", type=int, default=None,
                         help="Ganancia manual (0-255 aprox.), para escenas de alto contraste (prueba)")
    parser.add_argument("--sin-autoexposicion", action="store_true",
                         help="Desactiva el barrido de auto-exposición por software (más rápido, útil para pruebas de interior)")
    args = parser.parse_args()

    bloque = generar_bloque_reporte(
        indice_camara=args.indice_camara,
        carpeta_salida=args.salida,
        indice_medicion=args.indice_medicion,
        latitud=args.latitud,
        longitud=args.longitud,
        ancho_estimado_metros=args.ancho_estimado,
        ganancia_manual=args.ganancia,
        usar_autoexposicion=not args.sin_autoexposicion,
    )

    print(json.dumps(bloque, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()