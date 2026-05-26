import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bot,
  Inbox,
  Lightbulb,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Tooltip } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  AuditoriaAutodesarrollo,
  CuerpoFlagAutodesarrollo,
  EstadoAutodesarrollo,
  Sugerencia,
} from "@/types";

const CLAVE_SUGERENCIAS = ["sugerencias"] as const;
const CLAVE_AUTODESARROLLO = ["autodesarrollo"] as const;

const CABECERA = {
  titulo: "Buzón de sugerencias",
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

// Etiquetas y variante del estado de un intento de AUTO-DESARROLLO (#109).
const AUTODES_ESTADO_LABEL: Record<string, string> = {
  bloqueada: "Bloqueada",
  rechazada: "Rechazada",
  parked: "Necesita revisión",
  mergeada: "Mergeada",
  error: "Error",
};

const AUTODES_ESTADO_VARIANTE: Record<string, VarianteBadge> = {
  bloqueada: "secondary",
  rechazada: "destructive",
  parked: "aviso",
  mergeada: "ok",
  error: "error",
};

const AUTODES_MOTIVO_LABEL: Record<string, string> = {
  "flag-off": "El lazo estaba desactivado",
  "rutas-sensibles": "Tocó rutas sensibles (rechazado por alcance)",
  "supera-cap": "El cambio supera el límite de tamaño",
  "sin-cambios": "No produjo cambios",
  "ci-roja": "La CI no pasó en verde",
  "generacion-fallida": "El asistente falló al implementar",
  "merge-fallido": "No se pudo hacer fast-forward a main",
  excepcion: "Error inesperado",
};

function etiqueta(mapa: Record<string, string>, clave: string): string {
  return mapa[clave] ?? clave;
}

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function formatearFecha(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Buzón de sugerencias: panel izquierdo para enviar una idea; panel derecho con
 * el listado, su estado (editable) y borrado. Todo local, vía /api/sugerencias.
 */
export default function Sugerencias() {
  const query = useQuery({
    queryKey: CLAVE_SUGERENCIAS,
    queryFn: ({ signal }) => api.sugerencias(signal),
  });

  const autodes = useQuery({
    queryKey: CLAVE_AUTODESARROLLO,
    queryFn: ({ signal }) => api.autodesarrollo(signal),
  });

  const sugerencias = query.data?.sugerencias ?? [];
  const categorias = query.data?.categorias ?? Object.keys(CATEGORIA_LABEL);
  const estados = query.data?.estados ?? Object.keys(ESTADO_LABEL);
  const autoActivo = autodes.data?.activo ?? false;

  // Último intento de auto-desarrollo por sugerencia (para mostrar su estado en la tarjeta).
  const auditoriaPorSugerencia = React.useMemo(() => {
    const mapa = new Map<string, AuditoriaAutodesarrollo>();
    for (const entrada of autodes.data?.auditoria ?? []) {
      // La auditoría viene reciente primero: el primero por id es el más nuevo.
      if (!mapa.has(entrada.sugerencia_id)) mapa.set(entrada.sugerencia_id, entrada);
    }
    return mapa;
  }, [autodes.data?.auditoria]);

  return (
    <>
      <PageHeader {...CABECERA} />
      <PanelAutodesarrollo estado={autodes.data} cargando={autodes.isPending} />
      <div className="mt-6 grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevaSugerencia categorias={categorias} />
        <ListaSugerencias
          sugerencias={sugerencias}
          estados={estados}
          autoActivo={autoActivo}
          auditoriaPorSugerencia={auditoriaPorSugerencia}
          cargando={query.isPending}
          error={query.isError ? mensajeError(query.error) : null}
          onReintentar={() => void query.refetch()}
          reintentando={query.isFetching}
        />
      </div>
    </>
  );
}

// --- Auto-desarrollo (#109): flag peligroso + auditoría --------------------

function PanelAutodesarrollo({
  estado,
  cargando,
}: {
  estado: EstadoAutodesarrollo | undefined;
  cargando: boolean;
}) {
  const queryClient = useQueryClient();
  const [confirmaAbierto, setConfirmaAbierto] = React.useState(false);
  const [riesgoMarcado, setRiesgoMarcado] = React.useState(false);

  const cambiarFlag = useMutation({
    mutationFn: (cuerpo: CuerpoFlagAutodesarrollo) => api.flagAutodesarrollo(cuerpo),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AUTODESARROLLO });
      toast.success(res.mensaje ?? "Listo");
      setConfirmaAbierto(false);
      setRiesgoMarcado(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (cargando || !estado) {
    return <Skeleton className="h-24 w-full rounded-md" />;
  }

  const activo = estado.activo;
  const fijadoPorEntorno = estado.fijado_por_entorno;

  return (
    <Card
      className={cn(
        "border-l-4",
        activo ? "border-l-amber-500" : "border-l-muted-foreground/30",
      )}
    >
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bot className="h-4 w-4" />
          Auto-desarrollo
          <Badge variant={activo ? "aviso" : "secondary"} className="font-normal">
            {activo ? "Activado" : "Desactivado"}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <p className="flex items-start gap-2 font-medium text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            Función peligrosa. Cuando está activada, la app puede implementar una
            sugerencia con IA y mergearla a <code>main</code> ella sola.
          </p>
          <p className="mt-2 text-muted-foreground">
            Cada intento corre aislado en un worktree efímero, solo mergea si la CI local
            pasa en verde, rechaza cambios a rutas sensibles o que superen{" "}
            {estado.cap_lineas} líneas, no recibe secretos, y queda registrado en la
            auditoría. Aun así, revisa lo que se mergea. Por defecto está apagado.
          </p>
        </div>

        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {fijadoPorEntorno
              ? "Fijado por la variable de entorno KENI_AUTODESARROLLO (no se puede cambiar desde aquí)."
              : activo
                ? "El lazo está activo. Usa «Implementar» en una sugerencia para lanzarlo."
                : "Actívalo solo cuando quieras que la app implemente sugerencias sola."}
          </p>
          {activo ? (
            <Button
              variant="outline"
              disabled={fijadoPorEntorno || cambiarFlag.isPending}
              onClick={() => cambiarFlag.mutate({ activo: false })}
            >
              {cambiarFlag.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Desactivar
            </Button>
          ) : (
            <Button
              variant="destructive"
              disabled={fijadoPorEntorno}
              onClick={() => setConfirmaAbierto(true)}
            >
              Activar
            </Button>
          )}
        </div>

        {estado.auditoria.length > 0 && (
          <Auditoria entradas={estado.auditoria} />
        )}
      </CardContent>

      <Dialog open={confirmaAbierto} onOpenChange={setConfirmaAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              Activar auto-desarrollo
            </DialogTitle>
            <DialogDescription>
              Vas a permitir que la app implemente sugerencias con IA y las mergee a{" "}
              <code>main</code> automáticamente. Hay gates de seguridad (sandbox, CI verde,
              límites de alcance, sin secretos, auditoría), pero el riesgo residual existe:
              revisa siempre lo que se mergea y desactívalo al terminar.
            </DialogDescription>
          </DialogHeader>
          <label className="flex items-start gap-2 text-sm">
            <Checkbox
              checked={riesgoMarcado}
              onCheckedChange={(v) => setRiesgoMarcado(v === true)}
              className="mt-0.5"
            />
            <span>Entiendo el riesgo y quiero activar el auto-desarrollo.</span>
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmaAbierto(false)}>
              Cancelar
            </Button>
            <Button
              variant="destructive"
              disabled={!riesgoMarcado || cambiarFlag.isPending}
              onClick={() => cambiarFlag.mutate({ activo: true, confirmo_riesgo: true })}
            >
              {cambiarFlag.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              Activar de todos modos
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Auditoria({ entradas }: { entradas: AuditoriaAutodesarrollo[] }) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">Auditoría reciente</p>
      <ul className="space-y-1 text-sm">
        {entradas.slice(0, 8).map((e) => (
          <li key={e.id} className="flex flex-wrap items-center gap-2">
            <Badge
              variant={AUTODES_ESTADO_VARIANTE[e.estado] ?? "secondary"}
              className="font-normal"
            >
              {AUTODES_ESTADO_LABEL[e.estado] ?? e.estado}
            </Badge>
            <span className="min-w-0 truncate">{e.titulo || e.sugerencia_id}</span>
            {e.estado === "mergeada" && e.sha ? (
              <code className="text-xs text-muted-foreground">{e.sha.slice(0, 8)}</code>
            ) : e.motivo ? (
              <span className="text-xs text-muted-foreground">
                {AUTODES_MOTIVO_LABEL[e.motivo] ?? e.motivo}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
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
  autoActivo,
  auditoriaPorSugerencia,
  cargando,
  error,
  onReintentar,
  reintentando,
}: {
  sugerencias: Sugerencia[];
  estados: string[];
  autoActivo: boolean;
  auditoriaPorSugerencia: Map<string, AuditoriaAutodesarrollo>;
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
        <TarjetaSugerencia
          key={s.id}
          sugerencia={s}
          estados={estados}
          autoActivo={autoActivo}
          ultimoIntento={auditoriaPorSugerencia.get(s.id)}
        />
      ))}
    </div>
  );
}

function TarjetaSugerencia({
  sugerencia,
  estados,
  autoActivo,
  ultimoIntento,
}: {
  sugerencia: Sugerencia;
  estados: string[];
  autoActivo: boolean;
  ultimoIntento: AuditoriaAutodesarrollo | undefined;
}) {
  const queryClient = useQueryClient();

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });

  const implementar = useMutation({
    mutationFn: () => api.implementarSugerencia({ sugerencia_id: sugerencia.id }),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AUTODESARROLLO });
      toast.success(res?.mensaje ?? "Implementación lanzada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

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

  return (
    <Card className={cn(sugerencia.estado === "descartada" && "opacity-60")}>
      <CardContent className="space-y-3 p-4">
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
              {ultimoIntento && (
                <Tooltip
                  label={
                    ultimoIntento.estado === "mergeada" && ultimoIntento.sha
                      ? `Auto-desarrollo: mergeada (${ultimoIntento.sha.slice(0, 8)})`
                      : `Auto-desarrollo: ${
                          AUTODES_MOTIVO_LABEL[ultimoIntento.motivo ?? ""] ??
                          ultimoIntento.motivo ??
                          AUTODES_ESTADO_LABEL[ultimoIntento.estado]
                        }`
                  }
                >
                  <Badge
                    variant={AUTODES_ESTADO_VARIANTE[ultimoIntento.estado] ?? "secondary"}
                    className="font-normal"
                  >
                    <Bot className="mr-1 h-3 w-3" />
                    {AUTODES_ESTADO_LABEL[ultimoIntento.estado] ?? ultimoIntento.estado}
                  </Badge>
                </Tooltip>
              )}
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
            <Tooltip label="Borrar">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Borrar sugerencia"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => borrar.mutate()}
                disabled={borrar.isPending}
              >
                {borrar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
          </div>
        </div>
        {sugerencia.detalle && (
          <Markdown className="text-muted-foreground">{sugerencia.detalle}</Markdown>
        )}
        {autoActivo && (
          <div className="flex justify-end border-t pt-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => implementar.mutate()}
              disabled={implementar.isPending}
            >
              {implementar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Bot className="h-4 w-4" />
              )}
              Implementar con IA
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
