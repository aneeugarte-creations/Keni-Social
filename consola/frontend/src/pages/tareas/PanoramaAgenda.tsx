import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Hand, Pencil, Plus, Target, Trash2, UserPlus, Zap } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearDia, hoyCDMX, minutosHastaEvento, posicionTemporal } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosPublicacion, Publicacion, EventoRota, PrioridadEvento } from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { CLAVE_TAREAS } from "./claves";
import { DialogoAsignar } from "./dialogos";
import { IconoEvento } from "./icono-evento";
import { etiquetaRol, type RolCobertura } from "./roles";
import {
  RolesCubiertos,
  SelectorRol,
  SemaforoCobertura,
  TarjetaCobertura,
  TarjetaEventoLibre,
  TarjetaTarea,
} from "./tarjetas";
import { agrupar, type Item } from "./tipos";

import { DialogEditarEvento } from "@/pages/rota/calendario/dialogs";

/** Etiqueta del encabezado de día: «Hoy» / «Mañana» / día legible / «Sin fecha». */
function sumarDias(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function etiquetaDia(dia: string, hoy: string): string {
  if (!dia || dia === "9999-99-99") return "Sin fecha";
  if (dia === hoy) return "Hoy";
  if (dia === sumarDias(hoy, 1)) return "Mañana";
  return formatearDia(dia);
}

/**
 * AÑADIR-RÁPIDO: el atajo de 5 segundos, SIEMPRE visible y para TODOS (no solo admin). Crea un
 * ítem coverable que cae directo en «Por cubrir» (un evento de la rota sin cubridores): título +
 * hora opcional, HOY en CDMX por defecto, marca del tablero. Etiqueta GENÉRICA (vale para clip,
 * foto, reacción… no solo «partido»). El diálogo «Añadir» de la barra queda para el caso rico
 * (import por enlace/documento, encargos con dueño).
 */
function AnadirRapido({ marca }: { marca: string }) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [hora, setHora] = React.useState("");
  // «⚡ Urgente» = nace con prioridad «alta» (sin campo nuevo: reusa la prioridad del evento).
  // Por defecto OFF: lo normal no es breaking. Si ON, salta a la banda «Urgente ahora».
  const [urgente, setUrgente] = React.useState(false);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEventoRota({
        titulo: titulo.trim(),
        fecha: hoyCDMX(), // HOY en CDMX (no el día UTC): cae en el cajón «Hoy».
        hora: hora || undefined,
        tipo_cobertura: "transmision",
        prioridad: urgente ? "alta" : undefined,
        marca: marca || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(
        urgente
          ? `«${titulo.trim()}» es URGENTE: salta al tope.`
          : `«${titulo.trim()}» está en «Por cubrir».`,
      );
      setTitulo("");
      setHora("");
      setUrgente(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enviar = (e: React.FormEvent) => {
    e.preventDefault();
    if (!titulo.trim() || crear.isPending) return;
    crear.mutate();
  };

  return (
    <form
      onSubmit={enviar}
      className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border bg-card p-1.5 shadow-sm"
    >
      {/* `Input` ya fuerza text-base (16px) en móvil → sin auto-zoom de iOS al enfocar. En móvil
          ocupa toda la fila (los controles bajan debajo) para no asfixiarse a 3-4 letras. */}
      <Input
        value={titulo}
        onChange={(e) => setTitulo(e.target.value)}
        placeholder="¿Qué hay que cubrir?"
        aria-label="¿Qué hay que cubrir?"
        className="w-full min-w-0 border-0 bg-transparent shadow-none focus-visible:ring-0 sm:flex-1"
      />
      {/* Hora + acciones: su propia fila en móvil (`w-full`), comparten fila con el campo en sm+. */}
      <div className="flex w-full items-center gap-1.5 sm:w-auto">
        <Input
          type="time"
          value={hora}
          onChange={(e) => setHora(e.target.value)}
          aria-label="Hora (opcional)"
          className="min-w-0 flex-1 border-0 bg-transparent shadow-none focus-visible:ring-0 sm:w-[7rem] sm:flex-none"
        />
        {/* Toggle «Urgente»: estilo plataforma (outline gris) y, activo, teñido en rojo sutil.
            El texto se oculta en móvil (queda el icono) para no apretar la fila de acciones. */}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(
            "shrink-0",
            urgente && "border-red-500/50 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300",
          )}
          aria-label="Urgente"
          aria-pressed={urgente}
          title={urgente ? "Nace como urgente (salta al tope)" : "Marcar como urgente"}
          onClick={() => setUrgente((v) => !v)}
        >
          <Zap className="h-4 w-4 sm:mr-1" />
          <span className="hidden sm:inline">Urgente</span>
        </Button>
        <Button
          type="submit"
          variant="outline"
          size="sm"
          className="shrink-0"
          aria-label="Añadir a Por cubrir"
          disabled={!titulo.trim() || crear.isPending}
        >
          <Plus className="h-4 w-4 sm:mr-1" />
          <span className="hidden sm:inline">{crear.isPending ? "Añadiendo…" : "Añadir"}</span>
        </Button>
      </div>
    </form>
  );
}

/** ¿El ítem está SIN dueño? Un evento lo está si nadie lo cogió Y no lo cubre el turno de su
 *  franja; un encargo/cobertura-soltada, si no tiene responsable. */
function itemSinDueno(i: Item): boolean {
  return (i.kind === "evento" && !i.cubiertoPorTurno) || (i.kind === "tarea" && !i.tarea.responsable_id);
}

/** Hora «de pared» (HH:MM) del ítem, o "" si no la tiene. */
function horaItem(i: Item): string {
  return i.kind === "cobertura"
    ? i.cobertura.hora
    : i.kind === "tarea"
      ? i.tarea.hora_objetivo
      : i.evento.hora;
}

/**
 * Rango de URGENCIA de un ítem DENTRO de HOY (menor = más arriba): 0 en vivo (durante) · 1 empieza
 * pronto (0<min≤120) · 2 por cubrir (sin dueño) · 3 el resto. La hora desempata fuera. Solo se
 * aplica al cajón de HOY; los demás días siguen ordenados por hora (sin cambiar el agrupado).
 */
function rangoUrgenciaHoy(i: Item, dia: string): number {
  const hora = horaItem(i) || null;
  // «En vivo» exige hora concreta: sin hora, posicionTemporal devuelve "durante" por diseño y
  // colaría un ítem sin hora por encima de los que empiezan pronto. Sin hora → cae a «por cubrir».
  if (hora && posicionTemporal(dia, hora) === "durante") return 0;
  const min = minutosHastaEvento(dia, hora);
  if (min != null && min > 0 && min <= 120) return 1;
  if (itemSinDueno(i)) return 2;
  return 3;
}

/** Título del ítem (para toasts/etiquetas), sea cobertura, tarea o evento. */
function tituloItem(i: Item): string {
  return i.kind === "cobertura" ? i.cobertura.titulo : i.kind === "tarea" ? i.tarea.titulo : i.evento.titulo;
}

/**
 * Prioridad EFECTIVA del ítem: eventos y tareas la traen; la COBERTURA la HEREDA del evento
 * (propagada en `agrupar`). `undefined` de la cobertura → «media» (sin urgencia).
 */
function prioridadItem(i: Item): PrioridadEvento {
  return i.kind === "evento"
    ? i.evento.prioridad
    : i.kind === "cobertura"
      ? i.cobertura.prioridad ?? "media"
      : i.tarea.prioridad;
}

/**
 * ¿Es URGENTE-DE-AHORA (breaking)? = prioridad «alta» Y de HOY o SIN FECHA. Un partido urgente
 * de la semana que viene NO es breaking (se queda en su día con su badge rojo); solo lo de ahora
 * salta al tope. `i.orden` ya es el día («AAAA-MM-DD» o «9999-99-99» para «sin fecha»).
 */
function esUrgenteAhora(i: Item, hoy: string): boolean {
  if (prioridadItem(i) !== "alta") return false;
  return i.orden === hoy || i.orden === "9999-99-99";
}

/**
 * Orden de los CAJONES de día: HOY siempre primero, luego los días futuros (más próximo
 * antes), después los pasados (más reciente antes) y, al final, «Sin fecha». Devuelve la
 * clave de orden de un día («AAAA-MM-DD» o «9999-99-99»).
 */
function ordenDiaAgenda(dia: string, hoy: string): [number, string] {
  if (!dia || dia === "9999-99-99") return [3, dia]; // sin fecha → al final
  if (dia === hoy) return [0, dia]; // hoy → primero
  if (dia > hoy) return [1, dia]; // futuro → asc (la clave compara ascendente)
  return [2, invertirIso(dia)]; // pasado → desc (más reciente primero)
}

/** Clave que invierte el orden de una fecha ISO para ordenarla DESCENDENTE como string. */
function invertirIso(iso: string): string {
  let out = "";
  for (const ch of iso) out += /[0-9]/.test(ch) ? String(9 - Number(ch)) : ch;
  return out;
}

/**
 * Escalar / des-escalar un ítem del tablero: ⚡ que mueve su prioridad alta↔media reusando la API
 * que toque (sin backend nuevo). Evento por cubrir → PATCH del evento; cobertura → PATCH del EVENTO
 * subyacente (las tareas de cobertura no llevan prioridad propia); tarea/encargo → PATCH del
 * contenido. Tras escalar invalida CLAVE_TAREAS para que la banda «Urgente ahora» se rehaga.
 */
function AccionUrgente({ item }: { item: Item }) {
  const queryClient = useQueryClient();
  const esUrgente = prioridadItem(item) === "alta";
  const objetivo: PrioridadEvento = esUrgente ? "media" : "alta";

  const escalar = useMutation({
    mutationFn: async (): Promise<void> => {
      // Cada tipo de ítem escala por la API que toque (sin backend nuevo). Normalizamos a `void`:
      // las respuestas difieren (evento vs contenido) y solo nos interesa el efecto, no el cuerpo.
      if (item.kind === "evento") {
        await api.actualizarEventoRota(item.evento.id, { prioridad: objetivo });
      } else if (item.kind === "cobertura") {
        await api.actualizarEventoRota(item.cobertura.eventoId, { prioridad: objetivo });
      } else {
        await api.actualizarPublicacion(item.tarea.id, { prioridad: objetivo });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(
        esUrgente
          ? `«${tituloItem(item)}» ya no es urgente.`
          : `«${tituloItem(item)}» es URGENTE: salta al tope.`,
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={cn(
        "h-7 w-7 shrink-0",
        esUrgente &&
          "border-red-500/50 bg-red-50 text-red-700 dark:bg-red-950/30 dark:text-red-300",
      )}
      aria-label={esUrgente ? "Quitar urgente" : "Marcar urgente"}
      aria-pressed={esUrgente}
      title={esUrgente ? "Quitar urgente" : "Marcar urgente"}
      disabled={escalar.isPending}
      onClick={() => escalar.mutate()}
    >
      <Zap className="h-3.5 w-3.5" />
    </Button>
  );
}

/**
 * EDITAR / BORRAR en la PROPIA fila (sin desplegar), junto al ⚡: un lápiz que abre el mismo
 * diálogo de edición que el calendario (solo para partidos/eventos) y una papelera para borrar
 * cualquier fila. Solo admin (igual que editar en el calendario).
 *
 * Cada tipo de fila resuelve su evento editable y qué borrar:
 *  - evento «por cubrir» → edita/borra el evento (no tiene cobertura aún).
 *  - cobertura (partido cubierto) → edita el evento y propaga/cascada a sus tareas (la fila se
 *    deriva de ellas, no del evento); borrar = cancelar el partido (evento + tareas).
 *  - tarea/encargo → borra la tarea; si es una cobertura soltada (lleva `evento_id`) borra también
 *    el evento para que no resurja como «Por cubrir».
 */
function AccionesItem({
  item,
  catalogos,
}: {
  item: Item;
  catalogos: CatalogosPublicacion | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [editarAbierto, setEditarAbierto] = React.useState(false);
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const [rol, setRol] = React.useState<RolCobertura>("foto");

  // Evento editable (lápiz) y tareas a borrar en cascada, según el tipo de fila.
  const evento =
    item.kind === "evento"
      ? item.evento
      : item.kind === "cobertura"
        ? item.cobertura.evento ?? null
        : null;
  const tareasVinculadas =
    item.kind === "cobertura" ? [...item.cobertura.cubridores, ...item.cobertura.libres] : [];
  const titulo = tituloItem(item);

  // Asignar (UserPlus): para un EVENTO/COBERTURA se cubre con un rol (cubrirEvento); para una
  // TAREA suelta se asigna el responsable directo (asignarPublicacion). El rol se elige en el
  // propio diálogo cuando aplica.
  const usuarios = catalogos?.usuarios ?? [];
  const necesitaRol = item.kind === "evento" || item.kind === "cobertura";
  const responsableActual = item.kind === "tarea" ? item.tarea.responsable_id ?? "" : "";
  const asignar = useMutation({
    mutationFn: (personaId: string) =>
      item.kind === "tarea"
        ? api.asignarPublicacion(item.tarea.id, personaId)
        : api.cubrirEvento(
            item.kind === "evento" ? item.evento.id : item.cobertura.eventoId,
            personaId,
            rol,
          ),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const nombre =
        (res as { contenido?: { responsable_nombre?: string } })?.contenido?.responsable_nombre ||
        "esa persona";
      toast.success(`«${titulo}» asignada a ${nombre}: se le avisa en la app.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  const borrar = useMutation({
    mutationFn: async (): Promise<void> => {
      if (item.kind === "tarea") {
        await api.eliminarPublicacion(item.tarea.id);
        // Cobertura soltada (suelta con `evento_id`): borra también el evento para que no
        // reaparezca como «Por cubrir». Si el evento ya no existe, ignoramos el 404.
        if (item.tarea.evento_id) {
          try {
            await api.eliminarEventoRota(item.tarea.evento_id);
          } catch {
            /* el evento podía no existir ya */
          }
        }
        return;
      }
      if (evento) await api.eliminarEventoRota(evento.id);
      if (tareasVinculadas.length > 0) {
        await Promise.all(tareasVinculadas.map((t) => api.eliminarPublicacion(t.id)));
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(`«${titulo}» borrado.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });
  const pedirBorrar = async () => {
    const n = item.kind === "cobertura" ? item.cobertura.cubridores.length : 0;
    if (
      await confirmar({
        mensaje:
          n > 0
            ? `¿Borrar «${titulo}»? Cancelará la cobertura de ${n} ${n === 1 ? "persona" : "personas"}.`
            : `¿Borrar «${titulo}»? Desaparece de la lista para todos.`,
        destructivo: true,
        textoConfirmar: "Borrar",
      })
    )
      borrar.mutate();
  };

  // Sin permisos de coordinación no se editan ni borran partidos del tablero compartido.
  if (!esManager) return null;

  return (
    <span className="flex shrink-0 items-center gap-1">
      {/* Asignar (UserPlus): encarga el evento/tarea a alguien sin desplegar la fila. */}
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="h-7 w-7 shrink-0"
        aria-label="Asignar"
        title="Asignar"
        onClick={() => setAsignarAbierto(true)}
      >
        <UserPlus className="h-3.5 w-3.5" />
      </Button>
      {/* Lápiz: solo si hay evento detrás (partidos); abre el diálogo del calendario. */}
      {evento && (
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-7 w-7 shrink-0"
          aria-label="Editar"
          title="Editar"
          onClick={() => setEditarAbierto(true)}
        >
          <Pencil className="h-3.5 w-3.5" />
        </Button>
      )}
      {/* Papelera: borra cualquier fila (con confirmación). */}
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="h-7 w-7 shrink-0 text-muted-foreground hover:border-destructive/50 hover:text-destructive"
        aria-label="Borrar"
        title="Borrar"
        disabled={borrar.isPending}
        onClick={() => void pedirBorrar()}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
      {editarAbierto && evento && (
        <DialogEditarEvento
          evento={evento}
          tareasVinculadas={tareasVinculadas}
          onCerrar={() => setEditarAbierto(false)}
          onCambio={() => void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS })}
        />
      )}

      <DialogoAsignar
        titulo={titulo}
        abierto={asignarAbierto}
        onOpenChange={setAsignarAbierto}
        usuarios={usuarios}
        responsableActual={responsableActual}
        onElegir={(id) => asignar.mutate(id)}
        enviando={asignar.isPending}
        extra={
          necesitaRol ? (
            <div className="space-y-1.5">
              <p className="text-sm font-medium">Rol con que se cubre</p>
              <SelectorRol rol={rol} onRol={setRol} disabled={asignar.isPending} />
            </div>
          ) : undefined
        }
      />
    </span>
  );
}

/** Avatares de los cubridores, apilados (-space) con «+N» si son muchos. */
function AvataresApilados({ cubridores }: { cubridores: Publicacion[] }) {
  const MAX = 4;
  const vis = cubridores.slice(0, MAX);
  const resto = cubridores.length - vis.length;
  return (
    <span className="flex shrink-0 items-center">
      <span className="flex -space-x-1.5">
        {vis.map((t) => (
          <span key={t.id} className="rounded-full ring-2 ring-background">
            <AvatarPersona id={t.responsable_id} nombre={t.responsable_nombre} size="sm" />
          </span>
        ))}
      </span>
      {resto > 0 && <span className="ml-1 text-xs text-muted-foreground">+{resto}</span>}
    </span>
  );
}

/**
 * Una FILA del agenda: compacta (hora · título · estado · dueño/es-o-«por cubrir»). Al desplegar
 * muestra la(s) tarjeta(s) real(es) para coger/apuntarse/reasignar/avanzar sin salir del panorama.
 */
function FilaAgenda({
  item,
  abierta,
  onToggle,
  catalogos,
  urgente = false,
}: {
  item: Item;
  abierta: boolean;
  onToggle: () => void;
  catalogos: CatalogosPublicacion | undefined;
  /** En la banda «Urgente ahora»: acento ROJO en la fila (breaking), no el ámbar de «por cubrir». */
  urgente?: boolean;
}) {
  const tarea = item.kind === "tarea" ? item.tarea : null;
  const evento = item.kind === "evento" ? item.evento : null;
  const cob = item.kind === "cobertura" ? item.cobertura : null;
  const titulo = cob ? cob.titulo : tarea ? tarea.titulo : evento!.titulo;
  const hora = cob ? cob.hora : tarea ? tarea.hora_objetivo : evento!.hora;
  const sinDueno =
    (item.kind === "evento" && !item.cubiertoPorTurno) ||
    (item.kind === "tarea" && !tarea!.responsable_id);
  const esCobertura = item.kind === "cobertura" || item.kind === "evento" || Boolean(tarea?.evento_id);

  return (
    <div
      className={cn(
        "rounded-md border",
        urgente
          ? "border-red-500/50 bg-red-50/50 dark:bg-red-950/20"
          : sinDueno
            ? "border-dashed border-amber-500/40 bg-amber-50/40 dark:bg-amber-950/10"
            : "border-border bg-card",
      )}
    >
      <div className="flex items-center">
      <button
        type="button"
        onClick={onToggle}
        className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 text-left"
      >
        {abierta ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="w-11 shrink-0 text-xs tabular-nums text-muted-foreground">
          {hora || "—"}
        </span>
        {/* Semáforo a la IZQUIERDA, antes del título: luz de estado al inicio de la fila. */}
        {cob && <SemaforoCobertura fecha={cob.orden} hora={cob.hora} compacto />}
        {esCobertura && (
          <IconoEvento titulo={titulo} className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="flex-1 truncate text-sm font-medium">{titulo}</span>
        {tarea?.estado === "en_curso" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            En curso
          </Badge>
        )}
        {tarea?.estado === "hecha" && (
          <Badge
            variant="outline"
            className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300"
          >
            Hecha
          </Badge>
        )}
        {sinDueno ? (
          <span className="flex shrink-0 items-center gap-1.5">
            {/* Un recuperable (cobertura soltada) conserva su rol: deja claro QUÉ rol resurge. */}
            {tarea?.evento_id && (
              <span className="hidden text-xs text-muted-foreground sm:inline">
                {etiquetaRol(tarea.formato)}
              </span>
            )}
            <Badge
              variant="outline"
              className="border-amber-500/50 text-amber-700 dark:text-amber-300"
            >
              Sin cubrir
            </Badge>
          </span>
        ) : item.kind === "evento" ? (
          // Nadie lo cogió pero hay turno en su franja: lo cubre el turno (calmado, no ámbar).
          <Badge
            variant="outline"
            className="shrink-0 border-emerald-500/50 text-emerald-700 dark:text-emerald-300"
          >
            Cubierto por turno
          </Badge>
        ) : cob ? (
          <span className="flex shrink-0 items-center gap-1.5">
            {/* Semáforo agregado por rol: qué roles del evento están cubiertos. */}
            <span className="hidden sm:inline">
              <RolesCubiertos cubridores={cob.cubridores} />
            </span>
            <AvataresApilados cubridores={cob.cubridores} />
          </span>
        ) : (
          <span className="flex shrink-0 items-center gap-1">
            <AvatarPersona id={tarea!.responsable_id} nombre={tarea!.responsable_nombre} size="sm" />
            <span className="hidden text-xs text-muted-foreground sm:inline">
              {tarea!.responsable_nombre}
            </span>
          </span>
        )}
      </button>
        {/* Acciones de la fila: editar (lápiz) + borrar (papelera) + ⚡ escalar/des-escalar.
            La papelera queda pegada al ⚡; el lápiz abre el diálogo de edición del calendario. */}
        <span className="flex items-center gap-1 px-1.5">
          <AccionesItem item={item} catalogos={catalogos} />
          <AccionUrgente item={item} />
        </span>
      </div>
      {abierta && (
        <div className="border-t border-border/60 bg-muted/20 p-2">
          {cob ? (
            <TarjetaCobertura cobertura={cob} catalogos={catalogos} sinMenu />
          ) : tarea ? (
            <TarjetaTarea tarea={tarea} catalogos={catalogos} sinMenu />
          ) : (
            <TarjetaEventoLibre
              evento={evento!}
              catalogos={catalogos}
              sinMenu
              cubiertoPorTurno={item.kind === "evento" && Boolean(item.cubiertoPorTurno)}
            />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * PANORAMA (la cabina del coordinador de la rota): una AGENDA por día —como un calendario— de quién cubre qué.
 *
 * Arriba, la carga por persona (avatar + conteo) que además FILTRA la agenda, y una banda con
 * lo último que ha cogido el equipo. Debajo, los partidos/encargos agrupados por día (Hoy /
 * Mañana / fecha) y ordenados por hora; lo «por cubrir» resalta en ámbar (es lo que pide
 * decisión). Cada fila se despliega para coger/reasignar. «Cargar más» trae más días.
 */
/**
 * Re-renderiza cada `intervaloMs` para que el semáforo de cobertura avance con el reloj
 * (PRE-LIVE → «En vivo» → «Cubierto») sin esperar al refetch del tablero: la fase se deriva de
 * `Date.now()` en cada render, así que basta forzar un render periódico.
 */
function useRelojVivo(intervaloMs = 30_000) {
  const [, setTick] = React.useState(0);
  React.useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), intervaloMs);
    return () => clearInterval(id);
  }, [intervaloMs]);
}

export function PanoramaAgenda({
  tareas,
  eventos,
  catalogos,
  marca,
  cubiertosPorTurno,
}: {
  tareas: Publicacion[];
  eventos: EventoRota[];
  catalogos: CatalogosPublicacion | undefined;
  marca: string | undefined;
  /** Ids de eventos que cubre el turno de su franja (no son «sin cubrir»). */
  cubiertosPorTurno: Set<string>;
}) {
  useRelojVivo();
  const [abiertas, setAbiertas] = React.useState<Set<string>>(() => new Set());
  const [filtro, setFiltro] = React.useState<string | null>(null); // id de persona, "__pool__", o null
  const [diasVisibles, setDiasVisibles] = React.useState(5);
  const alternar = (clave: string) =>
    setAbiertas((prev) => {
      const next = new Set(prev);
      if (next.has(clave)) next.delete(clave);
      else next.add(clave);
      return next;
    });

  const { coberturas, encargos, eventosLibres, recuperables } = agrupar(tareas, eventos);
  const usuarios = catalogos?.usuarios ?? [];
  const conResponsable = tareas.filter((t) => t.responsable_id);

  // Nombre por id: lo del catálogo manda; si falta, lo sellado en la tarea.
  const nombrePorId = new Map<string, string>();
  for (const u of usuarios) nombrePorId.set(u.id, u.usuario);
  for (const t of conResponsable) {
    if (!nombrePorId.has(t.responsable_id) && t.responsable_nombre)
      nombrePorId.set(t.responsable_id, t.responsable_nombre);
  }

  // Carga por persona = nº de tareas ACTIVAS. «Activa» = ni hecha, ni un evento que YA pasó: un
  // partido que ya ocurrió no es trabajo pendiente (no se cubre hacia atrás), así que deja de
  // sumar al contador —pero SIGUE en el calendario/agenda para poder revisarlo—. Mismo criterio de
  // «ya pasó» que el semáforo «Cubierto» (posicionTemporal). Más cargados primero (cuello de botella).
  const yaPaso = (fecha?: string | null, hora?: string | null) =>
    posicionTemporal(fecha, hora) === "despues";
  const esCargaActiva = (t: Publicacion) =>
    t.estado !== "hecha" && !(t.evento_id && yaPaso(t.fecha_objetivo, t.hora_objetivo));
  const idsPersona = new Set<string>(usuarios.map((u) => u.id));
  for (const t of conResponsable) idsPersona.add(t.responsable_id);
  const cargas = [...idsPersona]
    .map((id) => ({
      id,
      nombre: nombrePorId.get(id) || "Sin nombre",
      n: conResponsable.filter((t) => t.responsable_id === id && esCargaActiva(t)).length,
    }))
    .sort((a, b) => b.n - a.n || a.nombre.localeCompare(b.nombre));
  // «Por cubrir» también excluye lo que ya pasó (un partido pasado no es coverable). Los encargos
  // sueltos sin dueño NO llevan fecha de evento, así que siguen contando aunque venzan (son tarea
  // pendiente, no un evento ido).
  const nPorCubrir =
    eventosLibres.filter((e) => !yaPaso(e.fecha, e.hora) && !cubiertosPorTurno.has(e.id)).length +
    recuperables.filter((t) => !yaPaso(t.fecha_objetivo, t.hora_objetivo)).length +
    encargos.filter((t) => !t.responsable_id).length;

  // Agenda, aplicando el filtro de persona/pool si lo hay.
  const soloPool = filtro === "__pool__";
  const items: Item[] = [
    // Coberturas: con filtro-persona, las que esa persona cubre; con pool, ninguna (tienen dueño).
    ...coberturas
      .filter((c) =>
        !filtro ? true : soloPool ? false : c.cubridores.some((t) => t.responsable_id === filtro),
      )
      .map((c) => ({
        kind: "cobertura" as const,
        clave: `c-${c.eventoId}`,
        orden: c.orden,
        cobertura: c,
      })),
    // Encargos sueltos + coberturas soltadas (recuperables): por su dueño (o pool si libre).
    ...[...encargos, ...recuperables]
      .filter((t) => (!filtro ? true : soloPool ? !t.responsable_id : t.responsable_id === filtro))
      .map((t) => ({
        kind: "tarea" as const,
        clave: `t-${t.id}`,
        orden: t.fecha_objetivo || "9999-99-99",
        tarea: t,
      })),
    // Eventos por cubrir (0 cubridores): solo sin filtro o con el pool.
    ...(!filtro || soloPool
      ? eventosLibres.map((e) => ({
          kind: "evento" as const,
          clave: `e-${e.id}`,
          orden: e.fecha || "9999-99-99",
          evento: e,
          cubiertoPorTurno: cubiertosPorTurno.has(e.id),
        }))
      : []),
  ];

  // Agrupar por día y ordenar cada día por hora (estilo rundown).
  const horaDe = (i: Item) =>
    i.kind === "cobertura"
      ? i.cobertura.hora || "99:99"
      : i.kind === "tarea"
        ? i.tarea.hora_objetivo || "99:99"
        : i.evento.hora || "99:99";
  const hoy = hoyCDMX();

  // MARCADOR DE HOY: progreso del día (hechos / total), en vivo. Cuenta TODO lo de hoy del equipo
  // —coberturas + encargos + recuperables + eventos por cubrir—, SIN el filtro de persona, para que
  // sea un marcador estable de «cómo va el día». «Hecho» = el partido ya pasó (cobertura, mismo
  // criterio que el semáforo «Cubierto») o la tarea está en «hecha»; un evento por cubrir o un
  // recuperable cuentan en el total pero aún no están hechos.
  const esDeHoy = (fecha?: string | null) => (fecha || "").slice(0, 10) === hoy;
  const coberturasHoy = coberturas.filter((c) => esDeHoy(c.orden));
  const tareasHoy = [...encargos, ...recuperables].filter((t) => esDeHoy(t.fecha_objetivo));
  const eventosHoy = eventosLibres.filter((e) => esDeHoy(e.fecha));
  const totalHoy = coberturasHoy.length + tareasHoy.length + eventosHoy.length;
  const hechosHoy =
    coberturasHoy.filter((c) => yaPaso(c.orden, c.hora)).length +
    tareasHoy.filter((t) => t.estado === "hecha").length;
  const pctHoy = totalHoy ? Math.round((hechosHoy / totalHoy) * 100) : 0;
  // Verde cuando ya está hecha la MAYORÍA del día (≥90%): el día se da por «casi cerrado».
  const hoyCasiListo = totalHoy > 0 && hechosHoy / totalHoy >= 0.9;

  // BANDA «URGENTE AHORA» (breaking): los ítems prioridad «alta» de HOY o SIN FECHA SALEN de los
  // cajones de día y saltan al tope. Lo urgente de otro día se queda en su día (con su badge rojo).
  const urgentes: Item[] = [];
  const enAgenda: Item[] = [];
  for (const it of items) (esUrgenteAhora(it, hoy) ? urgentes : enAgenda).push(it);
  urgentes.sort(
    (a, b) =>
      rangoUrgenciaHoy(a, a.orden) - rangoUrgenciaHoy(b, b.orden) ||
      horaDe(a).localeCompare(horaDe(b)),
  );

  const porDia = new Map<string, Item[]>();
  for (const it of enAgenda) {
    const lista = porDia.get(it.orden) ?? [];
    lista.push(it);
    porDia.set(it.orden, lista);
  }
  const diasOrdenados = [...porDia.keys()].sort((a, b) => {
    const [ra, ka] = ordenDiaAgenda(a, hoy);
    const [rb, kb] = ordenDiaAgenda(b, hoy);
    return ra - rb || ka.localeCompare(kb);
  });
  for (const d of diasOrdenados) {
    const lista = porDia.get(d)!;
    if (d === hoy) {
      // HOY ordena por URGENCIA (en vivo → empieza pronto → por cubrir → resto); la hora desempata.
      lista.sort(
        (a, b) =>
          rangoUrgenciaHoy(a, d) - rangoUrgenciaHoy(b, d) || horaDe(a).localeCompare(horaDe(b)),
      );
    } else {
      // El resto de días, como siempre: por hora (estilo rundown).
      lista.sort((a, b) => horaDe(a).localeCompare(horaDe(b)));
    }
  }
  // La cesta «Sin fecha» (encargos sueltos sin «Para cuándo») NO es un día del rundown: se ancla
  // SIEMPRE al fondo y queda EXENTA de la paginación de días. Si no, un encargo sin fecha (orden
  // "9999-99-99", siempre el último cajón por `ordenDiaAgenda`) cae más allá de la ventana de
  // `diasVisibles` y parece que «no se guardó» —aunque sí está en el tablero—. Solo los días CON
  // fecha se paginan; lo sin fecha es trabajo pendiente que nunca debe esconderse.
  const SIN_FECHA = "9999-99-99";
  const diasConFecha = diasOrdenados.filter((d) => d && d !== SIN_FECHA);
  const diasMostrados = diasConFecha.slice(0, diasVisibles);
  const hayMas = diasConFecha.length > diasVisibles;
  const sinFechaItems = porDia.get(SIN_FECHA) ?? [];

  return (
    <div className="space-y-4">
      {/* MARCADOR de hoy: «hechos / total» del día como UNA línea sutil (no una tile con doble
          chrome). En vivo: se rehace al cubrir/asignar/marcar hecha (invalida CLAVE_TAREAS) o
          cuando un partido pasa. */}
      {totalHoy > 0 && (
        <div
          className="flex items-center gap-2.5 px-0.5 text-xs text-muted-foreground"
          aria-label={`Avance de hoy: ${hechosHoy} de ${totalHoy}`}
        >
          <Target className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
          <span className="shrink-0">Avance de hoy</span>
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                hoyCasiListo ? "bg-emerald-500" : "bg-keni-500",
              )}
              style={{ width: `${pctHoy}%` }}
            />
          </div>
          <span className="shrink-0 tabular-nums">
            <span className={cn("font-semibold text-foreground", hoyCasiListo && "text-emerald-600")}>
              {hechosHoy}
            </span>
            {" / "}
            {totalHoy}
          </span>
        </div>
      )}

      {/* Atajo de 5 segundos para meter algo a cubrir (todos), antes de la agenda. Solo con marca
          concreta: sin ella crearía eventos sin marca que se pierden de las vistas por marca. */}
      {marca && <AnadirRapido marca={marca} />}

      {/* Carga por persona (avatar + conteo) que además filtra la agenda. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-label="Ver solo lo por cubrir"
          onClick={() => setFiltro(filtro === "__pool__" ? null : "__pool__")}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
            filtro === "__pool__"
              ? "border-amber-500 bg-amber-100/60 dark:bg-amber-950/30"
              : "border-amber-500/40 hover:bg-accent",
          )}
        >
          <Hand className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
          Por cubrir
          <Badge variant="outline" className="px-1.5 py-0 tabular-nums">
            {nPorCubrir}
          </Badge>
        </button>
        {cargas.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-label={`Ver solo lo de ${c.nombre}`}
            onClick={() => setFiltro(filtro === c.id ? null : c.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs",
              filtro === c.id ? "border-foreground/40 bg-accent" : "border-border hover:bg-accent",
            )}
          >
            <AvatarPersona id={c.id} nombre={c.nombre} size="sm" />
            <span className="font-medium">{c.nombre}</span>
            <Badge
              variant="outline"
              className={cn("px-1.5 py-0 tabular-nums", c.n === 0 && "text-muted-foreground")}
            >
              {c.n}
            </Badge>
          </button>
        ))}
        {filtro && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground"
            onClick={() => setFiltro(null)}
          >
            Ver todo
          </Button>
        )}
      </div>

      {/* BANDA «URGENTE AHORA» (breaking): por ENCIMA de la agenda por día. Solo si hay urgentes
          de ahora (alta + hoy/sin fecha); si no, no se muestra. Estas filas salieron de los cajones. */}
      {urgentes.length > 0 && (
        <section
          aria-label="Urgente ahora"
          className="space-y-1.5 rounded-lg border border-red-500/50 bg-red-50/60 p-2.5 shadow-sm dark:bg-red-950/20"
        >
          <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-red-700 dark:text-red-300">
            <Zap className="h-3.5 w-3.5" />
            Urgente ahora
            <span className="tabular-nums">({urgentes.length})</span>
          </h2>
          <div className="space-y-1.5">
            {urgentes.map((it) => (
              <FilaAgenda
                key={it.clave}
                item={it}
                abierta={abiertas.has(it.clave)}
                onToggle={() => alternar(it.clave)}
                catalogos={catalogos}
                urgente
              />
            ))}
          </div>
        </section>
      )}

      {urgentes.length === 0 && diasMostrados.length === 0 && sinFechaItems.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {filtro
              ? "Nada por aquí con este filtro."
              : "Aún no hay partidos ni tareas. Súbelos en Fuentes o añádelos aquí."}
          </p>
        </div>
      ) : diasMostrados.length === 0 && sinFechaItems.length === 0 ? null : (
        <div className="space-y-4">
          {diasMostrados.map((dia) => (
            <section key={dia} className="space-y-1.5">
              <h2 className="sticky top-0 z-10 bg-background/95 py-1 text-sm font-semibold backdrop-blur">
                {etiquetaDia(dia, hoy)}
                <span className="ml-1.5 font-normal tabular-nums text-muted-foreground">
                  ({porDia.get(dia)!.length})
                </span>
              </h2>
              <div className="space-y-1.5">
                {porDia.get(dia)!.map((it) => (
                  <FilaAgenda
                    key={it.clave}
                    item={it}
                    abierta={abiertas.has(it.clave)}
                    onToggle={() => alternar(it.clave)}
                    catalogos={catalogos}
                  />
                ))}
              </div>
            </section>
          ))}
          {hayMas && (
            <div className="flex justify-center">
              <Button variant="outline" size="sm" onClick={() => setDiasVisibles((d) => d + 5)}>
                Cargar más días
              </Button>
            </div>
          )}
          {/* «Sin fecha»: anclada al fondo y SIEMPRE visible (no la pagina «Cargar más días»).
              Son encargos sueltos sin «Para cuándo» — trabajo pendiente que no debe esconderse. */}
          {sinFechaItems.length > 0 && (
            <section key={SIN_FECHA} className="space-y-1.5">
              <h2 className="sticky top-0 z-10 bg-background/95 py-1 text-sm font-semibold backdrop-blur">
                {etiquetaDia(SIN_FECHA, hoy)}
                <span className="ml-1.5 font-normal tabular-nums text-muted-foreground">
                  ({sinFechaItems.length})
                </span>
              </h2>
              <div className="space-y-1.5">
                {sinFechaItems.map((it) => (
                  <FilaAgenda
                    key={it.clave}
                    item={it}
                    abierta={abiertas.has(it.clave)}
                    onToggle={() => alternar(it.clave)}
                    catalogos={catalogos}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
