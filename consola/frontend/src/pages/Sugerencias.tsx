import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox, Lightbulb, Loader2, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/Markdown";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { formatearFecha as fmtFechaCdmx } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { Sugerencia } from "@/types";

const CLAVE_SUGERENCIAS = ["sugerencias"] as const;

const CABECERA = {
  titulo: "Feedback",
  descripcion:
    "Deja ideas y mejoras del producto. Se guardan en tu máquina; nada sale a la red.",
};

const CATEGORIA_LABEL: Record<string, string> = {
  idea: "Idea",
  producto: "Producto",
  mejora: "Mejora",
  bug: "Bug",
};

const ESTADO_LABEL: Record<string, string> = {
  nueva: "Nueva",
  "en-estudio": "En estudio",
  hecha: "Hecha",
  descartada: "Descartada",
};

type VarianteBadge = "secondary" | "aviso" | "ok" | "error" | "outline" | "destructive";

const ESTADO_VARIANTE: Record<string, VarianteBadge> = {
  nueva: "secondary",
  "en-estudio": "aviso",
  hecha: "ok",
  descartada: "error",
};

function etiqueta(mapa: Record<string, string>, clave: string): string {
  return mapa[clave] ?? clave;
}

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

// Fecha en CDMX (el instante "creada" del backend es UTC); ver `@/lib/fecha`.
const formatearFecha = (iso: string): string => fmtFechaCdmx(iso);

/**
 * Buzón de sugerencias: panel izquierdo para enviar una idea; panel derecho con
 * el listado, su estado (editable) y borrado. Todo local, vía /api/sugerencias.
 */
export default function Sugerencias() {
  const query = useQuery({
    queryKey: CLAVE_SUGERENCIAS,
    queryFn: ({ signal }) => api.sugerencias(signal),
  });

  const sugerencias = query.data?.sugerencias ?? [];
  const categorias = query.data?.categorias ?? Object.keys(CATEGORIA_LABEL);
  const estados = query.data?.estados ?? Object.keys(ESTADO_LABEL);

  return (
    <>
      <PageHeader {...CABECERA} />
      <div className="mt-6 grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevaSugerencia categorias={categorias} />
        <ListaSugerencias
          sugerencias={sugerencias}
          estados={estados}
          cargando={query.isPending}
          error={query.isError ? mensajeError(query.error) : null}
          onReintentar={() => void query.refetch()}
          reintentando={query.isFetching}
        />
      </div>
    </>
  );
}

// --- Alta (panel izquierdo) ------------------------------------------------

function NuevaSugerencia({ categorias }: { categorias: string[] }) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [detalle, setDetalle] = React.useState("");
  const [categoria, setCategoria] = React.useState(categorias[0] ?? "idea");
  const [autor, setAutor] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearSugerencia({
        titulo: titulo.trim(),
        detalle: detalle.trim() || undefined,
        categoria,
        autor: autor.trim() || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });
      toast.success("Sugerencia enviada. ¡Gracias!");
      setTitulo("");
      setDetalle("");
      setAutor("");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeEnviar = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb className="h-4 w-4" />
          Nueva sugerencia
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="sugerencia-titulo">Título</Label>
          <Input
            id="sugerencia-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ej. Exportar métricas a Slack"
            maxLength={200}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="sugerencia-detalle">
            Detalle <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="sugerencia-detalle"
            value={detalle}
            onChange={(e) => setDetalle(e.target.value)}
            placeholder="¿Qué problema resuelve? ¿Cómo lo imaginas? Admite Markdown."
            rows={5}
            maxLength={8000}
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="sugerencia-categoria">Categoría</Label>
            <Select value={categoria} onValueChange={setCategoria}>
              <SelectTrigger id="sugerencia-categoria">
                <SelectValue placeholder="Categoría" />
              </SelectTrigger>
              <SelectContent>
                {categorias.map((c) => (
                  <SelectItem key={c} value={c}>
                    {etiqueta(CATEGORIA_LABEL, c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sugerencia-autor">
              Tu nombre <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Input
              id="sugerencia-autor"
              value={autor}
              onChange={(e) => setAutor(e.target.value)}
              placeholder="Quién sugiere"
              maxLength={120}
            />
          </div>
        </div>
        <div className="flex justify-end">
          <Button onClick={() => crear.mutate()} disabled={!puedeEnviar}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Enviar sugerencia
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Listado (panel derecho) -----------------------------------------------

function ListaSugerencias({
  sugerencias,
  estados,
  cargando,
  error,
  onReintentar,
  reintentando,
}: {
  sugerencias: Sugerencia[];
  estados: string[];
  cargando: boolean;
  error: string | null;
  onReintentar: () => void;
  reintentando: boolean;
}) {
  if (cargando) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <BloqueError
        titulo="No se pudieron cargar las sugerencias"
        mensaje={error}
        onReintentar={onReintentar}
        cargando={reintentando}
      />
    );
  }

  if (sugerencias.length === 0) {
    return (
      <EstadoVacio
        icono={Inbox}
        titulo="El buzón está vacío"
        texto="Envía la primera sugerencia con el formulario de la izquierda."
      />
    );
  }

  return (
    <div className="space-y-3">
      {sugerencias.map((s) => (
        <TarjetaSugerencia key={s.id} sugerencia={s} estados={estados} />
      ))}
    </div>
  );
}

function TarjetaSugerencia({
  sugerencia,
  estados,
}: {
  sugerencia: Sugerencia;
  estados: string[];
}) {
  const queryClient = useQueryClient();

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });

  const cambiarEstado = useMutation({
    mutationFn: (estado: string) => api.actualizarSugerencia(sugerencia.id, { estado }),
    onSuccess: () => {
      invalidar();
      toast.success("Estado actualizado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarSugerencia(sugerencia.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Sugerencia borrada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const fecha = formatearFecha(sugerencia.creada);

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar la sugerencia “${sugerencia.titulo}”? Esta acción no se puede deshacer.`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          borrar.mutate();
      },
      destructivo: true,
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      acciones={acciones}
      etiquetaAcciones={`Acciones de “${sugerencia.titulo}”`}
      kebab="hover"
      className={cn(
        "rounded-lg border border-border bg-card text-card-foreground shadow-sm",
        sugerencia.estado === "descartada" && "opacity-60",
      )}
    >
      <div className="space-y-3 p-4 pr-10">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium leading-snug">{sugerencia.titulo}</span>
              <Badge variant="outline" className="font-normal">
                {etiqueta(CATEGORIA_LABEL, sugerencia.categoria)}
              </Badge>
              <Badge
                variant={ESTADO_VARIANTE[sugerencia.estado] ?? "secondary"}
                className="font-normal"
              >
                {etiqueta(ESTADO_LABEL, sugerencia.estado)}
              </Badge>
            </div>
            {(sugerencia.autor || fecha) && (
              <p className="text-xs text-muted-foreground">
                {[sugerencia.autor, fecha].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Select
              value={sugerencia.estado}
              onValueChange={(v) => cambiarEstado.mutate(v)}
              disabled={cambiarEstado.isPending}
            >
              <SelectTrigger className="h-8 w-[8.5rem]" aria-label="Cambiar estado">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {estados.map((e) => (
                  <SelectItem key={e} value={e}>
                    {etiqueta(ESTADO_LABEL, e)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {sugerencia.detalle && (
          <Markdown className="text-muted-foreground">{sugerencia.detalle}</Markdown>
        )}
      </div>
    </FilaConAcciones>
  );
}
