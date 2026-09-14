"""Estimación de ancho de calle para SEAC.

Canny + Hough detectan bordes y orientación. Después se selecciona UNA
pareja global de bordes de calle usando transición visual, ancho estable,
solapamiento longitudinal, continuidad, tono de gris (calle vs. acera) y
bordes internos. Las 13 secciones posteriores quedan bloqueadas a esa
pareja para evitar saltar a aceras, parqueos u otras líneas paralelas.
"""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np
from PIL import Image

__all__ = ["detectar_bordes_calle"]


def diferencia_angulos(a: float, b: float) -> float:
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


def distancia_punto_segmento(punto: tuple[float, float], seg: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = seg
    a = np.array([x1, y1], dtype=float)
    v = np.array([x2 - x1, y2 - y1], dtype=float)
    vv = float(np.dot(v, v))
    if vv == 0.0:
        return float(np.linalg.norm(np.asarray(punto, dtype=float) - a))
    t = float(np.dot(np.asarray(punto, dtype=float) - a, v) / vv)
    t = min(1.0, max(0.0, t))
    return float(np.linalg.norm(np.asarray(punto, dtype=float) - (a + t * v)))


def datos_linea(linea: np.ndarray, centro: tuple[float, float]) -> dict[str, Any]:
    x1, y1, x2, y2 = (float(v) for v in linea)
    dx, dy = x2 - x1, y2 - y1
    puntos = (int(x1), int(y1), int(x2), int(y2))
    return {
        "puntos": puntos,
        "longitud_px": math.hypot(dx, dy),
        "angulo": math.atan2(dy, dx) % math.pi,
        "distancia_segmento_centro_px": distancia_punto_segmento(centro, puntos),
    }


def valor_vecindad(imagen: np.ndarray, punto: np.ndarray) -> int:
    x, y = np.rint(punto).astype(int)
    alto, ancho = imagen.shape[:2]
    if not (1 <= x < ancho - 1 and 1 <= y < alto - 1):
        return 0
    return int(np.max(imagen[y - 1 : y + 2, x - 1 : x + 2]))


def agrupar_posiciones(posiciones: list[float], distancia_maxima: float = 2.0) -> list[float]:
    if not posiciones:
        return []
    posiciones = sorted(posiciones)
    grupos = [[posiciones[0]]]
    for pos in posiciones[1:]:
        if pos - grupos[-1][-1] <= distancia_maxima:
            grupos[-1].append(pos)
        else:
            grupos.append([pos])
    return [float(np.median(g)) for g in grupos]


# ---------------------------------------------------------------------------
# Máscara y Canny
# ---------------------------------------------------------------------------


def crear_mascara_asfalto(
    bgr: np.ndarray,
    mascara_roi: np.ndarray,
    saturacion_maxima: int,
    textura_maxima: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Máscara amplia de pavimento gris/oscuro; no es clasificación semántica."""
    filtrada = cv2.bilateralFilter(bgr, 9, 50, 50)
    hsv = cv2.cvtColor(filtrada, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(filtrada, cv2.COLOR_BGR2LAB)
    gris = cv2.cvtColor(filtrada, cv2.COLOR_BGR2GRAY)

    gf = gris.astype(np.float32)
    media = cv2.blur(gf, (9, 9))
    varianza = cv2.blur(gf**2, (9, 9)) - media**2
    cromaticidad = np.sqrt(
        (lab[:, :, 1].astype(float) - 128.0) ** 2
        + (lab[:, :, 2].astype(float) - 128.0) ** 2
    )

    # Techo de brillo adaptativo por foto (Otsu), en vez del 160 fijo: se
    # ajusta solo a fotos sobre/sub-expuestas. El piso SI se conserva (y
    # tambien se adapta un poco) para no dejar pasar sombras muy negras,
    # que son tan oscuras como el asfalto pero no son calle.
    valores_roi = gris[mascara_roi > 0]
    if valores_roi.size:
        umbral_oscuro, _ = cv2.threshold(
            valores_roi.reshape(-1, 1).astype(np.uint8), 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU,
        )
        piso_sombra = max(35.0, float(np.percentile(valores_roi, 3)))
    else:
        umbral_oscuro, piso_sombra = 160.0, 35.0

    mascara = (
        (gris >= piso_sombra)
        & (gris <= float(umbral_oscuro) + 10.0)
        & (hsv[:, :, 1] <= saturacion_maxima)
        & (cromaticidad <= 35.0)
        & (varianza <= textura_maxima)
        & (mascara_roi > 0)
    ).astype(np.uint8) * 255

    mascara = cv2.morphologyEx(
        mascara, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )
    mascara = cv2.morphologyEx(
        mascara, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    return filtrada, gris, mascara


def calcular_bordes(
    gris: np.ndarray,
    mascara_roi: np.ndarray,
    mascara_asfalto: np.ndarray,
    canny_bajo: int | None,
    canny_alto: int | None,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    contraste = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gris)
    valores = contraste[mascara_asfalto > 0]
    if not valores.size:
        valores = contraste[mascara_roi > 0]
    mediana = float(np.median(valores)) if valores.size else 128.0

    if canny_bajo is None:
        canny_bajo = max(0, int(0.67 * mediana))
    if canny_alto is None:
        canny_alto = min(255, int(1.33 * mediana))
    if canny_alto <= canny_bajo:
        canny_alto = min(255, canny_bajo + 1)

    bordes = cv2.Canny(contraste, canny_bajo, canny_alto, apertureSize=3, L2gradient=True)

    # Se conserva la frontera asfalto/exterior dilatando la máscara antes de filtrar.
    mascara_dilatada = cv2.dilate(
        mascara_asfalto, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )
    bordes = cv2.bitwise_and(bordes, mascara_dilatada)
    bordes = cv2.bitwise_and(bordes, mascara_roi)
    bordes = cv2.morphologyEx(
        bordes, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    )
    return contraste, bordes, canny_bajo, canny_alto


# ---------------------------------------------------------------------------
# Intensidad de referencia de la calle (calle vs. acera)
# ---------------------------------------------------------------------------


def intensidad_referencia_calle(
    contraste: np.ndarray,
    mascara_asfalto: np.ndarray,
    mascara_roi: np.ndarray,
) -> tuple[float, float]:
    """Devuelve (intensidad_calle, tolerancia_gris) estimadas del propio ROI.

    No se asume que el punto GPS esta sobre la calle: podria estar sobre la
    acera midiendo hacia el otro lado. En su lugar, la mascara de asfalto
    (que ya mezcla calle y acera porque ambas comparten saturacion/brillo
    bajos) se separa en dos tonos con Otsu, y se toma el racimo mas oscuro
    como referencia de "asfalto real", ya que el concreto de acera casi
    siempre es mas claro que el asfalto de calzada.

    La tolerancia ya no es un numero fijo: se calcula a partir de que tan
    ruidoso es el propio asfalto de esta foto (su dispersion) y de que tan
    separado esta del racimo claro (acera). Si la separacion es marcada, se
    endurece sola; si los tonos son parecidos o no hay acera visible en el
    ROI, se relaja para no penalizar la calle real por variaciones normales
    de iluminacion.
    """
    combinada = cv2.bitwise_and(mascara_asfalto, mascara_roi)
    valores = contraste[combinada > 0]
    if valores.size < 20:
        valores = contraste[mascara_roi > 0]
    if not valores.size:
        return 128.0, 35.0

    muestra = valores.reshape(-1, 1).astype(np.uint8)
    umbral, _ = cv2.threshold(muestra, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    oscuros = valores[valores <= umbral]
    claros = valores[valores > umbral]

    # Si el racimo oscuro es minoritario/insignificante, no hay evidencia
    # real de dos superficies distintas: se usa toda la muestra y una
    # tolerancia laxa por defecto.
    if oscuros.size < max(10, int(0.05 * valores.size)):
        return float(np.median(valores)), 35.0

    intensidad_calle = float(np.median(oscuros))
    dispersion_calle = float(np.median(np.abs(oscuros - intensidad_calle))) * 1.4826

    separacion = float(np.median(claros)) - intensidad_calle if claros.size else 0.0

    tolerancia = max(dispersion_calle * 1.5, 12.0)
    if separacion > 0.0:
        tolerancia = min(tolerancia, 0.5 * separacion)
    tolerancia = float(np.clip(tolerancia, 10.0, 45.0))

    return intensidad_calle, tolerancia


# ---------------------------------------------------------------------------
# Orientación
# ---------------------------------------------------------------------------


def estimar_orientacion_calle(
    lineas: list[dict[str, Any]],
    metros_por_pixel: float,
    roi_metros: float,
    tolerancia_grados: float,
) -> tuple[float, float] | None:
    candidatas = [
        l for l in lineas
        if l["distancia_segmento_centro_px"] * metros_por_pixel <= 0.75 * roi_metros
    ]
    if not candidatas:
        return None

    tam_bin = 5.0
    hist = np.zeros(int(180 / tam_bin), dtype=float)
    for l in candidatas:
        distancia_m = l["distancia_segmento_centro_px"] * metros_por_pixel
        longitud_m = l["longitud_px"] * metros_por_pixel
        peso = longitud_m / (1.0 + distancia_m / 3.0)
        idx = int(math.degrees(l["angulo"]) // tam_bin) % len(hist)
        hist[idx] += peso

    idx = int(np.argmax(hist))
    base = math.radians(idx * tam_bin + tam_bin / 2.0)
    tol = math.radians(tolerancia_grados)
    alineadas = [l for l in candidatas if diferencia_angulos(l["angulo"], base) <= tol]
    if not alineadas:
        return None

    c = sum(l["longitud_px"] * math.cos(2.0 * l["angulo"]) for l in alineadas)
    s = sum(l["longitud_px"] * math.sin(2.0 * l["angulo"]) for l in alineadas)
    angulo = (0.5 * math.atan2(s, c)) % math.pi

    total = 0.0
    alineado = 0.0
    for l in candidatas:
        dm = l["distancia_segmento_centro_px"] * metros_por_pixel
        lm = l["longitud_px"] * metros_por_pixel
        peso = lm / (1.0 + dm / 3.0)
        total += peso
        if diferencia_angulos(l["angulo"], angulo) <= tol:
            alineado += peso
    return angulo, float(alineado / max(total, 1e-9))


# ---------------------------------------------------------------------------
# Segmentos en coordenadas longitudinales/laterales
# ---------------------------------------------------------------------------


def proyectar_segmento(
    linea: dict[str, Any],
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    mpp: float,
) -> dict[str, Any]:
    x1, y1, x2, y2 = linea["puntos"]
    p1 = np.array([x1, y1], dtype=float) - gps
    p2 = np.array([x2, y2], dtype=float) - gps
    s1, s2 = float(np.dot(p1, direccion) * mpp), float(np.dot(p2, direccion) * mpp)
    d1, d2 = float(np.dot(p1, normal) * mpp), float(np.dot(p2, normal) * mpp)

    if abs(s2 - s1) > 1e-6:
        pendiente = (d2 - d1) / (s2 - s1)
        intercepto = d1 - pendiente * s1
    else:
        pendiente = 0.0
        intercepto = (d1 + d2) / 2.0

    r = dict(linea)
    r.update({
        "s_min_m": min(s1, s2),
        "s_max_m": max(s1, s2),
        "pendiente_lateral": pendiente,
        "intercepto_lateral_m": intercepto,
        "longitud_m": linea["longitud_px"] * mpp,
    })
    return r


def lateral_en_s(seg: dict[str, Any], s_m: float) -> float:
    return float(seg["pendiente_lateral"] * s_m + seg["intercepto_lateral_m"])


def solapamiento_segmentos(a: dict[str, Any], b: dict[str, Any]) -> tuple[float, float, float]:
    inicio = max(a["s_min_m"], b["s_min_m"])
    final = min(a["s_max_m"], b["s_max_m"])
    return inicio, final, max(0.0, final - inicio)


# ---------------------------------------------------------------------------
# Transición visual
# ---------------------------------------------------------------------------


def proporcion_banda(
    mascara: np.ndarray,
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    s_m: float,
    d_m: float,
    desplazamientos_m: list[float],
    mpp: float,
) -> float:
    valores = []
    for delta in desplazamientos_m:
        p = gps + direccion * (s_m / mpp) + normal * ((d_m + delta) / mpp)
        valores.append(valor_vecindad(mascara, p) > 0)
    return float(np.mean(valores)) if valores else 0.0


def transicion_borde(
    mascara: np.ndarray,
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    s_m: float,
    d_m: float,
    lado_interior: int,
    mpp: float,
) -> tuple[float, float, float]:
    dist = [0.35, 0.55, 0.75, 0.95]
    dentro = [lado_interior * x for x in dist]
    fuera = [-lado_interior * x for x in dist]
    p_dentro = proporcion_banda(mascara, gps, direccion, normal, s_m, d_m, dentro, mpp)
    p_fuera = proporcion_banda(mascara, gps, direccion, normal, s_m, d_m, fuera, mpp)
    puntaje = float(np.clip((p_dentro - p_fuera + 0.20) / 1.20, 0.0, 1.0))
    return puntaje, p_dentro, p_fuera


def transicion_promedio(
    seg: dict[str, Any],
    lado_interior: int,
    inicio: float,
    final: float,
    mascara: np.ndarray,
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    mpp: float,
) -> float:
    if final <= inicio:
        return 0.0
    valores = []
    for s_m in np.linspace(inicio, final, 5):
        d_m = lateral_en_s(seg, float(s_m))
        valores.append(
            transicion_borde(mascara, gps, direccion, normal, float(s_m), d_m, lado_interior, mpp)[0]
        )
    return float(np.mean(valores)) if valores else 0.0


def fuerza_borde_interno(
    seg: dict[str, Any],
    inicio: float,
    final: float,
    mascara: np.ndarray,
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    mpp: float,
) -> float:
    a = max(inicio, seg["s_min_m"])
    b = min(final, seg["s_max_m"])
    solapado = max(0.0, b - a)
    if solapado <= 0.0:
        return 0.0

    diferencias = []
    for s_m in np.linspace(a, b, 4):
        d_m = lateral_en_s(seg, float(s_m))
        _, p_pos, p_neg = transicion_borde(
            mascara, gps, direccion, normal, float(s_m), d_m, +1, mpp
        )
        diferencias.append(abs(p_pos - p_neg))

    cambio = float(np.mean(diferencias)) if diferencias else 0.0
    continuidad = min(1.0, solapado / 6.0)
    return 0.65 * cambio + 0.35 * continuidad


def similitud_intensidad_franja(
    contraste: np.ndarray,
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    izq: dict[str, Any],
    der: dict[str, Any],
    inicio: float,
    final: float,
    intensidad_calle: float,
    mpp: float,
    tolerancia_gris: float,
) -> float:
    """Compara el tono de gris interior del par contra el tono real de asfalto.

    Una acera de concreto suele pasar el mismo filtro de saturacion/brillo
    que el asfalto, pero casi siempre tiene un tono de gris distinto una vez
    que se compara contra `intensidad_calle` (ver intensidad_referencia_calle).
    """
    if final <= inicio:
        return 0.0
    valores = []
    for s_m in np.linspace(inicio, final, 5):
        d_centro = (lateral_en_s(izq, float(s_m)) + lateral_en_s(der, float(s_m))) / 2.0
        p = gps + direccion * (s_m / mpp) + normal * (d_centro / mpp)
        valores.append(valor_vecindad(contraste, p))
    diferencia = abs(float(np.mean(valores)) - intensidad_calle)
    return max(0.0, 1.0 - diferencia / tolerancia_gris)


# ---------------------------------------------------------------------------
# Pareja global de bordes
# ---------------------------------------------------------------------------


def evaluar_pareja(
    a: dict[str, Any],
    b: dict[str, Any],
    alineadas: list[dict[str, Any]],
    mascara: np.ndarray,
    contraste: np.ndarray,
    intensidad_calle: float,
    tolerancia_gris: float,
    gps: np.ndarray,
    direccion: np.ndarray,
    normal: np.ndarray,
    mpp: float,
    ancho_min: float,
    ancho_max: float,
    relajado: bool,
) -> dict[str, Any] | None:
    inicio, final, solapado = solapamiento_segmentos(a, b)
    if solapado < (1.8 if relajado else 2.8):
        return None

    muestras = np.linspace(inicio, final, 7)
    anchos = []
    for s_m in muestras:
        da, db = lateral_en_s(a, float(s_m)), lateral_en_s(b, float(s_m))
        anchos.append(abs(db - da))

    ancho = float(np.median(anchos))
    if not ancho_min <= ancho <= ancho_max:
        return None

    mad = float(np.median(np.abs(np.asarray(anchos) - ancho)))
    if mad > (1.20 if relajado else 0.85):
        return None
    consistencia = max(0.0, 1.0 - mad / max(1.25, 0.20 * ancho))

    s_mid = (inicio + final) / 2.0
    if lateral_en_s(a, s_mid) <= lateral_en_s(b, s_mid):
        izq, der = a, b
    else:
        izq, der = b, a

    t_izq = transicion_promedio(izq, +1, inicio, final, mascara, gps, direccion, normal, mpp)
    t_der = transicion_promedio(der, -1, inicio, final, mascara, gps, direccion, normal, mpp)
    transicion = (t_izq + t_der) / 2.0

    similitud_gris = similitud_intensidad_franja(
        contraste, gps, direccion, normal, izq, der, inicio, final,
        intensidad_calle, mpp, tolerancia_gris,
    )

    longitud_min = min(izq["longitud_m"], der["longitud_m"])
    solap_rel = min(1.0, solapado / max(longitud_min, 1e-9))
    continuidad = min(1.0, longitud_min / 8.0)

    d_izq_0, d_der_0 = lateral_en_s(izq, 0.0), lateral_en_s(der, 0.0)
    distancia_gps = 0.0 if d_izq_0 <= 0.0 <= d_der_0 else min(abs(d_izq_0), abs(d_der_0))
    max_gps = 3.0 if relajado else 2.0
    if distancia_gps > max_gps:
        return None

    distancia_long = 0.0 if inicio <= 0.0 <= final else min(abs(inicio), abs(final))
    max_long = 7.0 if relajado else 5.0
    if distancia_long > max_long:
        return None

    d_izq_mid, d_der_mid = lateral_en_s(izq, s_mid), lateral_en_s(der, s_mid)
    fuerzas = []
    for otro in alineadas:
        if otro is izq or otro is der:
            continue
        d_otro = lateral_en_s(otro, s_mid)
        if d_izq_mid < d_otro < d_der_mid:
            fuerzas.append(
                fuerza_borde_interno(otro, inicio, final, mascara, gps, direccion, normal, mpp)
            )
    fuerza_interna = max(fuerzas, default=0.0)

    puntaje = (
        0.26 * transicion
        + 0.26 * consistencia
        + 0.16 * solap_rel
        + 0.16 * continuidad
        + 0.16 * similitud_gris
        - 0.12 * fuerza_interna
        - 0.08 * min(1.0, distancia_gps / max_gps)
        - 0.05 * min(1.0, distancia_long / max_long)
    )

    return {
        "borde_izquierdo": izq,
        "borde_derecho": der,
        "ancho_mediano_m": ancho,
        "mad_ancho_m": mad,
        "consistencia_ancho": consistencia,
        "solapamiento_m": solapado,
        "solapamiento_relativo": solap_rel,
        "continuidad": continuidad,
        "transicion_izquierda": t_izq,
        "transicion_derecha": t_der,
        "transicion_visual": transicion,
        "similitud_gris": similitud_gris,
        "fuerza_borde_interno": fuerza_interna,
        "distancia_gps_calle_m": distancia_gps,
        "puntaje": float(puntaje),
    }


def seleccionar_pareja_global(
    lineas: list[dict[str, Any]],
    angulo: float,
    gps: np.ndarray,
    mpp: float,
    mascara: np.ndarray,
    contraste: np.ndarray,
    intensidad_calle: float,
    tolerancia_gris: float,
    ancho_min: float,
    ancho_max: float,
    tolerancia_grados: float,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    direccion = np.array([math.cos(angulo), math.sin(angulo)], dtype=float)
    normal = np.array([-direccion[1], direccion[0]], dtype=float)
    tol = math.radians(tolerancia_grados * 1.35)

    alineadas = [
        proyectar_segmento(l, gps, direccion, normal, mpp)
        for l in lineas
        if diferencia_angulos(l["angulo"], angulo) <= tol
    ]
    if len(alineadas) < 2:
        return None, alineadas

    def buscar(relajado: bool) -> dict[str, Any] | None:
        mejor, mejor_puntaje = None, -math.inf
        for i, a in enumerate(alineadas):
            for b in alineadas[i + 1 :]:
                candidato = evaluar_pareja(
                    a, b, alineadas, mascara, contraste, intensidad_calle, tolerancia_gris,
                    gps, direccion, normal, mpp, ancho_min, ancho_max, relajado,
                )
                if candidato is not None and candidato["puntaje"] > mejor_puntaje:
                    mejor, mejor_puntaje = candidato, candidato["puntaje"]
        return mejor

    mejor = buscar(False)
    if mejor is None:
        mejor = buscar(True)
    return mejor, alineadas


# ---------------------------------------------------------------------------
# Secciones bloqueadas a la pareja global
# ---------------------------------------------------------------------------


def soporte_borde(bordes: np.ndarray, punto: np.ndarray, direccion: np.ndarray, mpp: float) -> float:
    alcance = max(3, int(round(3.0 / mpp)))
    valores = [
        valor_vecindad(bordes, punto + d * direccion) > 0
        for d in range(-alcance, alcance + 1, 2)
    ]
    return float(np.mean(valores)) if valores else 0.0


def buscar_borde_bloqueado(
    centro: np.ndarray,
    normal: np.ndarray,
    direccion: np.ndarray,
    esperado_m: float,
    lado_interior: int,
    bordes: np.ndarray,
    mascara: np.ndarray,
    gps: np.ndarray,
    s_m: float,
    mpp: float,
    ventana_m: float = 1.10,
) -> tuple[float, np.ndarray, float] | None:
    esperado_px = esperado_m / mpp
    ventana_px = max(2, int(round(ventana_m / mpp)))
    posiciones = []
    for t in range(int(round(esperado_px)) - ventana_px, int(round(esperado_px)) + ventana_px + 1):
        if valor_vecindad(bordes, centro + t * normal) > 0:
            posiciones.append(float(t))

    posiciones = agrupar_posiciones(posiciones)
    if not posiciones:
        return None

    mejor, mejor_puntaje = None, -math.inf
    for pos_px in posiciones:
        offset_m = pos_px * mpp
        punto = centro + pos_px * normal
        soporte = soporte_borde(bordes, punto, direccion, mpp)
        transicion = transicion_borde(
            mascara, gps, direccion, normal, s_m, offset_m, lado_interior, mpp
        )[0]
        proximidad = max(0.0, 1.0 - abs(offset_m - esperado_m) / ventana_m)
        puntaje = 0.50 * proximidad + 0.30 * soporte + 0.20 * transicion
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = (offset_m, punto, float(puntaje)), puntaje
    return mejor


def medir_secciones_bloqueadas(
    pareja: dict[str, Any],
    gps: np.ndarray,
    angulo: float,
    bordes: np.ndarray,
    mascara: np.ndarray,
    mpp: float,
    ancho_min: float,
    ancho_max: float,
) -> list[dict[str, Any]]:
    direccion = np.array([math.cos(angulo), math.sin(angulo)], dtype=float)
    normal = np.array([-direccion[1], direccion[0]], dtype=float)
    izq, der = pareja["borde_izquierdo"], pareja["borde_derecho"]
    ancho_ref = pareja["ancho_mediano_m"]
    mediciones = []

    for s_m in np.linspace(-6.0, 6.0, 13):
        s_m = float(s_m)
        centro = gps + direccion * (s_m / mpp)
        esperado_izq, esperado_der = lateral_en_s(izq, s_m), lateral_en_s(der, s_m)
        if esperado_izq > esperado_der:
            esperado_izq, esperado_der = esperado_der, esperado_izq

        hallado_izq = buscar_borde_bloqueado(
            centro, normal, direccion, esperado_izq, +1, bordes, mascara, gps, s_m, mpp
        )
        hallado_der = buscar_borde_bloqueado(
            centro, normal, direccion, esperado_der, -1, bordes, mascara, gps, s_m, mpp
        )
        if hallado_izq is None or hallado_der is None:
            continue

        off_izq, p_izq, q_izq = hallado_izq
        off_der, p_der, q_der = hallado_der
        ancho = off_der - off_izq
        if not ancho_min <= ancho <= ancho_max:
            continue
        if abs(ancho - ancho_ref) > 1.50:
            continue

        mediciones.append({
            "ancho_m": float(ancho),
            "borde_1": p_izq,
            "borde_2": p_der,
            "centro": centro,
            "desplazamiento_m": s_m,
            "calidad": float((q_izq + q_der) / 2.0),
        })
    return mediciones


def filtrar_mediciones_consistentes(mediciones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(mediciones) < 3:
        return []
    anchos = np.asarray([m["ancho_m"] for m in mediciones], dtype=float)
    mediana = float(np.median(anchos))
    mad = float(np.median(np.abs(anchos - mediana)))
    tolerancia = max(0.65, 2.5 * mad)
    filtradas = [m for m in mediciones if abs(m["ancho_m"] - mediana) <= tolerancia]
    return filtradas if len(filtradas) >= 3 else []


def dibujar_segmento(
    imagen: np.ndarray,
    segmento: dict[str, Any],
    color: tuple[int, int, int],
    grosor: int,
) -> None:
    x1, y1, x2, y2 = segmento["puntos"]
    cv2.line(imagen, (x1, y1), (x2, y2), color, grosor, cv2.LINE_AA)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def detectar_bordes_calle(
    mosaico: Image.Image,
    posicion_gps: tuple[float, float],
    metros_por_pixel: float,
    roi_metros: float,
    canny_bajo: int | None,
    canny_alto: int | None,
    longitud_minima_m: float,
    ancho_minimo_m: float,
    ancho_maximo_m: float,
    tolerancia_angulo_grados: float,
    saturacion_maxima: int,
    textura_maxima: float,
    radio_orientacion_local_m: float = 4.0,
) -> dict[str, Any]:
    """Estima el ancho usando dos bordes globales y 13 cortes bloqueados."""
    del radio_orientacion_local_m  # Se conserva por compatibilidad con versiones previas.

    bgr = cv2.cvtColor(np.asarray(mosaico), cv2.COLOR_RGB2BGR)
    centro = (int(round(posicion_gps[0])), int(round(posicion_gps[1])))
    gps = np.asarray(posicion_gps, dtype=float)
    radio_roi_px = max(10, int(round(roi_metros / metros_por_pixel)))

    mascara_roi = np.zeros(bgr.shape[:2], dtype=np.uint8)
    cv2.circle(mascara_roi, centro, radio_roi_px, 255, thickness=-1)

    filtrada, gris, mascara_asfalto = crear_mascara_asfalto(
        bgr, mascara_roi, saturacion_maxima, textura_maxima
    )
    contraste, bordes, canny_bajo, canny_alto = calcular_bordes(
        gris, mascara_roi, mascara_asfalto, canny_bajo, canny_alto
    )
    intensidad_calle, tolerancia_gris = intensidad_referencia_calle(
        contraste, mascara_asfalto, mascara_roi
    )

    longitud_px = max(8, int(round(longitud_minima_m / metros_por_pixel)))
    hough = cv2.HoughLinesP(
        bordes,
        rho=1,
        theta=np.pi / 180.0,
        threshold=20,
        minLineLength=longitud_px,
        maxLineGap=max(3, int(round(3.0 / metros_por_pixel))),
    )

    lineas = []
    if hough is not None:
        for linea in np.asarray(hough).reshape(-1, 4):
            if not np.array_equal(linea[:2], linea[2:]):
                lineas.append(datos_linea(linea, posicion_gps))

    orientacion = estimar_orientacion_calle(
        lineas, metros_por_pixel, roi_metros, tolerancia_angulo_grados
    )

    visual = filtrada.copy()
    for linea in lineas:
        dibujar_segmento(visual, linea, (0, 140, 255), 1)  # naranja: Hough
    cv2.circle(visual, centro, radio_roi_px, (255, 200, 0), 2)  # cian: ROI
    cv2.drawMarker(visual, centro, (255, 0, 0), cv2.MARKER_CROSS, 24, 2)  # azul: GPS

    angulo_grados = None
    confianza_orientacion = 0.0
    pareja = None
    alineadas = []
    mediciones = []
    validas = []
    centro_ancla_px = None
    distancia_recentrado_m = None

    if orientacion is not None:
        angulo, confianza_orientacion = orientacion
        angulo_grados = math.degrees(angulo)
        direccion = np.array([math.cos(angulo), math.sin(angulo)], dtype=float)
        normal = np.array([-direccion[1], direccion[0]], dtype=float)

        pareja, alineadas = seleccionar_pareja_global(
            lineas, angulo, gps, metros_por_pixel, mascara_asfalto,
            contraste, intensidad_calle, tolerancia_gris,
            ancho_minimo_m, ancho_maximo_m, tolerancia_angulo_grados,
        )

        largo = int(round(8.0 / metros_por_pixel))
        p1 = tuple(np.rint(gps - direccion * largo).astype(int))
        p2 = tuple(np.rint(gps + direccion * largo).astype(int))
        cv2.arrowedLine(visual, p1, p2, (255, 0, 255), 2)  # magenta: orientación

        if pareja is not None:
            dibujar_segmento(visual, pareja["borde_izquierdo"], (0, 0, 255), 4)  # rojo
            dibujar_segmento(visual, pareja["borde_derecho"], (0, 255, 0), 4)  # verde

            mediciones = medir_secciones_bloqueadas(
                pareja, gps, angulo, bordes, mascara_asfalto, metros_por_pixel,
                ancho_minimo_m, ancho_maximo_m,
            )
            validas = filtrar_mediciones_consistentes(mediciones)

            d_izq = lateral_en_s(pareja["borde_izquierdo"], 0.0)
            d_der = lateral_en_s(pareja["borde_derecho"], 0.0)
            d_centro = (d_izq + d_der) / 2.0
            centro_ancla = gps + normal * (d_centro / metros_por_pixel)
            centro_ancla_px = (float(centro_ancla[0]), float(centro_ancla[1]))
            distancia_recentrado_m = abs(float(d_centro))
            cv2.drawMarker(
                visual, tuple(np.rint(centro_ancla).astype(int)),
                (0, 255, 255), cv2.MARKER_DIAMOND, 16, 2,
            )

    ids_validos = {id(m) for m in validas}
    for m in mediciones:
        es_valida = id(m) in ids_validos
        color = (0, 255, 255) if es_valida else (150, 150, 150)  # amarillo / gris
        grosor = 3 if es_valida else 1
        a = tuple(np.rint(m["borde_1"]).astype(int))
        b = tuple(np.rint(m["borde_2"]).astype(int))
        cv2.line(visual, a, b, color, grosor, cv2.LINE_AA)

    ancho_estimado = None
    confianza = 0.0
    consistencia = 0.0
    cobertura = 0.0

    if len(validas) >= 3:
        anchos = np.asarray([m["ancho_m"] for m in validas], dtype=float)
        ancho_estimado = float(np.median(anchos))
        dispersion = float(np.std(anchos))
        consistencia = max(0.0, 1.0 - dispersion / max(ancho_estimado, 1e-9))
        cobertura = min(1.0, len(validas) / 7.0)
        calidad_pareja = float(pareja["puntaje"]) if pareja is not None else 0.0
        confianza = float(
            consistencia * cobertura * confianza_orientacion
            * max(0.0, min(1.0, calidad_pareja))
        )
        nivel = "alta" if confianza >= 0.55 else "media" if confianza >= 0.30 else "baja"
        texto = f"Ancho: {ancho_estimado:.2f} m | confianza {nivel}"
        color_texto = (0, 255, 0)
    else:
        nivel = "insuficiente"
        if orientacion is None:
            texto = "No se pudo estimar la orientacion"
        elif pareja is None:
            texto = "No se encontro una pareja global de bordes"
        else:
            texto = "No hay 3 secciones bloqueadas consistentes"
        color_texto = (0, 0, 255)

    cv2.putText(
        visual, texto, (20, 35), cv2.FONT_HERSHEY_SIMPLEX,
        0.7, color_texto, 2, cv2.LINE_AA,
    )

    diagnostico = None
    if pareja is not None:
        diagnostico = {
            "ancho_hough_m": float(pareja["ancho_mediano_m"]),
            "mad_ancho_m": float(pareja["mad_ancho_m"]),
            "consistencia_ancho": float(pareja["consistencia_ancho"]),
            "solapamiento_m": float(pareja["solapamiento_m"]),
            "solapamiento_relativo": float(pareja["solapamiento_relativo"]),
            "continuidad": float(pareja["continuidad"]),
            "transicion_izquierda": float(pareja["transicion_izquierda"]),
            "transicion_derecha": float(pareja["transicion_derecha"]),
            "transicion_visual": float(pareja["transicion_visual"]),
            "similitud_gris": float(pareja["similitud_gris"]),
            "fuerza_borde_interno": float(pareja["fuerza_borde_interno"]),
            "distancia_gps_calle_m": float(pareja["distancia_gps_calle_m"]),
            "puntaje": float(pareja["puntaje"]),
        }

    return {
        "gris_contraste": contraste,
        "mascara_asfalto": mascara_asfalto,
        "bordes_canny": bordes,
        "resultado_visual": visual,
        "cantidad_lineas": len(lineas),
        "cantidad_lineas_alineadas": len(alineadas),
        "angulo_calle_grados": angulo_grados,
        "confianza_orientacion": confianza_orientacion,
        "intensidad_calle_referencia": intensidad_calle,
        "tolerancia_gris_usada": tolerancia_gris,
        "cantidad_secciones_candidatas": len(mediciones),
        "cantidad_secciones_validas": len(validas),
        "anchos_candidatos_m": [float(m["ancho_m"]) for m in mediciones],
        "anchos_validos_m": [float(m["ancho_m"]) for m in validas],
        "ancho_estimado_m": ancho_estimado,
        "confianza": confianza,
        "consistencia": consistencia,
        "cobertura": cobertura,
        "nivel_confianza": nivel,
        "canny_bajo_usado": canny_bajo,
        "canny_alto_usado": canny_alto,
        "radio_roi_px": radio_roi_px,
        "centro_ancla_px": centro_ancla_px,
        "distancia_recentrado_m": distancia_recentrado_m,
        "pareja_global": diagnostico,
    }