import { useMutation } from "@tanstack/react-query";
import { Loader2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";
import { asignarMatriz } from "@/lib/rota-reparto";
import { cn } from "@/lib/utils";
import type { FranjaSemana, MiembroRota, TurnoRota } from "@/types";

import { aMinutos24 } from "./DialogoAsignarTurnos";

/** getDay(): 0=domingo … 6=sábado → letra del día (lunes=L). */
const LETRAS_SEM = ["D", "L", "M", "X", "J", "V", "S"];
function letraDeFecha(iso: string): string {
  return LETRAS_SEM[new Date(`${iso}T12:00:00`).getDay()] ?? "";
}

function esHoraValida(s: string): boolean {
  return aMinutos24(s) !== null;
}

const clave = (id: string, fecha: string) => `${id}|${fecha}`;

/** Token de persona (mismo lenguaje que el calendario: elegido = naranja suave). */
function Token({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={activo}
      onClick={onClick}
      className={cn(
        "rounded-full px-2.5 py-1 text-[13px] leading-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        activo
          ? "bg-keni-50 font-medium text-keni-700 dark:bg-keni-900/30 dark:text-keni-300"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Panel «Asignar turnos» de Gestión = Mes único (variante SELECCIÓN-EN-MES).
 *
 * Los DÍAS los marca el usuario en el calendario mensual (`diasSel`, puede cruzar semanas). Aquí
 * elige PERSONAS y HORARIO, y AFINA por persona en una matriz que pinta la REALIDAD: una celda
 * vacía está encendida por defecto y se CREA al asignar; una celda con turno real se muestra como
 * tal (naranja + punto) y un toque la marca para QUITAR (tachado gris, sin un segundo acento). El
 * mismo gesto añade o quita; el botón es uno e inteligente. Al asignar, el motor `asignarMatriz`
 * agrupa las fechas de cada persona por su semana y resuelve la franja con las franjas de ESA
 * semana; al quitar, se borran por lote los turnos reales de las celdas marcadas (con deshacer).
 */
export function ReparteMes({
  diasSel,
  cms,
  franjasPorSemana,
  turnosExistentes,
  onCambio,
  onCerrar,
  onLimpiarDias,
}: {
  /** Días ISO marcados en el calendario (columnas de la matriz). Controlado por Gestión. */
  diasSel: Set<string>;
  /** CMs asignables de la marca activa (filas candidatas). */
  cms: MiembroRota[];
  /** lunes ISO → franjas LABORALES vivas de esa semana (las de las semanas tocadas por `diasSel`). */
  franjasPorSemana: Map<string, FranjaSemana[]>;
  /** `${miembro_id}|${fecha}` → turnos reales en esa celda (de las semanas tocadas). La matriz los
   *  pinta como «turno real» y deja marcarlos para quitar. */
  turnosExistentes: Map<string, TurnoRota[]>;
  /** Refresca el calendario tras asignar/quitar. */
  onCambio: () => void;
  /** Oculta el panel (✕). */
  onCerrar: () => void;
  /** Limpia la selección de días del calendario (tras una tanda con cambios). */
  onLimpiarDias: () => void;
}) {
  const dias = React.useMemo(() => Array.from(diasSel).sort(), [diasSel]);
  const [personasSel, setPersonasSel] = React.useState<Set<string>>(() => new Set());
  const [inicio, setInicio] = React.useState("08:00");
  const [fin, setFin] = React.useState("16:00");
  // `excluidas[persona]` = días VACÍOS que ESA persona NO trabaja (opt-out). Por defecto cada celda
  // vacía está encendida (se creará); apagarla añade su fecha aquí.
  const [excluidas, setExcluidas] = React.useState<Map<string, Set<string>>>(() => new Map());
  // `paraBorrar` = celdas con turno REAL marcadas para quitar (`${persona}|${fecha}`).
  const [paraBorrar, setParaBorrar] = React.useState<Set<string>>(() => new Set());

  const togglePersona = (id: string) =>
    setPersonasSel((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const turnosEn = (id: string, fecha: string) => turnosExistentes.get(clave(id, fecha)) ?? [];
  const existe = (id: string, fecha: string) => turnosEn(id, fecha).length > 0;
  const celdaEncendida = (id: string, fecha: string) => !excluidas.get(id)?.has(fecha);

  type EstadoCelda = "vacia" | "add" | "existe" | "del";
  const estadoCelda = (id: string, fecha: string): EstadoCelda => {
    if (existe(id, fecha)) return paraBorrar.has(clave(id, fecha)) ? "del" : "existe";
    return celdaEncendida(id, fecha) ? "add" : "vacia";
  };

  const toggleCelda = (id: string, fecha: string) => {
    const k = clave(id, fecha);
    if (existe(id, fecha)) {
      setParaBorrar((prev) => {
        const n = new Set(prev);
        if (n.has(k)) n.delete(k);
        else n.add(k);
        return n;
      });
    } else {
      setExcluidas((prev) => {
        const n = new Map(prev);
        const s = new Set(n.get(id) ?? []);
        if (s.has(fecha)) s.delete(fecha);
        else s.add(fecha);
        n.set(id, s);
        return n;
      });
    }
  };

  const personasElegidas = cms.filter((m) => personasSel.has(m.id));
  // Altas: celdas VACÍAS encendidas (no recreamos las que ya existen).
  const addsDePersona = (id: string) => dias.filter((f) => !existe(id, f) && celdaEncendida(id, f));
  // Bajas: celdas con turno real marcadas para quitar.
  const delsDePersona = (id: string) => dias.filter((f) => existe(id, f) && paraBorrar.has(clave(id, f)));
  const totalAdds = personasElegidas.reduce((acc, m) => acc + addsDePersona(m.id).length, 0);
  const totalDels = personasElegidas.reduce((acc, m) => acc + delsDePersona(m.id).length, 0);
  const horasValidas = esHoraValida(inicio) && esHoraValida(fin);

  const incompleto =
    (totalAdds === 0 && totalDels === 0) || (totalAdds > 0 && !horasValidas);
  const pista =
    diasSel.size === 0
      ? "Marca días en el calendario para repartir."
      : personasElegidas.length === 0
        ? "Elige al menos una persona."
        : totalAdds > 0 && !horasValidas
          ? "Escribe un horario válido (HH:MM)."
          : totalAdds === 0 && totalDels === 0
            ? "Toca celdas: vacía añade · con turno quita."
            : null;

  // Restaura por lote los turnos borrados (deshacer): recrea con su franja/horas/override/nota.
  const deshacer = async (snapshot: TurnoRota[]) => {
    try {
      await api.crearTurnosLote({
        turnos: snapshot.map((t) => ({
          fecha: t.fecha,
          miembro_id: t.miembro_id,
          franja_id: t.franja_id,
          inicio: t.horario_propio ? t.inicio : "",
          fin: t.horario_propio ? t.fin : "",
          override: t.override,
          motivo: t.motivo,
          nota_relevo: t.nota_relevo,
        })),
      });
      onCambio();
      toast.success("Turnos restaurados.");
    } catch (e) {
      toast.error(mensajeError(e));
    }
  };

  const aplicar = useMutation({
    mutationFn: async () => {
      // Bajas: ids de los turnos reales de las celdas marcadas + snapshot para deshacer.
      const delIds: string[] = [];
      const snapshot: TurnoRota[] = [];
      personasElegidas.forEach((m) =>
        delsDePersona(m.id).forEach((f) =>
          turnosEn(m.id, f).forEach((t) => {
            delIds.push(t.id);
            snapshot.push(t);
          }),
        ),
      );
      // Altas: una entrada por persona con sus días vacíos encendidos.
      const porPersona = new Map<string, string[]>();
      personasElegidas.forEach((m) => {
        const fechas = addsDePersona(m.id);
        if (fechas.length) porPersona.set(m.id, fechas);
      });

      if (delIds.length) await api.borrarTurnosLote({ ids: delIds });
      const alta = porPersona.size
        ? await asignarMatriz(porPersona, franjasPorSemana, inicio, fin)
        : null;
      return { borrados: delIds.length, snapshot, alta };
    },
    onSuccess: ({ borrados, snapshot, alta }) => {
      onCambio();
      let hubo = false;
      if (borrados) {
        hubo = true;
        toast.success(`${borrados} turno${borrados === 1 ? "" : "s"} borrado${borrados === 1 ? "" : "s"}`, {
          action: { label: "Deshacer", onClick: () => void deshacer(snapshot) },
        });
      }
      if (alta) {
        const partes: string[] = [];
        if (alta.creados) {
          hubo = true;
          const p = alta.personasConCreados === 1 ? "1 persona" : `${alta.personasConCreados} personas`;
          partes.push(`${alta.creados} turno${alta.creados === 1 ? "" : "s"} para ${p}`);
        }
        if (alta.yaEstaba) partes.push(`${alta.yaEstaba} ya estaba${alta.yaEstaba === 1 ? "" : "n"}`);
        if (alta.requierenOverride)
          partes.push(
            `${alta.requierenOverride} por ausencia ${alta.requierenOverride === 1 ? "pide" : "piden"} override (hazlo desde la celda)`,
          );
        if (alta.sinFranja) partes.push(`${alta.sinFranja} sin franja laboral esa semana`);
        if (alta.fallos) partes.push(`${alta.fallos} con error`);
        const msg = partes.join(" · ");
        if (alta.creados > 0) toast.success(msg);
        else if (msg) toast.error(msg);
      }
      // Tras una tanda con cambios, limpia personas + marcas + la selección de días.
      if (hubo) {
        setPersonasSel(new Set());
        setExcluidas(new Map());
        setParaBorrar(new Set());
        onLimpiarDias();
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Antes de borrar, confirma con el conteo, de quién, y el aviso de turnos protegidos.
  const onAplicar = async () => {
    if (incompleto || aplicar.isPending) return;
    if (totalDels > 0) {
      const porPersona = new Map<string, number>();
      let protegidos = 0;
      personasElegidas.forEach((m) => {
        const n = delsDePersona(m.id).reduce((acc, f) => acc + turnosEn(m.id, f).length, 0);
        if (n) porPersona.set(m.nombre, n);
        delsDePersona(m.id).forEach((f) =>
          turnosEn(m.id, f).forEach((t) => {
            if (t.override || t.nota_relevo) protegidos += 1;
          }),
        );
      });
      const quien =
        porPersona.size === 1
          ? `de ${[...porPersona.keys()][0]}`
          : `de ${porPersona.size} personas`;
      const ok = await confirmar({
        titulo: `Borrar ${totalDels} turno${totalDels === 1 ? "" : "s"}`,
        destructivo: true,
        textoConfirmar: "Borrar",
        mensaje: (
          <div className="space-y-2 text-sm">
            <p>
              Se quitarán <b>{totalDels}</b> turno{totalDels === 1 ? "" : "s"} {quien} en los días
              marcados. Podrás deshacer unos segundos.
            </p>
            {protegidos > 0 && (
              <p className="text-amber-700 dark:text-amber-400">
                Incluye {protegidos} protegido{protegidos === 1 ? "" : "s"} (refuerzo de matchday /
                nota de relevo).
              </p>
            )}
          </div>
        ),
      });
      if (!ok) return;
    }
    aplicar.mutate();
  };

  const eyebrow = "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/70";

  return (
    <div className="flex shrink-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Asignar turnos</h2>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onCerrar}
          aria-label="Cerrar"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Personas */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <Label className={eyebrow}>Personas</Label>
          <div className="flex items-center gap-1.5 text-[11px]">
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground hover:underline"
              onClick={() => setPersonasSel(new Set(cms.map((m) => m.id)))}
            >
              Todas
            </button>
            <span className="text-muted-foreground/40">·</span>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground hover:underline"
              onClick={() => setPersonasSel(new Set())}
            >
              Ninguna
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-0.5">
          {cms.map((m) => (
            <Token key={m.id} activo={personasSel.has(m.id)} onClick={() => togglePersona(m.id)}>
              {m.nombre}
            </Token>
          ))}
        </div>
      </div>

      {/* Horario */}
      <div className="space-y-2">
        <Label className={eyebrow}>Horario</Label>
        <div className="flex items-center gap-3">
          <Input
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            placeholder="08:00"
            className="h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0"
            aria-label="Hora de inicio"
          />
          <span className="text-muted-foreground">–</span>
          <Input
            value={fin}
            onChange={(e) => setFin(e.target.value)}
            placeholder="16:00"
            className="h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0"
            aria-label="Hora de fin"
          />
        </div>
        {!horasValidas && (inicio || fin) && (
          <p className="text-xs text-destructive">Usa HH:MM (24h), p. ej. 08:00.</p>
        )}
      </div>

      {/* Matriz: filas = personas elegidas, columnas = días marcados en el calendario. */}
      <div className="space-y-2">
        <div>
          <Label className={eyebrow}>El patrón de cada persona</Label>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Toca una celda: vacía → añade · con turno → quita (tachado). Cada quien el suyo.
          </p>
        </div>
        {diasSel.size === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
            Marca días en el calendario para repartir.
          </p>
        ) : personasElegidas.length === 0 ? (
          <p className="rounded-lg border border-border px-3 py-4 text-center text-xs text-muted-foreground">
            Elige personas para ver la matriz.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border p-2">
            <table className="border-separate border-spacing-[3px] tabular-nums">
              <thead>
                <tr>
                  <th />
                  {dias.map((f) => (
                    <th key={f} className="px-0 text-center align-bottom font-normal leading-none">
                      <span className="block text-[10px] font-semibold uppercase text-muted-foreground/70">
                        {letraDeFecha(f)}
                      </span>
                      <span className="block text-[9px] text-muted-foreground/50">
                        {f.slice(8, 10)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {personasElegidas.map((m) => (
                  <tr key={m.id}>
                    <td className="max-w-[5rem] truncate pr-2 text-[11.5px] text-foreground/80">
                      {m.nombre}
                    </td>
                    {dias.map((f) => {
                      const st = estadoCelda(m.id, f);
                      const t = turnosEn(m.id, f)[0];
                      const tip = t
                        ? `${t.franja_nombre}${t.override ? " · refuerzo matchday" : ""}${t.nota_relevo ? " · nota de relevo" : ""}`
                        : "vacío";
                      return (
                        <td key={f}>
                          <button
                            type="button"
                            role="checkbox"
                            aria-checked={st === "add" || st === "existe"}
                            aria-label={`${m.nombre} ${f.slice(8, 10)}`}
                            title={tip}
                            onClick={() => toggleCelda(m.id, f)}
                            className={cn(
                              "relative h-[18px] w-[22px] rounded-[4px] border transition-colors",
                              st === "add" && "border-keni-400/40 bg-keni-50 dark:bg-keni-900/30",
                              st === "existe" && "border-keni-400 bg-keni-50 dark:bg-keni-900/30",
                              st === "del" && "border-border/60 bg-keni-50/50 dark:bg-keni-900/20",
                              st === "vacia" && "border-border/60 hover:bg-accent",
                            )}
                          >
                            {st === "existe" && (
                              <span className="pointer-events-none absolute right-0.5 top-0.5 h-1 w-1 rounded-full bg-keni-700 dark:bg-keni-300" />
                            )}
                            {st === "del" && (
                              <span
                                className="pointer-events-none absolute inset-0"
                                style={{
                                  backgroundImage:
                                    "linear-gradient(to top right, transparent 45%, hsl(var(--muted-foreground)) 45%, hsl(var(--muted-foreground)) 55%, transparent 55%)",
                                }}
                              />
                            )}
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pie: pista de qué falta, o el resumen de altas/bajas + el botón inteligente. */}
      <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
        <span className="text-xs text-muted-foreground">
          {pista ?? (
            <>
              {totalAdds > 0 && (
                <b className="font-semibold text-keni-700 dark:text-keni-300">
                  {totalAdds} nuevo{totalAdds === 1 ? "" : "s"}
                </b>
              )}
              {totalAdds > 0 && totalDels > 0 && " · "}
              {totalDels > 0 && (
                <span className="text-destructive">
                  {totalDels} a quitar
                </span>
              )}
            </>
          )}
        </span>
        <Button
          variant="secondary"
          onClick={() => void onAplicar()}
          disabled={incompleto || aplicar.isPending}
        >
          {aplicar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
          {aplicar.isPending
            ? "Aplicando…"
            : totalAdds > 0 && totalDels > 0
              ? `Aplicar (+${totalAdds} · −${totalDels})`
              : totalDels > 0
                ? `Quitar ${totalDels} turno${totalDels === 1 ? "" : "s"}`
                : totalAdds > 0
                  ? `Asignar ${totalAdds} turno${totalAdds === 1 ? "" : "s"}`
                  : "Asignar"}
        </Button>
      </div>
    </div>
  );
}
