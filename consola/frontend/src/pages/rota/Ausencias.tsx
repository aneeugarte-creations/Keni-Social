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
import { confirmar } from "@/components/comunes/confirmar";
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
  esAdmin,
  miId,
  onCreada,
}: {
  equipo: MiembroRota[];
  esAdmin: boolean;
  miId: string;
  onCreada: () => void;
}) {
  // Frontera de permisos: un editor solo registra LO SUYO (el back devuelve 403 si no);
  // el admin/coordinador, la de cualquiera. Para no ofrecer una acción condenada al 403,
  // el no-admin queda fijado a sí mismo (selector bloqueado a su nombre).
  const [miembroId, setMiembroId] = React.useState(esAdmin ? "" : miId);
  const [tipo, setTipo] = React.useState<TipoAusencia>("vacaciones");
  const [desde, setDesde] = React.useState("");
  const [hasta, setHasta] = React.useState("");
  const [motivo, setMotivo] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearAusenciaRota({ miembro_id: miembroId, tipo, desde, hasta, motivo: motivo.trim() }),
    onSuccess: (data) => {
      const n = data.conflictos?.length ?? 0;
      if (n > 0)
        toast.warning(
          `Ausencia registrada, pero deja ${n} turno${n > 1 ? "s" : ""} sin cubrir. Revisa la cobertura.`,
        );
      else toast.success("Ausencia registrada.");
      setDesde("");
      setHasta("");
      setMotivo("");
      onCreada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Las fechas ISO se comparan como string (AAAA-MM-DD = orden cronológico).
  const rangoInvalido = desde !== "" && hasta !== "" && hasta < desde;
  const puedeCrear =
    miembroId !== "" && desde !== "" && hasta !== "" && !rangoInvalido && !crear.isPending;

  // Sin wrapper Card: lo aporta el caller (CambiosYAusencias monta el formulario
  // colapsable dentro de su propio recuadro y elige el titulo segun el tipo).
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Persona</Label>
        {esAdmin ? (
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
        ) : (
          // No-admin: solo su propia ausencia. Campo bloqueado a su nombre.
          <Input value={equipo.find((m) => m.id === miId)?.nombre ?? "Tú"} disabled readOnly />
        )}
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
      {rangoInvalido && (
        <p className="text-xs text-destructive">
          La fecha de fin no puede ser anterior a la de inicio.
        </p>
      )}
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
  puedeGestionar,
  onCambio,
}: {
  ausencia: AusenciaRota;
  puedeGestionar: boolean;
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

  // Frontera de permisos: solo el dueño de la ausencia (o un admin) ve editar/borrar; el
  // resto la ve en modo lectura. Borrar pasa por confirmación (acción destructiva, antes
  // se ejecutaba al primer clic).
  const acciones: EntradaMenuContextual[] = puedeGestionar
    ? [
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
          onClick: async () => {
            if (
              await confirmar({
                titulo: "Borrar ausencia",
                mensaje: `¿Borrar la ausencia de ${ausencia.miembro_nombre || "este miembro"}?`,
                destructivo: true,
                textoConfirmar: "Borrar",
              })
            )
              borrar.mutate();
          },
          deshabilitado: borrar.isPending,
        },
      ]
    : [];

  return (
    // Misma ficha flotante que la tarjeta de cambio (rounded-lg + shadow-sm) para que la
    // lista fusionada se lea como un solo sistema; padding en el contenido (antes el texto
    // tocaba el borde) con `pr-10` para reservar el hueco del kebab de acciones.
    <Card className="rounded-lg shadow-sm">
      <FilaConAcciones
        como="div"
        realce={puedeGestionar}
        onPrimaria={puedeGestionar ? () => setEditando(true) : undefined}
        acciones={acciones}
      >
        <div className="min-w-0 space-y-1 p-4 pr-10">
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
    onSuccess: (data) => {
      const n = data.conflictos?.length ?? 0;
      if (n > 0)
        toast.warning(
          `Ausencia actualizada, pero deja ${n} turno${n > 1 ? "s" : ""} sin cubrir. Revisa la cobertura.`,
        );
      else toast.success("Ausencia actualizada.");
      onGuardada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const rangoInvalido = desde !== "" && hasta !== "" && hasta < desde;
  const puedeGuardar = desde !== "" && hasta !== "" && !rangoInvalido && !guardar.isPending;

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
          {rangoInvalido && (
            <p className="text-xs text-destructive">
              La fecha de fin no puede ser anterior a la de inicio.
            </p>
          )}
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

