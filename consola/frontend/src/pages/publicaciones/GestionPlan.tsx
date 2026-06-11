/**
 * Diálogo «Plan y horarios» de la página Programación: EL sitio donde se configura, por
 * marca, cuántos contenidos salen al día de cada LÍNEA y a qué horas (CDMX).
 *
 * Por debajo toca dos cosas que ya existen:
 *   - la CANTIDAD escribe el ajuste `KENI_PLAN_DIA::<marca>` ("linea:n,…", el que lee la
 *     admisión del pipeline) vía la API admin de ajustes;
 *   - los HORARIOS sincronizan las franjas editoriales CON CATEGORÍA de la marca (7 días a
 *     la misma hora; el backend guarda UTC, aquí se edita en hora CDMX).
 * «Breaking» no lleva horario: sale al instante cuando ocurre. Solo admin (la API de
 * ajustes rechaza al resto).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";
import { horaCdmxAUtc, horaUtcACdmx } from "@/lib/fecha";

import { ETIQUETA_LINEA } from "./PanelLineasPlan";

/** Líneas que el editor ofrece siempre (más las que ya traiga el plan de la marca). */
const LINEAS_BASE = ["mx", "internacional", "breaking", "entretenimiento", "evergreen"];

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

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

/** Parsea el plan "linea:n,…" del ajuste a mapa. */
function parsearPlan(crudo: string): Record<string, number> {
  const plan: Record<string, number> = {};
  for (const trozo of (crudo || "").split(",")) {
    const [cat, n] = trozo.split(":");
    const cupo = Number((n ?? "").trim());
    if (cat?.trim() && Number.isInteger(cupo) && cupo > 0) plan[cat.trim().toLowerCase()] = cupo;
  }
  return plan;
}

interface FilaLinea {
  cupo: string;
  horas: string;
}

export function GestionPlan({
  abierto,
  onCerrar,
  marca,
  nombreMarca,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marca: string;
  nombreMarca: string;
}) {
  const queryClient = useQueryClient();
  const clavePlan = `KENI_PLAN_DIA::${marca}`;

  const ajustes = useQuery({
    queryKey: ["ajustes"],
    queryFn: ({ signal }) => api.ajustes(signal),
    enabled: abierto,
  });
  const franjasQuery = useQuery({
    queryKey: ["franjas"],
    queryFn: ({ signal }) => api.franjas(signal),
    enabled: abierto,
  });

  // Estado del formulario, sembrado al abrir desde el plan + las franjas actuales.
  const [filas, setFilas] = React.useState<Record<string, FilaLinea>>({});
  const [sembrado, setSembrado] = React.useState(false);

  const valorPlan = React.useMemo(() => {
    for (const g of ajustes.data?.grupos ?? []) {
      const a = g.ajustes.find((x) => x.clave === clavePlan);
      if (a) return String(a.valor ?? "");
    }
    return "";
  }, [ajustes.data, clavePlan]);

  const franjasMarca = React.useMemo(
    () =>
      (franjasQuery.data?.franjas ?? []).filter(
        (f) => f.marca === marca && (f.categoria ?? "") !== "",
      ),
    [franjasQuery.data, marca],
  );

  React.useEffect(() => {
    if (!abierto) {
      setSembrado(false);
      return;
    }
    if (sembrado || ajustes.isPending || franjasQuery.isPending) return;
    const plan = parsearPlan(valorPlan);
    const horasPorLinea = new Map<string, Set<string>>();
    for (const f of franjasMarca) {
      const set = horasPorLinea.get(f.categoria) ?? new Set<string>();
      set.add(horaUtcACdmx(f.hora));
      horasPorLinea.set(f.categoria, set);
    }
    const lineas = new Set([...LINEAS_BASE, ...Object.keys(plan), ...horasPorLinea.keys()]);
    const sembradas: Record<string, FilaLinea> = {};
    for (const linea of lineas) {
      sembradas[linea] = {
        cupo: String(plan[linea] ?? 0),
        horas: [...(horasPorLinea.get(linea) ?? [])].sort().join(", "),
      };
    }
    setFilas(sembradas);
    setSembrado(true);
  }, [abierto, sembrado, ajustes.isPending, franjasQuery.isPending, valorPlan, franjasMarca]);

  const guardar = useMutation({
    mutationFn: async () => {
      // 1) Valida horas de todas las líneas (antes de tocar nada).
      const horasPorLinea: Record<string, string[]> = {};
      for (const [linea, fila] of Object.entries(filas)) {
        if (linea === "breaking") continue; // sin horario: sale al instante
        const horas = parsearHoras(fila.horas);
        if (horas === null) {
          throw new Error(
            `Horas inválidas en «${ETIQUETA_LINEA[linea] ?? linea}»: usa HH:MM separadas por comas.`,
          );
        }
        horasPorLinea[linea] = horas;
      }
      // 2) Plan (cantidad por línea): escribe el ajuste que lee la admisión.
      const partes = Object.entries(filas)
        .map(([linea, fila]) => [linea, Number(fila.cupo)] as const)
        .filter(([, n]) => Number.isInteger(n) && n > 0)
        .map(([linea, n]) => `${linea}:${n}`);
      await api.guardarAjuste({ clave: clavePlan, valor: partes.join(",") });
      // 3) Horarios: sincroniza las franjas de cada línea (7 días por hora, en UTC).
      for (const [linea, horasCdmx] of Object.entries(horasPorLinea)) {
        const objetivo = new Set(horasCdmx.map(horaCdmxAUtc));
        const actuales = franjasMarca.filter((f) => f.categoria === linea);
        const sobran = actuales.filter((f) => !objetivo.has(f.hora));
        await Promise.all(sobran.map((f) => api.eliminarFranja(f.id)));
        const existentes = new Set(actuales.map((f) => `${f.dia_semana}|${f.hora}`));
        const altas: Promise<unknown>[] = [];
        for (const hora of objetivo) {
          for (let dia = 0; dia < 7; dia += 1) {
            if (!existentes.has(`${dia}|${hora}`)) {
              altas.push(api.crearFranja({ dia_semana: dia, hora, marca, categoria: linea }));
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
      onCerrar();
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : mensajeError(e)),
  });

  const lineas = Object.keys(filas).sort(
    (a, b) => LINEAS_BASE.indexOf(a) - LINEAS_BASE.indexOf(b),
  );
  const total = lineas.reduce((acc, l) => acc + (Number(filas[l]?.cupo) || 0), 0);

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Plan y horarios · {nombreMarca}</DialogTitle>
          <DialogDescription>
            Cuántos contenidos salen al día de cada línea y a qué horas (hora de Ciudad de
            México). La cantidad gobierna la producción automática; los horarios, la
            programación. «Breaking» no lleva horario: sale al instante.
          </DialogDescription>
        </DialogHeader>
        {ajustes.isPending || franjasQuery.isPending ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
          </div>
        ) : (
          <div className="space-y-3">
            {lineas.map((linea) => (
              <div
                key={linea}
                className="grid grid-cols-[8rem_5rem_minmax(0,1fr)] items-center gap-3"
              >
                <Label className="text-sm">
                  {ETIQUETA_LINEA[linea] ?? linea.charAt(0).toUpperCase() + linea.slice(1)}
                </Label>
                <Input
                  type="number"
                  min={0}
                  value={filas[linea].cupo}
                  onChange={(e) =>
                    setFilas((prev) => ({
                      ...prev,
                      [linea]: { ...prev[linea], cupo: e.target.value },
                    }))
                  }
                  aria-label={`Contenidos al día de ${linea}`}
                  className="tabular-nums"
                />
                {linea === "breaking" ? (
                  <span className="text-xs text-muted-foreground">
                    Sin horario: se programa al instante al ocurrir.
                  </span>
                ) : (
                  <Input
                    type="text"
                    value={filas[linea].horas}
                    placeholder="08:45, 10:45, 12:45…"
                    onChange={(e) =>
                      setFilas((prev) => ({
                        ...prev,
                        [linea]: { ...prev[linea], horas: e.target.value },
                      }))
                    }
                    aria-label={`Horarios de ${linea} (hora CDMX)`}
                    className="font-mono text-xs"
                  />
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
      </DialogContent>
    </Dialog>
  );
}
