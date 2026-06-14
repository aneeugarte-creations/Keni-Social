/**
 * Panel de lanzamiento de un PROMPT sobre un target (contenido pegado / URL / sección de la
 * Consola / archivo), adjuntando la línea editorial de la marca. El resultado llega por
 * streaming (sondeo de la generación). Extraído del contenedor `pages/Texto.tsx` sin cambio
 * de comportamiento.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, Pencil, Send, X } from "lucide-react";
import * as React from "react";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { Tooltip } from "@/components/ui/tooltip";
import { MENSAJE_MARCA_REQUERIDA, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useGeneracion } from "@/hooks/use-generacion";
import { api } from "@/lib/api";
import type { TargetLanzamiento } from "@/types";

import type { TipoTarget } from "./tipos";

export function PanelLanzar({
  promptId,
  salida,
  marcas,
  areas,
  open,
  onOpenChange,
  marcaForzada,
  onEditarPrompt,
}: {
  promptId: string;
  salida: string;
  marcas: { id: string; nombre: string }[];
  areas: { id: string; nombre: string }[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Marca LOCAL que prevalece sobre el switch global: el cockpit de Producción puede lanzar
   *  contra una marca concreta aunque el switch esté en "Todas" (su propio selector). */
  marcaForzada?: string;
  /** Si se pasa, el popup muestra un botón "Editar prompt" en la cabecera (edición in-place). */
  onEditarPrompt?: () => void;
}) {
  // La marca la manda el switch GLOBAL salvo que el contenedor imponga una `marcaForzada`
  // (selector local del cockpit). Lanzar EXIGE marca concreta, así que si no hay marca válida
  // (switch en "Todas" sin marca forzada) el botón se deshabilita con el tooltip compartido.
  const { marcaActiva } = useMarcaActiva();
  const marcaBase = marcaForzada ?? marcaActiva;
  const marca = marcaBase && marcas.some((m) => m.id === marcaBase) ? marcaBase : "";
  const [adjuntos, setAdjuntos] = React.useState<Set<string>>(new Set());
  const [tipoTarget, setTipoTarget] = React.useState<TipoTarget>("contenido");
  const [valorTarget, setValorTarget] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);

  // Modo PIEZAS: si el prompt declara salida=piezas, ofrecemos el selector de redes y
  // el lanzamiento crea borradores por red (copy) en vez de un documento markdown.
  const esPiezas = salida === "piezas";
  const [redes, setRedes] = React.useState<Set<string>>(new Set());

  const { generacion, ejecutando, cancelando, iniciar, cancelar } = useGeneracion("keni:texto-lanzar");

  // "Pensando…" con cronómetro: el modelo puede tardar ~1-2 min en RAZONAR antes de emitir
  // el primer token (la fase de thinking NO se transmite a `salida`), así que mientras corre
  // sin salida la UI parecía colgada. Contamos los segundos para señalar que sigue vivo.
  const pensando = ejecutando && !generacion?.salida && !generacion?.error;
  const [pensandoSeg, setPensandoSeg] = React.useState(0);
  React.useEffect(() => {
    if (!pensando) return;
    setPensandoSeg(0);
    const t = setInterval(() => setPensandoSeg((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [pensando]);

  // Línea editorial auto-resuelta por marca (selección inicial = todas).
  const editorialesQuery = useQuery({
    queryKey: ["texto-editoriales", marca],
    queryFn: ({ signal }) => api.editorialesTexto(marca, undefined, signal),
    enabled: !!marca,
  });
  // Diagnóstico de los 4 pilares editoriales de la marca elegida: avisa si la línea
  // editorial está incompleta ANTES de lanzar (no bloquea, solo advierte).
  const validacionQuery = useQuery({
    queryKey: ["texto-validacion", marca],
    queryFn: ({ signal }) => api.validacionTexto(marca, signal),
    enabled: !!marca,
  });
  const validacion = validacionQuery.data;
  React.useEffect(() => {
    const ids = (editorialesQuery.data?.editoriales ?? []).map((d) => d.id);
    setAdjuntos(new Set(ids));
  }, [editorialesQuery.data]);

  // Redes disponibles (catálogo de publicaciones); preselección = todas, solo en piezas.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: esPiezas,
  });
  const opcionesRedes = React.useMemo(
    () => (opcionesQuery.data?.redes ?? []).map((r) => ({ id: r.id, nombre: r.nombre })),
    [opcionesQuery.data],
  );
  React.useEffect(() => {
    if (esPiezas) setRedes(new Set(opcionesRedes.map((r) => r.id)));
  }, [esPiezas, opcionesRedes]);

  const lanzarMut = useMutation({
    mutationFn: () => {
      const adj = [...adjuntos];
      const redesArr = esPiezas ? [...redes] : undefined;
      if (esPiezas && redesArr && redesArr.length === 0) {
        throw new Error("Elige al menos una red para generar las piezas.");
      }
      if (tipoTarget === "archivo") {
        if (!archivo) throw new Error("Adjunta un archivo o cambia de target.");
        return api.lanzarTextoArchivo(archivo, marca, {
          prompt_id: promptId,
          adjuntos: adj,
          redes: redesArr,
        });
      }
      const target: TargetLanzamiento =
        tipoTarget === "contenido"
          ? { tipo: "contenido", valor: valorTarget }
          : tipoTarget === "url"
            ? { tipo: "url", valor: valorTarget }
            : tipoTarget === "area"
              ? { tipo: "area", valor: valorTarget }
              : { tipo: "ninguno" };
      return api.lanzarTexto({
        prompt_id: promptId,
        marca,
        adjuntos: adj,
        target,
        redes: redesArr,
      });
    },
    onSuccess: (r) => iniciar(r.generacion),
  });

  const editoriales = editorialesQuery.data?.editoriales ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col gap-3 overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 pr-6">
            <DialogTitle className="flex items-center gap-2">
              <Send className="h-4 w-4" /> Lanzar prompt
            </DialogTitle>
            {onEditarPrompt ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 text-xs text-muted-foreground"
                onClick={onEditarPrompt}
              >
                <Pencil className="h-3.5 w-3.5" /> Editar prompt
              </Button>
            ) : null}
          </div>
        </DialogHeader>

      {marca && validacion ? (
        validacion.completa ? (
          <div className="flex items-center gap-2 rounded-md border border-emerald-600/30 bg-emerald-600/5 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>Línea editorial completa</span>
          </div>
        ) : (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{validacion.recomendacion}</span>
          </div>
        )
      ) : null}

      {marca ? (
        <div className="space-y-1">
          <Label>Línea editorial adjunta</Label>
          <div className="flex flex-wrap gap-1">
            {editoriales.length === 0 ? (
              <span className="text-xs text-muted-foreground">Sin editorial para esta marca.</span>
            ) : (
              editoriales.map((d) => {
                const activo = adjuntos.has(d.id);
                return (
                  <Badge
                    key={d.id}
                    variant={activo ? "default" : "outline"}
                    className="cursor-pointer"
                    onClick={() =>
                      setAdjuntos((prev) => {
                        const s = new Set(prev);
                        if (s.has(d.id)) s.delete(d.id);
                        else s.add(d.id);
                        return s;
                      })
                    }
                  >
                    {d.titulo}
                    {activo ? <X className="ml-1 h-3 w-3" /> : null}
                  </Badge>
                );
              })
            )}
          </div>
        </div>
      ) : null}

      {esPiezas ? (
        <SelectorRedMultiple
          opciones={opcionesRedes}
          seleccionadas={redes}
          onCambio={(red, marcada) =>
            setRedes((prev) => {
              const s = new Set(prev);
              if (marcada) s.add(red);
              else s.delete(red);
              return s;
            })
          }
          disabled={ejecutando || lanzarMut.isPending}
        />
      ) : null}

      <div className="space-y-1">
        <Label>Sobre qué</Label>
        <Select value={tipoTarget} onValueChange={(v) => setTipoTarget(v as TipoTarget)}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="contenido">Contenido (pegar texto)</SelectItem>
            <SelectItem value="url">URL</SelectItem>
            <SelectItem value="area">Sección de la Consola</SelectItem>
            <SelectItem value="archivo">Archivo</SelectItem>
            <SelectItem value="ninguno">Nada (solo el prompt)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {tipoTarget === "contenido" ? (
        <AutoTextarea
          value={valorTarget}
          onChange={(e) => setValorTarget(e.target.value)}
          maxHeight={340}
          placeholder="Pega aquí la nota, transcripción o texto…"
          className="min-h-[160px] w-full text-sm"
        />
      ) : tipoTarget === "url" ? (
        <Input value={valorTarget} onChange={(e) => setValorTarget(e.target.value)} placeholder="https://…" />
      ) : tipoTarget === "area" ? (
        <Select value={valorTarget} onValueChange={setValorTarget}>
          <SelectTrigger><SelectValue placeholder="Elige sección" /></SelectTrigger>
          <SelectContent>
            {areas.map((a) => (
              <SelectItem key={a.id} value={a.id}>{a.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : tipoTarget === "archivo" ? (
        <Input type="file" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
      ) : null}

      <Tooltip label={!marca ? MENSAJE_MARCA_REQUERIDA : ""} className="w-full">
        <Button
          variant="brand"
          className="w-full"
          onClick={() => lanzarMut.mutate()}
          disabled={!marca || ejecutando || lanzarMut.isPending}
        >
          {ejecutando || lanzarMut.isPending ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <MarcaIA className="mr-1" />
          )}
          Lanzar
        </Button>
      </Tooltip>
      {lanzarMut.isError ? (
        <p className="text-xs text-destructive">{(lanzarMut.error as Error).message}</p>
      ) : null}

      {/* C: el progreso aparece en cuanto ARRANCA el lanzamiento (estado intermedio
          "Lanzando…"), sin esperar a que el POST devuelva `r.generacion`. En cuanto
          llega la generación, el panel ya está montado y empieza a pintar el stream. */}
      {generacion || lanzarMut.isPending ? (
        <div className="min-h-0 flex-1 space-y-2 border-t border-border pt-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Resultado</span>
            {ejecutando ? (
              <Button size="sm" variant="ghost" className="ml-auto" onClick={cancelar} disabled={cancelando}>
                {cancelando ? "Cancelando…" : "Cancelar"}
              </Button>
            ) : null}
          </div>
          {!generacion ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Lanzando…</span>
            </div>
          ) : generacion.error ? (
            <p className="text-sm text-destructive">{generacion.error}</p>
          ) : pensando ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Pensando… {pensandoSeg}s</span>
            </div>
          ) : (
            <>
              <Markdown>{generacion.salida}</Markdown>
              {/* MODO PIEZAS: el copy NO se queda aquí, se guarda como borradores por red en
                  la Parrilla. Lo decimos al completar para que no se busque en este panel. */}
              {esPiezas && !ejecutando && generacion.salida ? (
                <p className="text-xs text-muted-foreground">
                  El copy se guardó como borradores en la Parrilla.
                </p>
              ) : null}
            </>
          )}
        </div>
      ) : null}
      </DialogContent>
    </Dialog>
  );
}
