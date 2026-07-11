/**
 * Cobertura — la MESA DE REDACCIÓN de Noticias.
 *
 * Con una marca activa, la vista ÚNICA es la mesa de Candidatas: el pool segmentado por las
 * líneas del plan editorial diario (cupo + progreso + top candidatas por línea; última hora
 * en rojo y primero). El empujar/descartar de cada historia vive en su subpágina de detalle.
 * La salud de feeds se redujo a UNA línea condicional (el detalle vive en Fuentes). Con la
 * vista «Todas» (admin, sin marca) se degrada a la lista plana clásica con filtros y
 * selección múltiple.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Newspaper, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
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
import { Spinner } from "@/components/ui/spinner";
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
// La usa la vista «Todas» (admin, sin marca: filtros completos + selección múltiple +
// borrado hard).

interface PropsVistaHistorias {
  marcaActiva: string | null;
}

function VistaHistorias({ marcaActiva }: PropsVistaHistorias) {
  const [estado, setEstado] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  // Selección estilo correo (papelera): ids marcados para descartar/borrar en lote.
  const [seleccion, setSeleccion] = React.useState<Set<string>>(() => new Set());
  const queryClient = useQueryClient();

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

  const confirmarYBorrarSeleccion = async () => {
    const n = seleccion.size;
    if (
      !(await confirmar({
        titulo: "Borrar historias",
        mensaje: `¿Borrar definitivamente ${n} historia${n !== 1 ? "s" : ""} y sus artículos? No se puede deshacer.`,
        destructivo: true,
        textoConfirmar: "Borrar",
      }))
    )
      return;
    borrarLoteMut.mutate([...seleccion]);
  };

  const confirmarYVaciarPool = async () => {
    const ambito = marcaActiva ? "de esta marca" : "de TODAS las marcas";
    const filtro = estado ? ` en estado «${estado}»` : "";
    if (
      !(await confirmar({
        titulo: "Vaciar el pool",
        mensaje: `¿Borrar definitivamente TODAS las historias ${ambito}${filtro} y sus artículos? Deja el pool a 0 y no se puede deshacer.`,
        destructivo: true,
        textoConfirmar: "Vaciar",
      }))
    )
      return;
    borrarTodoMut.mutate();
  };

  return (
    <>
      {/* Filtros de la vista plana (admin, sin marca). */}
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <Select
          value={estado || "__todos__"}
          onValueChange={(v) => setEstado(v === "__todos__" ? "" : v)}
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
          </SelectContent>
        </Select>

        {/* Totales (la acción "Borrar todo" vive en el menú ⋮ de la página) */}
        <div className="ml-auto flex items-center gap-3 self-center">
          {query.data && (
            <span className="text-xs text-muted-foreground">
              {total.toLocaleString("es-MX")} historia{total !== 1 ? "s" : ""}
              {query.isFetching && !query.isPending && (
                <Spinner className="inline ml-1 h-3 w-3" />
              )}
            </span>
          )}
        </div>
      </div>

      {/* Barra de selección (papelera estilo correo). Aquí vive también «Borrar todo» (vaciar el
          pool, irreversible): es una acción EN LOTE de esta vista, junto a Descartar/Borrar la
          selección — ya no en un "⋮" propio de la barra superior (la cabecera la posee el "⋮"
          único de la página, con los Ajustes). */}
      {!query.isError && historias.length > 0 && (
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
                  onClick={() => setSeleccion(new Set())}
                  disabled={descartarLoteMut.isPending}
                >
                  Cancelar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1"
                  onClick={() => descartarLoteMut.mutate([...seleccion])}
                  disabled={descartarLoteMut.isPending || borrarLoteMut.isPending}
                  data-testid="btn-descartar-seleccion"
                >
                  {descartarLoteMut.isPending && <Spinner className="h-3 w-3" />}
                  Descartar {seleccion.size}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="gap-1 text-destructive hover:text-destructive"
                  onClick={confirmarYBorrarSeleccion}
                  disabled={borrarLoteMut.isPending || descartarLoteMut.isPending}
                  data-testid="btn-borrar-seleccion"
                >
                  {borrarLoteMut.isPending ? (
                    <Spinner className="h-3 w-3" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                  Borrar {seleccion.size}
                </Button>
              </>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="gap-1 text-destructive hover:text-destructive"
              onClick={confirmarYVaciarPool}
              disabled={borrarTodoMut.isPending}
              data-testid="btn-borrar-todo"
            >
              {borrarTodoMut.isPending ? (
                <Spinner className="h-3 w-3" />
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
            <EstadoVacio icono={Newspaper} titulo="Sin historias por ahora" />
          ) : (
            <div className="space-y-2">
              {historias.map((h) => (
                <TarjetaHistoria
                  key={h.id}
                  historia={h}
                  seleccionada={seleccion.has(h.id)}
                  onToggleSeleccion={(checked: boolean) => alternarUna(h.id, checked)}
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

export default function Cobertura() {
  const { marcaActiva, nombreActiva } = useMarcaActiva();

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

  // Con marca activa, la vista ÚNICA es la mesa de Candidatas.
  return (
    <>
      <AvisoSalud />
      <MesaNoticias marca={marcaActiva} nombre={nombreActiva} />
    </>
  );
}
