/**
 * Diálogos de gestión de agentes genéricos: crear, conectar, renombrar y borrar.
 *
 * Los agentes son un conjunto abierto: 5 marcas de serie (no gestionables) más
 * agentes genéricos. Estos diálogos cubren el ciclo de vida de los genéricos.
 * React Query + invalidación de la caché de agentes; toasts (sonner); modo
 * claro/oscuro; texto es-MX.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderInput, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { AgenteResumen } from "@/types";

import { CLAVE_AGENTES } from "../Agentes";
import { mensajeError } from "./claves";

/**
 * Plantillas de CLAUDE.md disponibles al crear un agente. Coinciden con los
 * `tipo` que entiende el backend; "general" es el predeterminado.
 */
const PLANTILLAS_AGENTE = [
  { id: "general", nombre: "General" },
  { id: "noticias", nombre: "Noticias" },
  { id: "deportes", nombre: "Deportes" },
  { id: "podcast", nombre: "Podcast" },
  { id: "social", nombre: "Redes sociales" },
] as const;

/** Ruta del detalle de un agente. */
function rutaDetalle(id: string): string {
  return `/agentes/${encodeURIComponent(id)}`;
}

/** Diálogo para crear un agente genérico nuevo (nombre + plantilla). */
export function DialogoCrearAgente({
  abierto,
  onCerrar,
}: {
  abierto: boolean;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [nombre, setNombre] = React.useState("");
  const [tipo, setTipo] = React.useState<string>(PLANTILLAS_AGENTE[0].id);

  // Al cerrar, reseteamos el formulario.
  React.useEffect(() => {
    if (!abierto) {
      setNombre("");
      setTipo(PLANTILLAS_AGENTE[0].id);
    }
  }, [abierto]);

  const crear = useMutation({
    mutationFn: () => api.crearAgente({ nombre: nombre.trim(), tipo }),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AGENTES });
      toast.success(`Agente «${res.agente.nombre}» creado`);
      onCerrar();
      navigate(rutaDetalle(res.agente.id));
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = nombre.trim().length > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Crear agente
          </DialogTitle>
          <DialogDescription>
            Crea un agente genérico nuevo con su propia carpeta y un CLAUDE.md a
            partir de la plantilla elegida.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="agente-nombre">Nombre</Label>
            <Input
              id="agente-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Ej. Boletín semanal"
              maxLength={80}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && puedeCrear) crear.mutate();
              }}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="agente-tipo">Plantilla</Label>
            <Select value={tipo} onValueChange={setTipo}>
              <SelectTrigger id="agente-tipo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLANTILLAS_AGENTE.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear agente
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo para conectar (registrar) una subcarpeta existente de la raíz. */
export function DialogoConectarAgente({
  abierto,
  onCerrar,
}: {
  abierto: boolean;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [carpeta, setCarpeta] = React.useState("");

  React.useEffect(() => {
    if (!abierto) setCarpeta("");
  }, [abierto]);

  const conectar = useMutation({
    mutationFn: () => api.conectarAgente({ carpeta: carpeta.trim() }),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AGENTES });
      toast.success(`Carpeta «${res.agente.nombre}» conectada`);
      onCerrar();
      navigate(rutaDetalle(res.agente.id));
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeConectar = carpeta.trim().length > 0 && !conectar.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FolderInput className="h-5 w-5" />
            Conectar carpeta
          </DialogTitle>
          <DialogDescription>
            Registra como agente una subcarpeta que ya existe bajo la raíz de
            agentes. Indica su nombre exacto.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="agente-carpeta">Nombre de la subcarpeta</Label>
          <Input
            id="agente-carpeta"
            value={carpeta}
            onChange={(e) => setCarpeta(e.target.value)}
            placeholder="Ej. mi-carpeta"
            className="font-mono"
            maxLength={120}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && puedeConectar) conectar.mutate();
            }}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={conectar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => conectar.mutate()} disabled={!puedeConectar}>
            {conectar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FolderInput className="h-4 w-4" />
            )}
            Conectar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo para renombrar el nombre visible de un agente genérico. */
export function DialogoRenombrarAgente({
  agente,
  onCerrar,
}: {
  /** Agente a renombrar; `null` cierra el diálogo. */
  agente: AgenteResumen | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");

  // Al abrir con un agente, precargamos su nombre actual.
  React.useEffect(() => {
    if (agente) setNombre(agente.nombre);
  }, [agente]);

  const renombrar = useMutation({
    mutationFn: () => {
      if (!agente) throw new Error("Sin agente seleccionado.");
      return api.renombrarAgente(agente.id, { nombre: nombre.trim() });
    },
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AGENTES });
      void queryClient.invalidateQueries({ queryKey: ["agentes", res.agente.id] });
      toast.success("Agente renombrado");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const limpio = nombre.trim();
  const puedeGuardar =
    limpio.length > 0 && limpio !== agente?.nombre && !renombrar.isPending;

  return (
    <Dialog open={agente !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pencil className="h-5 w-5" />
            Renombrar agente
          </DialogTitle>
          <DialogDescription>
            Cambia el nombre visible del agente. No afecta a su carpeta ni a su
            contenido.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <Label htmlFor="agente-nuevo-nombre">Nombre</Label>
          <Input
            id="agente-nuevo-nombre"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            maxLength={80}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && puedeGuardar) renombrar.mutate();
            }}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={renombrar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => renombrar.mutate()} disabled={!puedeGuardar}>
            {renombrar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar cambios
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo de confirmación para borrar un agente genérico (y su carpeta). */
export function DialogoBorrarAgente({
  agente,
  onCerrar,
}: {
  /** Agente a borrar; `null` cierra el diálogo. */
  agente: AgenteResumen | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();

  const borrar = useMutation({
    mutationFn: () => {
      if (!agente) throw new Error("Sin agente seleccionado.");
      return api.eliminarAgente(agente.id);
    },
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_AGENTES });
      toast.success(res?.mensaje ?? "Agente borrado");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={agente !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <Trash2 className="h-5 w-5" />
            Borrar agente
          </DialogTitle>
          <DialogDescription>
            Vas a borrar el agente{" "}
            <span className="font-medium text-foreground">{agente?.nombre}</span>.
            Esto elimina su carpeta y todo su contenido (CLAUDE.md, sub-contextos
            y runs). Esta acción no se puede deshacer.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={borrar.isPending}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={() => borrar.mutate()}
            disabled={borrar.isPending}
          >
            {borrar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Borrar agente
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
