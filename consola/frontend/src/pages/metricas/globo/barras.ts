// Geometria de las barras 3D del globo de alcance.
//
// Cada ubicacion se convierte en un cuadrado pequeno (footprint en metros) que MapLibre
// extruye como una torre. El lado del pais es mayor que el de la ciudad; los metros se pasan
// a grados compensando la latitud (los meridianos se juntan hacia los polos) para que el
// cuadrado no se deforme. Las props viajan a la capa para la rampa de color, la altura y el
// tooltip. Sin dependencias de WebGL: solo datos y tipos GeoJSON.

import type { Feature, FeatureCollection, Polygon } from "geojson";

/** Una ubicacion resuelta a coordenadas, lista para el globo y el panel. */
export interface PuntoGlobo {
  lat: number;
  lng: number;
  /** Porcentaje de audiencia. */
  valor: number;
  /** Nombre legible (pais o ciudad). */
  etiqueta: string;
  nivel: "pais" | "ciudad";
  /** Intensidad normalizada [0,1] (valor / maximo del dataset). */
  intensidad: number;
}

/** Propiedades que cada barra lleva a la capa (color/altura por `intensidad`, tooltip por el resto). */
interface PropsBarra {
  intensidad: number;
  valor: number;
  etiqueta: string;
  nivel: "pais" | "ciudad";
}

const METROS_POR_GRADO = 111_320;
const LADO_PAIS_M = 95_000;
const LADO_CIUDAD_M = 38_000;

/** Cuadrado centrado en (lat,lng) de lado `ladoMetros`, con la longitud compensada por latitud. */
function huella(lat: number, lng: number, ladoMetros: number): Polygon["coordinates"] {
  const semiLat = ladoMetros / METROS_POR_GRADO / 2;
  const cos = Math.max(0.2, Math.cos((lat * Math.PI) / 180));
  const semiLng = ladoMetros / (METROS_POR_GRADO * cos) / 2;
  return [
    [
      [lng - semiLng, lat - semiLat],
      [lng + semiLng, lat - semiLat],
      [lng + semiLng, lat + semiLat],
      [lng - semiLng, lat + semiLat],
      [lng - semiLng, lat - semiLat],
    ],
  ];
}

/** Convierte los puntos en un FeatureCollection de cuadrados extruibles (uno por ubicacion). */
export function construirBarras(puntos: PuntoGlobo[]): FeatureCollection<Polygon, PropsBarra> {
  const features: Feature<Polygon, PropsBarra>[] = puntos.map((p) => ({
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: huella(p.lat, p.lng, p.nivel === "ciudad" ? LADO_CIUDAD_M : LADO_PAIS_M),
    },
    properties: {
      intensidad: p.intensidad,
      valor: p.valor,
      etiqueta: p.etiqueta,
      nivel: p.nivel,
    },
  }));
  return { type: "FeatureCollection", features };
}
