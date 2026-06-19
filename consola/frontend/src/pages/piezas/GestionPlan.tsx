/**
 * «Plan y horarios» de la página Programación: EL sitio donde se configura, por marca, cuántos
 * contenidos salen al día de cada LÍNEA y a qué horas (CDMX). Es una SECCIÓN INLINE del panel
 * de ajustes (capa base, colapsable), no un diálogo.
 *
 * Las LÍNEAS son las REALES de la marca (etiquetas `vertical`, las mismas de métricas y feeds):
 * se leen de `/api/etiquetas?clase=vertical`. Más dos filas especiales del motor: «Última hora»
 * (breaking, sin horario: sale al instante) y «Evergreen» (cajón de reciclaje). Por debajo toca:
 *   - la CANTIDAD por línea escribe `KENI_PLAN_DIA::<marca>` ("clave:n,…", clave = id de línea o
 *     'breaking'/'evergreen'), el ajuste que lee la admisión del pipeline;
 *   - los HORARIOS sincronizan las franjas editoriales de la marca (categoría = la misma clave;
 *     7 días a la misma hora; el backend guarda UTC, aquí se edita en hora CDMX).
 * Solo admin (la API de ajustes rechaza al resto).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";
import { horaCdmxAUtc, horaUtcACdmx } from "@/lib/fecha";

import { SelectorHoras } from "./SelectorHoras";

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Claves especiales del motor (no son líneas): última hora y reciclaje. */
const CLAVE_BREAKING = "breaking";
const CLAVE_EVERGREEN = "evergreen";

/** Parsea el CSV de horas del input ("8:45, 10:45") a "HH:MM" únicos y ordenados (CDMX). */
function parsearHoras(texto: string): string[] | null {
  const horas = new Set<string>();
  for (const trozo of texto.split(",")) {
    const t = trozo.trim();
    if (!t) continue;
    const norm = t.length === 4 ? `0${t}` : t; // "8:45" -> "08:45"
    if (!RE_HORA.test(norm)) return null;
    horas.add(norm);
  }
  return [...horas].sort();
}

/** Parsea el plan "clave:n,…" del ajuste a mapa (la clave es id de línea o señal del motor). */
function parsearPlan(crudo: string): Record<string, number> {
  const plan: Record<string, number> = {};
  for (const trozo of (crudo || "").split(",")) {
    const [clave, n] = trozo.split(":");
    const cupo = Number((n ?? "").trim());
    if (clave?.trim() && Number.isInteger(cupo) && cupo > 0) plan[clave.trim()] = cupo;
  }
  return plan;
}

interface Fila {
  cupo: string;
  horas: string;
}

/** Una fila del plan: una clave (id de línea o señal) + su etiqueta legible + si lleva horario. */
interface FilaPlan {
  clave: string;
  etiqueta: string;
  conHorario: boolean;
}

export function PanelPlan({ marca }: { marca: string }) {
  const queryClient = useQueryClient();
  const clavePlan = `KENI_PLAN_DIA::${marca}`;

  const ajustes = useQuery({
    queryKey: ["ajustes"],
    queryFn: ({ signal }) => api.ajustes(signal),
  });
  const franjasQuery = useQuery({
    queryKey: ["franjas"],
    queryFn: ({ signal }) => api.franjas(signal),
  });
  const lineasQuery = useQuery({
    queryKey: ["etiquetas", "vertical", marca],
    queryFn: ({ signal }) =>
      api.etiquetas({ marca, clase: "vertical", activas: true }, signal),
  });

  // Filas del plan: Última hora (breaking) + las líneas reales de la marca + Evergreen.
  const filasPlan: FilaPlan[] = React.useMemo(() => {
    const lineas = (lineasQuery.data?.etiquetas ?? []).map((l) => ({
      clave: l.id,
      etiqueta: l.grupo ? `${l.grupo} · ${l.nombre}` : l.nombre,
      conHorario: true,
    }));
    return [
      { clave: CLAVE_BREAKING, etiqueta: "Última hora", conHorario: false },
      ...lineas,
      { clave: CLAVE_EVERGREEN, etiqueta: "Evergreen", conHorario: true },
    ];
  }, [lineasQuery.data]);

  const [filas, setFilas] = React.useState<Record<string, Fila>>({});
  const [inicializado, setInicializado] = React.useState(false);

  const valorAjuste = React.useCallback(
    (clave: string) => {
      for (const g of ajustes.data?.grupos ?? []) {
        const a = g.ajustes.find((x) => x.clave === clave);
        if (a) return String(a.valor ?? "");
      }
      return "";
    },
    [ajustes.data],
  );
  const valorPlan = valorAjuste(clavePlan);

  const franjasMarca = React.useMemo(
    () =>
      (franjasQuery.data?.franjas ?? []).filter(
        (f) => f.marca === marca && (f.categoria ?? "") !== "",
      ),
    [franjasQuery.data, marca],
  );

  React.useEffect(() => {
    if (inicializado || ajustes.isPending || franjasQuery.isPending || lineasQuery.isPending) {
      return;
    }
    const plan = parsearPlan(valorPlan);
    const horasPorClave = new Map<string, Set<string>>();
    for (const f of franjasMarca) {
      const set = horasPorClave.get(f.categoria) ?? new Set<string>();
      set.add(horaUtcACdmx(f.hora));
      horasPorClave.set(f.categoria, set);
    }
    const inicializadas: Record<string, Fila> = {};
    for (const fila of filasPlan) {
      inicializadas[fila.clave] = {
        cupo: String(plan[fila.clave] ?? 0),
        horas: [...(horasPorClave.get(fila.clave) ?? [])].sort().join(", "),
      };
    }
    setFilas(inicializadas);
    setInicializado(true);
  }, [
    inicializado, ajustes.isPending, franjasQuery.isPending, lineasQuery.isPending,
    valorPlan, franjasMarca, filasPlan,
  ]);

  const guardar = useMutation({
    mutationFn: async () => {
      // 1) Valida horas de todas las filas con horario.
      const horasPorClave: Record<string, string[]> = {};
      for (const fila of filasPlan) {
        if (!fila.conHorario) continue;
        const horas = parsearHoras(filas[fila.clave]?.horas ?? "");
        if (horas === null) {
          throw new Error(
            `Horas inválidas en «${fila.etiqueta}»: usa HH:MM separadas por comas.`,
          );
        }
        horasPorClave[fila.clave] = horas;
      }
      // 2) Plan (cantidad por clave): escribe el ajuste que lee la admisión.
      const partes = filasPlan
        .map((fila) => [fila.clave, Number(filas[fila.clave]?.cupo)] as const)
        .filter(([, n]) => Number.isInteger(n) && n > 0)
        .map(([clave, n]) => `${clave}:${n}`);
      await api.guardarAjuste({ clave: clavePlan, valor: partes.join(",") });
      // 3) Limpia franjas de claves que ya no son filas del plan (líneas borradas).
      const vigentes = new Set(filasPlan.map((f) => f.clave));
      const huerfanas = franjasMarca.filter((f) => !vigentes.has(f.categoria));
      await Promise.all(huerfanas.map((f) => api.eliminarFranja(f.id)));
      // 4) Horarios: sincroniza las franjas de cada clave (7 días por hora, en UTC).
      for (const [clave, horasCdmx] of Object.entries(horasPorClave)) {
        const objetivo = new Set(horasCdmx.map(horaCdmxAUtc));
        const actuales = franjasMarca.filter((f) => f.categoria === clave);
        const sobran = actuales.filter((f) => !objetivo.has(f.hora));
        await Promise.all(sobran.map((f) => api.eliminarFranja(f.id)));
        const existentes = new Set(actuales.map((f) => `${f.dia_semana}|${f.hora}`));
        const altas: Promise<unknown>[] = [];
        for (const hora of objetivo) {
          for (let dia = 0; dia < 7; dia += 1) {
            if (!existentes.has(`${dia}|${hora}`)) {
              altas.push(api.crearFranja({ dia_semana: dia, hora, marca, categoria: clave }));
            }
          }
        }
        await Promise.all(altas);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["franjas"] });
      void queryClient.invalidateQueries({ queryKey: ["ajustes"] });
      void queryClient.invalidateQueries({ queryKey: ["produccion"] });
      toast.success("Plan y horarios guardados.");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : mensajeError(e)),
  });

  const total = filasPlan.reduce((acc, f) => acc + (Number(filas[f.clave]?.cupo) || 0), 0);
  const cargando =
    ajustes.isPending || franjasQuery.isPending || lineasQuery.isPending;

  return (
    <div>
      <p className="mb-3 text-xs text-muted-foreground">
        Cuántos contenidos al día publica cada línea de esta marca y a qué horas (CDMX). Las
        líneas se gestionan en su pestaña; aquí defines volumen y horario.
      </p>
      {cargando ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </div>
      ) : (
        <div className="space-y-3">
          {filasPlan.map((fila) => (
            <div
              key={fila.clave}
              className="grid grid-cols-[12rem_5rem_minmax(0,1fr)] items-center gap-3"
            >
              <Label className="text-sm">{fila.etiqueta}</Label>
              <Input
                type="number"
                min={0}
                value={filas[fila.clave]?.cupo ?? "0"}
                onChange={(e) =>
                  setFilas((prev) => ({
                    ...prev,
                    [fila.clave]: { ...(prev[fila.clave] ?? { cupo: "0", horas: "" }), cupo: e.target.value },
                  }))
                }
                aria-label={`Publicaciones al día de ${fila.etiqueta}`}
                className="tabular-nums"
              />
              {fila.conHorario ? (
                <SelectorHoras
                  value={filas[fila.clave]?.horas ?? ""}
                  onChange={(csv) =>
                    setFilas((prev) => ({
                      ...prev,
                      [fila.clave]: { ...(prev[fila.clave] ?? { cupo: "0", horas: "" }), horas: csv },
                    }))
                  }
                  ariaLabel={`Horarios de ${fila.etiqueta} (hora CDMX)`}
                />
              ) : (
                <span className="text-xs text-muted-foreground">
                  Sin horario: sale al instante.
                </span>
              )}
            </div>
          ))}

          <div className="flex items-center justify-between border-t border-border/60 pt-3">
            <span className="text-sm text-muted-foreground">
              Total: <span className="font-medium tabular-nums">{total}</span> contenidos/día
            </span>
            <Button onClick={() => guardar.mutate()} disabled={guardar.isPending}>
              {guardar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Guardar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
