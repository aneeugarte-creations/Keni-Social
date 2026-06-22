/**
 * Buscador de FOTOS DE STOCK: cuarta vía para dar imagen a una pieza, junto a Galería / Subir /
 * Generar IA. Propone fotos de APIs gratuitas (Pexels/Pixabay/Wikimedia/NASA/Openverse) o la foto
 * ORIGINAL del artículo de la fuente (RSS) como AYUDA VISUAL.
 *
 * Toda candidata se muestra ATENUADA + watermark "SIN LICENCIA": son referencias, no artes finales.
 * Al elegir una, se descarga y se adjunta a la pieza (`POST /api/artes/stock/adjuntar`), que la deja
 * `imagen_origen="stock"`, sin autorizar y con `falta_imagen` activo: visible pero NO publicable
 * hasta que un humano confirme derechos. El padre recibe la `PlataformaStock` para refrescar.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { ImageOff, Newspaper, Search } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { OverlaySinLicencia } from "@/components/media/OverlaySinLicencia";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { atribucionStock, nombreProveedor } from "@/lib/stock";
import { cn } from "@/lib/utils";
import type { CandidataStock, PlataformaStock } from "@/types";

export interface BuscadorStockProps {
  open: boolean;
  onCerrar: () => void;
  piezaId: string;
  /** URL original del artículo de la fuente (RSS): si la hay, se ofrece "Usar foto original". */
  imagenFuente?: string;
  /** Texto inicial de búsqueda: el TEMA de la pieza (su título), no el copy/titular largo. Opcional. */
  consultaInicial?: string;
  /** Tras adjuntar (candidata o fuente): la fila por plataforma actualizada, para refrescar. */
  onAdjuntada: (plataforma: PlataformaStock) => void;
}

export function BuscadorStock({
  open,
  onCerrar,
  piezaId,
  imagenFuente,
  consultaInicial = "",
  onAdjuntada,
}: BuscadorStockProps) {
  const [q, setQ] = React.useState(consultaInicial);
  const [qDebounced, setQDebounced] = React.useState(consultaInicial.trim());
  // Proveedor activo ("" = todos).
  const [proveedor, setProveedor] = React.useState("");

  // Al abrir, parte de la consulta inicial (el tema de la pieza) para una primera búsqueda útil.
  useEffect(() => {
    if (open) {
      setQ(consultaInicial);
      setQDebounced(consultaInicial.trim());
      setProveedor("");
    }
  }, [open, consultaInicial]);

  // Debounce de 350ms: cada API gratuita es lenta; no la golpeamos en cada tecla.
  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q.trim()), 350);
    return () => clearTimeout(t);
  }, [q]);

  const { data, isLoading, isFetching, isError, error } = useQuery({
    queryKey: ["stock", proveedor, qDebounced],
    queryFn: ({ signal }) =>
      api.buscarStock({ q: qDebounced || undefined, proveedor: proveedor || undefined }, signal),
    enabled: open,
  });

  const proveedores = data?.proveedores ?? [];
  const candidatos = data?.candidatos ?? [];

  // Adjuntar: descarga la candidata (o la foto original) y la deja como stock no autorizado.
  const adjuntar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.adjuntarStock>[0]) => api.adjuntarStock(cuerpo),
    onSuccess: (res) => {
      onAdjuntada(res.plataforma);
      toast.success("Foto adjuntada como referencia. Autorízala para poder publicarla.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const adjuntando = adjuntar.isPending;

  const elegir = (c: CandidataStock) =>
    adjuntar.mutate({
      pieza_id: piezaId,
      url: c.url,
      proveedor: c.proveedor,
      autor: c.autor,
      licencia: c.licencia,
      credito_url: c.credito_url,
    });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Buscar foto de stock</DialogTitle>
          <DialogDescription>
            Ayuda visual de bancos gratuitos. Toda foto entra SIN LICENCIA: autorízala (bajo tu
            responsabilidad) o sustitúyela antes de publicar.
          </DialogDescription>
        </DialogHeader>

        {imagenFuente && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            disabled={adjuntando}
            onClick={() => adjuntar.mutate({ pieza_id: piezaId, usar_fuente: true })}
          >
            {adjuntando ? <Spinner className="h-4 w-4" /> : <Newspaper className="h-4 w-4" />}
            Usar foto original de la fuente
          </Button>
        )}

        {/* Chips de proveedor: deshabilitados los no disponibles (su `motivo` va al tooltip). */}
        <div className="flex flex-wrap items-center gap-1.5">
          <ChipProveedor
            etiqueta="Todos"
            activo={proveedor === ""}
            disponible
            onClick={() => setProveedor("")}
          />
          {proveedores.map((p) => (
            <ChipProveedor
              key={p.proveedor}
              etiqueta={p.nombre || nombreProveedor(p.proveedor)}
              activo={proveedor === p.proveedor}
              disponible={p.disponible}
              motivo={p.motivo}
              onClick={() => p.disponible && setProveedor(p.proveedor)}
            />
          ))}
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar fotos… (ej. estadio fútbol)"
            className="h-9 rounded-lg border-transparent bg-muted/60 pl-8 placeholder:text-muted-foreground focus-visible:border-border"
            aria-label="Buscar fotos de stock"
          />
        </div>

        <div className="max-h-[55vh] min-h-[12rem] overflow-y-auto">
          {isLoading || (isFetching && candidatos.length === 0) ? (
            <div className="flex h-48 items-center justify-center text-muted-foreground">
              <Spinner className="h-5 w-5" />
            </div>
          ) : isError ? (
            <p className="flex h-48 items-center justify-center text-sm text-destructive">
              {mensajeError(error)}
            </p>
          ) : !qDebounced ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
              <Search className="h-6 w-6" />
              <p className="text-sm">Escribe qué foto buscas.</p>
            </div>
          ) : candidatos.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted-foreground">
              <ImageOff className="h-6 w-6" />
              <p className="text-sm">Sin resultados. Prueba otra búsqueda o proveedor.</p>
            </div>
          ) : (
            <div
              className={cn(
                "grid grid-cols-2 gap-3 sm:grid-cols-3",
                adjuntando && "pointer-events-none opacity-60",
              )}
            >
              {candidatos.map((c, i) => (
                <button
                  key={`${c.proveedor}-${c.url}-${i}`}
                  type="button"
                  disabled={adjuntando}
                  onClick={() => elegir(c)}
                  className="group block w-full overflow-hidden rounded-lg border border-border bg-muted/20 text-left transition-shadow hover:shadow-sm hover:ring-1 hover:ring-foreground/20"
                  title="Adjuntar como referencia (SIN LICENCIA)"
                >
                  <OverlaySinLicencia activo tamano="sm">
                    <img
                      src={c.thumb || c.url}
                      alt={c.titulo || "Foto de stock"}
                      loading="lazy"
                      className="aspect-square w-full object-cover"
                    />
                  </OverlaySinLicencia>
                  <span className="block truncate px-2 py-1 text-[11px] text-muted-foreground">
                    {atribucionStock({
                      autor: c.autor,
                      licencia: c.licencia,
                      proveedor: c.proveedor,
                    })}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Chip de proveedor: activo (resaltado), normal, o deshabilitado (con su motivo en tooltip). */
function ChipProveedor({
  etiqueta,
  activo,
  disponible,
  motivo,
  onClick,
}: {
  etiqueta: string;
  activo: boolean;
  disponible: boolean;
  motivo?: string;
  onClick: () => void;
}) {
  const chip = (
    <button
      type="button"
      aria-pressed={activo}
      disabled={!disponible}
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-full px-3 py-1 text-xs font-medium transition-colors",
        !disponible
          ? "cursor-not-allowed text-muted-foreground/50 line-through"
          : activo
            ? "bg-secondary text-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {etiqueta}
    </button>
  );
  return motivo && !disponible ? <Tooltip label={motivo}>{chip}</Tooltip> : chip;
}
