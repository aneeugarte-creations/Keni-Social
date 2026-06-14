import { ChevronDown, ChevronRight, Hand, Plus, Trophy } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatearDia, hoyCDMX, tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, Contenido, EventoRota } from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { DialogoAnadirPersona } from "./dialogos";
import { etiquetaRol } from "./roles";
import {
  RolesCubiertos,
  SemaforoCobertura,
  TarjetaCobertura,
  TarjetaEventoLibre,
  TarjetaTarea,
} from "./tarjetas";
import { agrupar, type Item } from "./tipos";

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

/** Banda superior: lo ÚLTIMO que ha cogido el equipo (por momento de asignación), para ver el pulso. */
function BandaReciente({ tareas }: { tareas: Contenido[] }) {
  const recientes = tareas
    .filter((t) => t.responsable_id)
    .slice()
    .sort((a, b) => (b.actualizado || "").localeCompare(a.actualizado || ""))
    .slice(0, 5);
  if (recientes.length === 0) return null;
  return (
    <section className="space-y-1.5">
      <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Lo último que ha cogido el equipo
      </h2>
      <div className="flex flex-wrap gap-2">
        {recientes.map((t) => {
          const rel = t.actualizado ? tiempoRelativo(t.actualizado) : "";
          return (
            <div
              key={t.id}
              className="flex items-center gap-1.5 rounded-full border border-border bg-card px-2 py-1 text-xs shadow-sm"
            >
              <AvatarPersona id={t.responsable_id} nombre={t.responsable_nombre} size="sm" />
              <span className="font-medium">{t.responsable_nombre}</span>
              <span className="max-w-[12rem] truncate text-muted-foreground">{t.titulo}</span>
              {rel && <span className="shrink-0 text-muted-foreground">· {rel}</span>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Avatares de los cubridores, apilados (-space) con «+N» si son muchos. */
function AvataresApilados({ cubridores }: { cubridores: Contenido[] }) {
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
}: {
  item: Item;
  abierta: boolean;
  onToggle: () => void;
  catalogos: CatalogosContenido | undefined;
}) {
  const tarea = item.kind === "tarea" ? item.tarea : null;
  const evento = item.kind === "evento" ? item.evento : null;
  const cob = item.kind === "cobertura" ? item.cobertura : null;
  const titulo = cob ? cob.titulo : tarea ? tarea.titulo : evento!.titulo;
  const hora = cob ? cob.hora : tarea ? tarea.hora_objetivo : evento!.hora;
  const sinDueno = item.kind === "evento" || (item.kind === "tarea" && !tarea!.responsable_id);
  const esCobertura = item.kind === "cobertura" || item.kind === "evento" || Boolean(tarea?.evento_id);

  return (
    <div
      className={cn(
        "rounded-md border",
        sinDueno
          ? "border-dashed border-amber-500/40 bg-amber-50/40 dark:bg-amber-950/10"
          : "border-border bg-card",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left"
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
        {esCobertura && <Trophy className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
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
              Por cubrir
            </Badge>
          </span>
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
      {abierta && (
        <div className="border-t border-border/60 bg-muted/20 p-2">
          {cob ? (
            <TarjetaCobertura cobertura={cob} catalogos={catalogos} />
          ) : tarea ? (
            <TarjetaTarea tarea={tarea} catalogos={catalogos} />
          ) : (
            <TarjetaEventoLibre evento={evento!} catalogos={catalogos} />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * PANORAMA (la cabina de Elias): una AGENDA por día —como un calendario— de quién cubre qué.
 *
 * Arriba, la carga por persona (avatar + conteo) que además FILTRA la agenda, y una banda con
 * lo último que ha cogido el equipo. Debajo, los partidos/encargos agrupados por día (Hoy /
 * Mañana / fecha) y ordenados por hora; lo «por cubrir» resalta en ámbar (es lo que pide
 * decisión). Cada fila se despliega para coger/reasignar. «Cargar más» trae más días.
 */
export function PanoramaAgenda({
  tareas,
  eventos,
  catalogos,
  marca,
  esAdmin,
}: {
  tareas: Contenido[];
  eventos: EventoRota[];
  catalogos: CatalogosContenido | undefined;
  marca: string | undefined;
  esAdmin: boolean;
}) {
  const [abiertas, setAbiertas] = React.useState<Set<string>>(() => new Set());
  const [filtro, setFiltro] = React.useState<string | null>(null); // id de persona, "__pool__", o null
  const [diasVisibles, setDiasVisibles] = React.useState(5);
  const [anadirAbierto, setAnadirAbierto] = React.useState(false);
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

  // Carga por persona = nº de tareas activas (no hechas). Más cargados primero (cuello de botella).
  const idsPersona = new Set<string>(usuarios.map((u) => u.id));
  for (const t of conResponsable) idsPersona.add(t.responsable_id);
  const cargas = [...idsPersona]
    .map((id) => ({
      id,
      nombre: nombrePorId.get(id) || "Sin nombre",
      n: conResponsable.filter((t) => t.responsable_id === id && t.estado !== "hecha").length,
    }))
    .sort((a, b) => b.n - a.n || a.nombre.localeCompare(b.nombre));
  const nPorCubrir =
    eventosLibres.length + recuperables.length + encargos.filter((t) => !t.responsable_id).length;

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
  const porDia = new Map<string, Item[]>();
  for (const it of items) {
    const lista = porDia.get(it.orden) ?? [];
    lista.push(it);
    porDia.set(it.orden, lista);
  }
  const diasOrdenados = [...porDia.keys()].sort();
  for (const d of diasOrdenados) porDia.get(d)!.sort((a, b) => horaDe(a).localeCompare(horaDe(b)));
  const diasMostrados = diasOrdenados.slice(0, diasVisibles);
  const hayMas = diasOrdenados.length > diasVisibles;
  const hoy = hoyCDMX();

  return (
    <div className="space-y-4">
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
        {esAdmin && marca && (
          <button
            type="button"
            aria-label="Añadir persona al equipo"
            onClick={() => setAnadirAbierto(true)}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        )}
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

      {!filtro && <BandaReciente tareas={tareas} />}

      {diasMostrados.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {filtro
              ? "Nada por aquí con este filtro."
              : "Aún no hay partidos ni tareas. Súbelos en Fuentes o añádelos aquí."}
          </p>
        </div>
      ) : (
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
        </div>
      )}

      {marca && (
        <DialogoAnadirPersona
          marca={marca}
          abierto={anadirAbierto}
          onOpenChange={setAnadirAbierto}
        />
      )}
    </div>
  );
}
