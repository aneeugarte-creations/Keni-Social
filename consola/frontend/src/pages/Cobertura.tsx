/**
 * Cobertura — la MESA DE REDACCIÓN de Noticias.
 *
 * Con una marca activa, la vista por defecto es la mesa: el pool segmentado por las líneas
 * del plan editorial diario (cupo + progreso + top candidatas por línea; última hora en
 * rojo y primero). Pestañas «En marcha» (promovidas hoy) y «Descartadas» (con deshacer)
 * completan el flujo. La salud de feeds se redujo a UNA línea condicional (el detalle vive
 * en Fuentes). Con la vista «Todas» (admin, sin marca) se degrada a la lista plana clásica
 * con filtros y selección múltiple.
 *
 * Contrato: docs/maquina-contenido/A-motor-ingesta.md
 *           docs/maquina-contenido/B-clustering-historias.md
 *           docs/maquina-contenido/D-cobertura-verificacion.md
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Newspaper, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { AvisoSalud } from "@/pages/noticias/AvisoSalud";
import { MesaNoticias } from "@/pages/noticias/MesaNoticias";
import { TarjetaHistoria } from "@/pages/noticias/TarjetaHistoria";

// ── Constantes ────────────────────────────────────────────────────────────────

/** Cada cuánto (ms) se refresca la lista automáticamente (sensación "live"). */
const REFETCH_INTERVAL_MS = 45_000;

/** Historias por página en la lista plana. */
const PAGE_SIZE = 30;

// ── Claves de React Query ─────────────────────────────────────────────────────

const CLAVE_HISTORIAS = (
  marcaActiva: string | null,
  estado: string,
  offset: number,
) => ["noticias", "historias", marcaActiva ?? "", estado, offset] as const;

// ── Vista: lista plana de historias ───────────────────────────────────────────
// La usan las pestañas «En marcha»/«Descartadas» (estado fijo) y la vista «Todas»
// (admin, sin marca: filtros completos + selección múltiple + borrado hard).

interface PropsVistaHistorias {
  marcaActiva: string | null;
  /** Estado FIJO de la vista (oculta el filtro): 'usado' | 'descartado'. */
  estadoFijo?: string;
}

function VistaHistorias({ marcaActiva, estadoFijo }: PropsVistaHistorias) {
  const [estadoLibre, setEstadoLibre] = React.useState("");
  const estado = estadoFijo ?? estadoLibre;
  const [offset, setOffset] = React.useState(0);
  // Selección estilo correo (papelera): ids marcados para descartar/borrar en lote.
  const [seleccion, setSeleccion] = React.useState<Set<string>>(() => new Set());
  const queryClient = useQueryClient();
  const conSeleccion = !estadoFijo; // la limpieza en lote es de la vista plana completa

  React.useEffect(() => {
    setOffset(0);
  }, [marcaActiva, estado]);

  // La selección NO debe sobrevivir a un cambio de marca/estado/página: mostraría otro conjunto
  // de historias y se descartarían ids que ya no se ven.
  React.useEffect(() => {
    setSeleccion(new Set());
  }, [marcaActiva, estado, offset]);

  const clave = CLAVE_HISTORIAS(marcaActiva, estado, offset);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.noticias.historias(
        {
          marca: marcaActiva ?? undefined,
          estado: estado || undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    staleTime: 20_000,
    refetchInterval: REFETCH_INTERVAL_MS,
  });

  const historias = query.data?.historias ?? [];
  const total = query.data?.total ?? 0;
  const hayMas = offset + PAGE_SIZE < total;
  const hayAnterior = offset > 0;

  // ── Selección estilo correo ─────────────────────────────────────────────
  const idsVisibles = historias.map((h) => h.id);
  const algunaSeleccion = seleccion.size > 0;
  const todasSeleccionadas =
    idsVisibles.length > 0 && idsVisibles.every((id) => seleccion.has(id));

  const alternarUna = (id: string, checked: boolean) =>
    setSeleccion((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });

  const alternarTodas = (checked: boolean) =>
    setSeleccion(checked ? new Set(idsVisibles) : new Set());

  const descartarLoteMut = useMutation({
    mutationFn: (ids: string[]) => api.noticias.descartarHistoriasLote(ids),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: clave });
      setSeleccion(new Set());
      const n = d.descartadas;
      toast.success(`${n} historia${n !== 1 ? "s" : ""} descartada${n !== 1 ? "s" : ""}.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // BORRAR HARD (irreversible): elimina el cluster Y sus artículos del archivo.
  const borrarLoteMut = useMutation({
    mutationFn: (ids: string[]) => api.noticias.borrarHistoriasLote(ids),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: clave });
      setSeleccion(new Set());
      const n = d.borradas;
      toast.success(`${n} historia${n !== 1 ? "s" : ""} borrada${n !== 1 ? "s" : ""}.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // "Dejar a 0": vacía el pool de la marca activa (respeta el filtro de estado).
  const borrarTodoMut = useMutation({
    mutationFn: () =>
      api.noticias.borrarTodasHistorias({
        marca: marcaActiva ?? undefined,
        estado: estado || undefined,
      }),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: clave });
      setSeleccion(new Set());
      const n = d.borradas;
      toast.success(`Pool vaciado: ${n} historia${n !== 1 ? "s" : ""} borrada${n !== 1 ? "s" : ""}.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const confirmarYBorrarSeleccion = () => {
    const n = seleccion.size;
    if (
      !window.confirm(
        `¿Borrar definitivamente ${n} historia${n !== 1 ? "s" : ""} y sus artículos? No se puede deshacer.`,
      )
    )
      return;
    borrarLoteMut.mutate([...seleccion]);
  };

  const confirmarYVaciarPool = () => {
    const ambito = marcaActiva ? "de esta marca" : "de TODAS las marcas";
    const filtro = estado ? ` en estado «${estado}»` : "";
    if (
      !window.confirm(
        `¿Borrar definitivamente TODAS las historias ${ambito}${filtro} y sus artículos? Deja el pool a 0 y no se puede deshacer.`,
      )
    )
      return;
    borrarTodoMut.mutate();
  };

  return (
    <>
      {/* Filtros (solo la vista plana completa; con estado fijo la pestaña ya lo dice) */}
      <div className="mb-5 flex flex-wrap items-end gap-3">
        {!estadoFijo && (
          <Select
            value={estado || "__todos__"}
            onValueChange={(v) => setEstadoLibre(v === "__todos__" ? "" : v)}
          >
            <SelectTrigger
              className="w-36"
              aria-label="Filtrar por estado"
              data-testid="filtro-estado-historias"
            >
              <SelectValue placeholder="Estado" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__todos__">Todos los estados</SelectItem>
              <SelectItem value="nuevo">Nuevo</SelectItem>
              <SelectItem value="usado">Usado</SelectItem>
              <SelectItem value="descartado">Descartado</SelectItem>
            </SelectContent>
          </Select>
        )}

        {/* Totales (la acción "Borrar todo" vive en el menú ⋮ de la página) */}
        <div className="ml-auto flex items-center gap-3 self-center">
          {query.data && (
            <span className="text-xs text-muted-foreground">
              {total.toLocaleString("es-MX")} historia{total !== 1 ? "s" : ""}
              {query.isFetching && !query.isPending && (
                <Loader2 className="inline ml-1 h-3 w-3 animate-spin" />
              )}
            </span>
          )}
        </div>
      </div>

      {/* Barra de selección (papelera estilo correo). Aquí vive también «Borrar todo» (vaciar el
          pool, irreversible): es una acción EN LOTE de esta vista, junto a Descartar/Borrar la
          selección — ya no en un "⋮" propio de la barra superior (la cabecera la posee el "⋮"
          único de la página, con los Ajustes). */}
      {conSeleccion && !query.isError && historias.length > 0 && (
        <div
          className="mb-3 flex items-center gap-3 rounded-md border bg-muted/30 px-3 py-2"
          data-testid="barra-seleccion-historias"
        >
          <Checkbox
            checked={todasSeleccionadas}
            onCheckedChange={alternarTodas}
            aria-label="Seleccionar todas las historias de esta página"
          />
          <span className="text-xs text-muted-foreground">
            {algunaSeleccion
              ? `${seleccion.size} seleccionada${seleccion.size !== 1 ? "s" : ""}`
              : "Seleccionar todo"}
          </span>
          <div className="ml-auto flex items-center gap-2">
            {algunaSeleccion && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => setSeleccion(new Set())}
                  disabled={descartarLoteMut.isPending}
                >
                  Cancelar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1 text-xs"
                  onClick={() => descartarLoteMut.mutate([...seleccion])}
                  disabled={descartarLoteMut.isPending || borrarLoteMut.isPending}
                  data-testid="btn-descartar-seleccion"
                >
                  {descartarLoteMut.isPending && <Loader2 className="h-3 w-3 animate-spin" />}
                  Descartar {seleccion.size}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1 text-xs border-destructive/50 text-destructive hover:text-destructive"
                  onClick={confirmarYBorrarSeleccion}
                  disabled={borrarLoteMut.isPending || descartarLoteMut.isPending}
                  data-testid="btn-borrar-seleccion"
                >
                  {borrarLoteMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                  Borrar {seleccion.size}
                </Button>
              </>
            )}
            <Button
              variant="outline"
              size="sm"
              className="h-7 gap-1 text-xs border-destructive/50 text-destructive hover:text-destructive"
              onClick={confirmarYVaciarPool}
              disabled={borrarTodoMut.isPending}
              data-testid="btn-borrar-todo"
            >
              {borrarTodoMut.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Trash2 className="h-3 w-3" />
              )}
              Borrar todo
            </Button>
          </div>
        </div>
      )}

      {/* Error */}
      {query.isError && (
        <BloqueError
          titulo="No se pudieron cargar las historias"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
        />
      )}

      {/* Esqueletos de carga */}
      {query.isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      )}

      {/* Lista */}
      {!query.isLoading && !query.isError && (
        <>
          {historias.length === 0 ? (
            <EstadoVacio
              icono={Newspaper}
              titulo={
                estadoFijo === "descartado"
                  ? "Nada descartado"
                  : estadoFijo === "usado"
                    ? "Nada en marcha todavía"
                    : "Sin historias por ahora"
              }
              texto={
                estadoFijo
                  ? "Lo que descartes o empujes desde Candidatas aparecerá aquí."
                  : "El motor de clustering agrupará las noticias conforme lleguen artículos corroborados de múltiples fuentes."
              }
            />
          ) : (
            <div className="space-y-2">
              {historias.map((h) => (
                <TarjetaHistoria
                  key={h.id}
                  historia={h}
                  clavesAInvalidar={[clave]}
                  conRestaurar={estadoFijo === "descartado"}
                  {...(conSeleccion
                    ? {
                        seleccionada: seleccion.has(h.id),
                        onToggleSeleccion: (checked: boolean) => alternarUna(h.id, checked),
                      }
                    : {})}
                />
              ))}
            </div>
          )}

          {/* Paginación */}
          {(hayAnterior || hayMas) && (
            <div className="mt-6 flex items-center justify-between gap-3">
              <Button
                variant="outline"
                size="sm"
                disabled={!hayAnterior}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                aria-label="Página anterior historias"
              >
                Anterior
              </Button>
              <span className="text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total.toLocaleString("es-MX")}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={!hayMas}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                aria-label="Página siguiente historias"
                data-testid="btn-siguiente-historias"
              >
                Siguiente
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

const VISTAS = [
  { id: "candidatas", etiqueta: "Candidatas" },
  { id: "en_marcha", etiqueta: "En marcha" },
  { id: "descartadas", etiqueta: "Descartadas" },
] as const;

type Vista = (typeof VISTAS)[number]["id"];

export default function Cobertura() {
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [vista, setVista] = React.useState<Vista>("candidatas");

  // Vista «Todas» (admin, sin marca concreta): el plan es por marca, así que la mesa no
  // aplica — lista plana clásica con filtros y limpieza en lote.
  if (!marcaActiva) {
    return (
      <>
        <AvisoSalud />
        <VistaHistorias marcaActiva={null} />
      </>
    );
  }

  return (
    <>
      <AvisoSalud />

      {/* Barra de ÁREAS del pool, PEGAJOSA arriba (Candidatas · En marcha · Descartadas): el
          trabajo real (la mesa/listas que renderiza la pestaña activa) es lo protagonista y las
          áreas quedan SIEMPRE a mano sin deslizar pasando el riel/chrome. Solo el área activa se
          monta debajo, así que no hay scroll largo para alcanzar otra. Mantiene el idiom de tabs
          ya presente (role=tablist + subrayado border-b-2 border-primary) y sus data-testids. */}
      <div
        className="sticky top-0 z-10 mb-4 flex gap-1 border-b bg-background"
        role="tablist"
        aria-label="Vista del pool"
      >
        {VISTAS.map((v) => (
          <button
            key={v.id}
            type="button"
            role="tab"
            aria-selected={vista === v.id}
            className={`px-3 py-1.5 text-sm transition-colors ${
              vista === v.id
                ? "border-b-2 border-primary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => setVista(v.id)}
            data-testid={`tab-${v.id}`}
          >
            {v.etiqueta}
          </button>
        ))}
      </div>

      {vista === "candidatas" && <MesaNoticias marca={marcaActiva} nombre={nombreActiva} />}
      {vista === "en_marcha" && (
        <VistaHistorias marcaActiva={marcaActiva} estadoFijo="usado" />
      )}
      {vista === "descartadas" && (
        <VistaHistorias marcaActiva={marcaActiva} estadoFijo="descartado" />
      )}
    </>
  );
}
