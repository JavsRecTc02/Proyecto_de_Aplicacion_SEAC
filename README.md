# SEAC: Sistema de estimación de ancho de una calle 

## Descripción

Este proyecto corresponde al desarrollo de un sistema automatizado para la estimación de parámetros físicos y geométricos de una calle, principalmente su **ancho**, utilizando  **geolocalización GPS, imágenes satelitales como método principal y el uso de **cámara** para complementar.

El sistema busca complementar soluciones existentes de medición de velocidad vehicular basadas en modelos de detección como **YOLO**, proporcionando información sobre el entorno físico de la vía que permita mejorar la calibración y precisión de dichas estimaciones.

## La propuesta utiliza una arquitectura en la que la adquisición de datos puede realizarse mediante hardware embebido, mientras que el procesamiento y análisis de la información puede realizarse posteriormente en un sistema externo.

# Arquitectura general

Actualmente, el desarrollo se divide en varias etapas:

```text
┌──────────────────────┐
│      NEO-6M GPS      │
└──────────┬───────────┘
           │
           │ Datos NMEA
           ▼
┌──────────────────────┐
│       Python Rpi4    │
│                      │
│ Validación de datos  │
│ GPS + satélites      │
│ + HDOP               │
└──────────┬───────────┘
           │
           │ 10 mediciones válidas
           ▼
┌──────────────────────┐
│        Python        │
│                      │
│ Análisis estadístico │
│ Promedio             │
│ Dispersión           │
│ Desviación           │
└──────────┬───────────┘
           │
           │ Latitud/Longitud promedio
           ▼
┌──────────────────────┐
│ Imágenes satelitales │
│      Esri World      │
│       Imagery        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Mosaico de teselas   │
│        3 × 3         │
│                      │
│ + posición GPS       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Análisis geométrico  │
│       de la vía      │
└──────────────────────┘
```

La arquitectura final incorporará además una cámara para utilizar información visual de la escena vial, de acuerdo con los objetivos establecidos para el proyecto.

---

# Etapa 1 — Adquisición de datos GPS

## Hardware

Para la adquisición de las coordenadas se utiliza un módulo **NEO-6M GPS**, conectado a la RaspBerry pi 4 mediante comunicación serial.

La conexión utilizada actualmente es:

| Componente   |        Rpi4    |
| ------------ | -------------: |
| NEO-6M TX    |          Pin RX|
| NEO-6M RX    |          Pin TX|
| Baud rate    |           9600 |
| Comunicación | SoftwareSerial |

La Rpi4 se encarga de recibir continuamente las sentencias NMEA generadas por el módulo GPS y procesarlas mediante la biblioteca `pymea2`.

---

# Validación de las mediciones GPS

No todas las mediciones proporcionadas por el GPS se consideran confiables para el sistema.

Antes de almacenar una medición, el programa verifica que estén disponibles:

* Coordenadas GPS válidas.
* Número de satélites válido.
* Valor de HDOP válido.

Posteriormente se aplican criterios mínimos de calidad:

```text
Satélites ≥ 4
HDOP ≤ 2.0
```

Además, las mediciones válidas deben estar separadas por un intervalo mínimo de:

```text
2 segundos
```

Esto evita tomar múltiples muestras prácticamente simultáneas y permite obtener una serie de mediciones distribuidas temporalmente.

---

# Obtención de las 10 mediciones

El sistema establece como objetivo:

```cpp
const int MEDICIONES_OBJETIVO = 10;
```

Por lo tanto, el Arduino continúa recibiendo y evaluando datos hasta obtener **10 mediciones que cumplan todos los criterios de validación**.

Cada medición se transmite por el puerto serial utilizando el siguiente formato:

```text
GPS,indice,latitud,longitud,satelites,HDOP
```

Por ejemplo:

![Imagen satelital](docs/mediciones.jpeg)

Cada registro contiene:

| Campo       | Descripción                       |
| ----------- | --------------------------------- |
| `GPS`       | Identificador del tipo de dato    |
| `indice`    | Número de medición                |
| `latitud`   | Latitud registrada                |
| `longitud`  | Longitud registrada               |
| `satelites` | Satélites utilizados/recibidos    |
| `HDOP`      | Indicador de precisión geométrica |

Cuando se obtienen las 10 mediciones, Arduino transmite:

```text
FIN_MEDICIONES
```

y detiene la adquisición.

---

# Etapa 2 — Procesamiento de los datos GPS

Una vez obtenidas las mediciones GPS, los datos son procesados mediante **Python**.

Esta etapa se encuentra implementada en el módulo:

```text
gps.py
```

El objetivo de esta etapa es validar las mediciones obtenidas y determinar una posición representativa de la ubicación donde se realizó la captura.

En lugar de utilizar directamente una única medición, el sistema procesa el conjunto de mediciones almacenadas en el archivo de entrada.

Cada registro GPS contiene:

```text
GPS,número,latitud,longitud,satélites,HDOP
```

El módulo verifica que las coordenadas sean válidas antes de utilizarlas.

---

# Análisis de las mediciones GPS

A partir de las mediciones válidas se calculan diferentes parámetros que permiten conocer la posición representativa y la dispersión de los datos.

Actualmente se calculan:

* Cantidad de mediciones válidas.
* Latitud promedio.
* Longitud promedio.
* Latitud mínima.
* Latitud máxima.
* Longitud mínima.
* Longitud máxima.
* Desviación estándar de la latitud.
* Desviación estándar de la longitud.
* Rango de latitud expresado en metros.
* Rango de longitud expresado en metros.
* Distancia de cada medición con respecto a la coordenada promedio.
* Distancia promedio con respecto al punto promedio.
* Distancia máxima con respecto al punto promedio.

El archivo de entrada también contiene el número de satélites y el valor HDOP de cada medición. Estos datos son leídos y almacenados por el módulo GPS, aunque actualmente no son utilizados para calcular la coordenada promedio.

> **Nota importante:** el sistema **no asume** que el punto GPS promedio cae exactamente sobre el centro de la calle. En campo, quien mide puede estar parado en la acera, en un camellón o en el borde de una plaza midiendo hacia el otro lado. Varias de las señales descritas más adelante (sección de "Selección de la pareja global de bordes") existen justamente para no depender de ese supuesto de forma rígida.

---

# Coordenada promedio

A partir de las mediciones válidas se obtiene una coordenada representativa mediante:

```text
Latitud promedio
Longitud promedio
```

El proceso puede representarse de la siguiente manera:

```text
Mediciones GPS
      ↓
Validación
      ↓
Latitudes y longitudes válidas
      ↓
Promedio
      ↓
Coordenada representativa
```

Esta coordenada se utiliza posteriormente como referencia para obtener la imagen satelital correspondiente.

![Imagen tabla](docs/tabla_promedio.png)

---

# Etapa 3 — Obtención de imágenes satelitales

Una vez determinada la coordenada promedio, el sistema utiliza la latitud y longitud para localizar la región correspondiente dentro del sistema de teselas de Esri.

Esta etapa se encuentra implementada en el módulo:

```text
esri.py
```

La fuente utilizada actualmente es:

```text
Esri World Imagery
```

mediante el servicio:

```text
ArcGIS World_Imagery
```

---

# ¿Qué es una tesela?

Los servicios de mapas dividen las imágenes del planeta en pequeñas imágenes cuadradas denominadas **teselas** (*tiles*).

Cada tesela utilizada por el sistema tiene:

```text
256 × 256 píxeles
```

y se identifica mediante tres parámetros:

```text
X → posición horizontal
Y → posición vertical
Z → nivel de zoom
```

El nivel de zoom determina el nivel de detalle de la imagen.

A mayor valor de `zoom`, mayor nivel de detalle y menor área geográfica representada por cada tesela.

Actualmente el valor predeterminado es:

```text
Zoom = 19
```

---

# Conversión de coordenadas GPS

Para determinar qué parte del mapa corresponde a la coordenada GPS promedio, el sistema transforma la posición geográfica utilizando la proyección **Web Mercator**.

El proceso es:

```text
Latitud / Longitud
        ↓
Web Mercator
        ↓
Píxel global
        ↓
Tesela X/Y
```

La función:

```python
latlon_a_pixel_global()
```

convierte la latitud y longitud en una posición dentro de la cuadrícula global de píxeles utilizada por el servicio de mapas.

Posteriormente, a partir de esos valores se determina la tesela que contiene la coordenada GPS.

---

# Generación del mosaico satelital

Una única tesela puede no proporcionar suficiente contexto alrededor de la posición GPS.

Por esta razón, con la configuración predeterminada se utiliza un radio de una tesela alrededor de la tesela central.

Esto produce un mosaico de:

```text
3 × 3 teselas
```

distribuidas de la siguiente manera:

```text
┌───────────┬───────────┬───────────┐
│ X-1,Y-1   │ X,Y-1     │ X+1,Y-1   │
├───────────┼───────────┼───────────┤
│ X-1,Y     │ X,Y       │ X+1,Y     │
├───────────┼───────────┼───────────┤
│ X-1,Y+1   │ X,Y+1     │ X+1,Y+1   │
└───────────┴───────────┴───────────┘
```

Como cada tesela posee:

```text
256 × 256 píxeles
```

el mosaico generado tiene:

```text
768 × 768 píxeles
```

El número de teselas puede modificarse mediante el parámetro:

```text
--radio-teselas
```

---

# Ubicación de la coordenada GPS dentro del mosaico

Además de obtener la imagen satelital, el sistema determina exactamente en qué posición del mosaico se encuentra la coordenada GPS promedio.

El procedimiento es:

```text
Coordenada GPS promedio
          ↓
Píxel global
          ↓
Origen del mosaico
          ↓
Píxel relativo dentro de la imagen
```

Como resultado se obtiene una posición:

```text
(x, y)
```

que representa el punto GPS dentro de la imagen satelital.

Esta posición funciona posteriormente como centro de referencia para el análisis de la vía (aunque, como se explica más adelante, no se asume que la calle esté centrada exactamente ahí).

---

# Resolución cartográfica

Para convertir las mediciones realizadas sobre la imagen desde píxeles hacia metros, el sistema calcula la resolución cartográfica local.

La función:

```python
resolucion_metros_por_pixel()
```

calcula aproximadamente cuántos metros representa cada píxel para una latitud y nivel de zoom determinados.

El resultado se expresa como:

```text
metros / píxel
```

Esta relación permite convertir posteriormente las distancias detectadas en la imagen a unidades reales.

---

# Marcador de posición

Para facilitar la comprobación visual, el sistema genera una copia del mosaico satelital con la posición GPS marcada.

El marcador está compuesto por:

* Un círculo.
* Una cruz.
* La posición correspondiente a la coordenada promedio.

La imagen original sin marcador también se conserva, ya que es utilizada durante el procesamiento de imagen para evitar que el marcador interfiera con la detección de bordes.

![Imagen satelital](docs/imagen_sat.png)

---

# Etapa 4 — Estimación del ancho de la calle

La estimación del ancho de la vía se encuentra implementada en el módulo:

```text
estimacion_ancho.py
```

Esta etapa utiliza la imagen satelital, la posición GPS y la resolución cartográfica obtenidas anteriormente.

El problema principal que resuelve esta etapa **no es solamente "encontrar dos bordes"**, sino **encontrar los dos bordes correctos**: en calles con acera de concreto junto al asfalto, ambas superficies son grises y de baja saturación, así que un filtro de color por sí solo no basta para diferenciarlas. Buena parte del diseño de este módulo existe específicamente para resolver esa ambigüedad sin necesitar un modelo entrenado.

El proceso general es:

```text
Imagen satelital
        ↓
Región de interés alrededor del GPS
        ↓
Máscara aproximada de asfalto (adaptativa por foto)
        ↓
Intensidad de referencia de la calle (tono real de asfalto)
        ↓
Detección de bordes (Canny) + segmentos (Hough)
        ↓
Estimación de orientación de la calle
        ↓
Selección de la PAREJA GLOBAL de bordes
        ↓
Reintento automático (ROI reducido) si la confianza es baja
        ↓
13 secciones transversales BLOQUEADAS a esa pareja
        ↓
Medición y conversión de píxeles a metros
        ↓
Filtrado de mediciones consistentes
        ↓
Ancho estimado + nivel de confianza
```

---

# Región de interés

El sistema utiliza una región circular alrededor del punto GPS para limitar la zona de análisis.

El tamaño de esta región se define mediante:

```text
--roi-metros
```

Por ejemplo:

```bash
--roi-metros 20
```

establece una región de interés de aproximadamente 20 metros alrededor de la posición GPS.

Este valor es el **punto de partida**, no necesariamente el que se usa al final: ver la sección "Reintento automático según confianza y tamaño de ROI".

---

# Máscara aproximada de asfalto

Antes de detectar los bordes se genera una máscara que intenta conservar las superficies visualmente compatibles con la vía. Para esto se analizan características relacionadas con:

* Saturación (`--saturacion-maxima`).
* Cromaticidad (canales a/b de Lab).
* Textura local (varianza de gris en una ventana pequeña, `--textura-maxima`).
* Brillo, con **dos límites**:
  * Un **techo adaptativo**: se calcula con el método de **Otsu** sobre los tonos de gris presentes en el ROI, en vez de usar un valor universal fijo. Esto evita que una foto sobre o sub-expuesta rompa el filtro.
  * Un **piso contra sombras**: sin este piso, sombras muy oscuras de árboles o edificios (que también son acromáticas y de textura lisa) pasarían el resto de los filtros. El piso se adapta un poco a cada foto, pero nunca baja de un mínimo absoluto.

También se utilizan operaciones morfológicas (cierre y apertura) para reducir pequeñas discontinuidades.

**Importante:** esta máscara es deliberadamente amplia. No distingue calle de acera — ambas suelen pasar el filtro, porque ambas son superficies grises de baja saturación. Su función es descartar vegetación, agua, techos de color, vehículos, etc., **no** resolver la ambigüedad calle/acera. Esa ambigüedad se resuelve más adelante, con señales específicas.

---

# Intensidad de referencia de la calle

En vez de asumir que el punto GPS está sobre la calle (podría estar sobre la acera midiendo hacia el otro lado), el sistema calcula una intensidad de referencia de "asfalto real" a partir de los propios datos de la imagen:

```text
Píxeles dentro de la máscara de asfalto (ROI)
                ↓
     Separación en dos tonos (Otsu)
                ↓
   Racimo MÁS OSCURO → referencia de asfalto
```

La razón: el concreto de una acera casi siempre es más claro que el asfalto de la calzada. Si no hay una separación clara entre dos tonos (por ejemplo, un ROI sin acera visible), el sistema usa la mediana completa como respaldo.

A partir de esa misma separación se calcula también una **tolerancia de gris**, que ya no es un número fijo: se ajusta según qué tan ruidoso es el propio asfalto de esa foto (su dispersión) y qué tan separado está del racimo claro. Si la separación es marcada, la tolerancia se endurece sola; si los tonos son parecidos, se relaja para no penalizar la calle real por variaciones normales de iluminación.

---

# Detección de bordes

Sobre la imagen procesada se utiliza:

```text
Canny Edge Detection
```

para detectar cambios significativos de intensidad que puedan corresponder a los límites de la vía.

Los umbrales utilizados por Canny pueden indicarse manualmente mediante:

```text
--canny-bajo
--canny-alto
```

Si no se proporcionan, el sistema determina automáticamente valores a partir de las características de intensidad de la imagen.

---

# Estimación de la orientación de la calle

Una vez detectados los bordes, se utiliza:

```text
HoughLinesP
```

para identificar segmentos de línea presentes en la imagen.

Los segmentos cercanos a la posición GPS son analizados para determinar la orientación predominante de la vía.

El proceso puede representarse como:

```text
Segmentos detectados
        ↓
Orientaciones
        ↓
Histograma angular
        ↓
Orientación dominante
```

Esta orientación representa aproximadamente la dirección longitudinal de la calle.

---

# Selección de la pareja global de bordes

Este es el núcleo del algoritmo. Con la orientación ya conocida, se proyectan todos los segmentos de Hough alineados con esa dirección sobre un sistema de coordenadas longitudinal/lateral (a lo largo y a lo ancho de la calle). Entre **todas las combinaciones posibles de dos segmentos**, se busca la pareja que mejor represente los dos bordes reales de la calle — no cualquier par de líneas paralelas, sino específicamente el que no sea, por ejemplo, un borde de calle emparejado con un borde de acera.

## Señales evaluadas por cada pareja candidata

| Señal | Qué mide | Por qué existe |
| --- | --- | --- |
| **Consistencia de ancho** | Qué tan estable es la distancia entre los dos segmentos a lo largo de todo su solapamiento | Un ancho que varía mucho sugiere que las líneas no son bordes paralelos reales de la misma vía |
| **Transición visual** | Diferencia de pertenencia a la máscara de asfalto justo adentro vs. justo afuera de cada borde | Un borde real de calle debería mostrar máscara adentro y no-máscara afuera |
| **Solapamiento relativo / continuidad** | Cuánto se superponen longitudinalmente los dos segmentos, y qué tan largos son | Bordes reales de calle corren paralelos por un tramo largo, no solo se cruzan en un punto |
| **Similitud de gris** | Qué tan cerca está el tono promedio de la franja interior del par respecto a la intensidad de referencia de la calle | Distingue asfalto de acera cuando ambos ya pasaron el filtro de color |
| **Consistencia de gris** | Dispersión del tono de gris a lo largo de la misma franja | Un promedio parecido a la calle puede esconder una franja que en realidad mezcla mitad calle, mitad acera; la dispersión alta delata esa mezcla |
| **Respaldo de doble línea (cordón)** | Si cada borde elegido tiene una segunda línea paralela muy cercana hacia su lado exterior (0.08–0.55 m) | El cordón + caño real casi siempre genera dos líneas de Canny pegadas; una grieta o cambio de tono aislado normalmente no |
| **Fuerza de borde interno** | Si existe alguna línea con buen soporte *entre* los dos bordes elegidos | Penaliza parejas que dejan "flotando" un borde más fuerte que el elegido, adentro del ancho escogido |
| **Distancia al punto GPS / distancia longitudinal** | Qué tan lejos queda el par del punto medido en campo | Favorece la calle donde realmente se hizo la medición, sin descartar por completo parejas algo alejadas |

Cada una de estas señales entra a una fórmula de puntaje ponderado; la pareja con mayor puntaje total, entre las que pasan un conjunto de filtros duros (ancho dentro de rango, solapamiento mínimo, cercanía razonable al GPS), es la que se usa para todo lo que sigue.

## Motivo de fallo y candidatos alternativos

Si ninguna combinación sobrevive los filtros duros, el sistema no inventa un resultado: registra **por qué** se rechazó cada combinación (`motivo_fallo_pareja`), por ejemplo:

```text
ancho_fuera_de_rango
solapamiento_insuficiente
lejos_del_gps
lejos_longitudinalmente
```

Esto permite diagnosticar la causa real de un fallo (ej. una intersección con muchas líneas pintadas, o un punto GPS tomado desde la acera) en vez de solo saber que "no se pudo estimar".

Cuando sí se encuentra una pareja, el sistema también guarda los **2 mejores candidatos que no ganaron** (`alternativas`), con el mismo desglose de señales — útil para revisar, ante un resultado dudoso, si el ganador le sacó ventaja clara al segundo lugar o si fue una decisión muy reñida.

---

# Reintento automático según confianza y tamaño de ROI

Un ROI grande (más contexto) puede sumar ruido de líneas ajenas a la calle (parqueos, cruces peatonales, plazas) y terminar promediando calle con acera. Un ROI chico reduce ese ruido, pero puede quedarse sin suficientes líneas para formar una pareja válida. No hay un tamaño único que funcione siempre.

Por eso, el sistema:

1. Corre primero con el `--roi-metros` indicado.
2. Si no se encontró pareja, **o** si se encontró pero con confianza por debajo de `--confianza-minima-reintento` (por defecto 0.45), reintenta **una vez** con un ROI reducido (60 % del original, con un piso de 8 m). No se descarga nada nuevo: es el mismo mosaico ya en memoria.
3. Entre los intentos que sí encontraron pareja, se conserva el de **mayor confianza** — no el que tenga más secciones válidas ni el ratio más alto de secciones válidas/candidatas, ya que un ROI muy chico puede lograr un ratio "perfecto" simplemente por no tener suficiente calle donde algo pueda salir mal. La métrica de confianza ya penaliza las muestras chicas (ver "Nivel de confianza").
4. Si dos intentos exitosos arrojan anchos que difieren en más de 1 metro, el resultado se marca con `roi_ambiguo: true` en vez de decidir en silencio — es una señal de que el algoritmo mismo está en desacuerdo consigo mismo según la ventana usada, y ese caso amerita revisión manual.

Todos los tamaños de ROI probados (con su ancho, confianza y cantidad de secciones) quedan documentados en `roi_candidatos` dentro del reporte.

---

# Secciones transversales bloqueadas a la pareja

Una vez fijada la pareja global de bordes, se buscan los bordes reales en 13 posiciones a lo largo de la calle, distribuidas entre aproximadamente:

```text
-6 m y +6 m
```

con respecto al punto GPS, medidos a lo largo de la dirección de la calle.

La diferencia clave respecto a una búsqueda de bordes independiente en cada corte es que aquí la búsqueda está **bloqueada**: en cada sección se busca el borde dentro de una ventana pequeña alrededor de la posición que predice la pareja global, en vez de aceptar cualquier línea fuerte cercana. Esto evita que una sección individual "salte" a una línea de acera, un auto estacionado o una junta de parqueo, incluso si esa línea es más marcada en Canny que el borde real en ese punto puntual.

El uso de múltiples secciones permite disminuir la dependencia de una única medición que podría verse afectada por:

* Vehículos.
* Sombras.
* Vegetación.
* Imperfecciones de la imagen.
* Bordes que no correspondan a la calle.

---

# Medición del ancho de la calle

En cada sección transversal se mide la distancia entre los dos bordes encontrados. La distancia detectada inicialmente se encuentra en píxeles y se convierte a metros mediante la resolución cartográfica calculada anteriormente:

```text
Distancia entre bordes en píxeles
                ×
         Metros por píxel
                ↓
          Ancho en metros
```

También se verifica que la medición se encuentre dentro del intervalo de ancho permitido. Por ejemplo:

```bash
--ancho-minimo-m 3
--ancho-maximo-m 10
```

---

# Filtrado de mediciones

No todas las mediciones transversales detectadas son utilizadas para obtener el resultado final.

El sistema busca grupos de mediciones cuyos valores de ancho sean similares (usando la mediana y la desviación absoluta respecto a ella) y descarta aquellas que sean inconsistentes.

Para generar una estimación final se requieren al menos:

```text
3 secciones transversales consistentes
```

Una vez seleccionadas las mediciones válidas, el ancho final se obtiene mediante:

```text
Mediana de los anchos válidos
```

El uso de la mediana permite reducir la influencia de valores atípicos.

---

# Nivel de confianza

Además del ancho estimado, el sistema calcula un valor de confianza asociado al resultado, compuesto por el producto de varios factores:

```text
Confianza
    =  Consistencia entre las mediciones válidas
    ×  Cobertura (cuántas secciones válidas hay, hasta un techo de 7)
    ×  Confianza de la orientación detectada
    ×  Calidad de la pareja global de bordes (su puntaje de selección)
```

Al ser un producto, un valor bajo en cualquiera de los cuatro factores baja la confianza total — por ejemplo, pocas secciones válidas (baja cobertura) penalizan el resultado aunque esas pocas secciones sean muy consistentes entre sí, evitando que una muestra chica parezca más confiable de lo que realmente es.

Actualmente el resultado puede clasificarse como:

```text
Alta
Media
Baja
Insuficiente
```

---

# Resultados generados

Al ejecutar el pipeline se genera la carpeta:

```text
resultados_seac/
```

que contiene diferentes etapas del procesamiento:

```text
01_imagen_satelital.png
02_imagen_con_gps.png
03_contraste_grises.png
04_mascara_asfalto.png
05_bordes_canny.png
06_secciones_transversales.png
reporte.json
```

### `01_imagen_satelital.png`

Mosaico original obtenido desde Esri.

### `02_imagen_con_gps.png`

Mosaico con la posición GPS promedio marcada.

### `03_contraste_grises.png`

Imagen en escala de grises (con CLAHE) utilizada durante el procesamiento, incluyendo el cálculo de intensidad de referencia de la calle.

### `04_mascara_asfalto.png`

Máscara aproximada de las regiones compatibles con la superficie de la vía (calle **y** acera; ver "Máscara aproximada de asfalto").

### `05_bordes_canny.png`

Bordes detectados mediante Canny, insumo para `HoughLinesP`.

### `06_secciones_transversales.png`

Resultado visual en el que se muestran los segmentos detectados (naranja), la orientación estimada (flecha magenta), la pareja global de bordes elegida (rojo/verde) y las 13 secciones bloqueadas (amarillo las válidas, gris las descartadas).

### `reporte.json`

Además de las mediciones GPS y la resolución cartográfica, incluye el diagnóstico completo de la detección:

| Campo | Contenido |
| --- | --- |
| `intensidad_calle_referencia` / `tolerancia_gris_usada` | Ver "Intensidad de referencia de la calle" |
| `pareja_global` | Todas las señales de la pareja ganadora (transición, similitud/consistencia de gris, respaldo de cordón, etc.) y sus `alternativas` (los 2 candidatos que no ganaron) |
| `motivo_fallo_pareja` | Desglose de por qué se rechazó cada combinación, cuando no se encontró pareja |
| `roi_metros_usado` / `roi_candidatos` / `roi_ambiguo` | Qué tamaño de ROI se usó al final, qué tamaños se probaron y si hubo desacuerdo entre ellos (ver "Reintento automático") |
| `cantidad_secciones_candidatas` / `cantidad_secciones_validas` | Ver "Filtrado de mediciones" |
| `confianza` / `nivel_confianza` | Ver "Nivel de confianza" |

---

# Arquitectura modular

El software se encuentra dividido en módulos independientes con responsabilidades específicas.

```text
mediciones_gps.txt
        │
        ▼
┌──────────────────┐
│      gps.py      │
│ Procesamiento GPS│
└────────┬─────────┘
         │
         │ Coordenada promedio
         ▼
┌──────────────────┐
│     esri.py      │
│ Imagen satelital │
└────────┬─────────┘
         │
         │ Mosaico + resolución
         ▼
┌────────────────────────┐
│ estimacion_ancho.py    │
│ Procesamiento de imagen│
│ y estimación del ancho │
└───────────┬────────────┘
            │
            ▼
       Ancho estimado
```

El archivo:

```text
seac_pipeline.py
```

actúa como coordinador del flujo general y utiliza las interfaces proporcionadas por cada módulo.

La estructura actual del software es:

```text
SEAC/
│
├── seac_pipeline.py
├── gps.py
├── esri.py
├── estimacion_ancho.py
├── mediciones_gps.txt
└── resultados_seac/
```

La separación en módulos permite modificar o sustituir un componente sin alterar la lógica interna de los demás, siempre que se mantenga la interfaz definida entre ellos.

Por ejemplo, el proveedor de imágenes satelitales podría ser sustituido por otro servicio manteniendo una interfaz equivalente para obtener el mosaico y su información asociada.

---

# Ejecución

El pipeline completo puede ejecutarse mediante:

```bash
py seac_pipeline.py mediciones_gps.txt
```

También es posible modificar diferentes parámetros del procesamiento. Por ejemplo:

```bash
py seac_pipeline.py mediciones_gps.txt --roi-metros 20 --ancho-maximo-m 10 --mostrar
```

## Parámetros disponibles

| Parámetro | Por defecto | Descripción |
| --- | --- | --- |
| `archivo` | `mediciones_gps.txt` | Archivo de texto con las mediciones GPS |
| `--zoom` | `19` | Nivel de zoom de las teselas de Esri |
| `--radio-teselas` | `1` | Radio de teselas alrededor de la tesela central (1 → mosaico 3×3) |
| `--salida` | `resultados_seac` | Carpeta donde se guardan las imágenes y el reporte |
| `--roi-metros` | `20.0` | Radio del ROI inicial alrededor del punto GPS |
| `--canny-bajo` / `--canny-alto` | Automático | Umbrales de Canny; si se omiten, se calculan a partir del contraste de la imagen |
| `--longitud-minima-m` | `4.0` | Longitud mínima (en metros) para que un segmento de Hough se considere |
| `--ancho-minimo-m` / `--ancho-maximo-m` | `3.0` / `12.0` | Rango de ancho de calle considerado válido |
| `--tolerancia-angulo` | `12.0` | Tolerancia angular (grados) para alinear segmentos con la orientación dominante |
| `--saturacion-maxima` | `90` | Saturación máxima admitida en la máscara de asfalto |
| `--textura-maxima` | `1000.0` | Varianza local máxima admitida en la máscara de asfalto |
| `--confianza-minima-reintento` | `0.45` | Umbral de confianza por debajo del cual se reintenta con un ROI reducido |
| `--mostrar` | `False` | Muestra visualmente el resultado final al terminar |

En el ejemplo anterior:

```text
--roi-metros 20
```

establece una región de interés de 20 metros alrededor de la posición GPS (punto de partida; ver "Reintento automático según confianza y tamaño de ROI").

```text
--ancho-maximo-m 10
```

establece en 10 metros el ancho máximo considerado durante la búsqueda de los límites de la vía.

```text
--mostrar
```

permite mostrar visualmente el resultado final del procesamiento.

---

# Tecnologías utilizadas

## Hardware

* Módulo GPS NEO-6M.
* Raspberry Pi 4.
* Cámara compatible CSI o USB para futuras etapas.

## Software

### Python

* Python 3.
* NumPy.
* OpenCV.
* Pillow.
* `urllib`.
* `math`.
* `argparse`.
* `json`.

### Procesamiento de imágenes

* Conversión de espacios de color (BGR, HSV, Lab).
* Filtrado bilateral.
* CLAHE.
* Umbral de Otsu (adaptativo, no solo binario global).
* Operaciones morfológicas.
* Canny Edge Detection.
* HoughLinesP.

### Datos geoespaciales

* Coordenadas GPS.
* Latitud.
* Longitud.
* HDOP.
* Número de satélites.
* Web Mercator.
* Teselas (*tiles*).
* Resolución cartográfica en metros por píxel.
* Imágenes satelitales.
* Esri World Imagery.
* ArcGIS REST API.

---

# Consideraciones actuales

La resolución calculada por el sistema corresponde a la escala cartográfica de Web Mercator para la latitud y el nivel de zoom utilizados.

Esta resolución no garantiza por sí sola la resolución espacial nativa ni la precisión posicional de la fotografía satelital.

Por esta razón, las estimaciones de ancho obtenidas deberán ser evaluadas posteriormente mediante su comparación con mediciones reales o valores de referencia.

## Limitaciones conocidas

En pruebas de campo, el sistema estima correctamente en aproximadamente el **90 % de las ubicaciones**. Los casos restantes se han rastreado, con evidencia del propio `reporte.json` (no solo sospecha), a causas identificables y no a fallas arbitrarias del algoritmo:

* **Punto GPS alejado del centro real de la calle** — si quien midió estaba parado en la acera, un camellón o el borde de una plaza en vez de en plena vía, ninguna pareja de bordes cae dentro de la distancia máxima admitida al GPS, sin importar el tamaño del ROI usado.
* **ROI con mucho ruido geométrico** — cruces, parqueos o zonas con muchas líneas pintadas (cruces peatonales, cajones) generan muchas combinaciones de segmentos con anchos y solapamientos que no corresponden a la calle real.
* **Calle y acera con tono de gris casi idéntico** — en algunas fotos, la máscara de asfalto no logra diferenciar entre ambas superficies (ver "Máscara aproximada de asfalto"); el desempate depende entonces de señales estructurales (respaldo de doble línea) o de gris relativo, que no siempre son suficientes por sí solas.

Estas causas quedan documentadas automáticamente en `motivo_fallo_pareja` y `roi_ambiguo` dentro del reporte, para que revisar un caso fallido no dependa de inspeccionar las imágenes a ojo desde cero.

Posibles extensiones evaluadas para reducir aún más este porcentaje, pendientes de justificarse con más casos de falla:

* Separar tonos con **k-means (k=3)** en vez de Otsu (k=2), para no confundir sombra dura con asfalto.
* Análisis de textura con **filtros de Gabor o GLCM**, para distinguir el patrón regular de baldosas/juntas de una acera del patrón continuo del asfalto.
* Un **canal invariante a sombra** antes de la escala de grises, para reducir bordes falsos generados por sombras duras de árboles o edificios.
* Segmentación semántica con un modelo entrenado, como techo de precisión a largo plazo — descartada por ahora porque implica un proyecto de otra naturaleza (dataset, entrenamiento, mantenimiento) en vez de una mejora incremental sobre las heurísticas actuales.

---

# Documentación de Esri

Consultar el [tutorial de múltiples capas](https://developers.arcgis.com/openlayers/maps/raster-tile-basemaps/display-multiple-basemap-layers/) para acceder a documentación relacionada con los mapas base de Esri.
---
