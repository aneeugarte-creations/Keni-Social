import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Hand,
  Pencil,
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
import type { CatalogosPublicacion, Publicacion, EventoRota } from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { CLAVE_TAREAS } from "./claves";
import { DialogoAsignar } from "./dialogos";
import { IconoEvento } from "./icono-evento";
import { etiquetaRol, type RolCobertura, ROLES_COBERTURA, rolesCubiertos } from "./roles";
import type { Cobertura } from "./tipos";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { DialogEditarEvento } from "@/pages/rota/calendario/dialogs";

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
 * Selector pequeño de ROL de cobertura (Foto/Video/Texto/Live), estilo plataforma (outline gris):
 * cuatro botones segmentados, uno marcado. Decide el `formato` con que se cubre/apunta a alguien.
 */
export function SelectorRol({
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
export function RolesCubiertos({ cubridores }: { cubridores: Publicacion[] }) {
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
 * Un ROL soltado dentro de una cobertura aún viva: tarea de cobertura SUELTA (sin dueño) que
 * conserva su `formato`. Resurge como «Por cubrir · <rol>» re-cogible (coger = retoma ESE rol).
 */
function RolLibre({ tarea }: { tarea: Publicacion }) {
  const queryClient = useQueryClient();
  const coger = useMutation({
    mutationFn: () => api.cogerPublicacion(tarea.id),
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
  sinMenu = false,
}: {
  evento: EventoRota;
  catalogos: CatalogosPublicacion | undefined;
  /** Oculta el kebab «⋮» (las acciones siguen accesibles por click derecho/teclado). Lo usa
   *  el Panorama, donde Asignar/Editar/Borrar ya viven como iconos en la propia fila. */
  sinMenu?: boolean;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const [editarAbierto, setEditarAbierto] = React.useState(false);
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
  // Borrar el evento por cubrir: no tiene cobertura aún (0 tareas), así que basta el evento.
  const borrar = useMutation({
    mutationFn: () => api.eliminarEventoRota(evento.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(`"${evento.titulo}" borrado.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });
  const pedirBorrar = async () => {
    if (
      await confirmar({
        mensaje: `¿Borrar "${evento.titulo}"? Desaparece de la lista para todos.`,
        destructivo: true,
        textoConfirmar: "Borrar",
      })
    )
      borrar.mutate();
  };

  // Editar/Borrar el partido: acciones de coordinación (solo admin), como el resto del reparto.
  const accionesEvento: EntradaMenuContextual[] = [];
  if (esManager) {
    accionesEvento.push({ etiqueta: "Asignar", icono: UserPlus, onClick: () => setAsignarAbierto(true) });
    accionesEvento.push({ etiqueta: "Editar", icono: Pencil, onClick: () => setEditarAbierto(true) });
    accionesEvento.push({ separador: true });
    accionesEvento.push({
      etiqueta: "Borrar",
      icono: Trash2,
      destructivo: true,
      onClick: () => void pedirBorrar(),
    });
  }

  return (
    <FilaConAcciones
      como="div"
      kebab={sinMenu ? "nunca" : "siempre"}
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

      {editarAbierto && (
        <div data-no-primaria>
          <DialogEditarEvento
            evento={evento}
            onCerrar={() => setEditarAbierto(false)}
            onCambio={() => void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS })}
          />
        </div>
      )}
    </FilaConAcciones>
  );
}

/** Una TAREA ya con dueño (cobertura cogida o encargo del equipo): estado, responsable, acciones. */
export function TarjetaTarea({
  tarea,
  catalogos,
  enCobertura = false,
  sinMenu = false,
}: {
  tarea: Publicacion;
  catalogos: CatalogosPublicacion | undefined;
  /** Dentro de una cobertura: oculta «Soltar»/«Reasignar» (se gestionan a nivel de evento). */
  enCobertura?: boolean;
  /** Oculta el kebab «⋮» (acciones siguen por click derecho/teclado). Lo usa el Panorama. */
  sinMenu?: boolean;
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
    mutationFn: () => api.cogerPublicacion(tarea.id),
    onSuccess: () => {
      void invalidar();
      toast.success(`"${tarea.titulo}" es tuya: el equipo ya lo ve.`);
    },
    onError: conError,
  });
  const soltar = useMutation({
    mutationFn: () => api.soltarPublicacion(tarea.id),
    onSuccess: () => {
      void invalidar();
      // En cobertura soltar SOLO libera ESE rol: el partido SIGUE (reaparece como «Por
      // cubrir» y se puede re-coger). NO borra nada — se deja MUY claro para no asustar.
      if (enCobertura) {
        toast.success(
          esMia
            ? `Te quitaste de "${tarea.titulo}". El partido sigue: vuelve como «Por cubrir».`
            : `${tarea.responsable_nombre} ya no cubre "${tarea.titulo}": vuelve como «Por cubrir».`,
        );
      } else {
        toast.success(`"${tarea.titulo}" vuelve a estar libre.`);
      }
    },
    onError: conError,
  });
  const asignar = useMutation({
    mutationFn: (personaId: string) => api.asignarPublicacion(tarea.id, personaId),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void invalidar();
      const nombre = res?.contenido?.responsable_nombre || "esa persona";
      toast.success(`"${tarea.titulo}" asignada a ${nombre}: se le avisa en la app.`);
    },
    onError: conError,
  });
  const cambiarEstado = useMutation({
    mutationFn: (estado: string) => api.actualizarPublicacion(tarea.id, { estado }),
    onSuccess: () => void invalidar(),
    onError: conError,
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarPublicacion(tarea.id),
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
      kebab={sinMenu ? "nunca" : "siempre"}
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
        {/* Quitar a quien cubre (yo mismo o, si soy manager, a otra persona): suelta SU rol;
            el partido sigue y el rol vuelve a «Por cubrir». Reemplaza el viejo chip «Cubren:». */}
        {enCobertura && (esMia || esManager) && (
          <button
            type="button"
            aria-label={esMia ? "Soltar (dejar de cubrir)" : `Quitar a ${tarea.responsable_nombre}`}
            title={esMia ? "Soltar (dejar de cubrir)" : `Quitar a ${tarea.responsable_nombre}`}
            disabled={soltar.isPending}
            onClick={(e) => {
              e.stopPropagation();
              soltar.mutate();
            }}
            className="ml-auto inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
          </button>
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
  sinMenu = false,
}: {
  cobertura: Cobertura;
  catalogos: CatalogosPublicacion | undefined;
  /** Oculta el kebab «⋮» (acciones siguen por click derecho/teclado). Lo usa el Panorama. */
  sinMenu?: boolean;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const [editarAbierto, setEditarAbierto] = React.useState(false);
  const [rol, setRol] = React.useState<RolCobertura>("foto");
  const usuarios = catalogos?.usuarios ?? [];
  const yaApuntado = Boolean(
    usuario && cobertura.cubridores.some((t) => t.responsable_id === usuario.id),
  );
  // El EVENTO subyacente (si sigue cargado) habilita editar/borrar el partido; las tareas
  // enlazadas (cubridores + roles soltados) viajan al diálogo para propagar/cascada.
  const evento = cobertura.evento;
  const vinculadas = [...cobertura.cubridores, ...cobertura.libres];

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

  // Borrar el partido = cancelarlo: borra el evento Y sus tareas de cobertura (la fila se deriva
  // de esas tareas, no del evento; sin borrarlas el partido seguiría vivo sin dueño claro).
  const borrar = useMutation({
    mutationFn: async () => {
      if (!evento) return;
      await api.eliminarEventoRota(evento.id);
      await Promise.all(vinculadas.map((t) => api.eliminarPublicacion(t.id)));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(`"${cobertura.titulo}" borrado.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });
  const pedirBorrar = async () => {
    const n = cobertura.cubridores.length;
    if (
      await confirmar({
        mensaje:
          n > 0
            ? `¿Borrar "${cobertura.titulo}"? Cancelará la cobertura de ${n} ${n === 1 ? "persona" : "personas"}.`
            : `¿Borrar "${cobertura.titulo}"? Desaparece de la lista para todos.`,
        destructivo: true,
        textoConfirmar: "Borrar",
      })
    )
      borrar.mutate();
  };

  const accionesCobertura: EntradaMenuContextual[] = [];
  if (esManager) {
    accionesCobertura.push({
      etiqueta: "Añadir a alguien",
      icono: UserPlus,
      onClick: () => setAsignarAbierto(true),
    });
    // Editar/Borrar el partido exigen el evento subyacente (la cobertura sola no basta).
    if (evento) {
      accionesCobertura.push({ etiqueta: "Editar", icono: Pencil, onClick: () => setEditarAbierto(true) });
      accionesCobertura.push({ separador: true });
      accionesCobertura.push({
        etiqueta: "Borrar",
        icono: Trash2,
        destructivo: true,
        onClick: () => void pedirBorrar(),
      });
    }
  }

  return (
    <FilaConAcciones
      como="div"
      kebab={sinMenu ? "nunca" : "siempre"}
      realce
      onPrimaria={!yaApuntado ? () => cubrir.mutate(undefined) : undefined}
      acciones={accionesCobertura}
      className="space-y-2"
    >
      {/* Quién cubre: UNA fila por persona (avatar · nombre · rol · semáforo · ×). Antes cada
          cubridor se pintaba DOS veces (chip «Cubren:» + tarjeta); ahora es una sola fila. El
          rol cubierto agregado ya vive en la cabecera de la fila (RolesCubiertos), no se repite. */}
      {cobertura.cubridores.length > 0 && (
        <div className="space-y-2" data-no-primaria>
          <span className="text-sm text-muted-foreground">Cubren:</span>
          {cobertura.cubridores.map((t) => (
            <TarjetaTarea key={t.id} tarea={t} catalogos={catalogos} enCobertura />
          ))}
        </div>
      )}
      {/* Roles SOLTADOS (sin dueño) de este evento aún vivo: «Por cubrir · <rol>» re-cogibles. */}
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

      {editarAbierto && evento && (
        <div data-no-primaria>
          <DialogEditarEvento
            evento={evento}
            tareasVinculadas={vinculadas}
            onCerrar={() => setEditarAbierto(false)}
            onCambio={() => void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS })}
          />
        </div>
      )}
    </FilaConAcciones>
  );
}
