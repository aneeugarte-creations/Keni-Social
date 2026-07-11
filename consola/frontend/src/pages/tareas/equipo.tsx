import { CalendarClock, Users } from "lucide-react";

import { ChipEstado } from "@/components/comunes/ChipEstado";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { formatearFecha, posicionTemporal } from "@/lib/fecha";
import { cn } from "@/lib/utils";

import { AvatarPersona } from "./AvatarPersona";
import { IconoEvento } from "./icono-evento";
import { etiquetaRol } from "./roles";
import { SemaforoCobertura } from "./tarjetas";
import type { Item } from "./tipos";

type Persona = { id: string; nombre: string };

/**
 * Dueños de un ítem: los cubridores de una cobertura (≥1) o el responsable de un encargo. Un
 * evento sin cubrir NO tiene dueño → no entra en el desglose por persona (vive en «Todo» ›
 * «Por cubrir»). Una cobertura compartida sale en la sección de CADA cubridor.
 */
function responsablesDe(i: Item): Persona[] {
  if (i.kind === "cobertura")
    return i.cobertura.cubridores
      .filter((c) => c.responsable_id)
      .map((c) => ({ id: c.responsable_id, nombre: c.responsable_nombre || c.responsable_id }));
  if (i.kind === "tarea" && i.tarea.responsable_id)
    return [{ id: i.tarea.responsable_id, nombre: i.tarea.responsable_nombre || i.tarea.responsable_id }];
  return [];
}

/** Una cobertura cuyo evento ya pasó está hecha (cae a «Hechas»), igual que en «Mis tareas». */
const coberturaPasada = (i: Item) =>
  i.kind === "cobertura" && posicionTemporal(i.cobertura.orden, i.cobertura.hora) === "despues";

const enMarcha = (i: Item) =>
  (i.kind === "cobertura" && !coberturaPasada(i)) ||
  (i.kind === "tarea" && i.tarea.estado !== "hecha");

const hecha = (i: Item) =>
  coberturaPasada(i) || (i.kind === "tarea" && i.tarea.estado === "hecha");

const BADGE_URGENTE = "border-red-500/40 font-normal text-red-700 dark:text-red-300";

/**
 * Ficha de SOLO LECTURA de un ítem en la vista «Equipo»: el admin INSPECCIONA lo que tiene cada
 * quien (no actúa desde aquí; el reparto vive en «Todo» y «Mis tareas»). Una cobertura se pinta
 * con los roles de ESA persona (no los del admin que mira), tal como ella los ve en su lista.
 */
function FilaItemPersona({ item, personaId }: { item: Item; personaId: string }) {
  if (item.kind === "cobertura") {
    const roles = item.cobertura.cubridores.filter((c) => c.responsable_id === personaId);
    return (
      <div className="rounded-xl border bg-card p-3">
        <div className="flex items-center gap-2">
          <IconoEvento titulo={item.cobertura.titulo} className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="font-medium">{item.cobertura.titulo}</span>
          {item.cobertura.prioridad === "alta" && (
            <Badge variant="outline" className={BADGE_URGENTE}>
              Urgente
            </Badge>
          )}
        </div>
        <div className="mt-2 space-y-1.5">
          {roles.map((t) => (
            <div key={t.id} className="flex items-center gap-2 text-sm">
              <SemaforoCobertura fecha={t.fecha_objetivo} hora={t.hora_objetivo} />
              <span className="text-muted-foreground">{etiquetaRol(t.formato)}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (item.kind === "tarea") {
    const t = item.tarea;
    return (
      <div className="rounded-xl border bg-card p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{t.titulo}</span>
          {t.estado === "en_curso" && <ChipEstado estado="en_curso" />}
          {t.estado === "hecha" && <ChipEstado estado="completado" />}
          {t.prioridad === "alta" && (
            <Badge variant="outline" className={BADGE_URGENTE}>
              Alta
            </Badge>
          )}
          {t.fecha_objetivo && (
            <span
              className={cn(
                "inline-flex items-center gap-1 text-sm",
                t.vencido ? "text-red-700 dark:text-red-300" : "text-muted-foreground",
              )}
            >
              <CalendarClock className="h-3.5 w-3.5" />
              {formatearFecha(t.fecha_objetivo)}
              {t.hora_objetivo ? ` · ${t.hora_objetivo}` : ""}
            </span>
          )}
        </div>
        {t.descripcion && (
          <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
            {t.descripcion}
          </p>
        )}
      </div>
    );
  }
  return null;
}

/**
 * Lente «Equipo» (solo manager): desglosa la MISMA lista compartida por PERSONA, para que un
 * admin vea de un vistazo qué tiene cada quien y cómo le aparece. Una sección por persona con
 * trabajo asignado (ordenadas por nombre), con sus ítems agrupados «En marcha / Hechas» igual
 * que en «Mis tareas». Lo que no tiene dueño no sale aquí (está en «Todo» › «Por cubrir»).
 */
export function VistaEquipo({ items }: { items: Item[] }) {
  const porPersona = new Map<string, { nombre: string; items: Item[] }>();
  for (const i of items) {
    for (const r of responsablesDe(i)) {
      const entrada = porPersona.get(r.id) ?? { nombre: r.nombre, items: [] };
      entrada.items.push(i);
      porPersona.set(r.id, entrada);
    }
  }
  const personas = [...porPersona.entries()]
    .map(([id, { nombre, items }]) => ({ id, nombre, items }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre));

  if (personas.length === 0)
    return (
      <EstadoVacio
        icono={Users}
        titulo="Nadie tiene trabajo asignado"
        texto="El trabajo sin dueño está en «Todo» › «Por cubrir»."
      />
    );

  return (
    <div className="space-y-6">
      {personas.map((p) => {
        const grupos = [
          { etiqueta: "En marcha", items: p.items.filter(enMarcha) },
          { etiqueta: "Hechas", items: p.items.filter(hecha) },
        ];
        return (
          <section key={p.id} aria-label={`Trabajo de ${p.nombre}`} className="space-y-2">
            <div className="flex items-center gap-2">
              <AvatarPersona id={p.id} nombre={p.nombre} size="sm" />
              <h2 className="text-sm font-semibold">{p.nombre}</h2>
              <span className="tabular-nums text-muted-foreground">({p.items.length})</span>
            </div>
            {grupos.map((g) =>
              g.items.length === 0 ? null : (
                <div key={g.etiqueta} className="space-y-2">
                  <h3 className="text-xs font-medium text-muted-foreground">
                    {g.etiqueta}
                    <span className="ml-1 tabular-nums">({g.items.length})</span>
                  </h3>
                  <div className="space-y-2">
                    {g.items.map((i) => (
                      <FilaItemPersona key={i.clave} item={i} personaId={p.id} />
                    ))}
                  </div>
                </div>
              ),
            )}
          </section>
        );
      })}
    </div>
  );
}
