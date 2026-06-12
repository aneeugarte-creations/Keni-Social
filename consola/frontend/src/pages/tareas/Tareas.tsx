import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  Hand,
  ListChecks,
  Play,
  Plus,
  RotateCcw,
  Trash2,
  Trophy,
  UserCheck,
  UserPlus,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFecha } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, Contenido, EventoRota } from "@/types";

import { CLAVE_TAREAS } from "./claves";
import { DialogoCrearTarea } from "./DialogoCrearTarea";

// El tablero es COMPARTIDO: late al mismo pulso para que el claim/asignación de un compañero
// se vea sin recargar (igual que el reparto del feed que esto sustituye).
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/** Lente sobre la MISMA lista: el panorama por persona, el pool, lo mío, o todo. */
type Lente = "equipo" | "personas" | "libres" | "mias";
const LENTES: { id: Lente; etiqueta: string }[] = [
  { id: "equipo", etiqueta: "Todo el equipo" },
  { id: "personas", etiqueta: "Por persona" },
  { id: "libres", etiqueta: "Por cubrir" },
  { id: "mias", etiqueta: "Lo mío" },
];

/** Avance de estado de una tarea ya cogida (pendiente → en_curso → hecha). */
const SIGUIENTE: Record<string, { estado: string; etiqueta: string; icono: typeof Play }> = {
  pendiente: { estado: "en_curso", etiqueta: "Empezar", icono: Play },
  en_curso: { estado: "hecha", etiqueta: "Marcar hecha", icono: Check },
};

const PRIORIDAD_CLASE: Record<string, string> = {
  alta: "border-red-500/40 text-red-700 dark:text-red-300",
  media: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  baja: "border-border text-muted-foreground",
};

/** Diálogo "Asignar a…" compartido (manager elige a quién encarga). */
function DialogoAsignar({
  titulo,
  abierto,
  onOpenChange,
  usuarios,
  responsableActual,
  onElegir,
  enviando,
}: {
  titulo: string;
  abierto: boolean;
  onOpenChange: (v: boolean) => void;
  usuarios: { id: string; usuario: string }[];
  responsableActual: string;
  onElegir: (personaId: string) => void;
  enviando: boolean;
}) {
  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Asignar "{titulo}"</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Elige a quién se la encargas; se le avisa en la app.
        </p>
        <div className="max-h-72 space-y-1 overflow-y-auto py-1">
          {usuarios.length === 0 && (
            <p className="px-1 text-sm text-muted-foreground">No hay compañeros para asignar.</p>
          )}
          {usuarios.map((u) => {
            const yaEs = u.id === responsableActual;
            return (
              <button
                key={u.id}
                type="button"
                disabled={enviando || yaEs}
                onClick={() => onElegir(u.id)}
                className={cn(
                  "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm disabled:opacity-100",
                  yaEs
                    ? "border-primary/50 bg-primary/5 text-primary"
                    : "border-border hover:border-foreground/30 hover:bg-accent",
                )}
              >
                <span className="truncate">{u.usuario}</span>
                {yaEs && <span className="ml-2 shrink-0 text-xs">la lleva ahora</span>}
              </button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Un EVENTO «Por cubrir»: un partido/transmisión que nadie ha cogido todavía. No tiene tarea
 * aún; al coger (o que Elias asigne) se crea su registro de cobertura vía `cubrirEvento`.
 */
function TarjetaEventoLibre({
  evento,
  catalogos,
}: {
  evento: EventoRota;
  catalogos: CatalogosContenido | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const usuarios = catalogos?.usuarios ?? [];

  const cubrir = useMutation({
    mutationFn: (responsableId?: string) => api.cubrirEvento(evento.id, responsableId),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const nombre = res?.contenido?.responsable_nombre || "ti";
      toast.success(`"${evento.titulo}" la cubre ${nombre}.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  return (
    <div className="rounded-lg border border-dashed border-border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Trophy className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="font-medium">{evento.titulo}</span>
        <Badge variant="outline" className="border-dashed text-muted-foreground">
          Por cubrir
        </Badge>
        {evento.cambiado && (
          <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
            Cambió de hora
          </Badge>
        )}
        {evento.prioridad && (
          <Badge variant="outline" className={cn("font-normal", PRIORIDAD_CLASE[evento.prioridad])}>
            {evento.prioridad}
          </Badge>
        )}
        {evento.fecha && (
          <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
            <CalendarClock className="h-3.5 w-3.5" />
            {formatearFecha(evento.fecha)}
            {evento.hora ? ` · ${evento.hora}` : ""}
          </span>
        )}
      </div>
      {evento.contenido && (
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{evento.contenido}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => cubrir.mutate(undefined)}
          disabled={cubrir.isPending}
          title="La cubro yo"
          aria-label="La cubro yo"
        >
          <Hand className="h-3.5 w-3.5" />
        </Button>
        {esManager && (
          <Button variant="outline" size="sm" onClick={() => setAsignarAbierto(true)}>
            <UserPlus className="mr-1 h-3.5 w-3.5" />
            Asignar
          </Button>
        )}
      </div>

      <DialogoAsignar
        titulo={evento.titulo}
        abierto={asignarAbierto}
        onOpenChange={setAsignarAbierto}
        usuarios={usuarios}
        responsableActual=""
        onElegir={(id) => cubrir.mutate(id)}
        enviando={cubrir.isPending}
      />
    </div>
  );
}

/** Una TAREA ya con dueño (cobertura cogida o encargo del equipo): estado, responsable, acciones. */
function TarjetaTarea({
  tarea,
  catalogos,
}: {
  tarea: Contenido;
  catalogos: CatalogosContenido | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const libre = !tarea.responsable_id;
  const esMia = Boolean(usuario && tarea.responsable_id === usuario.id);
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const usuarios = catalogos?.usuarios ?? [];

  const invalidar = () => queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
  const conError = (e: unknown) => {
    void invalidar();
    toast.error(mensajeError(e));
  };

  const coger = useMutation({
    mutationFn: () => api.cogerContenido(tarea.id),
    onSuccess: () => {
      void invalidar();
      toast.success(`"${tarea.titulo}" es tuya: el equipo ya lo ve.`);
    },
    onError: conError,
  });
  const soltar = useMutation({
    mutationFn: () => api.soltarContenido(tarea.id),
    onSuccess: () => {
      void invalidar();
      toast.success(`"${tarea.titulo}" vuelve a estar libre.`);
    },
    onError: conError,
  });
  const asignar = useMutation({
    mutationFn: (personaId: string) => api.asignarContenido(tarea.id, personaId),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void invalidar();
      const nombre = res?.contenido?.responsable_nombre || "esa persona";
      toast.success(`"${tarea.titulo}" asignada a ${nombre}: se le avisa en la app.`);
    },
    onError: conError,
  });
  const cambiarEstado = useMutation({
    mutationFn: (estado: string) => api.actualizarContenido(tarea.id, { estado }),
    onSuccess: () => void invalidar(),
    onError: conError,
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarContenido(tarea.id),
    onSuccess: () => {
      setConfirmarBorrado(false);
      void invalidar();
      toast.success("Tarea borrada.");
    },
    onError: conError,
  });

  const avance = SIGUIENTE[tarea.estado];
  const esCobertura = Boolean(tarea.evento_id);

  return (
    <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        {esCobertura && <Trophy className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <span className="font-medium">{tarea.titulo}</span>
        {libre ? (
          <Badge variant="outline" className="border-dashed text-muted-foreground">
            Libre
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className={cn(
              "gap-1 font-normal",
              esMia
                ? "border-primary/50 text-primary"
                : "border-violet-500/40 text-violet-700 dark:text-violet-300",
            )}
          >
            <UserCheck className="h-3 w-3" />
            {esMia ? "Tuya" : tarea.responsable_nombre}
          </Badge>
        )}
        {tarea.estado === "en_curso" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            En curso
          </Badge>
        )}
        {tarea.estado === "hecha" && (
          <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300">
            Hecha
          </Badge>
        )}
        {tarea.prioridad && (
          <Badge variant="outline" className={cn("font-normal", PRIORIDAD_CLASE[tarea.prioridad])}>
            {tarea.prioridad}
          </Badge>
        )}
        {tarea.fecha_objetivo && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-sm",
              tarea.vencido ? "text-red-700 dark:text-red-300" : "text-muted-foreground",
            )}
          >
            <CalendarClock className="h-3.5 w-3.5" />
            {formatearFecha(tarea.fecha_objetivo)}
            {tarea.hora_objetivo ? ` · ${tarea.hora_objetivo}` : ""}
          </span>
        )}
      </div>

      {tarea.descripcion && (
        <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
          {tarea.descripcion}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {libre && (
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => coger.mutate()}
            disabled={coger.isPending}
            title={esCobertura ? "La cubro yo" : "Coger"}
            aria-label={esCobertura ? "La cubro yo" : "Coger"}
          >
            <Hand className="h-3.5 w-3.5" />
          </Button>
        )}
        {avance && !libre && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiarEstado.mutate(avance.estado)}
            disabled={cambiarEstado.isPending}
          >
            <avance.icono className="mr-1 h-3.5 w-3.5" />
            {avance.etiqueta}
          </Button>
        )}
        {tarea.estado === "hecha" && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiarEstado.mutate("pendiente")}
            disabled={cambiarEstado.isPending}
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" />
            Reabrir
          </Button>
        )}
        {!libre && (esMia || esManager) && (
          <Button variant="outline" size="sm" onClick={() => soltar.mutate()} disabled={soltar.isPending}>
            <Hand className="mr-1 h-3.5 w-3.5" />
            Soltar
          </Button>
        )}
        {esManager && (
          <Button variant="outline" size="sm" onClick={() => setAsignarAbierto(true)}>
            <UserPlus className="mr-1 h-3.5 w-3.5" />
            {libre ? "Asignar" : "Reasignar"}
          </Button>
        )}
        {esManager && !esCobertura && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => setConfirmarBorrado(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      <DialogoAsignar
        titulo={tarea.titulo}
        abierto={asignarAbierto}
        onOpenChange={setAsignarAbierto}
        usuarios={usuarios}
        responsableActual={tarea.responsable_id}
        onElegir={(id) => asignar.mutate(id)}
        enviando={asignar.isPending}
      />

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar "{tarea.titulo}"</DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmarBorrado(false)} disabled={borrar.isPending}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => borrar.mutate()} disabled={borrar.isPending}>
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Un ítem de la lista unificada: o un evento aún por cubrir, o una tarea (cobertura o encargo). */
type Item =
  | { kind: "evento"; clave: string; orden: string; evento: EventoRota }
  | { kind: "tarea"; clave: string; orden: string; tarea: Contenido };

/** El reparto de una persona en el panorama: lo que lleva activo, lo empezado y lo cerrado. */
type CargaPersona = {
  id: string;
  nombre: string;
  activas: Contenido[];
  enCurso: number;
  hechas: number;
};

/** Vista previa de «lo que lleva»: cada título es su propio chip (truncado, pero entero en el DOM). */
function PreviewTitulos({ titulos }: { titulos: string[] }) {
  if (titulos.length === 0)
    return <span className="text-sm text-muted-foreground">Sin tareas — libre para coger</span>;
  const MAX = 3;
  const visibles = titulos.slice(0, MAX);
  const resto = titulos.length - visibles.length;
  return (
    <div className="flex flex-wrap items-center gap-1">
      {visibles.map((t, i) => (
        <span
          key={i}
          className="max-w-[16rem] truncate rounded border border-border bg-muted/40 px-1.5 py-0.5 text-xs"
        >
          {t}
        </span>
      ))}
      {resto > 0 && <span className="text-xs text-muted-foreground">+{resto} más</span>}
    </div>
  );
}

/**
 * Una fila del panorama (el pool «Por cubrir» o una persona): los conteos de un vistazo y, al
 * desplegar, las tarjetas reales para coger/reasignar/avanzar sin salir de la tabla.
 */
function FilaPanorama({
  abierta,
  onToggle,
  expandible,
  icono: Icono,
  nombre,
  destacar,
  carga,
  enCurso,
  hechas,
  titulos,
  detalle,
}: {
  abierta: boolean;
  onToggle: () => void;
  expandible: boolean;
  icono: typeof Hand;
  nombre: string;
  destacar?: boolean;
  carga: number;
  enCurso: number | null;
  hechas: number | null;
  titulos: string[];
  detalle: React.ReactNode;
}) {
  return (
    <>
      <TableRow
        className={cn(destacar && "bg-muted/30", expandible && "cursor-pointer")}
        onClick={expandible ? onToggle : undefined}
      >
        <TableCell className="font-medium">
          <div className="flex items-center gap-2">
            {expandible ? (
              abierta ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              )
            ) : (
              <span className="inline-block w-4 shrink-0" />
            )}
            <Icono className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{nombre}</span>
          </div>
        </TableCell>
        <TableCell className="text-center">
          <Badge
            variant="outline"
            className={cn("px-1.5 py-0 tabular-nums", carga === 0 && "text-muted-foreground")}
          >
            {carga}
          </Badge>
        </TableCell>
        <TableCell className="text-center tabular-nums text-muted-foreground">
          {enCurso === null ? "—" : enCurso}
        </TableCell>
        <TableCell className="text-center tabular-nums text-muted-foreground">
          {hechas === null ? "—" : hechas}
        </TableCell>
        <TableCell>
          <PreviewTitulos titulos={titulos} />
        </TableCell>
      </TableRow>
      {abierta && expandible && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={5} className="bg-muted/20">
            <div className="space-y-2 py-1">{detalle}</div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

/**
 * Panorama POR PERSONA (la cabina de Elias): una TABLA con quién lleva qué de un vistazo, para
 * repartir y equilibrar carga. Una fila «Por cubrir» con el pool sin dueño y, debajo, una fila por
 * cada miembro del equipo con su carga (activas / en curso / hechas) y una vista de lo que lleva.
 * Más cargados arriba (el cuello de botella salta a la vista). Cada fila se despliega para
 * coger/reasignar sin salir del panorama. Los libres (sin nada) salen también, para repartirles.
 */
function PanoramaPorPersona({
  tareas,
  eventosLibres,
  catalogos,
}: {
  tareas: Contenido[];
  eventosLibres: EventoRota[];
  catalogos: CatalogosContenido | undefined;
}) {
  const [abiertas, setAbiertas] = React.useState<Set<string>>(() => new Set());
  const alternar = (clave: string) =>
    setAbiertas((prev) => {
      const next = new Set(prev);
      if (next.has(clave)) next.delete(clave);
      else next.add(clave);
      return next;
    });

  const usuarios = catalogos?.usuarios ?? [];
  const conResponsable = tareas.filter((t) => t.responsable_id);
  const sinResponsable = tareas.filter((t) => !t.responsable_id);

  // Nombre por id: lo del catálogo manda; si falta, el que vino sellado en la tarea.
  const nombrePorId = new Map<string, string>();
  for (const u of usuarios) nombrePorId.set(u.id, u.usuario);
  for (const t of conResponsable) {
    if (!nombrePorId.has(t.responsable_id) && t.responsable_nombre)
      nombrePorId.set(t.responsable_id, t.responsable_nombre);
  }

  // Sembramos con TODO el equipo para que los libres salgan; añadimos responsables externos.
  const ids = new Set<string>(usuarios.map((u) => u.id));
  for (const t of conResponsable) ids.add(t.responsable_id);

  const ordenFecha = (a: Contenido, b: Contenido) =>
    (a.fecha_objetivo || "9999-99-99").localeCompare(b.fecha_objetivo || "9999-99-99");

  const cargas: CargaPersona[] = [...ids]
    .map((id) => {
      const suyas = conResponsable.filter((t) => t.responsable_id === id);
      const activas = suyas.filter((t) => t.estado !== "hecha").sort(ordenFecha);
      return {
        id,
        nombre: nombrePorId.get(id) || "Sin nombre",
        activas,
        enCurso: activas.filter((t) => t.estado === "en_curso").length,
        hechas: suyas.filter((t) => t.estado === "hecha").length,
      };
    })
    // Más cargados arriba (Elias ve el cuello de botella); a igualdad, por nombre.
    .sort((a, b) => b.activas.length - a.activas.length || a.nombre.localeCompare(b.nombre));

  // El pool «Por cubrir»: eventos sin tarea + encargos/coberturas aún sin dueño, por fecha.
  const porCubrir: Item[] = [
    ...sinResponsable.map((t) => ({
      kind: "tarea" as const,
      clave: `t-${t.id}`,
      orden: t.fecha_objetivo || "9999-99-99",
      tarea: t,
    })),
    ...eventosLibres.map((e) => ({
      kind: "evento" as const,
      clave: `e-${e.id}`,
      orden: e.fecha || "9999-99-99",
      evento: e,
    })),
  ].sort((a, b) => a.orden.localeCompare(b.orden));
  const tituloItem = (i: Item) => (i.kind === "evento" ? i.evento.titulo : i.tarea.titulo);

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[30%]">Quién</TableHead>
            <TableHead className="w-16 text-center">Carga</TableHead>
            <TableHead className="w-20 text-center">En curso</TableHead>
            <TableHead className="w-16 text-center">Hechas</TableHead>
            <TableHead>Lo que lleva</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {/* El pool sin dueño va primero: es lo que urge repartir. */}
          <FilaPanorama
            abierta={abiertas.has("__pool__")}
            onToggle={() => alternar("__pool__")}
            expandible={porCubrir.length > 0}
            icono={Hand}
            nombre="Por cubrir"
            destacar
            carga={porCubrir.length}
            enCurso={null}
            hechas={null}
            titulos={porCubrir.map(tituloItem)}
            detalle={porCubrir.map((i) =>
              i.kind === "evento" ? (
                <TarjetaEventoLibre key={i.clave} evento={i.evento} catalogos={catalogos} />
              ) : (
                <TarjetaTarea key={i.clave} tarea={i.tarea} catalogos={catalogos} />
              ),
            )}
          />
          {cargas.map((c) => (
            <FilaPanorama
              key={c.id}
              abierta={abiertas.has(c.id)}
              onToggle={() => alternar(c.id)}
              expandible={c.activas.length > 0}
              icono={UserCheck}
              nombre={c.nombre}
              carga={c.activas.length}
              enCurso={c.enCurso}
              hechas={c.hechas}
              titulos={c.activas.map((t) => t.titulo)}
              detalle={c.activas.map((t) => (
                <TarjetaTarea key={t.id} tarea={t} catalogos={catalogos} />
              ))}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

/**
 * Página de TAREAS del equipo (ClaroSports): la lista compartida que sustituye al WhatsApp.
 *
 * Se LLENA SOLA con los eventos/partidos a cubrir (los que entran por Fuentes o se añaden aquí)
 * y los muestra ordenados por fecha como «Por cubrir»; el equipo los coge o Elias los reparte.
 * Conviven los encargos sueltos (tareas sin evento). El dueño de una cobertura se registra como
 * una tarea (clase='tarea') enlazada al evento: el evento es la unidad canónica, sin duplicar.
 */
export default function Tareas() {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const [lente, setLente] = React.useState<Lente>("equipo");
  const [crearAbierto, setCrearAbierto] = React.useState(false);

  const marca = marcaActiva && marcaActiva !== MARCA_ACTIVA_TODAS ? marcaActiva : undefined;
  const hoy = new Date().toISOString().slice(0, 10);

  const tareasQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
  });
  const eventosQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "eventos", marca ?? "todas"],
    queryFn: ({ signal }) => api.rotaEventos({ desde: hoy, marca }, signal),
    ...REFRESCO,
  });

  const tareas = tareasQuery.data?.contenidos ?? [];
  const catalogos = tareasQuery.data?.catalogos;
  const cargando = tareasQuery.isLoading || eventosQuery.isLoading;

  // Eventos a cubrir = los coverables (no "no_cubrir") que aún NO tienen tarea de cobertura.
  const eventosConTarea = new Set(tareas.map((t) => t.evento_id).filter(Boolean));
  const eventosLibres = (eventosQuery.data?.eventos ?? []).filter(
    (e) => e.tipo_cobertura !== "no_cubrir" && !eventosConTarea.has(e.id),
  );

  // Lista unificada, ordenada por fecha (las sin fecha, al final).
  const conOrden = (f: string) => f || "9999-99-99";
  const items: Item[] = [
    ...tareas.map((t) => ({
      kind: "tarea" as const,
      clave: `t-${t.id}`,
      orden: conOrden(t.fecha_objetivo),
      tarea: t,
    })),
    ...eventosLibres.map((e) => ({
      kind: "evento" as const,
      clave: `e-${e.id}`,
      orden: conOrden(e.fecha),
      evento: e,
    })),
  ].sort((a, b) => a.orden.localeCompare(b.orden));

  const cumpleLente = (i: Item) => {
    if (lente === "libres") return i.kind === "evento" || !i.tarea.responsable_id;
    if (lente === "mias")
      return i.kind === "tarea" && Boolean(usuario && i.tarea.responsable_id === usuario.id);
    return true;
  };
  const visibles = items.filter(cumpleLente);

  // Tres grupos para que «se organice»: lo que falta por cubrir, lo que está en marcha, lo hecho.
  const grupos: { etiqueta: string; items: Item[] }[] = [
    {
      etiqueta: "Por cubrir",
      items: visibles.filter((i) => i.kind === "evento" || !i.tarea.responsable_id),
    },
    {
      etiqueta: "En marcha",
      items: visibles.filter(
        (i) => i.kind === "tarea" && i.tarea.responsable_id && i.tarea.estado !== "hecha",
      ),
    },
    {
      etiqueta: "Hechas",
      items: visibles.filter((i) => i.kind === "tarea" && i.tarea.estado === "hecha"),
    },
  ];
  const conteoPorCubrir = items.filter(
    (i) => i.kind === "evento" || !i.tarea.responsable_id,
  ).length;

  const pintar = (i: Item) =>
    i.kind === "evento" ? (
      <TarjetaEventoLibre key={i.clave} evento={i.evento} catalogos={catalogos} />
    ) : (
      <TarjetaTarea key={i.clave} tarea={i.tarea} catalogos={catalogos} />
    );

  return (
    <>
      <TituloPagina titulo="Tareas del equipo" icono={ListChecks} />
      <AccionesPagina>
        <Button size="sm" onClick={() => setCrearAbierto(true)}>
          <Plus className="mr-1 h-4 w-4" />
          Añadir
        </Button>
      </AccionesPagina>

      <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {LENTES.map((l) => (
          <Button
            key={l.id}
            variant={lente === l.id ? "default" : "outline"}
            size="sm"
            onClick={() => setLente(l.id)}
          >
            {l.etiqueta}
            {l.id === "libres" && conteoPorCubrir > 0 && (
              <Badge variant="outline" className="ml-1.5 bg-background px-1.5 py-0 tabular-nums">
                {conteoPorCubrir}
              </Badge>
            )}
          </Button>
        ))}
      </div>

      {cargando && <p className="text-sm text-muted-foreground">Cargando…</p>}

      {!cargando && lente === "personas" && (
        <PanoramaPorPersona
          tareas={tareas}
          eventosLibres={eventosLibres}
          catalogos={catalogos}
        />
      )}

      {!cargando && lente !== "personas" && visibles.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {lente === "mias"
              ? "No tienes nada asignado. Coge algo de «Por cubrir»."
              : lente === "libres"
                ? "No hay nada por cubrir ahora mismo."
                : "Aún no hay partidos ni tareas. Súbelos en Fuentes o añádelos aquí."}
          </p>
        </div>
      )}

      {!cargando &&
        lente !== "personas" &&
        visibles.length > 0 &&
        grupos.map((g) =>
          g.items.length === 0 ? null : (
            <section key={g.etiqueta} className="space-y-2">
              <h2 className="text-sm font-medium text-muted-foreground">
                {g.etiqueta}
                <span className="ml-1.5 tabular-nums">({g.items.length})</span>
              </h2>
              <div className="space-y-2">{g.items.map(pintar)}</div>
            </section>
          ),
        )}

      <DialogoCrearTarea
        abierto={crearAbierto}
        onOpenChange={setCrearAbierto}
        catalogos={catalogos}
        marca={marca}
      />
      </div>
    </>
  );
}
