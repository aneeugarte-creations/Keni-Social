import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, FileText, Pencil, Plus, Save, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AgenteDetalle, SubContexto } from "@/types";

import { claveAgente, mensajeError } from "./claves";

type Modo = "editar" | "vista";

/** Editor del CLAUDE.md con toggle Editar/Vista y guardado vía PUT. */
function EditorClaudeMd({ agente }: { agente: AgenteDetalle }) {
  const queryClient = useQueryClient();
  const [modo, setModo] = React.useState<Modo>("editar");
  const [contenido, setContenido] = React.useState(agente.claude_md ?? "");

  // Si el agente vuelve a cargarse, sincronizamos el contenido editable.
  React.useEffect(() => {
    setContenido(agente.claude_md ?? "");
  }, [agente.claude_md]);

  const guardar = useMutation({
    mutationFn: () => api.guardarClaudeMdAgente(agente.id, { contenido }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "CLAUDE.md guardado.");
      void queryClient.invalidateQueries({ queryKey: claveAgente(agente.id) });
    },
    onError: (error) => toast.error(mensajeError(error)),
  });

  const sucio = contenido !== (agente.claude_md ?? "");

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            CLAUDE.md
          </CardTitle>
          <div className="flex items-center gap-2">
            <Tabs value={modo} onValueChange={(v) => setModo(v as Modo)}>
              <TabsList>
                <TabsTrigger value="editar" className="gap-1.5">
                  <Pencil className="h-4 w-4" />
                  Editar
                </TabsTrigger>
                <TabsTrigger value="vista" className="gap-1.5">
                  <Eye className="h-4 w-4" />
                  Vista
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <Button onClick={() => guardar.mutate()} disabled={guardar.isPending || !sucio}>
              <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
              {guardar.isPending ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {modo === "editar" ? (
          <Textarea
            value={contenido}
            onChange={(e) => setContenido(e.target.value)}
            placeholder="# Contexto del agente&#10;&#10;Escribe aquí las instrucciones para Claude Code…"
            className="min-h-[320px] font-mono text-xs"
            disabled={guardar.isPending}
            aria-label="Contenido de CLAUDE.md"
          />
        ) : contenido.trim() === "" ? (
          <EstadoVacioTexto texto="Sin contenido. Cambia a «Editar» para escribir el contexto." />
        ) : (
          <div className="min-h-[320px] rounded-md border border-border bg-muted/30 p-4">
            <Markdown>{contenido}</Markdown>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Diálogo para crear/editar/ver un sub-contexto (`contexto/*.md`). */
function DialogoContexto({
  agenteId,
  contexto,
  modoInicial,
  abierto,
  onAbiertoChange,
}: {
  agenteId: string;
  /** `null` => crear uno nuevo. */
  contexto: SubContexto | null;
  modoInicial: Modo;
  abierto: boolean;
  onAbiertoChange: (abierto: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const creando = contexto === null;
  const [nombre, setNombre] = React.useState(contexto?.nombre ?? "");
  const [contenido, setContenido] = React.useState(contexto?.contenido ?? "");
  const [modo, setModo] = React.useState<Modo>(modoInicial);

  React.useEffect(() => {
    if (abierto) {
      setNombre(contexto?.nombre ?? "");
      setContenido(contexto?.contenido ?? "");
      setModo(modoInicial);
    }
  }, [abierto, contexto, modoInicial]);

  const nombreLimpio = nombre.trim();

  const guardar = useMutation({
    mutationFn: () => api.guardarContextoAgente(agenteId, nombreLimpio, { contenido }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "Sub-contexto guardado.");
      void queryClient.invalidateQueries({ queryKey: claveAgente(agenteId) });
      onAbiertoChange(false);
    },
    onError: (error) => toast.error(mensajeError(error)),
  });

  // El nombre solo se edita al crear; sin barras ni rutas.
  const errorNombre =
    creando && nombreLimpio !== "" && (nombreLimpio.includes("/") || nombreLimpio.includes("\\"))
      ? "Escribe solo el nombre del archivo, sin barras (/)."
      : null;
  const valido = nombreLimpio !== "" && errorNombre === null;

  const titulo = creando ? "Nuevo sub-contexto" : nombreLimpio;

  return (
    <Dialog open={abierto} onOpenChange={onAbiertoChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="truncate">{titulo}</DialogTitle>
          <DialogDescription>
            Archivo en <code className="font-mono text-xs">contexto/</code> del agente. Se usa como
            contexto adicional para Claude Code.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {creando && (
            <div className="space-y-2">
              <Label htmlFor="contexto-nombre">Nombre del archivo</Label>
              <Input
                id="contexto-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="estilo.md"
                className="font-mono text-xs"
                disabled={guardar.isPending}
                aria-invalid={errorNombre !== null}
                autoFocus
              />
              {errorNombre ? (
                <p className="text-xs text-destructive">{errorNombre}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Solo el nombre del archivo (p. ej. <code className="font-mono">estilo.md</code>).
                </p>
              )}
            </div>
          )}

          {!creando && (
            <Tabs value={modo} onValueChange={(v) => setModo(v as Modo)}>
              <TabsList>
                <TabsTrigger value="editar" className="gap-1.5">
                  <Pencil className="h-4 w-4" />
                  Editar
                </TabsTrigger>
                <TabsTrigger value="vista" className="gap-1.5">
                  <Eye className="h-4 w-4" />
                  Vista
                </TabsTrigger>
              </TabsList>
            </Tabs>
          )}

          {modo === "vista" && !creando ? (
            contenido.trim() === "" ? (
              <EstadoVacioTexto texto="Sin contenido." />
            ) : (
              <div className="min-h-[240px] rounded-md border border-border bg-muted/30 p-4">
                <Markdown>{contenido}</Markdown>
              </div>
            )
          ) : (
            <Textarea
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              placeholder="Escribe aquí el sub-contexto…"
              className="min-h-[240px] font-mono text-xs"
              disabled={guardar.isPending}
              aria-label="Contenido del sub-contexto"
            />
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onAbiertoChange(false)}
            disabled={guardar.isPending}
          >
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!valido || guardar.isPending}>
            <Save className={cn("h-4 w-4", guardar.isPending && "animate-pulse")} />
            {guardar.isPending ? "Guardando…" : "Guardar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Fila de un sub-contexto con acciones ver/editar/borrar. */
function FilaSubContexto({
  agenteId,
  contexto,
  onVer,
  onEditar,
}: {
  agenteId: string;
  contexto: SubContexto;
  onVer: () => void;
  onEditar: () => void;
}) {
  const queryClient = useQueryClient();
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);

  const borrar = useMutation({
    mutationFn: () => api.eliminarContextoAgente(agenteId, contexto.nombre),
    onSuccess: (res) => {
      setConfirmarBorrado(false);
      toast.success(res?.mensaje ?? "Sub-contexto borrado.");
      void queryClient.invalidateQueries({ queryKey: claveAgente(agenteId) });
    },
    onError: (error) => toast.error(mensajeError(error)),
  });

  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <button
        type="button"
        onClick={onVer}
        className="min-w-0 flex-1 truncate text-left font-mono text-sm hover:underline"
        title={contexto.nombre}
      >
        {contexto.nombre}
      </button>
      <div className="flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="icon" aria-label="Ver" title="Ver" onClick={onVer}>
          <Eye className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="icon" aria-label="Editar" title="Editar" onClick={onEditar}>
          <Pencil className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar"
          title="Borrar"
          onClick={() => setConfirmarBorrado(true)}
          className="text-muted-foreground hover:text-destructive"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar sub-contexto</DialogTitle>
            <DialogDescription>
              ¿Seguro que quieres borrar «{contexto.nombre}»? Esta acción no se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmarBorrado(false)}
              disabled={borrar.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => borrar.mutate()}
              disabled={borrar.isPending}
            >
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  );
}

/** Lista de sub-contextos del agente (`contexto/*.md`) con crear/ver/editar/borrar. */
function ListaSubContextos({ agente }: { agente: AgenteDetalle }) {
  const [dialogo, setDialogo] = React.useState<{
    contexto: SubContexto | null;
    modo: Modo;
  } | null>(null);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            Sub-contextos
            <Badge variant="secondary">{agente.sub_contextos.length}</Badge>
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDialogo({ contexto: null, modo: "editar" })}
          >
            <Plus className="h-4 w-4" />
            Nuevo sub-contexto
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {agente.sub_contextos.length === 0 ? (
          <EstadoVacioTexto texto="Aún no hay sub-contextos. Añade archivos de contexto adicional para este agente." />
        ) : (
          <ul className="divide-y divide-border">
            {agente.sub_contextos.map((c) => (
              <FilaSubContexto
                key={c.nombre}
                agenteId={agente.id}
                contexto={c}
                onVer={() => setDialogo({ contexto: c, modo: "vista" })}
                onEditar={() => setDialogo({ contexto: c, modo: "editar" })}
              />
            ))}
          </ul>
        )}
      </CardContent>

      <DialogoContexto
        agenteId={agente.id}
        contexto={dialogo?.contexto ?? null}
        modoInicial={dialogo?.modo ?? "editar"}
        abierto={dialogo !== null}
        onAbiertoChange={(abierto) => {
          if (!abierto) setDialogo(null);
        }}
      />
    </Card>
  );
}

/** Pestaña «Contexto»: editor de CLAUDE.md + lista de sub-contextos. */
export function PestanaContexto({ agente }: { agente: AgenteDetalle }) {
  return (
    <div className="space-y-6">
      <EditorClaudeMd agente={agente} />
      <ListaSubContextos agente={agente} />
    </div>
  );
}
