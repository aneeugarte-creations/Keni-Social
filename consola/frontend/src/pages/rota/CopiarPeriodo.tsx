import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { ArrowDown, CalendarDays, ChevronDown, ChevronRight, Copy } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";
import {
  diasDeSemana,
  formatearRango,
  mesSiguiente,
  nombreMes,
  semanasDelMes,
} from "@/lib/rota-calendario";

interface CopiarPeriodoProps {
  /** GRID POR MARCA: rejilla que se copia. "" = «Todas» (no se puede copiar). */
  marca: string;
  /** Mes en vista del calendario ("YYYY-MM"); ancla los selectores. */
  mesActual: string;
  /** Refrescar la rejilla tras copiar. */
  onCopiado: () => void;
}

const turnosOcupados = (turnos: { miembro_id: string }[] | undefined) =>
  (turnos ?? []).filter((t) => t.miembro_id).length;

/**
 * Bloque «Copiar semana» / «Copiar mes» del panel de reparto (MÁS OPCIONES). Elige un periodo
 * origen y otro destino y replica los turnos reusando la API existente (`copiarSemana`/`copiarMes`,
 * que conserva el horario a medida y deja todo como propuesta). Acordeón: un bloque abierto a la vez.
 * Si el destino ya tiene turnos, avisa y ofrece reemplazar (si no, se añaden a los actuales).
 */
export function CopiarPeriodo({ marca, mesActual, onCopiado }: CopiarPeriodoProps) {
  const mesBase = mesActual || hoyCDMX().slice(0, 7);
  const hoy = hoyCDMX();
  const [abierto, setAbierto] = React.useState<"semana" | "mes" | null>(null);

  // Opciones de semana: las semanas del mes en vista y de los meses vecinos (para copiar a través de
  // un cambio de mes), por lunes único y ordenadas.
  const semanasOpts = React.useMemo(() => {
    const vistos = new Set<string>();
    const arr: { lunes: string; fin: string; label: string }[] = [];
    for (const m of [mesSiguiente(mesBase, -1), mesBase, mesSiguiente(mesBase, 1)]) {
      for (const semana of semanasDelMes(m)) {
        const lunes = semana[0];
        if (vistos.has(lunes)) continue;
        vistos.add(lunes);
        arr.push({ lunes, fin: semana[6], label: formatearRango(semana[0], semana[6]) });
      }
    }
    arr.sort((a, b) => a.lunes.localeCompare(b.lunes));
    return arr;
  }, [mesBase]);

  const mesesOpts = React.useMemo(
    () =>
      [-2, -1, 0, 1, 2].map((i) => {
        const mes = mesSiguiente(mesBase, i);
        return { mes, label: nombreMes(mes) };
      }),
    [mesBase],
  );

  // Índice de la semana «de hoy» dentro de las opciones (o la primera). Ancla los defaults.
  const idxBaseSemana = React.useMemo(() => {
    if (!semanasOpts.length) return 0;
    return Math.max(
      0,
      semanasOpts.findIndex((s) => s.lunes <= hoy && hoy <= s.fin),
    );
  }, [semanasOpts, hoy]);

  // Defaults válidos desde el primer render (mesBase nunca es ""): semana = la de hoy → la
  // siguiente; mes = el de vista → el siguiente.
  const [deSemana, setDeSemana] = React.useState(
    () => semanasOpts[idxBaseSemana]?.lunes ?? "",
  );
  const [aSemana, setASemana] = React.useState(
    () => semanasOpts[Math.min(idxBaseSemana + 1, semanasOpts.length - 1)]?.lunes ?? "",
  );
  const [deMes, setDeMes] = React.useState(mesBase);
  const [aMes, setAMes] = React.useState(() => mesSiguiente(mesBase, 1));
  const [repSemana, setRepSemana] = React.useState(false);
  const [repMes, setRepMes] = React.useState(false);

  // Reajusta los defaults al cambiar el mes en vista (p. ej. cuando el calendario lo notifica).
  React.useEffect(() => {
    if (!semanasOpts.length) return;
    setDeSemana(semanasOpts[idxBaseSemana].lunes);
    setASemana(semanasOpts[Math.min(idxBaseSemana + 1, semanasOpts.length - 1)].lunes);
    setDeMes(mesBase);
    setAMes(mesSiguiente(mesBase, 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mesBase]);

  // Turnos del destino (para avisar si ya hay roster). Comparten queryKey con la rejilla.
  const destSemanaQ = useQuery({
    queryKey: ["rota", "turnos", aSemana, marca] as const,
    queryFn: ({ signal }) => api.listarTurnos({ lunes: aSemana, marca: marca || undefined }, signal),
    enabled: abierto === "semana" && !!aSemana && !!marca,
  });
  const nDestSemana = turnosOcupados(destSemanaQ.data?.turnos);

  const semanasDestMes = React.useMemo(
    () => (aMes ? semanasDelMes(aMes).map((w) => w[0]) : []),
    [aMes],
  );
  const destMesQs = useQueries({
    queries: semanasDestMes.map((l) => ({
      queryKey: ["rota", "turnos", l, marca] as const,
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        api.listarTurnos({ lunes: l, marca: marca || undefined }, signal),
      enabled: abierto === "mes" && !!aMes && !!marca,
    })),
  });
  const nDestMes = destMesQs.reduce((acc, q) => acc + turnosOcupados(q.data?.turnos), 0);

  const copiaSemana = useMutation({
    mutationFn: () =>
      api.copiarSemana({ de_lunes: deSemana, a_lunes: aSemana, reemplazar: repSemana, marca }),
    onSuccess: (res) => {
      toast.success(`Copiados ${res.copiados ?? 0} turnos a la semana del ${labelSemana(aSemana)}.`);
      onCopiado();
      setAbierto(null);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const copiaMes = useMutation({
    mutationFn: () => api.copiarMes({ a_mes: aMes, de_mes: deMes, reemplazar: repMes, marca }),
    onSuccess: (res) => {
      toast.success(`Copiados ${res.copiados ?? 0} turnos a ${nombreMes(aMes)}.`);
      onCopiado();
      setAbierto(null);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const labelSemana = (lunes: string) => {
    if (!lunes) return "";
    const dias = diasDeSemana(lunes);
    return (
      semanasOpts.find((s) => s.lunes === lunes)?.label ||
      formatearRango(dias[0] ?? "", dias[6] ?? "")
    );
  };

  const sinMarca = !marca;
  const mismaSemana = deSemana === aSemana;
  const mismoMes = deMes === aMes;

  return (
    <div className="space-y-0.5">
      <FilaAcordeon
        icono={<Copy className="h-[15px] w-[15px]" />}
        titulo="Copiar semana"
        subtitulo="Replica una semana en otra · solo turnos"
        abierto={abierto === "semana"}
        onClick={() => setAbierto((v) => (v === "semana" ? null : "semana"))}
      />
      {abierto === "semana" && (
        <div className="px-1.5 pb-2 pt-1">
          <SelectorDeA
            valorDe={deSemana}
            valorA={aSemana}
            onDe={setDeSemana}
            onA={setASemana}
            opciones={semanasOpts.map((s) => ({ valor: s.lunes, label: s.label }))}
          />
          <Resumen
            sinMarca={sinMarca}
            mismo={mismaSemana}
            avisoMismo="Elige dos semanas distintas."
            nDestino={nDestSemana}
            reemplazar={repSemana}
            onReemplazar={setRepSemana}
            unidad="semana"
            textoOk={`Copiará la semana del ${labelSemana(deSemana)} en la del ${labelSemana(aSemana)}. Entra como propuesta para revisar.`}
          />
          <Acciones
            onCancelar={() => setAbierto(null)}
            onCopiar={() => copiaSemana.mutate()}
            cargando={copiaSemana.isPending}
            deshabilitado={sinMarca || mismaSemana}
          />
        </div>
      )}

      <FilaAcordeon
        icono={<CalendarDays className="h-[15px] w-[15px]" />}
        titulo="Copiar mes"
        subtitulo="Replica un mes entero en otro · solo turnos"
        abierto={abierto === "mes"}
        onClick={() => setAbierto((v) => (v === "mes" ? null : "mes"))}
      />
      {abierto === "mes" && (
        <div className="px-1.5 pb-2 pt-1">
          <SelectorDeA
            valorDe={deMes}
            valorA={aMes}
            onDe={setDeMes}
            onA={setAMes}
            opciones={mesesOpts.map((m) => ({ valor: m.mes, label: m.label }))}
          />
          <Resumen
            sinMarca={sinMarca}
            mismo={mismoMes}
            avisoMismo="Elige dos meses distintos."
            nDestino={nDestMes}
            reemplazar={repMes}
            onReemplazar={setRepMes}
            unidad="mes"
            textoOk={`Copiará ${nombreMes(deMes)} en ${nombreMes(aMes)}, casando cada semana por día. Entra como propuesta para revisar.`}
          />
          <Acciones
            onCancelar={() => setAbierto(null)}
            onCopiar={() => copiaMes.mutate()}
            cargando={copiaMes.isPending}
            deshabilitado={sinMarca || mismoMes}
          />
        </div>
      )}
    </div>
  );
}

function FilaAcordeon({
  icono,
  titulo,
  subtitulo,
  abierto,
  onClick,
}: {
  icono: React.ReactNode;
  titulo: string;
  subtitulo: string;
  abierto: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={abierto}
      className="flex w-full items-center gap-3 rounded-lg px-1.5 py-2 text-left transition-colors hover:bg-accent"
    >
      <span className="flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        {icono}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13.5px] font-medium text-foreground">{titulo}</span>
        <span className="block text-[11.5px] text-muted-foreground">{subtitulo}</span>
      </span>
      {abierto ? (
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground/60" />
      ) : (
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/60" />
      )}
    </button>
  );
}

function SelectorDeA({
  valorDe,
  valorA,
  onDe,
  onA,
  opciones,
}: {
  valorDe: string;
  valorA: string;
  onDe: (v: string) => void;
  onA: (v: string) => void;
  opciones: { valor: string; label: string }[];
}) {
  return (
    <div className="space-y-1">
      <FilaSelect etiqueta="De" valor={valorDe} onCambio={onDe} opciones={opciones} />
      <div className="flex justify-center text-muted-foreground/50">
        <ArrowDown className="h-4 w-4" />
      </div>
      <FilaSelect etiqueta="A" valor={valorA} onCambio={onA} opciones={opciones} />
    </div>
  );
}

function FilaSelect({
  etiqueta,
  valor,
  onCambio,
  opciones,
}: {
  etiqueta: string;
  valor: string;
  onCambio: (v: string) => void;
  opciones: { valor: string; label: string }[];
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-6 shrink-0 text-xs font-semibold text-muted-foreground">{etiqueta}</span>
      <Select value={valor} onValueChange={onCambio}>
        <SelectTrigger className="h-9 flex-1" aria-label={`${etiqueta} (periodo origen/destino)`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {opciones.map((o) => (
            <SelectItem key={o.valor} value={o.valor}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function Resumen({
  sinMarca,
  mismo,
  avisoMismo,
  nDestino,
  reemplazar,
  onReemplazar,
  unidad,
  textoOk,
}: {
  sinMarca: boolean;
  mismo: boolean;
  avisoMismo: string;
  nDestino: number;
  reemplazar: boolean;
  onReemplazar: (v: boolean) => void;
  unidad: string;
  textoOk: string;
}) {
  if (sinMarca) {
    return (
      <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
        Elige una marca concreta para copiar (ahora estás en «Todas»).
      </p>
    );
  }
  if (mismo) {
    return <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{avisoMismo}</p>;
  }
  if (nDestino > 0) {
    return (
      <div className="mt-3 space-y-2">
        <p className="text-xs leading-relaxed text-amber-600 dark:text-amber-500">
          Ya hay {nDestino} turnos en ese {unidad}.{" "}
          {reemplazar
            ? "Se borrarán y se sustituirán por los del origen."
            : "Sin reemplazar, los del origen se añaden a los actuales."}
        </p>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-foreground">
          <input
            type="checkbox"
            checked={reemplazar}
            onChange={(e) => onReemplazar(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          Reemplazar lo que ya hay
        </label>
      </div>
    );
  }
  return <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{textoOk}</p>;
}

function Acciones({
  onCancelar,
  onCopiar,
  cargando,
  deshabilitado,
}: {
  onCancelar: () => void;
  onCopiar: () => void;
  cargando: boolean;
  deshabilitado: boolean;
}) {
  return (
    <div className="mt-3 flex justify-end gap-2">
      <Button variant="ghost" size="sm" onClick={onCancelar}>
        Cancelar
      </Button>
      <Button variant="secondary" size="sm" disabled={deshabilitado || cargando} onClick={onCopiar}>
        {cargando && <Spinner className="mr-1.5 h-4 w-4" />}
        Copiar
      </Button>
    </div>
  );
}
