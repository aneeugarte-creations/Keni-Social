/**
 * PanelProgramas — catálogo de programas/campañas evergreen de Claro Sports.
 *
 * Extraído de `pages/Rota.tsx` (ola "Programas → Fuentes"): la gestión del
 * catálogo de programas dejó de vivir en la pestaña "Programas" del Calendario
 * y ahora habita en el hub de Fuentes/Investigación (`pages/EventosCobertura.tsx`,
 * sub-pestaña "Programas"). El componente es autónomo y reutiliza los endpoints
 * existentes `/api/rota/programas` (sin tocar ningún otro endpoint).
 *
 * NON-DESTRUCTIVO: los endpoints de backend `/api/rota/programas` permanecen
 * intactos; solo se reubica la superficie de gestión.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { confirmar } from "@/components/comunes/confirmar";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { ApiError, api, mensajeError } from "@/lib/api";
import type {
  CuerpoActualizarProgramaRota,
  CuerpoCrearProgramaRota,
  ProgramaRota,
} from "@/types";

// --- Subcomponentes internos ------------------------------------------------

function NuevoPrograma({ onCreado }: { onCreado: () => void }) {
  const [abierto, setAbierto] = React.useState(false);
  const [nombre, setNombre] = React.useState("");
  const [descripcion, setDescripcion] = React.useState("");
  const [color, setColor] = React.useState("#7c7c7c");
  const [inicio, setInicio] = React.useState("");
  const [fin, setFin] = React.useState("");
  // Validación inline: fin >= inicio. Si ambos están y el orden está mal,
  // bloqueamos el submit y mostramos el mensaje pegado al campo.
  const [errorFechas, setErrorFechas] = React.useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearProgramaRota = {
        nombre: nombre.trim(),
        descripcion: descripcion.trim() || undefined,
        color: color || undefined,
        inicio: inicio || undefined,
        fin: fin || undefined,
      };
      return api.crearProgramaRota(cuerpo);
    },
    onSuccess: () => {
      toast.success("Programa creado.");
      setNombre("");
      setDescripcion("");
      setColor("#7c7c7c");
      setInicio("");
      setFin("");
      setErrorFechas(null);
      setAbierto(false);
      onCreado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function intentarCrear() {
    if (inicio && fin && fin < inicio) {
      setErrorFechas("La fecha de fin no puede ser anterior al inicio.");
      return;
    }
    setErrorFechas(null);
    crear.mutate();
  }

  if (!abierto) {
    return (
      <Button size="sm" variant="outline" onClick={() => setAbierto(true)}>
        <Plus className="h-3.5 w-3.5" /> Nuevo programa
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-md border bg-background p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="prog-nombre" className="text-xs">
            Nombre
          </Label>
          <Input
            id="prog-nombre"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Álvaro Fidalgo, MUNDIAL, Paty Cantú…"
            maxLength={200}
            className="h-8 text-xs"
            autoFocus
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="prog-desc" className="text-xs">
            Descripción
          </Label>
          <Textarea
            id="prog-desc"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
            placeholder="Notas internas, qué cubre el programa…"
            rows={2}
            maxLength={1000}
            className="text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-inicio" className="text-xs">
            Inicio
          </Label>
          <Input
            id="prog-inicio"
            type="date"
            value={inicio}
            onChange={(e) => {
              setInicio(e.target.value);
              if (errorFechas) setErrorFechas(null);
            }}
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-fin" className="text-xs">
            Fin
          </Label>
          <Input
            id="prog-fin"
            type="date"
            value={fin}
            onChange={(e) => {
              setFin(e.target.value);
              if (errorFechas) setErrorFechas(null);
            }}
            className="h-8 text-xs"
            aria-invalid={errorFechas ? true : undefined}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-color" className="text-xs">
            Color
          </Label>
          <Input
            id="prog-color"
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            className="h-8 w-14 cursor-pointer p-1"
          />
        </div>
        {errorFechas && (
          <p className="text-xs text-destructive sm:col-span-2">{errorFechas}</p>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setAbierto(false)}>
          Cancelar
        </Button>
        <Button
          size="sm"
          onClick={intentarCrear}
          disabled={!nombre.trim() || crear.isPending}
        >
          {crear.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          Crear programa
        </Button>
      </div>
    </div>
  );
}

function DialogEditarPrograma({
  programa,
  onCerrar,
  onCambio,
}: {
  programa: ProgramaRota;
  onCerrar: () => void;
  onCambio: () => void;
}) {
  const [nombre, setNombre] = React.useState(programa.nombre);
  const [descripcion, setDescripcion] = React.useState(programa.descripcion);
  const [color, setColor] = React.useState(programa.color || "#7c7c7c");
  const [inicio, setInicio] = React.useState(programa.inicio);
  const [fin, setFin] = React.useState(programa.fin);
  const [activo, setActivo] = React.useState(programa.activo);
  // Validación inline `fin >= inicio` antes de PATCH.
  const [errorFechas, setErrorFechas] = React.useState<string | null>(null);

  const guardar = useMutation({
    mutationFn: () => {
      // Solo enviamos los campos que han cambiado: el backend acepta PATCH parcial
      // y la cascada del rename SOLO se dispara si `nombre` viaja en el cuerpo.
      const cuerpo: CuerpoActualizarProgramaRota = {};
      if (nombre.trim() !== programa.nombre) cuerpo.nombre = nombre.trim();
      if (descripcion !== programa.descripcion) cuerpo.descripcion = descripcion;
      if (color !== (programa.color || "#7c7c7c")) cuerpo.color = color;
      if (inicio !== programa.inicio) cuerpo.inicio = inicio;
      if (fin !== programa.fin) cuerpo.fin = fin;
      if (activo !== programa.activo) cuerpo.activo = activo;
      return api.actualizarProgramaRota(programa.id, cuerpo);
    },
    onSuccess: () => {
      // La cascada en piezas es transparente (el backend la hace en la misma
      // transacción). No emite contador: avisamos si el nombre cambió.
      if (nombre.trim() !== programa.nombre) {
        toast.success(
          `Programa renombrado. Las piezas con «${programa.nombre}» se actualizaron a «${nombre.trim()}».`,
        );
      } else {
        toast.success("Programa actualizado.");
      }
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function intentarGuardar() {
    if (inicio && fin && fin < inicio) {
      setErrorFechas("La fecha de fin no puede ser anterior al inicio.");
      return;
    }
    setErrorFechas(null);
    guardar.mutate();
  }

  const sinCambios =
    nombre.trim() === programa.nombre &&
    descripcion === programa.descripcion &&
    color === (programa.color || "#7c7c7c") &&
    inicio === programa.inicio &&
    fin === programa.fin &&
    activo === programa.activo;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar programa</DialogTitle>
          <DialogDescription>
            Al renombrar, las piezas que usaban «{programa.nombre}» se renombran automáticamente
            en la misma transacción.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ep-nombre">Nombre</Label>
            <Input
              id="ep-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ep-desc">Descripción</Label>
            <Textarea
              id="ep-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              rows={3}
              maxLength={1000}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ep-inicio">Inicio</Label>
              <Input
                id="ep-inicio"
                type="date"
                value={inicio}
                onChange={(e) => {
                  setInicio(e.target.value);
                  if (errorFechas) setErrorFechas(null);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ep-fin">Fin</Label>
              <Input
                id="ep-fin"
                type="date"
                value={fin}
                onChange={(e) => {
                  setFin(e.target.value);
                  if (errorFechas) setErrorFechas(null);
                }}
                aria-invalid={errorFechas ? true : undefined}
              />
            </div>
          </div>
          {errorFechas && (
            <p className="text-xs text-destructive">{errorFechas}</p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ep-color">Color</Label>
              <Input
                id="ep-color"
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="h-9 w-14 cursor-pointer p-1"
              />
            </div>
            <div className="flex items-end gap-2 pb-1">
              <Checkbox
                id="ep-activo"
                checked={activo}
                onCheckedChange={(v) => setActivo(v === true)}
              />
              <Label htmlFor="ep-activo" className="cursor-pointer font-normal">
                Activo (aparece en el autocomplete de piezas)
              </Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            onClick={intentarGuardar}
            disabled={sinCambios || !nombre.trim() || guardar.isPending}
          >
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FilaPrograma({
  programa,
  onCambio,
}: {
  programa: ProgramaRota;
  onCambio: () => void;
}) {
  const [editando, setEditando] = React.useState(false);
  // Estado pendiente del 409 al borrar: el backend dice cuántas piezas hay; el
  // usuario decide forzar.
  const [confirmarBorradoForzado, setConfirmarBorradoForzado] = React.useState<{
    piezasAfectadas: number;
  } | null>(null);

  const activar = useMutation({
    mutationFn: (activo: boolean) => api.actualizarProgramaRota(programa.id, { activo }),
    onSuccess: () => {
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: (forzar: boolean) => api.eliminarProgramaRota(programa.id, { forzar }),
    onSuccess: (res) => {
      const afectadas = res.piezas_afectadas ?? 0;
      toast.success(
        afectadas > 0
          ? `Programa eliminado (${afectadas} pieza${afectadas === 1 ? "" : "s"} huérfana${
              afectadas === 1 ? "" : "s"
            } conservan el nombre).`
          : "Programa eliminado.",
      );
      setConfirmarBorradoForzado(null);
      onCambio();
    },
    onError: (e, forzar) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        !forzar &&
        e.cuerpo &&
        (e.cuerpo as { en_uso?: boolean }).en_uso
      ) {
        const piezas = Number((e.cuerpo as { piezas_afectadas?: number }).piezas_afectadas ?? 0);
        setConfirmarBorradoForzado({ piezasAfectadas: piezas });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  if (editando) {
    return (
      <DialogEditarPrograma
        programa={programa}
        onCerrar={() => setEditando(false)}
        onCambio={onCambio}
      />
    );
  }

  return (
    <>
      <TableRow>
        <TableCell className="align-top">
          <div className="flex items-center gap-2">
            {programa.color && (
              <span
                aria-hidden
                className="inline-block h-3 w-3 rounded-sm border"
                style={{ backgroundColor: programa.color }}
              />
            )}
            <span className="font-medium">{programa.nombre}</span>
          </div>
        </TableCell>
        <TableCell className="align-top text-sm text-muted-foreground">
          {programa.descripcion || <span className="opacity-50">—</span>}
        </TableCell>
        <TableCell className="align-top text-sm">
          {programa.inicio || <span className="text-muted-foreground opacity-50">—</span>}
        </TableCell>
        <TableCell className="align-top text-sm">
          {programa.fin || <span className="text-muted-foreground opacity-50">—</span>}
        </TableCell>
        <TableCell className="text-center align-top">
          <Checkbox
            checked={programa.activo}
            onCheckedChange={(v) => activar.mutate(v === true)}
            disabled={activar.isPending}
            aria-label={`Activar / desactivar ${programa.nombre}`}
          />
        </TableCell>
        <TableCell className="align-top">
          <div className="flex items-center gap-0.5">
            <Tooltip label="Editar">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                aria-label={`Editar ${programa.nombre}`}
                onClick={() => setEditando(true)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </Tooltip>
            <Tooltip label="Borrar">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                aria-label={`Borrar ${programa.nombre}`}
                onClick={async () => {
                  if (
                    await confirmar({
                      mensaje: `¿Borrar el programa «${programa.nombre}»?`,
                      destructivo: true,
                      textoConfirmar: "Borrar",
                    })
                  )
                    borrar.mutate(false);
                }}
                disabled={borrar.isPending}
              >
                {borrar.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </Tooltip>
          </div>
        </TableCell>
      </TableRow>
      {confirmarBorradoForzado && (
        <Dialog open onOpenChange={(o) => !o && setConfirmarBorradoForzado(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Este programa tiene piezas</DialogTitle>
              <DialogDescription>
                «{programa.nombre}» está en uso por {confirmarBorradoForzado.piezasAfectadas}{" "}
                pieza
                {confirmarBorradoForzado.piezasAfectadas === 1 ? "" : "s"}. Si lo borras, las
                piezas conservarán el nombre textual pero ya no tendrás el catálogo.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setConfirmarBorradoForzado(null)}>
                Cancelar
              </Button>
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={() => borrar.mutate(true)}
                disabled={borrar.isPending}
              >
                {borrar.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Borrar igualmente
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

// --- Panel público -----------------------------------------------------------

/**
 * Panel completo del catálogo de programas (campañas evergreen).
 *
 * Reutilizable: lo monta `pages/EventosCobertura.tsx` (hub de Fuentes) como
 * sub-pestaña "Programas". Antes vivía inline en la pestaña "Programas" del
 * Calendario (`pages/Rota.tsx`).
 *
 * La lista es global (sin filtro de marca): los programas son del catálogo
 * editorial de Claro Sports y aplican a toda la rota.
 */
export function PanelProgramas() {
  const queryClient = useQueryClient();
  const [soloActivos, setSoloActivos] = React.useState(false);
  // Filtro de búsqueda (case-insensitive) sobre nombre/descripción.
  const [busqueda, setBusqueda] = React.useState("");
  const clave = ["rota", "programas", soloActivos ? "activos" : "todos"] as const;
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.listarProgramasRota(soloActivos ? { activo: true } : {}, signal),
  });
  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: ["rota", "programas"] });
  };
  const programas = React.useMemo(() => q.data?.programas ?? [], [q.data?.programas]);
  // Filtro local (no toca la API: el backend no expone búsqueda y la lista es corta).
  const programasFiltrados = React.useMemo(() => {
    const term = busqueda.trim().toLowerCase();
    if (!term) return programas;
    return programas.filter(
      (p) =>
        p.nombre.toLowerCase().includes(term) ||
        (p.descripcion ?? "").toLowerCase().includes(term),
    );
  }, [programas, busqueda]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Catálogo de programas</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Campañas evergreen del Excel «PARRILLA 2026» (Álvaro Fidalgo, MUNDIAL,
              Paty Cantú…). Las piezas las referencian por nombre: al renombrar, la
              consola actualiza todas las piezas en una sola transacción.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Checkbox
              id="prog-solo-activos"
              checked={soloActivos}
              onCheckedChange={(v) => setSoloActivos(v === true)}
            />
            <Label htmlFor="prog-solo-activos" className="cursor-pointer font-normal">
              Solo activos
            </Label>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <NuevoPrograma onCreado={invalidar} />
          {/* Búsqueda inline: filtra por nombre/descripción. */}
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por nombre o descripción…"
              className="h-9 pl-8"
              aria-label="Buscar programas"
            />
          </div>
          {q.isPending ? (
            <Skeleton className="h-32 w-full rounded-md" />
          ) : q.isError ? (
            <BloqueError
              titulo="No se pudo cargar el catálogo"
              mensaje={mensajeError(q.error)}
              onReintentar={() => void q.refetch()}
              cargando={q.isFetching}
            />
          ) : programas.length === 0 ? (
            <EstadoVacio
              icono={Search}
              titulo="Sin programas"
              texto="Da de alta un programa con el formulario de arriba para que aparezca en el autocomplete de piezas."
            />
          ) : programasFiltrados.length === 0 ? (
            <EstadoVacio
              icono={Search}
              titulo="Sin resultados"
              texto={`No hay programas que coincidan con «${busqueda}». Borra el filtro para verlos todos.`}
            />
          ) : (
            <div className="overflow-x-auto rounded-md border bg-background">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[14rem]">Nombre</TableHead>
                    <TableHead className="min-w-[18rem]">Descripción</TableHead>
                    <TableHead className="min-w-[8rem]">Inicio</TableHead>
                    <TableHead className="min-w-[8rem]">Fin</TableHead>
                    <TableHead className="min-w-[5rem] text-center">Activo</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {programasFiltrados.map((p) => (
                    <FilaPrograma key={p.id} programa={p} onCambio={invalidar} />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default PanelProgramas;
