// Globo 3D real (MapLibre GL v5, proyeccion de globo) cargado de forma DIFERIDA.
//
// Este modulo es el unico que toca WebGL/MapLibre, por eso vive aparte y el padre lo monta
// con React.lazy: ni infla el bundle de Metricas ni se carga en jsdom (tests). Pinta las
// ubicaciones como torres extruidas (fill-extrusion nativo: cero deps nuevas) con altura y
// color por intensidad de audiencia (ambar -> naranja keni). El drag rota/mueve el globo y
// scroll/trackpad hacen zoom de forma nativa. Trae su selector de formato (satelite/regular)
// y los botones de zoom; el panel y la leyenda los pinta el padre por encima.

import { Check, Globe, Minus, Plus } from "lucide-react";
import type { GeoJSONSource, LayerSpecification } from "maplibre-gl";
import * as maplibregl from "maplibre-gl";
import * as React from "react";

import "maplibre-gl/dist/maplibre-gl.css";

import { porcentaje } from "@/lib/formato";

import { construirBarras, type PuntoGlobo } from "./barras";
import { ESTILOS, type FormatoMapa } from "./basemaps";

const FUENTE_BARRAS = "barras-alcance";
const CAPA_BARRAS = "barras-3d";

/** Capa de torres: color y altura por `intensidad`; rampa ambar -> naranja keni. */
const CAPA_TORRES: LayerSpecification = {
  id: CAPA_BARRAS,
  type: "fill-extrusion",
  source: FUENTE_BARRAS,
  paint: {
    "fill-extrusion-color": ["interpolate", ["linear"], ["get", "intensidad"], 0, "#fcd34d", 1, "#ea580c"],
    // Curva RAIZ: los valores medios/bajos también levantan torre visible (con la lineal solo
    // el máximo sobresalía y el resto quedaba achatado). Rango alto para drama tipo Climate TRACE.
    "fill-extrusion-height": ["interpolate", ["linear"], ["sqrt", ["get", "intensidad"]], 0, 130000, 1, 1100000],
    "fill-extrusion-base": 0,
    "fill-extrusion-opacity": 0.95,
  },
};

/** Anade (o actualiza) la fuente + capa de barras; se re-llama tras cada cambio de estilo. */
function sincronizarBarras(map: maplibregl.Map, puntos: PuntoGlobo[]): void {
  const datos = construirBarras(puntos);
  const fuente = map.getSource(FUENTE_BARRAS) as GeoJSONSource | undefined;
  if (fuente) {
    fuente.setData(datos);
    return;
  }
  map.addSource(FUENTE_BARRAS, { type: "geojson", data: datos });
  map.addLayer(CAPA_TORRES);
}

/** Tooltip al pasar por una torre: nombre + % de audiencia. Se registra una sola vez. */
function registrarTooltip(map: maplibregl.Map, popup: maplibregl.Popup): void {
  map.on("mousemove", CAPA_BARRAS, (e) => {
    const rasgo = e.features?.[0];
    if (!rasgo) return;
    map.getCanvas().style.cursor = "pointer";
    const props = rasgo.properties as { etiqueta?: string; valor?: number } | null;
    const etiqueta = String(props?.etiqueta ?? "");
    const valor = Number(props?.valor ?? 0);
    popup
      .setLngLat(e.lngLat)
      .setHTML(
        `<div style="background:#ffffff;color:#171717;padding:6px 10px;border-radius:8px;` +
          `font-size:12px;font-weight:500;box-shadow:0 2px 8px rgba(0,0,0,.25)">` +
          `${etiqueta} &middot; ${porcentaje(valor)}</div>`,
      )
      .addTo(map);
  });
  map.on("mouseleave", CAPA_BARRAS, () => {
    map.getCanvas().style.cursor = "";
    popup.remove();
  });
}

/** Miniatura de formato del popover: gradiente que evoca cada basemap + check si esta activo. */
function OpcionFormato({
  activo,
  etiqueta,
  clase,
  onClick,
}: {
  activo: boolean;
  etiqueta: string;
  clase: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={activo}
      className="flex w-full items-center gap-2 rounded-lg p-1.5 text-left transition-colors hover:bg-accent"
    >
      <span className={`h-9 w-12 shrink-0 rounded-md ring-1 ring-border ${clase}`} />
      <span className="text-xs font-medium text-neutral-800">{etiqueta}</span>
      {activo ? <Check className="ml-auto h-3.5 w-3.5 text-keni" aria-hidden="true" /> : null}
    </button>
  );
}

export default function MapaGlobo({
  puntos,
  centro,
  nivel,
}: {
  puntos: PuntoGlobo[];
  centro: { lat: number; lng: number };
  nivel: "pais" | "ciudad";
}) {
  const contenedorRef = React.useRef<HTMLDivElement | null>(null);
  const mapaRef = React.useRef<maplibregl.Map | null>(null);
  const popupRef = React.useRef<maplibregl.Popup | null>(null);
  const puntosRef = React.useRef(puntos);
  const centroRef = React.useRef(centro);

  const [formato, setFormato] = React.useState<FormatoMapa>("satelite");
  const [abierto, setAbierto] = React.useState(false);

  const formatoRef = React.useRef(formato);
  const formatoAplicadoRef = React.useRef(formato);

  puntosRef.current = puntos;
  formatoRef.current = formato;
  centroRef.current = centro;

  // Crea el mapa UNA vez: estilo satelite, centrado en la ubicacion lider, con halo de
  // espacio. El drag rota el globo y scroll/trackpad hacen zoom (nativo de MapLibre).
  React.useEffect(() => {
    const cont = contenedorRef.current;
    if (!cont) return;
    const map = new maplibregl.Map({
      container: cont,
      style: ESTILOS[formatoRef.current],
      center: [centroRef.current.lng, centroRef.current.lat],
      zoom: 2.5,
      pitch: 38,
      minZoom: 0.8,
      maxZoom: 16,
      attributionControl: { compact: true },
    });
    mapaRef.current = map;
    formatoAplicadoRef.current = formatoRef.current;
    // Planeta centrado HORIZONTALMENTE (sin padding lateral); solo un margen inferior para que
    // la ubicacion lider (la torre mas alta) quede algo por encima del centro y el panel
    // flotante de abajo-izquierda no la tape.
    map.setPadding({ top: 0, right: 0, bottom: 150, left: 0 });
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false });
    popupRef.current = popup;
    registrarTooltip(map, popup);
    map.on("load", () => sincronizarBarras(map, puntosRef.current));

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(cont);

    return () => {
      ro.disconnect();
      popup.remove();
      map.remove();
      mapaRef.current = null;
      popupRef.current = null;
    };
  }, []);

  // Al cambiar de granularidad (pais <-> ciudad) vuela a la region de la ubicacion lider: en
  // ciudad acerca a vista regional para ver el bosque denso de torres; en pais vuelve a la
  // panoramica del globo. No se dispara en el primer render (la camara inicial ya esta puesta).
  const nivelMontadoRef = React.useRef(true);
  React.useEffect(() => {
    const map = mapaRef.current;
    if (!map) return;
    if (nivelMontadoRef.current) {
      nivelMontadoRef.current = false;
      return;
    }
    map.flyTo({
      center: [centroRef.current.lng, centroRef.current.lat],
      zoom: nivel === "ciudad" ? 4.2 : 2.5,
      duration: 1400,
    });
  }, [nivel]);

  // Conmuta de basemap sin perder la camara: setStyle conserva el encuadre, la proyeccion y
  // el cielo (van en el propio estilo); solo hay que re-anadir las barras (capa custom).
  React.useEffect(() => {
    const map = mapaRef.current;
    if (!map || formato === formatoAplicadoRef.current) return;
    formatoAplicadoRef.current = formato;
    map.setStyle(ESTILOS[formato]);
    const reaplicar = () => sincronizarBarras(map, puntosRef.current);
    if (map.isStyleLoaded()) reaplicar();
    else map.once("styledata", reaplicar);
  }, [formato]);

  // Cambiar marca/red/granularidad reescribe los datos de las barras sin recolocar la camara.
  React.useEffect(() => {
    const map = mapaRef.current;
    if (!map || !map.isStyleLoaded()) return;
    sincronizarBarras(map, puntos);
  }, [puntos]);

  const elegir = (f: FormatoMapa) => {
    setFormato(f);
    setAbierto(false);
  };

  return (
    <div className="absolute inset-0">
      <div ref={contenedorRef} className="h-full w-full" />

      {/* Controles (abajo-derecha, estilo Climate TRACE): formato + zoom. */}
      <div className="absolute bottom-4 right-4 z-10 flex flex-col items-end gap-2">
        {abierto ? (
          <div className="w-44 rounded-xl border border-border bg-white/95 p-2 shadow-lg backdrop-blur">
            <p className="px-1.5 pb-1 text-[11px] font-medium uppercase tracking-wide text-neutral-500">
              Formato
            </p>
            <OpcionFormato
              activo={formato === "regular"}
              etiqueta="Regular"
              clase="bg-gradient-to-br from-neutral-100 to-neutral-300"
              onClick={() => elegir("regular")}
            />
            <OpcionFormato
              activo={formato === "satelite"}
              etiqueta="Satellite"
              clase="bg-gradient-to-br from-emerald-900 via-sky-900 to-slate-950"
              onClick={() => elegir("satelite")}
            />
          </div>
        ) : null}

        <div className="flex flex-col overflow-hidden rounded-lg border border-border bg-white/95 shadow-lg backdrop-blur">
          <button
            type="button"
            aria-label="Acercar"
            onClick={() => mapaRef.current?.zoomIn({ duration: 300 })}
            className="grid h-9 w-9 place-items-center text-neutral-700 transition-colors hover:bg-accent"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="h-px w-full bg-border" aria-hidden="true" />
          <button
            type="button"
            aria-label="Alejar"
            onClick={() => mapaRef.current?.zoomOut({ duration: 300 })}
            className="grid h-9 w-9 place-items-center text-neutral-700 transition-colors hover:bg-accent"
          >
            <Minus className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <button
          type="button"
          aria-label="Formato del mapa"
          aria-expanded={abierto}
          onClick={() => setAbierto((v) => !v)}
          className="grid h-9 w-9 place-items-center rounded-lg border border-border bg-white/95 text-neutral-700 shadow-lg backdrop-blur transition-colors hover:bg-accent"
        >
          <Globe className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
