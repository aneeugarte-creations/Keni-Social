import { useMutation } from "@tanstack/react-query";
import { X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { AvisoZonaOperativa } from "@/components/comunes/AvisoZonaOperativa";
import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { ApiError, api, mensajeError } from "@/lib/api";
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

const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
/** "2026-06-13" → "13 jun" (para listar eventos en el aviso de huecos). */
function fechaCorta(iso: string): string {
  return `${Number(iso.slice(8, 10))} ${MESES_CORTOS[Number(iso.slice(5, 7)) - 1] ?? ""}`;
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
 * Editor de hora de UN turno real, en línea en el panel (variante «ahí mismo»): toca un turno de
 * la matriz y aquí cambias su horario sin abrir el calendario. «Guardar hora» hace un PATCH
 * (`actualizarTurno`) que pone horas a medida; si el back pide override por ausencia (409) ofrece
 * «Forzar». «Quitar turno» NO borra al vuelo: marca la celda para el lote de borrado del pie (con
 * su confirmación, aviso de huecos y deshacer). Keyed por `turno.id` para resetear el estado local.
 */
function EditorHoraCelda({
  turno,
  marcadoQuitar,
  onCambio,
  onToggleQuitar,
  onCerrar,
}: {
  turno: TurnoRota;
  /** ¿La celda ya está marcada para el lote de borrado? Alterna la etiqueta Quitar/No quitar. */
  marcadoQuitar: boolean;
  onCambio: () => void;
  onToggleQuitar: () => void;
  onCerrar: () => void;
}) {
  const [inicio, setInicio] = React.useState(turno.inicio);
  const [fin, setFin] = React.useState(turno.fin);
  // Mensaje del 409 `requiere_override` (turno en día de ausencia): muestra «Forzar».
  const [pendienteOverride, setPendienteOverride] = React.useState<string | null>(null);

  const horasValidas = esHoraValida(inicio) && esHoraValida(fin);
  const sinCambios = inicio === turno.inicio && fin === turno.fin;

  const guardar = useMutation({
    mutationFn: (override: boolean) =>
      api.actualizarTurno(turno.id, {
        inicio: inicio.trim(),
        fin: fin.trim(),
        ...(override ? { override: true } : {}),
      }),
    onSuccess: () => {
      toast.success("Horario actualizado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        setPendienteOverride(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const claseInput =
    "h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0";

  return (
    <div className="space-y-2.5 rounded-lg border border-keni-400/50 bg-keni-50/40 p-3 dark:border-keni-400/30 dark:bg-keni-900/15">
      <div className="flex items-center justify-between">
        <p className="text-[11.5px] font-medium text-foreground/80">
          {turno.miembro_nombre} · {letraDeFecha(turno.fecha)} {turno.fecha.slice(8, 10)} ·{" "}
          {turno.franja_nombre}
        </p>
        <button
          type="button"
          onClick={onCerrar}
          aria-label="Cerrar editor de hora"
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      <div className="flex items-center gap-2">
        <Input
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          placeholder="08:00"
          aria-label="Nueva hora de inicio"
          className={claseInput}
        />
        <span className="text-muted-foreground">–</span>
        <Input
          value={fin}
          onChange={(e) => setFin(e.target.value)}
          placeholder="16:00"
          aria-label="Nueva hora de fin"
          className={claseInput}
        />
        <span className="text-[11px] text-muted-foreground">
          {turno.horario_propio ? "a medida" : "de la franja"}
        </span>
      </div>
      {!horasValidas && (inicio || fin) && (
        <p className="text-xs text-destructive">Usa HH:MM (24h), p. ej. 08:00.</p>
      )}
      {pendienteOverride && (
        <p className="text-xs text-amber-700 dark:text-amber-400">{pendienteOverride}</p>
      )}
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={onToggleQuitar}
          className={cn(
            "text-xs hover:underline",
            marcadoQuitar ? "text-muted-foreground" : "text-destructive",
          )}
        >
          {marcadoQuitar ? "No quitar" : "Quitar turno"}
        </button>
        {pendienteOverride ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={guardar.isPending}
            onClick={() => guardar.mutate(true)}
          >
            {guardar.isPending && <Spinner className="mr-1.5 h-3.5 w-3.5" />}
            Forzar
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            disabled={!horasValidas || sinCambios || guardar.isPending}
            onClick={() => guardar.mutate(false)}
          >
            {guardar.isPending && <Spinner className="mr-1.5 h-3.5 w-3.5" />}
            Guardar hora
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * Panel «Asignar turnos» de Gestión = Mes único (variante SELECCIÓN-EN-MES).
 *
 * Los DÍAS los marca el usuario en el calendario mensual (`diasSel`, puede cruzar semanas). Aquí
 * elige PERSONAS y HORARIO, y AFINA por persona en una matriz que pinta la REALIDAD: una celda
 * vacía está encendida por defecto y se CREA al asignar; una celda con turno real se abre en un
 * editor en línea (`EditorHoraCelda`) para CAMBIARLE LA HORA ahí mismo o marcarla para QUITAR
 * (tachado gris). Al asignar, el motor `asignarMatriz` agrupa las fechas de cada persona por su
 * semana y resuelve la franja con las franjas de ESA semana; al quitar, se borran por lote los
 * turnos reales de las celdas marcadas (con deshacer).
 */
export function ReparteMes({
  diasSel,
  cms,
  franjasPorSemana,
  turnosExistentes,
  calcularHuecos,
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
  /** Dado los ids de turnos a borrar, devuelve los eventos que quedarían SIN CUBRIR (para avisar
   *  antes de confirmar). Lo resuelve Gestión con la cobertura de las semanas tocadas. */
  calcularHuecos?: (idsBorrados: string[]) => { titulo: string; fecha: string }[];
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
  // Turno real abierto en el editor de hora en línea (null = cerrado).
  const [editando, setEditando] = React.useState<TurnoRota | null>(null);

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

  // Toca una celda: con turno real → abre el editor de hora; vacía → alterna su alta.
  const toggleCelda = (id: string, fecha: string) => {
    if (existe(id, fecha)) {
      setEditando(turnosEn(id, fecha)[0]);
      return;
    }
    setExcluidas((prev) => {
      const n = new Map(prev);
      const s = new Set(n.get(id) ?? []);
      if (s.has(fecha)) s.delete(fecha);
      else s.add(fecha);
      n.set(id, s);
      return n;
    });
  };

  // Marca/desmarca la celda del turno editado para el lote de borrado del pie (la lleva el editor).
  const toggleQuitar = (id: string, fecha: string) =>
    setParaBorrar((prev) => {
      const n = new Set(prev);
      const k = clave(id, fecha);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  // Cierra el editor si su celda deja de ser válida (persona deseleccionada o día fuera de la selección).
  React.useEffect(() => {
    if (editando && (!personasSel.has(editando.miembro_id) || !diasSel.has(editando.fecha))) {
      setEditando(null);
    }
  }, [editando, personasSel, diasSel]);

  const personasElegidas = cms.filter((m) => personasSel.has(m.id));
  // Altas: celdas VACÍAS encendidas (no recreamos las que ya existen).
  const addsDePersona = (id: string) => dias.filter((f) => !existe(id, f) && celdaEncendida(id, f));
  // Bajas: celdas con turno real marcadas para quitar.
  const delsDePersona = (id: string) => dias.filter((f) => existe(id, f) && paraBorrar.has(clave(id, f)));
  const totalAdds = personasElegidas.reduce((acc, m) => acc + addsDePersona(m.id).length, 0);
  const totalDels = personasElegidas.reduce((acc, m) => acc + delsDePersona(m.id).length, 0);
  const horasValidas = esHoraValida(inicio) && esHoraValida(fin);
  // El «Horario» solo gobierna las ALTAS (qué hora y franja toma un turno NUEVO). Si no hay celdas
  // vacías entre las personas elegidas, no se puede añadir nada: lo ocultamos para no confundir con
  // el editor de hora de cada turno existente.
  const puedeAniadir = personasElegidas.some((m) => dias.some((f) => !existe(m.id, f)));

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
            ? "Celda vacía añade · toca un turno para editar su hora."
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
        setEditando(null);
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
      const delIds: string[] = [];
      let protegidos = 0;
      personasElegidas.forEach((m) => {
        const n = delsDePersona(m.id).reduce((acc, f) => acc + turnosEn(m.id, f).length, 0);
        if (n) porPersona.set(m.nombre, n);
        delsDePersona(m.id).forEach((f) =>
          turnosEn(m.id, f).forEach((t) => {
            delIds.push(t.id);
            if (t.override || t.nota_relevo) protegidos += 1;
          }),
        );
      });
      const quien =
        porPersona.size === 1
          ? `de ${[...porPersona.keys()][0]}`
          : `de ${porPersona.size} personas`;
      const huecos = calcularHuecos?.(delIds) ?? [];
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
            {huecos.length > 0 && (
              <Aviso>
                Esto deja {huecos.length} evento{huecos.length === 1 ? "" : "s"} sin cubrir:{" "}
                {huecos.map((h) => `${h.titulo} (${fechaCorta(h.fecha)})`).join(" · ")}.
              </Aviso>
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
    <div className="flex shrink-0 flex-col gap-3 rounded-xl border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Asignar turnos</h2>
        <Button
          variant="ghost"
          size="icon"
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

      {/* Horario de las ALTAS: solo cuando hay celdas vacías que rellenar (si no, sobra y confunde
          con el editor de hora de cada turno). */}
      {puedeAniadir && (
        <div className="space-y-2">
          <Label className={eyebrow}>Horario de los turnos nuevos</Label>
          <div className="flex items-center gap-3">
            <Input
              value={inicio}
              onChange={(e) => setInicio(e.target.value)}
              placeholder="08:00"
              className="h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0"
              aria-label="Hora de inicio (CDMX)"
            />
            <span className="text-muted-foreground">–</span>
            <Input
              value={fin}
              onChange={(e) => setFin(e.target.value)}
              placeholder="16:00"
              className="h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0"
              aria-label="Hora de fin (CDMX)"
            />
          </div>
          {!horasValidas && (inicio || fin) && (
            <p className="text-xs text-destructive">Usa HH:MM (24h), p. ej. 08:00.</p>
          )}
          <AvisoZonaOperativa que="Los turnos" />
        </div>
      )}

      {/* Matriz: filas = personas elegidas, columnas = días marcados en el calendario. */}
      <div className="space-y-2">
        <div>
          <Label className={eyebrow}>El patrón de cada persona</Label>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Celda vacía → añade. Toca un turno para cambiarle la hora o quitarlo. Cada quien el suyo.
          </p>
        </div>
        {diasSel.size === 0 ? (
          <p className="rounded-xl border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
            Marca días en el calendario para repartir.
          </p>
        ) : personasElegidas.length === 0 ? (
          <p className="rounded-xl border px-3 py-4 text-center text-xs text-muted-foreground">
            Elige personas para ver la matriz.
          </p>
        ) : (
          <div className="rounded-xl border p-2">
            <Table className="w-auto border-separate border-spacing-[3px] tabular-nums">
              <TableHeader className="[&_tr]:border-0">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="h-auto p-0" />
                  {dias.map((f) => (
                    <TableHead
                      key={f}
                      className="h-auto px-0 text-center align-bottom font-normal leading-none"
                    >
                      <span className="block text-[10px] font-semibold uppercase text-muted-foreground/70">
                        {letraDeFecha(f)}
                      </span>
                      <span className="block text-[9px] text-muted-foreground/50">
                        {f.slice(8, 10)}
                      </span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {personasElegidas.map((m) => (
                  <TableRow key={m.id} className="border-0 hover:bg-transparent">
                    <TableCell className="max-w-[5rem] truncate p-0 pr-2 text-[11.5px] text-foreground/80">
                      {m.nombre}
                    </TableCell>
                    {dias.map((f) => {
                      const st = estadoCelda(m.id, f);
                      const t = turnosEn(m.id, f)[0];
                      const enEdicion = editando?.miembro_id === m.id && editando?.fecha === f;
                      const tip = t
                        ? `${t.franja_nombre}${t.override ? " · refuerzo matchday" : ""}${t.nota_relevo ? " · nota de relevo" : ""}`
                        : "vacío";
                      return (
                        <TableCell key={f} className="p-0">
                          <Tooltip label={tip}>
                            <button
                              type="button"
                              role="checkbox"
                              aria-checked={st === "add" || st === "existe"}
                              aria-label={`${m.nombre} ${f.slice(8, 10)}`}
                              onClick={() => toggleCelda(m.id, f)}
                              className={cn(
                                "relative h-[18px] w-[22px] rounded-[4px] border transition-colors",
                                st === "add" && "border-keni-400/40 bg-keni-50 dark:bg-keni-900/30",
                                st === "existe" && "border-keni-400 bg-keni-50 dark:bg-keni-900/30",
                                st === "del" && "border-border/60 bg-keni-50/50 dark:bg-keni-900/20",
                                st === "vacia" && "border-border/60 hover:bg-accent",
                                enEdicion && "ring-2 ring-keni-400 ring-offset-1",
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
                          </Tooltip>
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
        {editando && (
          <EditorHoraCelda
            key={editando.id}
            turno={editando}
            marcadoQuitar={paraBorrar.has(clave(editando.miembro_id, editando.fecha))}
            onCambio={onCambio}
            onToggleQuitar={() => {
              toggleQuitar(editando.miembro_id, editando.fecha);
              setEditando(null);
            }}
            onCerrar={() => setEditando(null)}
          />
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
          {aplicar.isPending && <Spinner className="mr-1.5 h-4 w-4" />}
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
