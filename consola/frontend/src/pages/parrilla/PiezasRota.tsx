/**
 * Piezas de la parrilla (#150 PARRILLA 2026.xlsx): cada pieza es UN post individual,
 * atado a un evento o suelto (campaña evergreen). CRUD completo: listar (tabla),
 * crear/editar (diálogo), duplicar y eliminar.
 *
 * Solo lectura del modelo desde `/api/rota/piezas`; las mutaciones invalidan la
 * caché. Sigue el patrón del repo: tanstack-query + shadcn + EstadoVacio/BloqueError;
 * toasts (sonner); modo claro/oscuro; texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, ListChecks, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
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
import { api, ApiError } from "@/lib/api";
import type {
  CuerpoCrearPiezaRota,
  EstadoPieza,
  MiembroRota,
  PiezaRota,
} from "@/types";

const CABECERA = {
  titulo: "Piezas",
  descripcion:
    "Cada pieza es un post individual de la parrilla (atado a un evento o suelto, campaña evergreen). Crea, edita, duplica o elimina piezas con su programa, red, tipo, día y responsable.",
};

/** Clave raíz de React Query para invalidar el listado de piezas en bloque. */
const CLAVE_PIEZAS = ["rota", "piezas"] as const;

/** Etiqueta + variante de badge por estado de la pieza. */
const ESTADO_META: Record<EstadoPieza, { etiqueta: string; variante: "secondary" | "aviso" | "ok" }> = {
  pendiente: { etiqueta: "Pendiente", variante: "secondary" },
  en_curso: { etiqueta: "En curso", variante: "aviso" },
  listo: { etiqueta: "Listo", variante: "aviso" },
  publicado: { etiqueta: "Publicado", variante: "ok" },
};

const ESTADOS: EstadoPieza[] = ["pendiente", "en_curso", "listo", "publicado"];

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Valores editables del formulario (subconjunto útil del modelo de pieza). */
interface FormPieza {
  programa: string;
  red_social: string;
  tipo_pieza: string;
  contenido_sugerido: string;
  dia: string;
  hora_post: string;
  estado: EstadoPieza;
  responsable_id: string;
  enlace: string;
  notas: string;
  always_on: boolean;
}

const FORM_VACIO: FormPieza = {
  programa: "",
  red_social: "",
  tipo_pieza: "",
  contenido_sugerido: "",
  dia: "",
  hora_post: "",
  estado: "pendiente",
  responsable_id: "",
  enlace: "",
  notas: "",
  always_on: false,
};

function formDesdePieza(p: PiezaRota): FormPieza {
  return {
    programa: p.programa,
    red_social: p.red_social,
    tipo_pieza: p.tipo_pieza,
    contenido_sugerido: p.contenido_sugerido,
    dia: p.dia,
    hora_post: p.hora_post,
    estado: p.estado,
    responsable_id: p.responsable_id,
    enlace: p.enlace,
    notas: p.notas,
    always_on: p.always_on,
  };
}

const SIN_RESPONSABLE = "__sin__";

/** Diálogo de alta/edición de una pieza. `pieza` null => alta. */
function DialogoPieza({
  abierto,
  onCerrar,
  pieza,
  equipo,
}: {
  abierto: boolean;
  onCerrar: () => void;
  pieza: PiezaRota | null;
  equipo: MiembroRota[];
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = React.useState<FormPieza>(FORM_VACIO);

  // Sincroniza el formulario al abrir (alta = vacío; edición = datos de la pieza).
  React.useEffect(() => {
    if (abierto) setForm(pieza ? formDesdePieza(pieza) : FORM_VACIO);
  }, [abierto, pieza]);

  const set = <K extends keyof FormPieza>(clave: K, valor: FormPieza[K]) =>
    setForm((f) => ({ ...f, [clave]: valor }));

  function cuerpo(): CuerpoCrearPiezaRota {
    return {
      programa: form.programa.trim(),
      red_social: form.red_social.trim(),
      tipo_pieza: form.tipo_pieza.trim(),
      contenido_sugerido: form.contenido_sugerido.trim(),
      dia: form.dia,
      hora_post: form.hora_post.trim(),
      estado: form.estado,
      responsable_id: form.responsable_id,
      enlace: form.enlace.trim(),
      notas: form.notas.trim(),
      always_on: form.always_on,
    };
  }

  const guardar = useMutation({
    mutationFn: () =>
      pieza ? api.actualizarPiezaRota(pieza.id, cuerpo()) : api.crearPiezaRota(cuerpo()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      toast.success(pieza ? "Pieza actualizada" : "Pieza creada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // El backend exige al menos uno entre programa / contenido (o evento). Aquí, para
  // piezas sueltas, pedimos al menos programa o contenido sugerido.
  const puedeGuardar =
    (form.programa.trim() !== "" || form.contenido_sugerido.trim() !== "") && !guardar.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ListChecks className="h-5 w-5" />
            {pieza ? "Editar pieza" : "Nueva pieza"}
          </DialogTitle>
          <DialogDescription>
            Indica al menos un <strong>programa</strong> o un <strong>contenido sugerido</strong>.
            El resto de campos son opcionales.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="pieza-programa">Programa / campaña</Label>
              <Input
                id="pieza-programa"
                value={form.programa}
                onChange={(e) => set("programa", e.target.value)}
                placeholder="Álvaro Fidalgo, MUNDIAL, Paty Cantú…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-red">Red social</Label>
              <Input
                id="pieza-red"
                value={form.red_social}
                onChange={(e) => set("red_social", e.target.value)}
                placeholder="FB, IG, X / HISTORIA / WEB…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-tipo">Tipo de pieza</Label>
              <Input
                id="pieza-tipo"
                value={form.tipo_pieza}
                onChange={(e) => set("tipo_pieza", e.target.value)}
                placeholder="IMAGEN / VIDEO / REEL / NOTA…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-estado">Estado</Label>
              <Select
                value={form.estado}
                onValueChange={(v) => set("estado", v as EstadoPieza)}
              >
                <SelectTrigger id="pieza-estado">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ESTADOS.map((e) => (
                    <SelectItem key={e} value={e}>
                      {ESTADO_META[e].etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-dia">Día</Label>
              <Input
                id="pieza-dia"
                type="date"
                value={form.dia}
                onChange={(e) => set("dia", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-hora">Hora del post</Label>
              <Input
                id="pieza-hora"
                value={form.hora_post}
                onChange={(e) => set("hora_post", e.target.value)}
                placeholder="16:00 / 5:15 LINK VIVO / TBD"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-responsable">Responsable</Label>
              <Select
                value={form.responsable_id || SIN_RESPONSABLE}
                onValueChange={(v) => set("responsable_id", v === SIN_RESPONSABLE ? "" : v)}
              >
                <SelectTrigger id="pieza-responsable">
                  <SelectValue placeholder="Sin asignar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
                  {equipo.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pieza-enlace">Enlace</Label>
              <Input
                id="pieza-enlace"
                value={form.enlace}
                onChange={(e) => set("enlace", e.target.value)}
                placeholder="URL del post publicado (opcional)"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="pieza-contenido">Contenido sugerido</Label>
            <Textarea
              id="pieza-contenido"
              value={form.contenido_sugerido}
              onChange={(e) => set("contenido_sugerido", e.target.value)}
              placeholder="Clip del gol, resumen 1 min, frase del DT…"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="pieza-notas">Notas</Label>
            <Textarea
              id="pieza-notas"
              value={form.notas}
              onChange={(e) => set("notas", e.target.value)}
              placeholder="Notas internas de coordinación (opcional)"
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.always_on}
              onChange={(e) => set("always_on", e.target.checked)}
              className="h-4 w-4 rounded border-border"
            />
            Perenne (always-on, sin fecha fija)
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {pieza ? "Guardar cambios" : "Crear pieza"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Una fila de la tabla de piezas con sus acciones (editar / duplicar / eliminar). */
function FilaPieza({
  pieza,
  onEditar,
}: {
  pieza: PiezaRota;
  onEditar: (p: PiezaRota) => void;
}) {
  const queryClient = useQueryClient();

  const duplicar = useMutation({
    mutationFn: () => api.duplicarPiezaRota(pieza.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      toast.success("Pieza duplicada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminar = useMutation({
    mutationFn: () => api.eliminarPiezaRota(pieza.id),
    onSuccess: (res) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      toast.success(res?.mensaje ?? "Pieza eliminada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const estado = ESTADO_META[pieza.estado] ?? ESTADO_META.pendiente;
  const titulo = pieza.programa || pieza.contenido_sugerido || "(sin título)";

  return (
    <TableRow>
      <TableCell className="max-w-[22rem]">
        <p className="truncate font-medium" title={titulo}>
          {titulo}
        </p>
        {pieza.contenido_sugerido && pieza.programa && (
          <p className="truncate text-xs text-muted-foreground" title={pieza.contenido_sugerido}>
            {pieza.contenido_sugerido}
          </p>
        )}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">{pieza.red_social || "—"}</TableCell>
      <TableCell className="text-sm text-muted-foreground">{pieza.tipo_pieza || "—"}</TableCell>
      <TableCell className="whitespace-nowrap text-sm tabular-nums text-muted-foreground">
        {pieza.always_on ? "Perenne" : pieza.dia || "—"}
        {pieza.hora_post && <span className="ml-1">· {pieza.hora_post}</span>}
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {pieza.responsable_nombre || "Sin asignar"}
      </TableCell>
      <TableCell>
        <Badge variant={estado.variante}>{estado.etiqueta}</Badge>
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Editar pieza"
            title="Editar"
            onClick={() => onEditar(pieza)}
          >
            <Pencil className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Duplicar pieza"
            title="Duplicar"
            onClick={() => duplicar.mutate()}
            disabled={duplicar.isPending}
          >
            {duplicar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Eliminar pieza"
            title="Eliminar"
            className="text-muted-foreground hover:text-destructive"
            onClick={() => eliminar.mutate()}
            disabled={eliminar.isPending}
          >
            {eliminar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

export default function PiezasRota() {
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [editando, setEditando] = React.useState<PiezaRota | null>(null);

  const piezasQuery = useQuery({
    queryKey: CLAVE_PIEZAS,
    queryFn: ({ signal }) => api.listarPiezasRota({}, signal),
  });

  // Equipo para el selector de responsable (todos, incl. quienes no cubren turnos).
  const equipoQuery = useQuery({
    queryKey: ["rota", "equipo", "todos"],
    queryFn: ({ signal }) => api.rotaEquipoTodos(signal),
  });
  const equipo = equipoQuery.data?.equipo ?? [];

  function abrirAlta() {
    setEditando(null);
    setDialogoAbierto(true);
  }
  function abrirEdicion(p: PiezaRota) {
    setEditando(p);
    setDialogoAbierto(true);
  }

  const acciones = (
    <Button size="sm" onClick={abrirAlta}>
      <Plus className="h-4 w-4" />
      Nueva pieza
    </Button>
  );

  const piezas = piezasQuery.data?.piezas ?? [];

  return (
    <>
      <PageHeader {...CABECERA} acciones={acciones} />

      {piezasQuery.isPending ? (
        <Skeleton className="h-64 w-full rounded-md" />
      ) : piezasQuery.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las piezas"
          mensaje={mensajeError(piezasQuery.error)}
          onReintentar={() => void piezasQuery.refetch()}
          cargando={piezasQuery.isFetching}
        />
      ) : piezas.length === 0 ? (
        <EstadoVacio
          icono={ListChecks}
          titulo="Aún no hay piezas"
          texto="Crea la primera pieza de la parrilla con el botón de arriba."
          accion={
            <Button size="sm" onClick={abrirAlta}>
              <Plus className="h-4 w-4" />
              Nueva pieza
            </Button>
          }
        />
      ) : (
        <div className="rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pieza</TableHead>
                <TableHead>Red</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Cuándo</TableHead>
                <TableHead>Responsable</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Acciones</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {piezas.map((p) => (
                <FilaPieza key={p.id} pieza={p} onEditar={abrirEdicion} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <DialogoPieza
        abierto={dialogoAbierto}
        onCerrar={() => setDialogoAbierto(false)}
        pieza={editando}
        equipo={equipo}
      />
    </>
  );
}
