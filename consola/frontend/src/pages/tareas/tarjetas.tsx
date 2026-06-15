import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Hand,
  Play,
  Trash2,
  UserCheck,
  UserMinus,
  UserPlus,
  X,
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
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFecha, minutosHastaEvento, posicionTemporal } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type {
  CatalogosContenido,
  Contenido,
  EventoRota,
  TipoCoberturaEvento,
} from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { CLAVE_TAREAS } from "./claves";
import { DialogoAsignar } from "./dialogos";
import { IconoEvento } from "./icono-evento";
import { PLANTILLA_DEFECTO, type PlantillaGuion } from "./guion";
import { etiquetaRol, type RolCobertura, ROLES_COBERTURA, rolesCubiertos } from "./roles";
import type { Cobertura } from "./tipos";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";

/**
 * Umbral (minutos) de la fase PRE-LIVE del semáforo: cuando falta ≤ esto para el pitido, el evento
 * deja de ser un «Programado» plano y pasa a «Empieza en X min» (ámbar). 120' ≈ la antesala típica
 * (precalentamiento + previa) en que el equipo ya debería estar moviéndose.
 */
const UMBRAL_PRELIVE_MIN = 120;

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

/**
 * Semáforo de cobertura: el equipo NO marca estados a mano (les hace perder tiempo); el estado
 * se deriva de la fecha/hora del evento (su reloj maestro es la hora de inicio del partido):
 *   · gris  «Programado»     → aún falta mucho
 *   · ámbar «Empieza en X min» → PRE-LIVE: el pitido está cerca (≤ 2 h) → la antesala, a moverse
 *   · verde «En vivo»        → mientras transcurre el evento (punto verde)
 *   · tick  «Cubierto»       → ya pasó (completado → ✓)
 *
 * Por defecto se pinta como ETIQUETA con texto (siempre visible, no se confunde con el color del
 * avatar). En la fila colapsada se usa `compacto` (solo el punto/tick) para no recargar el rundown:
 * el punto se tiñe de ámbar en PRE-LIVE para que la cuenta atrás se note de un vistazo.
 */
export function SemaforoCobertura({
  fecha,
  hora,
  compacto = false,
}: {
  fecha?: string | null;
  hora?: string | null;
  compacto?: boolean;
}) {
  const pos = posicionTemporal(fecha, hora);
  const completado = pos === "despues";
  const envivo = pos === "durante";
  // PRE-LIVE: aún no empieza (pos "antes") pero el pitido está a ≤ 2 h → cuenta atrás en ámbar.
  const min = minutosHastaEvento(fecha, hora);
  const preLive = pos === "antes" && min != null && min > 0 && min <= UMBRAL_PRELIVE_MIN;
  // `titulo`: estado corto (tooltip del punto compacto). `texto`: etiqueta del badge (con la cuenta).
  const titulo = envivo
    ? "En vivo"
    : completado
      ? "Cubierto"
      : preLive
        ? "Empieza pronto"
        : "Programado";
  const texto = preLive ? `Empieza en ${min} min` : titulo;
  const claseBadge =
    envivo || completado
      ? "border-emerald-500/50 text-emerald-700 dark:text-emerald-300"
      : preLive
        ? "border-amber-500/50 text-amber-700 dark:text-amber-300"
        : "text-muted-foreground";
  const dot = envivo
    ? "bg-emerald-500"
    : preLive
      ? "bg-amber-500"
      : "bg-slate-400 dark:bg-slate-500";

  if (compacto) {
    return completado ? (
      <span title={titulo} aria-label={titulo} className="inline-flex shrink-0">
        <Check className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden />
      </span>
    ) : (
      <span
        title={titulo}
        aria-label={titulo}
        className={cn("inline-block h-2.5 w-2.5 shrink-0 rounded-full", dot)}
      />
    );
  }
  return (
    <Badge variant="outline" title={texto} className={cn("gap-1.5 font-normal", claseBadge)}>
      {completado ? (
        <Check className="h-3.5 w-3.5 shrink-0" aria-hidden />
      ) : (
        <span className={cn("h-2 w-2 shrink-0 rounded-full", dot)} />
      )}
      {texto}
    </Badge>
  );
}

/**
 * GUION DEL PARTIDO dentro de la cobertura: el run-of-show por fases (Antes / Durante / Después)
 * como CHECKLIST DE REFERENCIA NEUTRA (mismo idioma visual del tablero: outline gris). NO es un
 * tablero de estado ni duplica la cobertura: cada entregable es un bullet NEUTRO con su etiqueta de
 * rol (Foto/Video/Texto/Live) que solo RECUERDA qué suele producirse en cada fase. El ÚNICO
 * indicador de qué roles están cubiertos es `RolesCubiertos` (el semáforo agregado), no el guion.
 *
 * Va COLAPSADO por defecto (toggle con chevron, estilo plataforma) para no separar el resumen
 * «Cubren:» de las tarjetas accionables. Respeta el `tipo_cobertura` del evento: en «solo imágenes»
 * (sin señal) oculta la fase «Durante» (entregables de directo: Live/Video) que no aplican; en
 * «transmisión»/desconocido pinta el guion completo. La plantilla por TAMAÑO de partido es un dial
 * preparado (`plantillaParaTipo`); hoy siempre usa el default ("Partido normal").
 */
export function GuionPartido({
  tipoCobertura,
  plantilla = PLANTILLA_DEFECTO,
}: {
  tipoCobertura?: TipoCoberturaEvento | null;
  plantilla?: PlantillaGuion;
}) {
  const [abierto, setAbierto] = React.useState(false);
  // «Solo imágenes»: sin señal de directo → la fase «Durante» (Live/Video) no aplica; se oculta.
  const fases =
    tipoCobertura === "imagenes" ? plantilla.fases.filter((f) => f.id !== "vivo") : plantilla.fases;
  return (
    <section aria-label="Guion del partido" className="rounded-md border border-border bg-card/40">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="flex w-full items-center gap-1.5 p-2.5 text-left"
      >
        {abierto ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <ClipboardList className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="text-xs font-medium text-muted-foreground">Guion del partido</span>
        <Badge variant="outline" className="ml-auto font-normal text-muted-foreground">
          {plantilla.etiqueta}
        </Badge>
      </button>
      {abierto && (
        <div className="grid gap-2.5 px-2.5 pb-2.5 sm:grid-cols-3">
          {fases.map((fase) => (
            <div key={fase.id} className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {fase.etiqueta}
              </p>
              <ul className="space-y-0.5">
                {fase.entregables.map((e) => (
                  <li key={e.titulo} className="flex items-center gap-1.5 text-xs">
                    <span
                      className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/40"
                      aria-hidden
                    />
                    <span className="truncate text-muted-foreground">{e.titulo}</span>
                    {e.rol && (
                      <span className="shrink-0 text-[10px] text-muted-foreground">
                        · {etiquetaRol(e.rol)}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * Selector pequeño de ROL de cobertura (Foto/Video/Texto/Live), estilo plataforma (outline gris):
 * cuatro botones segmentados, uno marcado. Decide el `formato` con que se cubre/apunta a alguien.
 */
function SelectorRol({
  rol,
  onRol,
  disabled,
}: {
  rol: RolCobertura;
  onRol: (r: RolCobertura) => void;
  disabled?: boolean;
}) {
  return (
    <div role="group" aria-label="Rol de cobertura" className="inline-flex items-center gap-1">
      {ROLES_COBERTURA.map((r) => (
        <button
          key={r}
          type="button"
          disabled={disabled}
          aria-pressed={rol === r}
          onClick={() => onRol(r)}
          className={cn(
            "rounded-md border px-2 py-1 text-xs transition-colors disabled:opacity-60",
            rol === r
              ? "border-foreground/40 bg-accent text-foreground"
              : "border-border text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {etiquetaRol(r)}
        </button>
      ))}
    </div>
  );
}

/** Semáforo AGREGADO por rol: qué roles del evento están cubiertos ("Foto · Video" / "N roles"). */
export function RolesCubiertos({ cubridores }: { cubridores: Contenido[] }) {
  const roles = rolesCubiertos(cubridores);
  if (roles.length === 0) return null;
  const texto = roles.length <= 2 ? roles.map(etiquetaRol).join(" · ") : `${roles.length} roles`;
  return (
    <span className="shrink-0 truncate text-xs text-muted-foreground" title={roles.map(etiquetaRol).join(" · ")}>
      {texto}
    </span>
  );
}

/**
 * Un ROL soltado dentro de una cobertura aún viva: tarea de cobertura HUÉRFANA (sin dueño) que
 * conserva su `formato`. Resurge como «Por cubrir · <rol>» re-cogible (coger = retoma ESE rol).
 */
function RolLibre({ tarea }: { tarea: Contenido }) {
  const queryClient = useQueryClient();
  const coger = useMutation({
    mutationFn: () => api.cogerContenido(tarea.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(`Cubres "${tarea.titulo}" (${etiquetaRol(tarea.formato)}).`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed border-amber-500/40 bg-amber-50/40 px-2.5 py-1.5 dark:bg-amber-950/10">
      <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-300">
        Por cubrir
      </Badge>
      <span className="text-sm text-muted-foreground">{etiquetaRol(tarea.formato)}</span>
      <Button
        variant="outline"
        size="icon"
        className="ml-auto h-7 w-7"
        onClick={() => coger.mutate()}
        disabled={coger.isPending}
        title="La cubro yo"
        aria-label="La cubro yo"
      >
        <Hand className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

/**
 * Un EVENTO «Por cubrir»: un partido/transmisión que nadie ha cogido todavía. No tiene tarea
 * aún; al coger (o que el coordinador de la rota asigne) se crea su registro de cobertura vía `cubrirEvento`.
 */
export function TarjetaEventoLibre({
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
  const [rol, setRol] = React.useState<RolCobertura>("foto");
  const usuarios = catalogos?.usuarios ?? [];

  const cubrir = useMutation({
    mutationFn: (responsableId?: string) => api.cubrirEvento(evento.id, responsableId, rol),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const nombre = res?.contenido?.responsable_nombre || "ti";
      toast.success(`"${evento.titulo}" la cubre ${nombre} (${etiquetaRol(rol)}).`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  const accionesEvento: EntradaMenuContextual[] = [];
  if (esManager) {
    accionesEvento.push({ etiqueta: "Asignar", icono: UserPlus, onClick: () => setAsignarAbierto(true) });
  }

  return (
    <FilaConAcciones
      como="div"
      kebab="siempre"
      realce
      onPrimaria={() => cubrir.mutate(undefined)}
      acciones={accionesEvento}
      className="rounded-lg border border-dashed border-border bg-card p-3 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        <IconoEvento titulo={evento.titulo} className="h-4 w-4 shrink-0 text-muted-foreground" />
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
      {/* Rol con que se cubre (Foto/Video/Texto/Live): el reparto es por rol. */}
      <div className="mt-3">
        <SelectorRol rol={rol} onRol={setRol} disabled={cubrir.isPending} />
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
    </FilaConAcciones>
  );
}

/** Una TAREA ya con dueño (cobertura cogida o encargo del equipo): estado, responsable, acciones. */
export function TarjetaTarea({
  tarea,
  catalogos,
  enCobertura = false,
}: {
  tarea: Contenido;
  catalogos: CatalogosContenido | undefined;
  /** Dentro de una cobertura: oculta «Soltar»/«Reasignar» (se gestionan a nivel de evento). */
  enCobertura?: boolean;
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
      // En cobertura «Quitarme» SOLO libera mi rol: el partido SIGUE (reaparece como «Por
      // cubrir» y se puede re-coger). NO borra nada — se deja MUY claro para no asustar.
      if (enCobertura) {
        toast.success(
          `Te quitaste de "${tarea.titulo}". El partido sigue: vuelve como «Por cubrir».`,
        );
      } else {
        toast.success(`"${tarea.titulo}" vuelve a estar libre.`);
      }
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

  // Acción primaria: avance de estado más prominente según el estado actual.
  const primaria: (() => void) | undefined = enCobertura
    ? (esMia ? () => soltar.mutate() : undefined)
    : libre
      ? () => coger.mutate()
      : avance
        ? () => cambiarEstado.mutate(avance.estado)
        : tarea.estado === "hecha"
          ? () => cambiarEstado.mutate("pendiente")
          : undefined;

  // Acciones del menú contextual (el resto de acciones disponibles en este estado).
  const accionesTarea: EntradaMenuContextual[] = [];
  if (!enCobertura) {
    if (esManager) {
      accionesTarea.push({
        etiqueta: libre ? "Asignar" : "Reasignar",
        icono: UserPlus,
        onClick: () => setAsignarAbierto(true),
      });
    }
    if (!libre && (esMia || esManager)) {
      accionesTarea.push({ etiqueta: "Soltar", icono: UserMinus, onClick: () => soltar.mutate() });
    }
    if (esManager && !esCobertura) {
      if (accionesTarea.length > 0) accionesTarea.push({ separador: true });
      accionesTarea.push({
        etiqueta: "Borrar",
        icono: Trash2,
        destructivo: true,
        onClick: () => setConfirmarBorrado(true),
      });
    }
  }

  return (
    <FilaConAcciones
      como="div"
      kebab="siempre"
      realce
      onPrimaria={primaria}
      acciones={accionesTarea}
      className="rounded-lg border border-border bg-card p-3 shadow-sm"
    >
      <div className="flex flex-wrap items-center gap-2">
        {/* Dentro de una cobertura el título del evento ya está en la cabecera de la fila
            (y la fecha también): cada tarjeta encabeza por la PERSONA para no repetirlo. */}
        {enCobertura ? (
          <>
            {/* Semáforo automático por fecha/hora (sin botones de estado). */}
            <SemaforoCobertura fecha={tarea.fecha_objetivo} hora={tarea.hora_objetivo} />
            <span className="inline-flex items-center gap-1.5 font-medium">
              <AvatarPersona
                id={tarea.responsable_id ?? ""}
                nombre={tarea.responsable_nombre ?? ""}
                size="sm"
              />
              {tarea.responsable_nombre}
              {/* Persona + SU rol: "[avatar] roger · Video". */}
              <span className="font-normal text-muted-foreground">· {etiquetaRol(tarea.formato)}</span>
              {esMia && <span className="font-normal text-muted-foreground">· tú</span>}
            </span>
          </>
        ) : (
          <>
            {esCobertura && (
              <IconoEvento titulo={tarea.titulo} className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <span className="font-medium">{tarea.titulo}</span>
            {/* Rol de la cobertura: en un recuperable («Por cubrir») deja claro qué rol resurge. */}
            {esCobertura && (
              <Badge variant="outline" className="font-normal text-muted-foreground">
                {etiquetaRol(tarea.formato)}
              </Badge>
            )}
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
          </>
        )}
        {/* Estados manuales solo fuera de cobertura: en cobertura manda el semáforo. */}
        {!enCobertura && tarea.estado === "en_curso" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            En curso
          </Badge>
        )}
        {!enCobertura && tarea.estado === "hecha" && (
          <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300">
            Hecha
          </Badge>
        )}
        {tarea.prioridad && (
          <Badge variant="outline" className={cn("font-normal", PRIORIDAD_CLASE[tarea.prioridad])}>
            {tarea.prioridad}
          </Badge>
        )}
        {!enCobertura && tarea.fecha_objetivo && (
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
    </FilaConAcciones>
  );
}

/**
 * COBERTURA de un evento con uno o VARIOS cubridores. Cabecera con quién lo cubre + acciones
 * («Apuntarme» yo, «Añadir a alguien» el manager) y, debajo, la tarjeta de cada cubridor para
 * que cada quien avance o suelte LA SUYA (soltar = dejar de cubrir; los demás siguen).
 */
export function TarjetaCobertura({
  cobertura,
  catalogos,
}: {
  cobertura: Cobertura;
  catalogos: CatalogosContenido | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const [rol, setRol] = React.useState<RolCobertura>("foto");
  const usuarios = catalogos?.usuarios ?? [];
  const yaApuntado = Boolean(
    usuario && cobertura.cubridores.some((t) => t.responsable_id === usuario.id),
  );

  const cubrir = useMutation({
    mutationFn: (responsableId?: string) =>
      api.cubrirEvento(cobertura.eventoId, responsableId, rol),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const nombre = res?.contenido?.responsable_nombre || "ti";
      toast.success(`"${cobertura.titulo}" la cubre ${nombre} (${etiquetaRol(rol)}).`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  // Quitar a un cubridor (× del chip): suelta SU pieza; el rol vuelve a «Por cubrir».
  const soltar = useMutation({
    mutationFn: (v: { id: string; nombre: string; rol: string }) => api.soltarContenido(v.id),
    onSuccess: (_res, v) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(`${v.nombre} ya no cubre (${etiquetaRol(v.rol)}); el rol vuelve a «Por cubrir».`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  const accionesCobertura: EntradaMenuContextual[] = [];
  if (esManager) {
    accionesCobertura.push({
      etiqueta: "Añadir a alguien",
      icono: UserPlus,
      onClick: () => setAsignarAbierto(true),
    });
  }

  return (
    <FilaConAcciones
      como="div"
      kebab="siempre"
      realce
      onPrimaria={!yaApuntado ? () => cubrir.mutate(undefined) : undefined}
      acciones={accionesCobertura}
      className="space-y-2"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Cubren:</span>
        {cobertura.cubridores.map((t) => {
          const esMio = t.responsable_id === usuario?.id;
          const puedeQuitar = esManager || esMio;
          return (
            <span
              key={t.id}
              className="inline-flex items-center gap-1 rounded-full border border-border bg-card py-0.5 pl-1 pr-2 text-sm"
            >
              <AvatarPersona id={t.responsable_id} nombre={t.responsable_nombre} size="sm" />
              {t.responsable_nombre}
              <span className="text-muted-foreground">· {etiquetaRol(t.formato)}</span>
              {puedeQuitar && (
                <button
                  type="button"
                  aria-label={esMio ? "Soltar (dejar de cubrir)" : `Quitar a ${t.responsable_nombre}`}
                  title={esMio ? "Soltar (dejar de cubrir)" : `Quitar a ${t.responsable_nombre}`}
                  disabled={soltar.isPending}
                  onClick={() =>
                    soltar.mutate({ id: t.id, nombre: t.responsable_nombre, rol: t.formato })
                  }
                  className="ml-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          );
        })}
        {/* Semáforo agregado por rol del evento (qué roles están cubiertos). */}
        <RolesCubiertos cubridores={cobertura.cubridores} />
      </div>
      {/* Guion del partido (run-of-show por fases): checklist de referencia neutra, colapsable. */}
      <GuionPartido tipoCobertura={cobertura.tipoCobertura} />
      <div className="space-y-2" data-no-primaria>
        {cobertura.cubridores.map((t) => (
          <TarjetaTarea key={t.id} tarea={t} catalogos={catalogos} enCobertura />
        ))}
      </div>
      {/* Roles SOLTADOS (huérfanos) de este evento aún vivo: «Por cubrir · <rol>» re-cogibles. */}
      {cobertura.libres.length > 0 && (
        <div className="space-y-1.5" data-no-primaria>
          {cobertura.libres.map((t) => (
            <RolLibre key={t.id} tarea={t} />
          ))}
        </div>
      )}
      {/* Rol con que me apunto / añaden a alguien (selector inline; la acción va al menú). */}
      {(!yaApuntado || esManager) && (
        <div className="flex flex-wrap items-center gap-2">
          <SelectorRol rol={rol} onRol={setRol} disabled={cubrir.isPending} />
        </div>
      )}

      <DialogoAsignar
        titulo={cobertura.titulo}
        abierto={asignarAbierto}
        onOpenChange={setAsignarAbierto}
        usuarios={usuarios}
        responsableActual=""
        onElegir={(id) => cubrir.mutate(id)}
        enviando={cubrir.isPending}
      />
    </FilaConAcciones>
  );
}
