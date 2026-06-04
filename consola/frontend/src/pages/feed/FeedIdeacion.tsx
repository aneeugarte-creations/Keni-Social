/**
 * FEED DE IDEACIÓN (`/parrilla/feed`) — Flujo D, Fase 4 del plan de máquina automática.
 *
 * La superficie de "red social interna": el equipo ve las piezas como POSTS (copy de IA +
 * arte/formato), con un LABEL de su etapa en la tubería, y APRUEBA en línea —como quien
 * interactúa con un post— sin abrir el kanban.
 *
 * UN SOLO feed por fecha, con 3 PESTAÑAS que son VISTAS del mismo listado (no bandejas que
 * fragmenten el flujo ni hagan fetches distintos): se pide TODO una vez (`creado DESC`) y la
 * pestaña solo FILTRA en cliente qué se enseña —
 *   - "Todo el feed": todas las piezas, mezcladas y por fecha (la vista por defecto).
 *   - "Por aprobar": las que esperan tu OK (`estado = en_revision`).
 *   - "Publicado y programado": lo que ya salió o tiene hueco (`estado ∈ {publicado, programado}`).
 * Cada pieza enseña en qué va con su label de etapa, y el OK aparece en línea cuando te toca.
 *
 * Vive DENTRO del AppShell (a diferencia del feed móvil `/feed`, que es de una columna y sin
 * sidebar para revisores en el móvil). Aquí es una pestaña del hub Parrilla, pensada para
 * trabajar el día entero desde el feed.
 *
 * Reutiliza lo existente sin tocar backend:
 *  - `GET /api/publicaciones?marca=` (sin `estado`) para listar TODAS las piezas por fecha;
 *    las pestañas filtran ese único listado en memoria (sin más llamadas).
 *  - `PostFeed`: cada pieza como post + aprobación en línea (forwardea a la cadena multinivel)
 *    + comentarios (`Comentarios`).
 *  - El alta de material la implementa el Flujo A (acción de alta): este feed NO la duplica.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutGrid, Minus, Plus, RefreshCw } from "lucide-react";
import * as React from "react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";
import { FILTRO_TODOS } from "@/pages/publicaciones/Filtros";
import type { Publicacion } from "@/types";

import { PostFeed } from "./PostFeed";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema. Vuelve a intentarlo.";
}

// --- Tamaño y columnas del feed (preferencia local del usuario, por dispositivo) --- //
const COLUMNAS_MIN = 1;
const COLUMNAS_MAX = 3;
const ESCALA_MIN = 0.6;
const ESCALA_MAX = 1.4;
// Clases estáticas (Tailwind las detecta) por nº de columnas en pantallas anchas (lg+).
const GRID_LG: Record<number, string> = {
  1: "lg:grid-cols-1",
  2: "lg:grid-cols-2",
  3: "lg:grid-cols-3",
};

/** Lee una preferencia numérica de localStorage, acotada a [min, max]; `defecto` si falta/ inválida. */
function leerPref(clave: string, defecto: number, min: number, max: number): number {
  try {
    const v = Number(window.localStorage.getItem(clave));
    if (!Number.isFinite(v) || v <= 0) return defecto;
    return Math.min(max, Math.max(min, v));
  } catch {
    return defecto; // entornos sin localStorage (SSR/tests): usa el valor por defecto
  }
}

/** Guarda una preferencia en localStorage de forma tolerante (ignora entornos sin storage). */
function guardarPref(clave: string, valor: number): void {
  try {
    window.localStorage.setItem(clave, String(valor));
  } catch {
    /* sin localStorage: la preferencia simplemente no persiste */
  }
}

/**
 * Pestañas del feed: NO son bandejas (un fetch por estado), son VISTAS del mismo listado
 * único. `filtra` decide qué piezas se enseñan; `vacio` el mensaje cuando esa vista no tiene.
 */
type Vista = "todo" | "por_aprobar" | "publicado";

const VISTAS: {
  id: Vista;
  etiqueta: string;
  filtra: (p: Publicacion) => boolean;
  vacio: { titulo: string; texto: string };
}[] = [
  {
    id: "todo",
    etiqueta: "Todo el feed",
    filtra: () => true,
    vacio: {
      titulo: "El feed está vacío",
      texto:
        "El equipo postea material y la IA lo convierte en piezas; aparecerán aquí, las más recientes primero, y aprobarás en línea cuando alguna esté lista.",
    },
  },
  {
    id: "por_aprobar",
    etiqueta: "Por aprobar",
    filtra: (p) => p.estado === "en_revision",
    vacio: {
      titulo: "Nada por aprobar",
      texto: "Cuando la IA deje una pieza lista, aparecerá aquí para tu visto bueno (los 2 OK).",
    },
  },
  {
    id: "publicado",
    etiqueta: "Publicado y programado",
    filtra: (p) => p.estado === "publicado" || p.estado === "programado",
    vacio: {
      titulo: "Nada publicado ni programado",
      texto: "Las piezas que apruebes y tengan hueco en la parrilla saldrán aquí.",
    },
  },
];

export default function FeedIdeacion() {
  const queryClient = useQueryClient();
  // La marca la manda el switch global de la barra superior (deriva del perfil).
  // El feed se filtra implícitamente por la marca activa; no hay selector local.
  const { marcaActiva } = useMarcaActiva();

  const [vista, setVista] = React.useState<Vista>("todo");
  // Filtros propios del feed: Red + Línea editorial (la marca la fija el switch global).
  // Se aplican en SERVIDOR (van en la query); las pestañas siguen filtrando por estado en memoria.
  const [red, setRed] = React.useState(FILTRO_TODOS);
  const [linea, setLinea] = React.useState(FILTRO_TODOS);

  // Tamaño (escala) y nº de columnas de los posts en PC. Preferencia local, persistida.
  const [columnas, setColumnas] = React.useState(() =>
    leerPref("keni_feed_columnas", 2, COLUMNAS_MIN, COLUMNAS_MAX),
  );
  const [escala, setEscala] = React.useState(() =>
    leerPref("keni_feed_escala", 1, ESCALA_MIN, ESCALA_MAX),
  );
  React.useEffect(() => {
    guardarPref("keni_feed_columnas", columnas);
  }, [columnas]);
  React.useEffect(() => {
    guardarPref("keni_feed_escala", escala);
  }, [escala]);
  const ajustarEscala = (delta: number) =>
    setEscala((s) => Math.round(Math.min(ESCALA_MAX, Math.max(ESCALA_MIN, s + delta)) * 100) / 100);

  // Catálogo para los selects (redes + líneas editoriales).
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  // Líneas elegibles: las de la marca activa + las globales (marca === ""). Sin marca (todas)
  // se muestran todas. Si la línea filtrada deja de pertenecer a la marca activa, se resetea.
  const lineasElegibles = React.useMemo(
    () =>
      (opcionesQuery.data?.lineas ?? []).filter(
        (l) => l.marca === "" || marcaActiva == null || l.marca === marcaActiva,
      ),
    [opcionesQuery.data, marcaActiva],
  );
  React.useEffect(() => {
    if (linea !== FILTRO_TODOS && !lineasElegibles.some((l) => l.id === linea)) {
      setLinea(FILTRO_TODOS);
    }
  }, [lineasElegibles, linea]);

  // UN solo fetch por (marca, red, línea): TODAS las etapas mezcladas y ordenadas por fecha
  // (el backend devuelve `creado DESC` cuando no se filtra estado). Las pestañas filtran ese
  // listado en memoria (por estado), sin más llamadas.
  const feedQuery = useQuery({
    queryKey: [
      ...CLAVE_PUBLICACIONES,
      "feed-ideacion",
      marcaActiva ?? MARCA_ACTIVA_TODAS,
      red,
      linea,
    ],
    queryFn: ({ signal }) =>
      api.publicaciones(
        {
          marca: marcaActiva ?? undefined,
          red: red === FILTRO_TODOS ? undefined : red,
          linea: linea === FILTRO_TODOS ? undefined : linea,
        },
        signal,
      ),
  });

  // El backend ya acota por la marca activa (o devuelve todo en la vista "Todas" de admin).
  const piezas = React.useMemo(
    () => feedQuery.data?.publicaciones ?? [],
    [feedQuery.data],
  );

  // Conteo por pestaña (sobre el listado ya acotado por marca) para el badge de cada tab.
  const conteos = React.useMemo(
    () =>
      Object.fromEntries(VISTAS.map((v) => [v.id, piezas.filter(v.filtra).length])) as Record<
        Vista,
        number
      >,
    [piezas],
  );
  const vistaActual = VISTAS.find((v) => v.id === vista) ?? VISTAS[0];
  const piezasVista = React.useMemo(
    () => piezas.filter(vistaActual.filtra),
    [piezas, vistaActual],
  );

  const refrescar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });

  return (
    <div>
      <PageHeader
        titulo="Feed de ideación"
        descripcion="Una sola línea por fecha: la IA genera y verifica, tú das tu OK en línea, y la pieza sigue a programada y publicada."
        acciones={
          <Button
            variant="outline"
            size="sm"
            onClick={refrescar}
            disabled={feedQuery.isFetching}
          >
            <RefreshCw className={feedQuery.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
            Refrescar
          </Button>
        }
      />

      {/* Pestañas (formato tab, no bubble) + filtros. Las pestañas son VISTAS del MISMO feed
          (filtran por estado en cliente); Red y Línea filtran en servidor. La marca la fija el
          switch global de la topbar. En móvil las pestañas hacen wrap y los filtros se apilan. */}
      <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Tabs value={vista} onValueChange={(v) => setVista(v as Vista)}>
          <TabsList
            className="flex h-auto w-full flex-wrap justify-start gap-1 lg:w-auto"
            aria-label="Vista del feed"
          >
            {VISTAS.map((v) => (
              <TabsTrigger key={v.id} value={v.id} className="gap-1.5">
                {v.etiqueta}
                <span className="rounded-full bg-muted px-1.5 text-xs tabular-nums">
                  {conteos[v.id]}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <SelectorRed
            redes={opcionesQuery.data?.redes ?? []}
            valor={red}
            onCambio={setRed}
            ariaLabel="Filtrar por red"
            className="w-full sm:w-[160px]"
          />
          <Select value={linea} onValueChange={setLinea}>
            <SelectTrigger
              className="w-full sm:w-[200px]"
              aria-label="Filtrar por línea editorial"
            >
              <SelectValue placeholder="Línea editorial" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={FILTRO_TODOS}>Todas las líneas</SelectItem>
              {lineasElegibles.map((l) => (
                <SelectItem key={l.id} value={l.id}>
                  {l.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Control de TAMAÑO y COLUMNAS de los posts (solo PC): nº por fila + escala. Persiste. */}
          <div
            className="hidden items-center gap-1 rounded-md border border-input bg-background px-1.5 py-1 lg:flex"
            role="group"
            aria-label="Tamaño y columnas del feed"
          >
            <LayoutGrid className="mr-0.5 h-4 w-4 text-muted-foreground" aria-hidden="true" />
            {Array.from({ length: COLUMNAS_MAX }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setColumnas(n)}
                aria-pressed={columnas === n}
                title={`${n} ${n === 1 ? "post por fila" : "posts por fila"}`}
                className={cn(
                  "h-6 w-6 rounded text-xs tabular-nums transition-colors",
                  columnas === n
                    ? "bg-accent font-semibold text-foreground"
                    : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                {n}
              </button>
            ))}
            <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />
            <button
              type="button"
              onClick={() => ajustarEscala(-0.1)}
              disabled={escala <= ESCALA_MIN}
              title="Posts más pequeños"
              aria-label="Reducir tamaño"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent/50 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="w-9 text-center text-xs tabular-nums text-muted-foreground">
              {Math.round(escala * 100)}%
            </span>
            <button
              type="button"
              onClick={() => ajustarEscala(0.1)}
              disabled={escala >= ESCALA_MAX}
              title="Posts más grandes"
              aria-label="Aumentar tamaño"
              className="flex h-6 w-6 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent/50 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Feed: 1 columna = centrado (lectura cómoda); 2-3 = rejilla a lo ancho. `zoom` escala el
          tamaño de los posts. Ambas cosas las controla el usuario (arriba) y se persisten. */}
      <div
        className={cn(
          columnas === 1
            ? "mx-auto w-full max-w-2xl space-y-4"
            : cn("grid grid-cols-1 items-start gap-4", GRID_LG[columnas]),
        )}
        style={escala !== 1 ? { zoom: escala } : undefined}
      >
        {feedQuery.isLoading ? (
          [0, 1, 2].map((i) => <Skeleton key={i} className="h-80 w-full rounded-xl" />)
        ) : feedQuery.isError ? (
          <div className="col-span-full rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-center text-sm text-destructive">
            No se pudo cargar el feed. {mensajeError(feedQuery.error)}
          </div>
        ) : piezasVista.length === 0 ? (
          <div className="col-span-full">
            <EstadoVacio titulo={vistaActual.vacio.titulo} texto={vistaActual.vacio.texto} />
          </div>
        ) : (
          piezasVista.map((p) => <PostFeed key={p.id} publicacion={p} />)
        )}
      </div>
    </div>
  );
}
