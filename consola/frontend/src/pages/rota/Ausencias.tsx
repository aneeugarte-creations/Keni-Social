// Alta/edición/tarjeta de AUSENCIAS. Partido mecánicamente de pages/Rota.tsx.
import { useMutation } from "@tanstack/react-query";
import {
  CalendarOff,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
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
import { api, mensajeError } from "@/lib/api";
import {
  formatearRango,
} from "@/lib/rota-calendario";
import type {
  AusenciaRota,
  MiembroRota,
  TipoAusencia,
} from "@/types";

import { TIPOS_AUSENCIA } from "./comun";


// --- Formulario de nueva ausencia (reutilizado por CambiosYAusencias) -------

export function NuevaAusencia({
  equipo,
  onCreada,
}: {
  equipo: MiembroRota[];
  onCreada: () => void;
}) {
  const [miembroId, setMiembroId] = React.useState("");
  const [tipo, setTipo] = React.useState<TipoAusencia>("vacaciones");
  const [desde, setDesde] = React.useState("");
  const [hasta, setHasta] = React.useState("");
  const [motivo, setMotivo] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearAusenciaRota({ miembro_id: miembroId, tipo, desde, hasta, motivo: motivo.trim() }),
    onSuccess: () => {
      toast.success("Ausencia registrada.");
      setDesde("");
      setHasta("");
      setMotivo("");
      onCreada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = miembroId !== "" && desde !== "" && hasta !== "" && !crear.isPending;

  // Sin wrapper Card: lo aporta el caller (CambiosYAusencias monta el formulario
  // colapsable dentro de su propio recuadro y elige el titulo segun el tipo).
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Persona</Label>
        <Select value={miembroId} onValueChange={setMiembroId}>
          <SelectTrigger aria-label="Persona">
            <SelectValue placeholder="Elige a un miembro" />
          </SelectTrigger>
          <SelectContent>
            {equipo.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Tipo</Label>
        <Select value={tipo} onValueChange={(v) => setTipo(v as TipoAusencia)}>
          <SelectTrigger aria-label="Tipo de ausencia">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TIPOS_AUSENCIA.map((t) => (
              <SelectItem key={t.valor} value={t.valor}>
                {t.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="au-desde">Desde</Label>
          <Input id="au-desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="au-hasta">Hasta</Label>
          <Input id="au-hasta" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="au-motivo">Motivo</Label>
        <Input
          id="au-motivo"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Opcional: vacaciones, evento, etc."
          maxLength={200}
        />
      </div>
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => crear.mutate()} disabled={!puedeCrear}>
          {crear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Registrar ausencia
        </Button>
      </div>
    </div>
  );
}

export function TarjetaAusencia({
  ausencia,
  onCambio,
}: {
  ausencia: AusenciaRota;
  onCambio: () => void;
}) {
  const borrar = useMutation({
    mutationFn: () => api.eliminarAusenciaRota(ausencia.id),
    onSuccess: () => {
      toast.success("Ausencia eliminada.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const [editando, setEditando] = React.useState(false);

  const etiquetaTipo =
    TIPOS_AUSENCIA.find((t) => t.valor === ausencia.tipo)?.etiqueta ?? ausencia.tipo;

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Editar",
      icono: Pencil,
      onClick: () => setEditando(true),
      deshabilitado: borrar.isPending,
    },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      destructivo: true,
      onClick: () => borrar.mutate(),
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <Card>
      <FilaConAcciones
        como="div"
        realce
        onPrimaria={() => setEditando(true)}
        acciones={acciones}
      >
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-normal">
              <CalendarOff className="mr-1 h-3 w-3" /> Ausencia
            </Badge>
            <span className="font-medium">{ausencia.miembro_nombre || "—"}</span>
            <Badge variant="secondary" className="font-normal">
              {etiquetaTipo}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground">
            {formatearRango(ausencia.desde, ausencia.hasta)}
          </div>
          {ausencia.motivo && (
            <div className="text-sm text-muted-foreground">{ausencia.motivo}</div>
          )}
        </div>
      </FilaConAcciones>
      <DialogoEditarAusencia
        ausencia={ausencia}
        abierto={editando}
        onCerrar={() => setEditando(false)}
        onGuardada={() => {
          setEditando(false);
          onCambio();
        }}
      />
    </Card>
  );
}

/**
 * Diálogo para EDITAR una ausencia existente (PATCH /api/rota/ausencias/{id}).
 * Reutiliza los mismos campos que `NuevaAusencia` salvo la PERSONA: el backend
 * (`CuerpoActualizarAusenciaRota`) solo permite cambiar tipo / fechas / motivo.
 */
export function DialogoEditarAusencia({
  ausencia,
  abierto,
  onCerrar,
  onGuardada,
}: {
  ausencia: AusenciaRota;
  abierto: boolean;
  onCerrar: () => void;
  onGuardada: () => void;
}) {
  const [tipo, setTipo] = React.useState<TipoAusencia>(ausencia.tipo);
  const [desde, setDesde] = React.useState(ausencia.desde);
  const [hasta, setHasta] = React.useState(ausencia.hasta);
  const [motivo, setMotivo] = React.useState(ausencia.motivo);

  // Al (re)abrir, repuebla los campos con los valores vigentes de la ausencia.
  React.useEffect(() => {
    if (abierto) {
      setTipo(ausencia.tipo);
      setDesde(ausencia.desde);
      setHasta(ausencia.hasta);
      setMotivo(ausencia.motivo);
    }
  }, [abierto, ausencia]);

  const guardar = useMutation({
    mutationFn: () =>
      api.actualizarAusenciaRota(ausencia.id, { tipo, desde, hasta, motivo: motivo.trim() }),
    onSuccess: () => {
      toast.success("Ausencia actualizada.");
      onGuardada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar = desde !== "" && hasta !== "" && !guardar.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar ausencia</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Persona</Label>
            <Input value={ausencia.miembro_nombre || "—"} disabled readOnly />
          </div>
          <div className="space-y-1.5">
            <Label>Tipo</Label>
            <Select value={tipo} onValueChange={(v) => setTipo(v as TipoAusencia)}>
              <SelectTrigger aria-label="Tipo de ausencia">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIPOS_AUSENCIA.map((t) => (
                  <SelectItem key={t.valor} value={t.valor}>
                    {t.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="au-edit-desde">Desde</Label>
              <Input
                id="au-edit-desde"
                type="date"
                value={desde}
                onChange={(e) => setDesde(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="au-edit-hasta">Hasta</Label>
              <Input
                id="au-edit-hasta"
                type="date"
                value={hasta}
                onChange={(e) => setHasta(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="au-edit-motivo">Motivo</Label>
            <Input
              id="au-edit-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Opcional: vacaciones, evento, etc."
              maxLength={200}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button variant="secondary" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

