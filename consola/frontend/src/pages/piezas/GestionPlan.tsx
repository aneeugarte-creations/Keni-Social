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
import { Loader2, Plus, Save, Tags, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";
import { horaCdmxAUtc, horaUtcACdmx } from "@/lib/fecha";

import { ORDEN_REDES, iconoRed, nombreRed } from "./meta";
import { SelectorHoras } from "./SelectorHoras";

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Claves especiales del motor (no son líneas): última hora y reciclaje. */
const CLAVE_BREAKING = "breaking";
const CLAVE_EVERGREEN = "evergreen";

/** Redes preseleccionadas cuando la marca aún no ha guardado su selección. */
const REDES_PLAN_DEFECTO = ["facebook", "instagram"];

/** Parsea la CSV de ids de red del ajuste a un set de ids canónicos conocidos. */
function parsearRedes(crudo: string): Set<string> {
  const redes = new Set<string>();
  for (const trozo of (crudo || "").split(",")) {
    const id = trozo.trim().toLowerCase();
    if (id && (ORDEN_REDES as readonly string[]).includes(id)) redes.add(id);
  }
  return redes;
}

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

/** Una fila del plan: una clave (id de línea o señal) + su etiqueta legible + si lleva horario.
 *  `esLinea` distingue las LÍNEAS reales (se pueden quitar) de las señales del motor. */
interface FilaPlan {
  clave: string;
  etiqueta: string;
  conHorario: boolean;
  esLinea: boolean;
  /** Palabras clave (CSV) con que el clasificador asigna esta línea. Solo en líneas reales. */
  keywords: string;
}

export function PanelPlan({ marca }: { marca: string }) {
  const queryClient = useQueryClient();
  const clavePlan = `KENI_PLAN_DIA::${marca}`;
  const claveRedes = `KENI_PLAN_REDES::${marca}`;

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
      esLinea: true,
      keywords: l.keywords ?? "",
    }));
    return [
      { clave: CLAVE_BREAKING, etiqueta: "Última hora", conHorario: false, esLinea: false, keywords: "" },
      ...lineas,
      { clave: CLAVE_EVERGREEN, etiqueta: "Evergreen", conHorario: true, esLinea: false, keywords: "" },
    ];
  }, [lineasQuery.data]);

  const [filas, setFilas] = React.useState<Record<string, Fila>>({});
  const [redes, setRedes] = React.useState<Set<string>>(new Set());
  const [inicializado, setInicializado] = React.useState(false);
  const [nuevaLinea, setNuevaLinea] = React.useState("");

  const claveLineas = ["etiquetas", "vertical", marca] as const;
  const crearLinea = useMutation({
    mutationFn: (nombre: string) =>
      api.crearEtiqueta({ nombre: nombre.trim(), clase: "vertical", marca }),
    onSuccess: () => {
      setNuevaLinea("");
      void queryClient.invalidateQueries({ queryKey: claveLineas });
      toast.success("Línea añadida.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const quitarLinea = useMutation({
    mutationFn: (id: string) => api.actualizarEtiqueta(id, { activo: false }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: claveLineas });
      void queryClient.invalidateQueries({ queryKey: ["franjas"] });
      toast.success("Línea quitada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  // Edición de las PALABRAS CLAVE de una línea (lo que el clasificador usa). Inline, sin pop-up.
  const [editando, setEditando] = React.useState<string | null>(null);
  const [kwDraft, setKwDraft] = React.useState("");
  const editarKeywords = useMutation({
    mutationFn: ({ id, keywords }: { id: string; keywords: string }) =>
      api.actualizarEtiqueta(id, { keywords }),
    onSuccess: () => {
      setEditando(null);
      void queryClient.invalidateQueries({ queryKey: claveLineas });
      toast.success("Palabras clave guardadas.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

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
  const valorRedes = valorAjuste(claveRedes);

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
    // Redes esperadas por el plan: las guardadas, o el defecto si la marca aún no eligió.
    const redesGuardadas = parsearRedes(valorRedes);
    setRedes(redesGuardadas.size > 0 ? redesGuardadas : new Set(REDES_PLAN_DEFECTO));
    setInicializado(true);
  }, [
    inicializado, ajustes.isPending, franjasQuery.isPending, lineasQuery.isPending,
    valorPlan, valorRedes, franjasMarca, filasPlan,
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
      // 2b) Redes esperadas por el plan (CSV de ids, orden canónico): solo declara qué redes
      //     pinta el calendario como huecos; no cambia cómo se generan las piezas.
      const redesCsv = ORDEN_REDES.filter((id) => redes.has(id)).join(",");
      await api.guardarAjuste({ clave: claveRedes, valor: redesCsv });
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
        Las líneas de esta marca: cuántos contenidos al día publica cada una y a qué horas
        (CDMX). Añade o quita líneas aquí mismo.
      </p>
      {cargando ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </div>
      ) : (
        <div className="space-y-3">
          {/* Redes que el plan espera por slot: el calendario las pinta como huecos por red. */}
          <div className="space-y-2 border-b border-border/60 pb-3">
            <Label className="text-sm">Redes del plan</Label>
            <p className="text-xs text-muted-foreground">
              Las redes que el plan espera cada día; el calendario marca un hueco por cada una.
            </p>
            <div className="flex flex-wrap gap-2">
              {ORDEN_REDES.map((id) => {
                const Icono = iconoRed(id);
                const activa = redes.has(id);
                return (
                  <Button
                    key={id}
                    type="button"
                    size="sm"
                    variant={activa ? "default" : "outline"}
                    aria-pressed={activa}
                    onClick={() =>
                      setRedes((prev) => {
                        const sig = new Set(prev);
                        if (sig.has(id)) sig.delete(id);
                        else sig.add(id);
                        return sig;
                      })
                    }
                  >
                    <Icono className="h-4 w-4" />
                    {nombreRed(id)}
                  </Button>
                );
              })}
            </div>
          </div>
          {filasPlan.map((fila) => (
            <React.Fragment key={fila.clave}>
            <div className="grid grid-cols-[12rem_5rem_minmax(0,1fr)_auto] items-center gap-3">
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
              {fila.esLinea ? (
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-foreground"
                    aria-label={`Palabras clave de ${fila.etiqueta}`}
                    onClick={() => {
                      setEditando(editando === fila.clave ? null : fila.clave);
                      setKwDraft(fila.keywords);
                    }}
                  >
                    <Tags className="h-4 w-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    aria-label={`Quitar ${fila.etiqueta}`}
                    disabled={quitarLinea.isPending}
                    onClick={() => quitarLinea.mutate(fila.clave)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <span />
              )}
            </div>
            {fila.esLinea && editando === fila.clave && (
              <div className="ml-[12rem] space-y-2 rounded-md border border-dashed border-border p-3">
                <Label className="text-xs">
                  Palabras clave — el clasificador asigna a esta línea las piezas que las contengan.
                </Label>
                <Textarea
                  value={kwDraft}
                  onChange={(e) => setKwDraft(e.target.value)}
                  rows={2}
                  placeholder="liga, gol, partido, jornada"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" size="sm" onClick={() => setEditando(null)}>
                    Cancelar
                  </Button>
                  <Button
                    size="sm"
                    disabled={editarKeywords.isPending}
                    onClick={() => editarKeywords.mutate({ id: fila.clave, keywords: kwDraft })}
                  >
                    {editarKeywords.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    Guardar
                  </Button>
                </div>
              </div>
            )}
            </React.Fragment>
          ))}

          {/* Añadir una LÍNEA nueva a esta marca (la crea de verdad; aparece como fila). */}
          <div className="grid grid-cols-[12rem_minmax(0,1fr)_auto] items-center gap-3 pt-1">
            <Label className="text-sm text-muted-foreground">Añadir línea</Label>
            <Input
              value={nuevaLinea}
              placeholder="Nombre de la línea"
              maxLength={60}
              onChange={(e) => setNuevaLinea(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && nuevaLinea.trim()) {
                  e.preventDefault();
                  crearLinea.mutate(nuevaLinea);
                }
              }}
              aria-label="Nombre de la nueva línea"
            />
            <Button
              type="button"
              variant="outline"
              disabled={!nuevaLinea.trim() || crearLinea.isPending}
              onClick={() => crearLinea.mutate(nuevaLinea)}
            >
              {crearLinea.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Añadir
            </Button>
          </div>

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
