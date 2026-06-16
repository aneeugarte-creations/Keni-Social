/**
 * "Estrategia de marca": el espacio de trabajo editorial de una marca en la Biblioteca.
 *
 * No es una lista de ficheros: es el "quién somos" de la marca. Tres franjas:
 *   1. Cabecera de salud: anillo de completitud (X/4 pilares obligatorios) + recomendación.
 *   2. Los 5 pilares como tarjetas grandes (orden fijo: identidad → voz → tropicalización
 *      → plataformas → reglas), con estado visual claro (vacía / sin publicar / publicada),
 *      extracto del contenido y CTA "Definir ahora" cuando el pilar no tiene documento.
 *   3. "Cómo se ensambla para la IA": el orden REAL de inyección (adjuntos_copy) como
 *      cadena numerada de chips clicables. Debajo, el material de apoyo (extras).
 *
 * Datos: `GET /api/texto/estrategia?marca=` (backend NUEVO, en construcción en paralelo).
 * Si aún no responde, FALLBACK transparente desde `GET /api/texto` + `/validacion`
 * (misma forma normalizada; ver `datos.ts`). La apertura del documento completo
 * (versiones, publicación…) se DELEGA vía `onAbrirDoc`: este componente no navega.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Fingerprint,
  Layers,
  LayoutGrid,
  MapPin,
  MessageSquareText,
  MoveRight,
  Plus,
  Scale,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";

import { apiEstrategia, claveEstrategia } from "./api";
import { CLASES_PILAR, META_PILAR, desdeFallback, normalizar, type ClasePilar } from "./datos";
import type { EstrategiaNormalizada, PilarNormalizado } from "./tipos";

/** Icono por clase de pilar (extras sin clase: pergamino). */
const ICONO_PILAR: Record<string, LucideIcon> = {
  marca: Fingerprint,
  voz: MessageSquareText,
  tropicalizacion: MapPin,
  plataforma: LayoutGrid,
  reglas: Scale,
};

function iconoDe(clase: string): LucideIcon {
  return ICONO_PILAR[clase] ?? ScrollText;
}

// --------------------------------------------------------------------------- //
// Piezas visuales                                                             //
// --------------------------------------------------------------------------- //

/** Anillo de completitud: X/4 pilares obligatorios con contenido. SVG puro, sobrio. */
function AnilloCompletitud({
  cubiertos,
  total,
  completa,
}: {
  cubiertos: number;
  total: number;
  completa: boolean;
}) {
  const radio = 22;
  const circunferencia = 2 * Math.PI * radio;
  const fraccion = total > 0 ? Math.min(1, cubiertos / total) : 0;
  return (
    <div
      className="relative h-14 w-14 shrink-0"
      role="img"
      aria-label={`${cubiertos} de ${total} pilares obligatorios con contenido`}
    >
      <svg viewBox="0 0 56 56" className="h-14 w-14 -rotate-90">
        <circle
          cx="28"
          cy="28"
          r={radio}
          fill="none"
          strokeWidth="4"
          className="stroke-border"
        />
        <circle
          cx="28"
          cy="28"
          r={radio}
          fill="none"
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circunferencia}
          strokeDashoffset={circunferencia * (1 - fraccion)}
          className={cn(
            "transition-[stroke-dashoffset] duration-500",
            completa ? "stroke-emerald-500" : "stroke-amber-500",
          )}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xs font-semibold tabular-nums">
        {cubiertos}/{total}
      </span>
    </div>
  );
}

/** Badge de estado de publicación de la tarjeta (vacía / publicada / sin publicar). */
function EstadoPilar({ pilar }: { pilar: PilarNormalizado }) {
  if (pilar.vacio) {
    return (
      <span className="inline-flex items-center rounded-full border border-dashed border-border px-2 py-0.5 text-[11px] text-muted-foreground">
        vacía
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {pilar.publicado ? (
        <span
          className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300"
          title="Versión publicada: es la que sirven los pipelines"
        >
          <span aria-hidden>●</span> publicada
        </span>
      ) : (
        <span
          className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
          title="Sin versión publicada: los pipelines usan la copia de trabajo"
        >
          sin publicar aún
        </span>
      )}
      {pilar.sinPublicar ? (
        <span
          className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300"
          title="El borrador difiere de la versión publicada"
        >
          <AlertTriangle className="h-3 w-3" aria-hidden /> cambios sin publicar
        </span>
      ) : null}
    </span>
  );
}

/** Tarjeta GRANDE de un pilar: icono, estado, extracto y acciones. */
function TarjetaPilar({
  pilar,
  creando,
  onAbrir,
  onCrear,
}: {
  pilar: PilarNormalizado;
  /** `true` mientras se crea el documento de ESTE pilar. */
  creando: boolean;
  onAbrir: (docId: string) => void;
  onCrear: (clase: string) => void;
}) {
  const Icono = iconoDe(pilar.clase);
  const guia = META_PILAR[pilar.clase as ClasePilar]?.guia ?? "";
  const sinDocumento = pilar.docId === null;

  return (
    <article
      data-testid={`pilar-${pilar.clase}`}
      className={cn(
        "flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-sm transition-colors",
        pilar.vacio
          ? "border-dashed border-border bg-muted/20"
          : "border-border hover:border-keni/40",
      )}
    >
      <header className="flex items-start gap-3">
        <span
          className={cn(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
            pilar.vacio ? "bg-muted text-muted-foreground" : "bg-keni/10 text-keni",
          )}
          aria-hidden
        >
          <Icono className="h-[18px] w-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold leading-snug">{pilar.titulo}</h4>
          {pilar.global ? (
            <span
              className="mt-0.5 inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground"
              title="Capa global: la comparten todas las marcas"
            >
              global
            </span>
          ) : null}
        </div>
        <EstadoPilar pilar={pilar} />
      </header>

      {pilar.extracto ? (
        <p className="line-clamp-3 text-sm leading-relaxed text-foreground/80">
          {pilar.extracto}
        </p>
      ) : (
        <p className="text-sm italic leading-relaxed text-muted-foreground">{guia}</p>
      )}

      <footer className="mt-auto flex items-center gap-2 pt-1">
        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
          {pilar.actualizado
            ? `Actualizado ${tiempoRelativo(pilar.actualizado) || pilar.actualizado.slice(0, 10)}`
            : sinDocumento
              ? "Sin documento todavía"
              : ""}
        </span>
        {sinDocumento ? (
          <Button
            size="sm"
            variant="outline"
            className="border-dashed"
            disabled={creando}
            onClick={() => onCrear(pilar.clase)}
          >
            <Plus className="mr-1 h-3.5 w-3.5" aria-hidden />
            {creando ? "Creando…" : "Definir ahora"}
          </Button>
        ) : (
          <Button size="sm" variant="outline" onClick={() => onAbrir(pilar.docId as string)}>
            Abrir
          </Button>
        )}
      </footer>
    </article>
  );
}

/** Franja "Cómo se ensambla para la IA": cadena numerada del orden real de inyección. */
function FranjaEnsamblaje({
  orden,
  onAbrir,
}: {
  orden: { docId: string; etiqueta: string }[];
  onAbrir: (docId: string) => void;
}) {
  return (
    <section
      aria-label="Cómo se ensambla para la IA"
      className="rounded-lg border border-border bg-muted/20 p-4"
    >
      <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        <Layers className="h-3.5 w-3.5" aria-hidden /> Cómo se ensambla para la IA
      </h3>
      {orden.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Aún no hay capas activas que inyectar para esta marca.
        </p>
      ) : (
        <ol className="mt-3 flex flex-wrap items-center gap-y-2">
          {orden.map((o, i) => (
            <li key={o.docId} className="flex items-center">
              {i > 0 ? (
                <MoveRight className="mx-1.5 h-3.5 w-3.5 text-muted-foreground/50" aria-hidden />
              ) : null}
              <button
                type="button"
                onClick={() => onAbrir(o.docId)}
                className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-xs font-medium shadow-sm transition-colors hover:border-keni/40 hover:bg-muted/60"
                title={`${o.etiqueta} — abrir documento`}
              >
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-keni/10 text-[10px] font-semibold tabular-nums text-keni">
                  {i + 1}
                </span>
                {o.etiqueta}
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Tarjeta COMPACTA de material de apoyo (extras: patrones medidos, etc.). */
function TarjetaExtra({
  extra,
  onAbrir,
}: {
  extra: PilarNormalizado;
  onAbrir: (docId: string) => void;
}) {
  const Icono = iconoDe(extra.clase);
  return (
    <button
      type="button"
      onClick={() => extra.docId && onAbrir(extra.docId)}
      className="flex w-full items-center gap-2.5 rounded-md border border-border bg-card px-3 py-2 text-left shadow-sm transition-colors hover:border-keni/40 hover:bg-muted/40"
      title={`${extra.tituloDoc || extra.titulo} — abrir documento`}
    >
      <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">
          {extra.tituloDoc || extra.titulo}
        </span>
        {extra.extracto ? (
          <span className="block truncate text-xs text-muted-foreground">{extra.extracto}</span>
        ) : null}
      </span>
      {extra.sinPublicar ? (
        <AlertTriangle
          className="h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400"
          aria-label="Cambios sin publicar"
        />
      ) : null}
    </button>
  );
}

// --------------------------------------------------------------------------- //
// Componente raíz                                                             //
// --------------------------------------------------------------------------- //

export function EstrategiaMarca({
  marca,
  onAbrirDoc,
  className,
}: {
  /** Id de la marca (p. ej. "unotv"). */
  marca: string;
  /** Abre el documento completo en la vista detalle de la página (no navegamos aquí). */
  onAbrirDoc: (docId: string) => void;
  className?: string;
}) {
  const qc = useQueryClient();

  // ── Endpoint NUEVO; si falla (aún sin desplegar), fallback al listado clásico. ──
  const estrategiaQuery = useQuery({
    queryKey: claveEstrategia(marca),
    queryFn: ({ signal }) => apiEstrategia.estrategia(marca, signal),
    enabled: !!marca,
    retry: false,
  });
  const usarFallback = estrategiaQuery.isError;
  const docsQuery = useQuery({
    queryKey: ["texto-estrategia-fallback", marca],
    queryFn: ({ signal }) => api.texto({ marca, tipo: "editorial" }, signal),
    enabled: !!marca && usarFallback,
  });
  const validacionQuery = useQuery({
    queryKey: ["texto-validacion", marca],
    queryFn: ({ signal }) => api.validacionTexto(marca, signal),
    enabled: !!marca && usarFallback,
    retry: false,
  });

  // Nombre legible de la marca (catálogo cacheado; fallback: el propio id).
  const marcasQuery = useQuery({
    queryKey: ["texto-marcas"],
    queryFn: ({ signal }) => api.marcasTexto(signal),
    staleTime: 5 * 60_000,
  });
  const nombreMarca =
    (marcasQuery.data?.marcas ?? []).find((m) => m.id === marca)?.nombre ?? marca;

  const datos: EstrategiaNormalizada | null = React.useMemo(() => {
    if (estrategiaQuery.data) return normalizar(estrategiaQuery.data);
    if (usarFallback && docsQuery.data) {
      return desdeFallback(docsQuery.data.documentos, validacionQuery.data);
    }
    return null;
  }, [estrategiaQuery.data, usarFallback, docsQuery.data, validacionQuery.data]);

  // ── Crear el documento de un pilar que falta (CTA "Definir ahora"). ──
  const crearMut = useMutation({
    mutationFn: (clase: string) =>
      api.crearDocumento({
        titulo: `${META_PILAR[clase as ClasePilar]?.titulo ?? clase} · ${nombreMarca}`,
        tipo: "editorial",
        // Convención editorial: editorial/rrss/<marca>/<doc>.md (el id sale de tipo+carpeta+slug).
        carpeta: `rrss/${marca}`,
        clase,
        marcas: [marca],
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: claveEstrategia(marca) });
      qc.invalidateQueries({ queryKey: ["texto-estrategia-fallback", marca] });
      onAbrirDoc(r.documento.id);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // ── Sin marca: esta vista es por-marca. ──
  if (!marca) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        Elige una marca para ver su estrategia.
      </p>
    );
  }

  // ── Carga (endpoint nuevo o fallback en curso). ──
  const cargando =
    estrategiaQuery.isPending || (usarFallback && docsQuery.isPending);
  if (cargando) {
    return (
      <div className={cn("space-y-4", className)} data-testid="estrategia-cargando">
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {CLASES_PILAR.map((c) => (
            <Skeleton key={c} className="h-40 w-full" />
          ))}
        </div>
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  // ── Fallback también caído: degradar con un mensaje sobrio, sin romper la página. ──
  if (!datos) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        {mensajeError(docsQuery.error ?? estrategiaQuery.error)}
      </p>
    );
  }

  return (
    <div className={cn("space-y-5", className)}>
      {/* ───────── 1 · Cabecera de salud ───────── */}
      <header className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card p-4 shadow-sm">
        <AnilloCompletitud
          cubiertos={datos.cubiertos}
          total={datos.total}
          completa={datos.completa}
        />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Estrategia de marca
          </p>
          <h2 className="truncate text-lg font-semibold leading-tight">{nombreMarca}</h2>
          {!datos.completa && (
            <p className="mt-0.5 text-sm text-muted-foreground">
              {datos.recomendacion ||
                `Faltan ${datos.total - datos.cubiertos}/${datos.total} pilares por definir.`}
            </p>
          )}
        </div>
      </header>

      {/* ───────── 2 · Los 5 pilares ───────── */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {datos.pilares.map((p) => (
          <TarjetaPilar
            key={p.clase}
            pilar={p}
            creando={crearMut.isPending && crearMut.variables === p.clase}
            onAbrir={onAbrirDoc}
            onCrear={(clase) => crearMut.mutate(clase)}
          />
        ))}
      </div>

      {/* ───────── 3 · El orden real de inyección ───────── */}
      <FranjaEnsamblaje orden={datos.orden} onAbrir={onAbrirDoc} />

      {/* ───────── 4 · Material de apoyo (extras) ───────── */}
      {datos.extras.length > 0 ? (
        <section aria-label="Material de apoyo">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Material de apoyo
          </h3>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {datos.extras.map((e) => (
              <TarjetaExtra key={e.docId ?? e.titulo} extra={e} onAbrir={onAbrirDoc} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
