/**
 * Globo terraqueo 3D del alcance de audiencia de una marca×red (estrategia digital).
 *
 * Pinta la distribucion geografica de la audiencia como torres extruidas desde cada ubicacion
 * (estilo Climate TRACE): a mas audiencia, mas alta y mas naranja la torre. La fuente la da
 * por CUENTA, asi que es una vista marca×red con selectores propios: Instagram trae pais y
 * ciudad; Facebook, el pais de los seguidores. El toggle «Ciudades» (solo IG) cambia la
 * GRANULARIDAD de pais a ciudad. Cada `clave` se resuelve a coordenadas con el modulo `./geo`;
 * las claves sin coordenada se OMITEN del globo pero se CUENTAN aparte (se dice cuantas «sin
 * ubicar» en vez de falsear el mapa). El globo real (MapLibre/WebGL) se carga de forma
 * diferida para no inflar el bundle; si la red no expone geografia se degrada con honestidad
 * en lugar de pintar un mundo vacio.
 */
import { useQuery } from "@tanstack/react-query";
import { Globe2 } from "lucide-react";
import * as React from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { nombreMarca, nombreRed, plural, porcentaje } from "@/lib/formato";
import type { MarcaDisponible, PuntoDistribucion } from "@/types";

import { centroideCiudad, centroidePais, type Centroide } from "./geo";
import type { PuntoGlobo } from "./globo/barras";
import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";

// Carga diferida del globo: MapLibre/WebGL solo se descarga y monta cuando esta seccion es
// visible y hay datos que situar; jsdom (tests) nunca llega a montarlo.
const MapaGlobo = React.lazy(() => import("./globo/MapaGlobo"));

/** Redes que exponen geografia de audiencia (IG: pais + ciudad; FB: pais de seguidores). */
const REDES_ALCANCE = ["instagram", "facebook"] as const;

/** Color de poca audiencia (ambar claro) y de mucha (naranja keni). */
const COLOR_BAJO: [number, number, number] = [0xfc, 0xd3, 0x4d];
const COLOR_ALTO: [number, number, number] = [0xea, 0x58, 0x0c];

/** Rampa de color por intensidad: ambar claro (poca audiencia) → naranja keni (mucha). */
function rampaColor(t: number): string {
  const c = Math.min(1, Math.max(0, t));
  const canal = (i: number) => Math.round(COLOR_BAJO[i] + (COLOR_ALTO[i] - COLOR_BAJO[i]) * c);
  return `rgb(${canal(0)}, ${canal(1)}, ${canal(2)})`;
}

/** Distribucion activa segun red + toggle de ciudades, con su nivel y nombre. */
function distribucionActiva(
  red: string,
  ciudades: boolean,
): { clave: string; nivel: "pais" | "ciudad" } {
  if (red === "instagram") {
    return ciudades ? { clave: "city", nivel: "ciudad" } : { clave: "country", nivel: "pais" };
  }
  return { clave: "page_follows_country", nivel: "pais" };
}

/** Resuelve una clave (codigo pais o nombre de ciudad) a coordenadas, o `undefined` si no se ubica. */
function resolver(clave: string, nivel: "pais" | "ciudad"): Centroide | undefined {
  return nivel === "ciudad" ? centroideCiudad(clave) : centroidePais(clave);
}

/** Mini-barra horizontal del top-N del panel (ancho = proporcion del maximo, color por intensidad). */
function FilaTop({ punto }: { punto: PuntoGlobo }) {
  return (
    <li className="flex items-center gap-2">
      <span className="w-28 shrink-0 truncate text-xs text-neutral-700" title={punto.etiqueta}>
        {punto.etiqueta}
      </span>
      <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-neutral-200">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${Math.max(4, punto.intensidad * 100)}%`,
            backgroundColor: rampaColor(punto.intensidad),
          }}
        />
      </span>
      <span className="w-12 shrink-0 text-right text-xs tabular-nums text-neutral-900">
        {porcentaje(punto.valor)}
      </span>
    </li>
  );
}

export function MapaAlcance({
  marcas,
  marcaActual = MARCA_TODAS,
}: {
  marcas: MarcaDisponible[];
  marcaActual?: string;
}) {
  // Selectores PROPIOS (el alcance es por cuenta, no agregable): marca concreta + red + toggle.
  // La marca arranca en la del foco global si es concreta; si no (o «Todas»), la primera.
  const marcaInicial = marcas.some((m) => m.id === marcaActual) ? marcaActual : marcas[0]?.id ?? "";
  const [marcaSel, setMarcaSel] = React.useState(marcaInicial);
  const [redSel, setRedSel] = React.useState<string>(REDES_ALCANCE[0]);
  const [ciudades, setCiudades] = React.useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "alcance-mundial", marcaSel, redSel],
    queryFn: ({ signal }) => api.metricasDemografia({ marca: marcaSel, red: redSel }, signal),
    enabled: Boolean(marcaSel && redSel),
    staleTime: 5 * 60_000,
  });

  // Solo Instagram tiene ciudades: el toggle solo aplica ahi (en FB se ignora con honestidad).
  const usaCiudades = redSel === "instagram" && ciudades;
  const { clave, nivel } = distribucionActiva(redSel, usaCiudades);

  // Resuelve cada clave a coordenadas; las no ubicadas se cuentan aparte (no se inventan).
  const { ubicados, sinUbicar, totalCrudos } = React.useMemo(() => {
    const crudos: PuntoDistribucion[] = data?.distribuciones?.[clave] ?? [];
    const maxValor = crudos.reduce((m, p) => Math.max(m, p.valor), 0);
    const out: PuntoGlobo[] = [];
    let sin = 0;
    for (const p of crudos) {
      const c = resolver(p.clave, nivel);
      if (!c) {
        sin += 1;
        continue;
      }
      out.push({
        lat: c.lat,
        lng: c.lng,
        valor: p.valor,
        etiqueta: c.nombre,
        nivel,
        intensidad: maxValor > 0 ? p.valor / maxValor : 0,
      });
    }
    out.sort((a, b) => b.valor - a.valor);
    return { ubicados: out, sinUbicar: sin, totalCrudos: crudos.length };
  }, [data, clave, nivel]);

  const top = ubicados[0];
  const nivelSingular = usaCiudades ? "ciudad" : "país";
  const nivelPlural = usaCiudades ? "ciudades" : "países";

  const selectores = (
    <div className="flex flex-wrap items-center gap-2">
      <Select value={marcaSel} onValueChange={setMarcaSel}>
        <SelectTrigger className="h-8 w-[160px] text-xs" aria-label="Marca">
          <SelectValue placeholder="Marca">{nombreMarca(marcaSel, marcas)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {marcas.map((m) => (
            <SelectItem key={m.id} value={m.id} className="text-xs">
              {m.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select value={redSel} onValueChange={setRedSel}>
        <SelectTrigger className="h-8 w-[130px] text-xs" aria-label="Red">
          <SelectValue placeholder="Red">{nombreRed(redSel)}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {REDES_ALCANCE.map((r) => (
            <SelectItem key={r} value={r} className="text-xs">
              {nombreRed(r)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <span className="flex items-center gap-1.5">
        <Switch
          id="alcance-ciudades"
          checked={usaCiudades}
          onCheckedChange={setCiudades}
          disabled={redSel !== "instagram"}
          aria-label="Mostrar ciudades"
        />
        <label
          htmlFor="alcance-ciudades"
          className="cursor-pointer text-xs text-muted-foreground"
          title={redSel === "instagram" ? undefined : "Solo Instagram expone ciudades"}
        >
          Ciudades
        </label>
      </span>
    </div>
  );

  let contenido: React.ReactNode;
  if (isPending) {
    contenido = <Skeleton className="h-[560px] w-full rounded-xl sm:h-[640px]" />;
  } else if (isError) {
    contenido = (
      <Card className="p-6">
        <p className="py-6 text-center text-sm text-muted-foreground">
          No se pudo cargar el alcance mundial.
        </p>
      </Card>
    );
  } else if (totalCrudos === 0) {
    contenido = (
      <Card className="p-6">
        <p className="py-6 text-center text-sm text-muted-foreground">
          {usaCiudades
            ? "Instagram no expone ciudades de audiencia para esta marca."
            : `${nombreRed(redSel)} no expone alcance geográfico para esta marca.`}
        </p>
      </Card>
    );
  } else {
    contenido = (
      <div className="relative h-[560px] w-full overflow-hidden rounded-xl bg-black sm:h-[640px]">
        {top ? (
          <React.Suspense
            fallback={
              <div className="absolute inset-0 grid place-items-center text-xs text-white/60">
                Cargando globo…
              </div>
            }
          >
            <MapaGlobo puntos={ubicados} centro={{ lat: top.lat, lng: top.lng }} />
          </React.Suspense>
        ) : (
          <div className="absolute inset-0 grid place-items-center px-6 text-center text-sm text-white/70">
            No se pudo situar ninguna ubicación en el mapa ({sinUbicar} sin ubicar).
          </div>
        )}

        {/* Panel flotante (abajo-izquierda): marca·red, dato lider, conteos y top-5. */}
        <div className="absolute bottom-4 left-4 z-10 w-64 rounded-xl bg-white/95 p-4 text-neutral-900 shadow-lg backdrop-blur">
          <p className="text-[11px] font-medium uppercase tracking-wide text-neutral-500">
            {nombreMarca(marcaSel, marcas)} · {nombreRed(redSel)}
          </p>
          {top ? (
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-2xl font-semibold tabular-nums">{porcentaje(top.valor)}</span>
              <span className="truncate text-xs text-neutral-500" title={top.etiqueta}>
                {top.etiqueta} · {nivelSingular} líder
              </span>
            </div>
          ) : null}
          <p className="mt-1 text-xs text-neutral-500">
            {plural(ubicados.length, nivelSingular, nivelPlural)} en el mapa
            {sinUbicar > 0 ? ` · ${sinUbicar} sin ubicar` : ""}
          </p>
          {ubicados.length > 0 ? (
            <ul className="mt-3 space-y-1.5">
              {ubicados.slice(0, 5).map((p) => (
                <FilaTop key={`${p.nivel}-${p.etiqueta}`} punto={p} />
              ))}
            </ul>
          ) : null}
        </div>

        {/* Leyenda (arriba-derecha): la rampa de color de intensidad de audiencia. */}
        <div className="absolute right-4 top-4 z-10 rounded-lg bg-white/95 px-3 py-2 text-[11px] text-neutral-700 shadow-lg backdrop-blur">
          <p className="mb-1 font-medium text-neutral-900">Audiencia</p>
          <div className="flex items-center gap-2">
            <span>Menos</span>
            <span
              className="h-2 w-20 rounded-full"
              style={{ background: `linear-gradient(to right, ${rampaColor(0)}, ${rampaColor(1)})` }}
            />
            <span>Más</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Seccion
      id="alcance-mundial"
      titulo="Alcance mundial"
      icono={Globe2}
      descripcion="Dónde está la audiencia de la cuenta: cada barra es un lugar y su altura/color mide el % de seguidores. La fuente la da por cuenta: elige marca y red. Instagram añade ciudades."
      acciones={selectores}
    >
      {contenido}
    </Seccion>
  );
}
