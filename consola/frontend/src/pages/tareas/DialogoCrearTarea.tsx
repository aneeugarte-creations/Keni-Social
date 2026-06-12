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
import type { CatalogosContenido } from "@/types";

import { CLAVE_TAREAS } from "./claves";

// Centinelas para los `Select` (Radix no admite item con value=""): se mapean a "" al enviar.
const SIN_RESPONSABLE = "__libre__";
const SIN_EVENTO = "__ninguno__";

/**
 * Alta de una TAREA del equipo (cubrir un partido, grabar, editar, subir fotos…). Crea un
 * item `clase='tarea'` por el tablero unificado (`/api/contenido`); NO es una pieza de
 * contenido. Si se deja sin responsable, nace LIBRE y aparece en «Por coger».
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
  /** Marca activa del workspace; la tarea se crea en ella (vacío = sin marca / todas). */
  marca: string | undefined;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [descripcion, setDescripcion] = React.useState("");
  const [prioridad, setPrioridad] = React.useState("media");
  const [fecha, setFecha] = React.useState("");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);
  const [evento, setEvento] = React.useState(SIN_EVENTO);

  const usuarios = catalogos?.usuarios ?? [];
  const eventos = catalogos?.eventos ?? [];
  const prioridades = catalogos?.prioridades ?? ["alta", "media", "baja"];

  const reiniciar = () => {
    setTitulo("");
    setDescripcion("");
    setPrioridad("media");
    setFecha("");
    setResponsable(SIN_RESPONSABLE);
    setEvento(SIN_EVENTO);
  };

  const crear = useMutation({
    mutationFn: () =>
      api.crearContenido({
        clase: "tarea",
        titulo: titulo.trim(),
        descripcion: descripcion.trim() || undefined,
        prioridad: prioridad as never,
        fecha_objetivo: fecha || undefined,
        responsable_id: responsable === SIN_RESPONSABLE ? undefined : responsable,
        evento_id: evento === SIN_EVENTO ? undefined : evento,
        marca: marca || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(
        responsable === SIN_RESPONSABLE
          ? `"${titulo.trim()}" creada: está en «Por coger».`
          : `"${titulo.trim()}" creada y asignada.`,
      );
      reiniciar();
      onOpenChange(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva tarea del equipo</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="tarea-titulo">Qué hay que hacer</Label>
            <Input
              id="tarea-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Cubrir el partido del Cruz Azul, editar el clip del gol…"
              autoFocus
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="tarea-desc">Detalle (opcional)</Label>
            <Textarea
              id="tarea-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              placeholder="Notas, lugar, qué se espera entregar…"
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
            <div className="space-y-1.5">
              <Label htmlFor="tarea-fecha">Para cuándo</Label>
              <Input
                id="tarea-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Responsable</Label>
            <Select value={responsable} onValueChange={setResponsable}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SIN_RESPONSABLE}>Por coger (que la tome el equipo)</SelectItem>
                {usuarios.map((u) => (
                  <SelectItem key={u.id} value={u.id}>
                    {u.usuario}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {eventos.length > 0 && (
            <div className="space-y-1.5">
              <Label>Cobertura de evento (opcional)</Label>
              <Select value={evento} onValueChange={setEvento}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_EVENTO}>Ninguno</SelectItem>
                  {eventos.map((ev) => (
                    <SelectItem key={ev.id} value={ev.id}>
                      {ev.titulo}
                      {ev.fecha ? ` · ${ev.fecha}` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button
            onClick={() => crear.mutate()}
            disabled={crear.isPending || !titulo.trim()}
          >
            {crear.isPending ? "Creando…" : "Crear tarea"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
