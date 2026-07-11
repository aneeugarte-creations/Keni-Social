/**
 * Tarjeta de detalle de una ubicacion del globo de «Alcance mundial» (estilo Climate TRACE).
 *
 * Aparece como overlay al elegir una barra del globo y resume ese lugar: cabecera con la
 * imagen SATELITAL real (tesela ESRI World Imagery calculada para sus coordenadas), su
 * ranking dentro del dataset, nombre, coordenadas, el tipo (ciudad/pais) y el DATO GRANDE:
 * el porcentaje de audiencia de la marca×red en ese lugar. Si la tesela no carga, deja el
 * fondo neutro sin romper la tarjeta.
 */
import { MapPin, X } from "lucide-react";
import * as React from "react";

import { porcentaje } from "@/lib/formato";

import type { PuntoGlobo } from "./globo/barras";

/** Tesela ESRI World Imagery (satelite) que cubre (lat,lng) a zoom 13. */
function teselaSatelital(lat: number, lng: number): string {
  const z = 13;
  const n = 2 ** z;
  const x = Math.floor(((lng + 180) / 360) * n);
  const y = Math.floor(((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * n);
  return `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}`;
}

export function TarjetaDetalleAlcance({
  punto,
  rank,
  total,
  marcaNombre,
  redNombre,
  onCerrar,
}: {
  punto: PuntoGlobo;
  rank: number;
  total: number;
  marcaNombre: string;
  redNombre: string;
  onCerrar: () => void;
}) {
  const [imagenFallo, setImagenFallo] = React.useState(false);

  const src = React.useMemo(() => teselaSatelital(punto.lat, punto.lng), [punto.lat, punto.lng]);
  const esCiudad = punto.nivel === "ciudad";
  const tipo = esCiudad ? "Ciudad" : "País";
  const plural = esCiudad ? "ciudades" : "países";
  const numero = (v: number) => v.toLocaleString("es-MX");

  return (
    <div className="w-[340px] overflow-hidden rounded-2xl bg-white text-neutral-900 shadow-xl">
      {/* Cabecera: imagen satelital del lugar, con ranking (izq.) y cerrar (der.) encima. */}
      <div className="relative h-32 w-full bg-neutral-200">
        {imagenFallo ? null : (
          <img
            src={src}
            alt={`Imagen satelital de ${punto.etiqueta}`}
            loading="lazy"
            onError={() => setImagenFallo(true)}
            className="absolute inset-0 h-full w-full object-cover"
          />
        )}
        <span className="absolute left-3 top-3 rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">
          N.º {numero(rank)} de {numero(total)} {plural}
        </span>
        <button
          type="button"
          onClick={onCerrar}
          aria-label="Cerrar"
          className="absolute right-3 top-3 grid h-7 w-7 place-items-center rounded-full bg-black/40 text-white transition-colors hover:bg-black/60"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Cuerpo: nombre, coordenadas, chip de tipo y el % de audiencia (acento naranja). */}
      <div className="space-y-3 p-4">
        <div>
          <h3 className="text-lg font-semibold leading-tight">{punto.etiqueta}</h3>
          <p className="mt-0.5 flex items-center gap-1 text-xs text-neutral-500">
            <MapPin className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="tabular-nums">
              {punto.lat.toFixed(3)}, {punto.lng.toFixed(3)}
            </span>
          </p>
        </div>

        <span className="inline-flex items-center rounded-md bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
          {tipo}
        </span>

        <div>
          <p className="text-4xl font-bold tabular-nums text-keni-600">{porcentaje(punto.valor)}</p>
          <p className="mt-1 text-xs text-neutral-500">
            de la audiencia de {marcaNombre} en {redNombre}
          </p>
        </div>
      </div>
    </div>
  );
}
