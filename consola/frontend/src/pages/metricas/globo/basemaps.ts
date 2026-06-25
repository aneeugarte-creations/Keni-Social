// Basemaps del globo de alcance: dos estilos raster gratuitos y sin token.
//
// "satelite" = imagenes ESRI World Imagery (ojo: orden de tesela {z}/{y}/{x}); "regular" =
// CARTO Voyager retina (@2x, dominios a-d). Ambos llevan dentro la proyeccion de globo, el
// cielo de espacio y el halo de atmosfera, asi que conmutar de formato con `setStyle`
// conserva el look espacial sin re-aplicar nada (solo hay que re-anadir la capa de barras,
// que es custom). El fondo negro evita destellos blancos mientras cargan las teselas.

import type { ProjectionSpecification, SkySpecification, StyleSpecification } from "maplibre-gl";

/** Proyeccion de globo: el planeta como esfera, no un mapa plano. */
const PROYECCION: ProjectionSpecification = { type: "globe" };

/** Cielo de espacio: negro azulado con un halo de atmosfera que se difumina al acercarse. */
const CIELO: SkySpecification = {
  "sky-color": "#0a0f1f",
  "horizon-color": "#22335f",
  "fog-color": "#0a0f1f",
  "sky-horizon-blend": 0.5,
  "horizon-fog-blend": 0.6,
  "fog-ground-blend": 0,
  "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.9, 4, 0.5, 7, 0],
};

/** Capa de fondo comun (espacio) detras de las teselas. */
const FONDO = {
  id: "fondo-espacio",
  type: "background" as const,
  paint: { "background-color": "#05070d" },
};

export type FormatoMapa = "satelite" | "regular";

/** ESRI World Imagery (satelite). Orden de tesela {z}/{y}/{x}; teselas de 256. */
export const ESTILO_SATELITE: StyleSpecification = {
  version: 8,
  projection: PROYECCION,
  sky: CIELO,
  sources: {
    satelite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [FONDO, { id: "satelite", type: "raster", source: "satelite" }],
};

/** CARTO Voyager retina (regular). @2x, dominios a-d; teselas de 512. */
export const ESTILO_REGULAR: StyleSpecification = {
  version: 8,
  projection: PROYECCION,
  sky: CIELO,
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 512,
      maxzoom: 20,
      attribution: "OpenStreetMap, CARTO",
    },
  },
  layers: [FONDO, { id: "carto", type: "raster", source: "carto" }],
};

export const ESTILOS: Record<FormatoMapa, StyleSpecification> = {
  satelite: ESTILO_SATELITE,
  regular: ESTILO_REGULAR,
};
