"""Pipeline principal del Sistema de Estimación de Ancho de Calles (SEAC).

Coordina los módulos de procesamiento GPS, obtención de imágenes
satelitales y estimación del ancho de la calle, sin contener la lógica
interna de esos componentes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
from PIL import Image

from imagenes_esri import crear_mosaico, dibujar_marcador, resolucion_metros_por_pixel
from estimacion_ancho import detectar_bordes_calle
from gps import analizar_mediciones, leer_mediciones

def mostrar_resumen(
    analisis: dict[str, Any],
    metros_por_pixel: float,
    tamano_imagen: tuple[int, int],
    deteccion: dict[str, Any],
) -> None:
    """Muestra los resultados mas importantes del pipeline."""
    ancho_px, alto_px = tamano_imagen
    print("\n" + "=" * 62)
    print("SEAC - ANALISIS GPS, IMAGEN SATELITAL Y BORDES")
    print("=" * 62)
    print(f"Mediciones validas:        {analisis['cantidad_mediciones']}")
    print(f"Latitud promedio:          {analisis['latitud_promedio']:.8f}")
    print(f"Longitud promedio:         {analisis['longitud_promedio']:.8f}")
    print(f"Distancia GPS promedio:    {analisis['distancia_promedio_m']:.3f} m")
    print(f"Distancia GPS maxima:      {analisis['distancia_maxima_m']:.3f} m")
    print(f"Resolucion cartografica:   {metros_por_pixel:.6f} m/pixel")
    print(f"Equivalencia de 10 pixeles:{10.0 * metros_por_pixel:9.3f} m")
    print(
        f"Cobertura aproximada:      {ancho_px * metros_por_pixel:.2f} x "
        f"{alto_px * metros_por_pixel:.2f} m"
    )
    print(f"Segmentos Hough:           {deteccion['cantidad_lineas']}")
    if deteccion["angulo_calle_grados"] is None:
        print("Orientacion de calle:      no estimada")
    else:
        print(
            f"Orientacion de calle:      "
            f"{deteccion['angulo_calle_grados']:.2f} grados"
        )
    if deteccion.get("distancia_recentrado_m") is None:
        print("Recentrado respecto al GPS: no disponible")
    else:
        print(
            f"Recentrado respecto al GPS: "
            f"{deteccion['distancia_recentrado_m']:.3f} m"
        )
    print(
        f"Secciones validas:         "
        f"{deteccion['cantidad_secciones_validas']} de "
        f"{deteccion['cantidad_secciones_candidatas']} candidatas"
    )
    if deteccion["ancho_estimado_m"] is None:
        print("Ancho preliminar:          no estimado")
    else:
        print(
            f"Ancho preliminar:          {deteccion['ancho_estimado_m']:.3f} m"
        )
        print("-" * 62)
        print("DESGLOSE DE CONFIANZA")
        print("-" * 62)

        print(
            f"Consistencia de anchos:    "
            f"{deteccion['consistencia']:.3f}"
        )
        print(
            f"Cobertura de secciones:    "
            f"{deteccion['cobertura']:.3f}"
        )
        print(
            f"Confianza de orientacion:  "
            f"{deteccion['confianza_orientacion']:.3f}"
        )
        print(
            f"Confianza geometrica:      "
            f"{deteccion['confianza']:.3f} "
            f"({deteccion['nivel_confianza']})"
        )
    print("=" * 62)


def ejecutar_pipeline(args: argparse.Namespace) -> Path:
    """Ejecuta el flujo completo y devuelve la carpeta de resultados."""
    archivo = Path(args.archivo).expanduser().resolve()
    salida = Path(args.salida).expanduser().resolve()
    salida.mkdir(parents=True, exist_ok=True)

    mediciones = leer_mediciones(archivo)
    analisis = analizar_mediciones(mediciones)
    latitud = analisis["latitud_promedio"]
    longitud = analisis["longitud_promedio"]

    print(f"Leyendo {archivo.name}...")
    print(f"Descargando mosaico Esri para ({latitud:.8f}, {longitud:.8f})...")
    mosaico, posicion_gps = crear_mosaico(
        latitud, longitud, args.zoom, args.radio_teselas
    )
    metros_por_pixel = resolucion_metros_por_pixel(latitud, args.zoom)

    # Se guarda la imagen limpia para no introducir el marcador en Canny.
    mosaico.save(salida / "01_imagen_satelital.png")
    marcada = dibujar_marcador(mosaico, posicion_gps)
    marcada.save(salida / "02_imagen_con_gps.png")

    deteccion = detectar_bordes_calle(
        mosaico=mosaico,
        posicion_gps=posicion_gps,
        metros_por_pixel=metros_por_pixel,
        roi_metros=args.roi_metros,
        canny_bajo=args.canny_bajo,
        canny_alto=args.canny_alto,
        longitud_minima_m=args.longitud_minima_m,
        ancho_minimo_m=args.ancho_minimo_m,
        ancho_maximo_m=args.ancho_maximo_m,
        tolerancia_angulo_grados=args.tolerancia_angulo,
        saturacion_maxima=args.saturacion_maxima,
        textura_maxima=args.textura_maxima,
    )

    cv2.imwrite(str(salida / "03_contraste_grises.png"), deteccion["gris_contraste"])
    cv2.imwrite(str(salida / "04_mascara_asfalto.png"), deteccion["mascara_asfalto"])
    cv2.imwrite(str(salida / "05_bordes_canny.png"), deteccion["bordes_canny"])
    cv2.imwrite(
        str(salida / "06_secciones_transversales.png"),
        deteccion["resultado_visual"],
    )

    reporte = {
        "fuente": "Esri World Imagery",
        "archivo_mediciones": str(archivo),
        "zoom": args.zoom,
        "radio_teselas": args.radio_teselas,
        "posicion_gps_en_imagen_px": {
            "x": posicion_gps[0],
            "y": posicion_gps[1],
        },
        "resolucion_cartografica_m_por_pixel": metros_por_pixel,
        "cobertura_aproximada_m": {
            "ancho": mosaico.width * metros_por_pixel,
            "alto": mosaico.height * metros_por_pixel,
        },
        "analisis_gps": analisis,
        "deteccion": {
            "cantidad_segmentos_hough": deteccion["cantidad_lineas"],
            "canny_bajo_usado": deteccion["canny_bajo_usado"],
            "canny_alto_usado": deteccion["canny_alto_usado"],
            "radio_roi_px": deteccion["radio_roi_px"],
            "centro_ancla_px": deteccion.get("centro_ancla_px"),
            "distancia_recentrado_m": deteccion.get("distancia_recentrado_m"),
            "angulo_calle_grados": deteccion["angulo_calle_grados"],
            "confianza_orientacion": deteccion["confianza_orientacion"],
            "cantidad_secciones_candidatas": deteccion[
                "cantidad_secciones_candidatas"
            ],
            "cantidad_secciones_validas": deteccion["cantidad_secciones_validas"],
            "anchos_candidatos_m": deteccion["anchos_candidatos_m"],
            "anchos_validos_m": deteccion["anchos_validos_m"],
            "ancho_preliminar_m": deteccion["ancho_estimado_m"],
            "confianza": deteccion["confianza"],
            "nivel_confianza": deteccion["nivel_confianza"],
        },
        "advertencia": (
            "La resolucion calculada corresponde a la escala de Web Mercator. "
            "No garantiza la resolucion nativa ni la precision posicional de "
            "la fotografia. Los bordes y el ancho deben validarse."
        ),
    }
    with (salida / "reporte.json").open("w", encoding="utf-8") as archivo_reporte:
        json.dump(reporte, archivo_reporte, indent=2, ensure_ascii=False)

    mostrar_resumen(analisis, metros_por_pixel, mosaico.size, deteccion)
    print(f"Resultados guardados en: {salida}")

    if args.mostrar:
        Image.open(salida / "06_secciones_transversales.png").show()

    return salida


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Integra mediciones GPS, descarga de Esri, resolucion espacial y "
            "deteccion preliminar de bordes de calle."
        )
    )
    parser.add_argument(
        "archivo",
        nargs="?",
        default="mediciones_gps.txt",
        help="Archivo TXT de mediciones (predeterminado: mediciones_gps.txt).",
    )
    parser.add_argument("--zoom", type=int, default=19)
    parser.add_argument("--radio-teselas", type=int, default=1)
    parser.add_argument("--salida", default="resultados_seac")
    parser.add_argument("--roi-metros", type=float, default=20.0)
    parser.add_argument("--canny-bajo", type=int, default=None)
    parser.add_argument("--canny-alto", type=int, default=None)
    parser.add_argument("--longitud-minima-m", type=float, default=4.0)
    parser.add_argument("--ancho-minimo-m", type=float, default=3.0)
    parser.add_argument("--ancho-maximo-m", type=float, default=12.0)
    parser.add_argument("--tolerancia-angulo", type=float, default=12.0)
    parser.add_argument("--saturacion-maxima", type=int, default=90)
    parser.add_argument("--textura-maxima", type=float, default=1000.0)
    parser.add_argument("--mostrar", action="store_true")
    return parser


def validar_argumentos(args: argparse.Namespace) -> None:
    if not 0 <= args.zoom <= 23:
        raise ValueError("El zoom debe estar entre 0 y 23.")
    if args.radio_teselas < 0:
        raise ValueError("El radio de teselas no puede ser negativo.")
    if args.roi_metros <= 0 or args.longitud_minima_m <= 0:
        raise ValueError("ROI y longitud minima deben ser mayores que cero.")
    if not 0 < args.ancho_minimo_m < args.ancho_maximo_m:
        raise ValueError("El intervalo de ancho de calle no es valido.")
    if not 0 <= args.saturacion_maxima <= 255:
        raise ValueError("La saturacion maxima debe estar entre 0 y 255.")
    if args.textura_maxima <= 0:
        raise ValueError("La textura maxima debe ser mayor que cero.")
    for nombre in ("canny_bajo", "canny_alto"):
        valor = getattr(args, nombre)
        if valor is not None and not 0 <= valor <= 255:
            raise ValueError(f"{nombre} debe estar entre 0 y 255.")


def main() -> None:
    parser = crear_parser()
    args = parser.parse_args()
    try:
        validar_argumentos(args)
        ejecutar_pipeline(args)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()