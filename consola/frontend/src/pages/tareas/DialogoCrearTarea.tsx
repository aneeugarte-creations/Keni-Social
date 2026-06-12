import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CatalogosContenido } from "@/types";

import { CLAVE_TAREAS } from "./claves";

const SIN_RESPONSABLE = "__libre__";

type Modo = "partido" | "encargo";

/**
 * Añadir a la lista de Tareas: un PARTIDO/evento a cubrir (crea un evento de la rota, igual que
 * Fuentes — aparece como «Por cubrir») o un ENCARGO suelto del equipo (tarea sin evento).
 */
export function DialogoCrearTarea({
  abierto,
  onOpenChange,
  catalogos,
  marca,
}: {
  abierto: boolean;
  onOpenChange: (abierto: boolean) => void;
  catalogos: CatalogosContenido | undefined;
  marca: string | undefined;
}) {
  const queryClient = useQueryClient();
  const [modo, setModo] = React.useState<Modo>("partido");
  const [titulo, setTitulo] = React.useState("");
  const [fecha, setFecha] = React.useState("");
  const [hora, setHora] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [prioridad, setPrioridad] = React.useState("media");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);

  const usuarios = catalogos?.usuarios ?? [];
  const prioridades = catalogos?.prioridades ?? ["alta", "media", "baja"];

  const reiniciar = () => {
    setTitulo("");
    setFecha("");
    setHora("");
    setContenido("");
    setPrioridad("media");
    setResponsable(SIN_RESPONSABLE);
  };

  const cerrar = () => {
    reiniciar();
    onOpenChange(false);
  };

  const crear = useMutation({
    mutationFn: async () => {
      if (modo === "partido") {
        await api.crearEventoRota({
          titulo: titulo.trim(),
          fecha,
          hora: hora || undefined,
          contenido: contenido.trim() || undefined,
          prioridad: prioridad as never,
          tipo_cobertura: "transmision",
          marca: marca || undefined,
        });
        return;
      }
      await api.crearContenido({
        clase: "tarea",
        titulo: titulo.trim(),
        descripcion: contenido.trim() || undefined,
        prioridad: prioridad as never,
        fecha_objetivo: fecha || undefined,
        responsable_id: responsable === SIN_RESPONSABLE ? undefined : responsable,
        marca: marca || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(
        modo === "partido"
          ? `"${titulo.trim()}" añadido: está en «Por cubrir».`
          : `"${titulo.trim()}" creado.`,
      );
      cerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Para un partido la fecha es obligatoria; para un encargo basta el título.
  const incompleto = !titulo.trim() || (modo === "partido" && !fecha);

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Añadir a la lista</DialogTitle>
        </DialogHeader>

        {/* Qué se añade: un partido/evento a cubrir, o un encargo suelto del equipo. */}
        <div className="inline-flex overflow-hidden rounded-md border border-border">
          {(["partido", "encargo"] as Modo[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModo(m)}
              className={cn(
                "px-3 py-1 text-sm transition-colors",
                modo === m
                  ? "bg-primary text-primary-foreground"
                  : "bg-card text-muted-foreground hover:bg-muted",
              )}
            >
              {m === "partido" ? "Partido / evento" : "Encargo del equipo"}
            </button>
          ))}
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tarea-titulo">
              {modo === "partido" ? "Qué partido / evento" : "Qué hay que hacer"}
            </Label>
            <Input
              id="tarea-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder={
                modo === "partido"
                  ? "Cruz Azul vs América, final de la Copa…"
                  : "Editar el clip del gol, subir fotos del entreno…"
              }
              autoFocus
            />
          </div>

          {modo === "partido" ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="tarea-fecha">Día</Label>
                <Input
                  id="tarea-fecha"
                  type="date"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tarea-hora">Hora</Label>
                <Input
                  id="tarea-hora"
                  type="time"
                  value={hora}
                  onChange={(e) => setHora(e.target.value)}
                />
              </div>
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="tarea-fecha">Para cuándo (opcional)</Label>
              <Input
                id="tarea-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="tarea-desc">
              {modo === "partido" ? "Qué sacar (opcional)" : "Detalle (opcional)"}
            </Label>
            <Textarea
              id="tarea-desc"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              placeholder={
                modo === "partido"
                  ? "Gol, reacciones, entrada del estadio…"
                  : "Notas, lugar, qué se espera entregar…"
              }
              rows={2}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Prioridad</Label>
              <Select value={prioridad} onValueChange={setPrioridad}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {prioridades.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {modo === "encargo" && (
              <div className="space-y-1.5">
                <Label>Responsable</Label>
                <Select value={responsable} onValueChange={setResponsable}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SIN_RESPONSABLE}>Por coger</SelectItem>
                    {usuarios.map((u) => (
                      <SelectItem key={u.id} value={u.id}>
                        {u.usuario}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={cerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={crear.isPending || incompleto}>
            {crear.isPending ? "Añadiendo…" : modo === "partido" ? "Añadir partido" : "Crear encargo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
