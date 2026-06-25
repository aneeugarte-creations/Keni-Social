/**
 * Buscador de FOTOS para dar imagen a una pieza, junto a Galería / Subir / Generar IA. Sirve a dos
 * fuentes según la prop `fuente`:
 *  - "stock" (def): fotos de APIs gratuitas (Pexels/Pixabay/Wikimedia/NASA/Openverse) o la foto
 *    ORIGINAL del artículo (RSS) como AYUDA VISUAL. Toda candidata se rotula "SIN LICENCIA": son
 *    referencias. Al adjuntarla (`POST /api/artes/stock/adjuntar`) queda `imagen_origen="stock"`,
 *    sin autorizar y con `falta_imagen` activo: visible pero NO publicable hasta confirmar derechos.
 *  - "agencias": fotos LICENCIADAS de agencia (AFP). Se muestran con su crédito y SIN overlay de
 *    "Sin licencia": al adjuntarlas (`POST /api/artes/agencias/adjuntar`) la pieza queda PUBLICABLE
 *    (`imagen_origen="licenciada"`, `imagen_autorizada=true`), arrastrando su crédito obligatorio.
 *  - "propio": fotos de la galería LOCAL del equipo (apps keni-fotos conectadas por el túnel; solo
 *    Claro Sports). Se muestran limpias y al elegirlas (`POST /api/artes/propio/adjuntar`, por
 *    `galeria_id`+`archivo`, no por URL) el back trae el original por el túnel y deja la pieza
 *    PUBLICABLE (`imagen_origen="propia"`). Si no hay dispositivos conectados, se avisa.
 *
 * El padre recibe la `PlataformaStock` para refrescar.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { ImageOff, Newspaper, Search } from "lucide-react";
import * as React from "react";
import { useEffect } from "react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
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
import type { CandidataStock, FuenteFoto, PlataformaStock } from "@/types";

export interface BuscadorStockProps {
  open: boolean;
  onCerrar: () => void;
  piezaId: string;
  /**
   * Fuente de la búsqueda. "stock" (def): bancos gratuitos, AYUDA VISUAL no publicable. "agencias":
   * fotos LICENCIADAS de agencia (AFP), publicables con crédito. "propio": galería local del equipo
   * (apps keni-fotos por el túnel; solo Claro Sports), publicable y adjuntada por el túnel.
   */
  fuente?: FuenteFoto;
  /** Marca de la pieza: acota las fuentes a las habilitadas para ella (toggles de la etapa Stock). */
  marca?: string;
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
  fuente = "stock",
  marca,
  imagenFuente,
  consultaInicial = "",
  onAdjuntada,
}: BuscadorStockProps) {
  const esStock = fuente === "stock";
  const esAgencias = fuente === "agencias";
  const esPropio = fuente === "propio";
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
    queryKey: [fuente, proveedor, qDebounced, marca ?? ""],
    queryFn: ({ signal }) => {
      if (esAgencias) return api.buscarAgencias({ q: qDebounced || undefined }, signal);
      if (esPropio)
        return api.buscarPropio({ q: qDebounced || undefined, marca: marca || undefined }, signal);
      return api.buscarStock(
        {
          q: qDebounced || undefined,
          proveedor: proveedor || undefined,
          marca: marca || undefined,
        },
        signal,
      );
    },
    enabled: open,
  });

  const proveedores = data?.proveedores ?? [];
  const candidatos = data?.candidatos ?? [];
  // Agencias/propio: el (único) proveedor sin credenciales/dispositivos trae el motivo a mostrar en
  // vez del grid (p. ej. «Sin dispositivos conectados»).
  const proveedorNoDisponible =
    (esAgencias || esPropio) && proveedores.length > 0 && !proveedores[0].disponible;

  // Adjuntar STOCK: descarga la candidata (o la foto original) y la deja como stock no autorizado.
  const adjuntar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.adjuntarStock>[0]) => api.adjuntarStock(cuerpo),
    onSuccess: (res) => {
      onAdjuntada(res.plataforma);
      toast.success("Foto adjuntada como referencia. Autorízala para poder publicarla.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  // Adjuntar LICENCIADA: descarga la candidata de agencia y deja la pieza publicable con crédito.
  const adjuntarLicenciada = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.adjuntarAgencia>[0]) => api.adjuntarAgencia(cuerpo),
    onSuccess: (res) => {
      onAdjuntada(res.plataforma);
      toast.success("Foto licenciada adjuntada. Publicable con su crédito obligatorio.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  // Adjuntar PROPIA: el back trae el original por el túnel, lo sube a keni-media y deja la pieza
  // publicable. Se identifica por galería + archivo (no por URL, que es una miniatura efímera).
  const adjuntarPropia = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.adjuntarPropio>[0]) => api.adjuntarPropio(cuerpo),
    onSuccess: (res) => {
      onAdjuntada(res.plataforma);
      toast.success("Foto propia adjuntada. Lista para publicar.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const adjuntando = adjuntar.isPending || adjuntarLicenciada.isPending || adjuntarPropia.isPending;

  const elegir = (c: CandidataStock) => {
    if (esPropio) {
      if (!c.galeria_id || !c.archivo) return;
      adjuntarPropia.mutate({
        pieza_id: piezaId,
        galeria_id: c.galeria_id,
        archivo: c.archivo,
        dispositivo: c.dispositivo,
      });
      return;
    }
    if (esAgencias) {
      adjuntarLicenciada.mutate({
        pieza_id: piezaId,
        url: c.url,
        proveedor: c.proveedor,
        autor: c.autor,
        licencia: c.licencia,
        credito_url: c.credito_url,
      });
      return;
    }
    adjuntar.mutate({
      pieza_id: piezaId,
      url: c.url,
      proveedor: c.proveedor,
      autor: c.autor,
      licencia: c.licencia,
      credito_url: c.credito_url,
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {esAgencias
              ? "Buscar foto de agencia (AFP)"
              : esPropio
                ? "Buscar foto propia"
                : "Buscar foto de stock"}
          </DialogTitle>
          <DialogDescription>
            {esAgencias
              ? "Fotos licenciadas de agencia, publicables con crédito obligatorio. Al adjuntar una, la pieza queda lista para publicar."
              : esPropio
                ? "Fotos de la galería local del equipo (apps keni-fotos conectadas). Al adjuntar una, la pieza queda lista para publicar."
                : "Ayuda visual de bancos gratuitos. Toda foto entra SIN LICENCIA: autorízala (bajo tu responsabilidad) o sustitúyela antes de publicar."}
          </DialogDescription>
        </DialogHeader>

        {esStock && imagenFuente && (
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

        {/* Chips de proveedor (solo stock): deshabilitados los no disponibles (su `motivo` va al
            tooltip). En agencias hay un único proveedor (AFP): su indisponibilidad se muestra como
            aviso, no como chip. */}
        {esStock && (
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
        )}

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
          ) : proveedorNoDisponible ? (
            <div className="flex h-48 items-center justify-center px-4">
              <Aviso>
                {proveedores[0].motivo ||
                  (esPropio
                    ? "Sin dispositivos conectados."
                    : "La agencia (AFP) no está disponible ahora mismo.")}
              </Aviso>
            </div>
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
                  title={
                    esAgencias
                      ? "Adjuntar foto licenciada (publicable con crédito)"
                      : esPropio
                        ? "Adjuntar foto propia (publicable)"
                        : "Adjuntar como referencia (SIN LICENCIA)"
                  }
                >
                  {!esStock ? (
                    // Foto publicable (agencia licenciada o propia): nítida, sin overlay "Sin licencia".
                    <img
                      src={c.thumb || c.url}
                      alt={c.titulo || (esPropio ? "Foto propia" : "Foto de agencia")}
                      loading="lazy"
                      className="aspect-square w-full object-cover"
                    />
                  ) : (
                    <OverlaySinLicencia
                      activo
                      tamano="sm"
                      proveedor={c.proveedor}
                      licencia={c.licencia}
                    >
                      <img
                        src={c.thumb || c.url}
                        alt={c.titulo || "Foto de stock"}
                        loading="lazy"
                        className="aspect-square w-full object-cover"
                      />
                    </OverlaySinLicencia>
                  )}
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
