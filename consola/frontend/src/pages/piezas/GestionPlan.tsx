/**
 * Pestaña «Horarios» de Plan (hub Programa): EL sitio donde se configura, por marca, cuántos
 * contenidos salen al día de cada LÍNEA y a qué horas (CDMX), más las redes del plan y el
 * alta/baja de líneas. El hashtag y los keywords de cada línea viven en la pestaña «Keywords».
 *
 * Las LÍNEAS son las REALES de la marca (etiquetas `categoria`, las mismas de métricas y feeds):
 * se leen de `/api/etiquetas?clase=categoria`. Más dos filas especiales del motor: «Última hora»
 * (breaking, sin horario: sale al instante) y «Evergreen» (cajón de reciclaje). Por debajo toca:
 *   - la CANTIDAD por línea escribe `KENI_PLAN_DIA::<marca>` ("clave:n,…", clave = id de línea o
 *     'breaking'/'evergreen'), el ajuste que lee la admisión del pipeline;
 *   - los HORARIOS sincronizan las franjas editoriales de la marca (categoría = la misma clave;
 *     7 días a la misma hora; el backend guarda UTC, aquí se edita en hora CDMX).
 * No hay botón «Guardar»: cada cambio (hora, «al día», red) se guarda solo. Las escrituras se
 * agrupan con un debounce y se serializan; cada guardado relee las franjas para no duplicarlas.
 * Solo admin (la API de ajustes rechaza al resto).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AvisoZonaOperativa } from "@/components/comunes/AvisoZonaOperativa";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import { horaCdmxAUtc, horaUtcACdmx } from "@/lib/fecha";
import { cn } from "@/lib/utils";

import { ORDEN_REDES, iconoRed, nombreRed } from "./meta";
import { SelectorHoras } from "./SelectorHoras";

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Claves especiales del motor (no son líneas): última hora y reciclaje. */
const CLAVE_BREAKING = "breaking";
const CLAVE_EVERGREEN = "evergreen";

/** Espera (ms) tras el último cambio antes de guardar: agrupa ráfagas en una sola escritura. */
const ESPERA_GUARDADO = 700;

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
}

type EstadoGuardado = "reposo" | "guardando" | "guardado";

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
    queryKey: ["etiquetas", "categoria", marca],
    queryFn: ({ signal }) =>
      api.etiquetas({ marca, clase: "categoria", activas: true }, signal),
  });

  // Filas del plan: Última hora (breaking) + las líneas reales de la marca + Evergreen.
  const filasPlan: FilaPlan[] = React.useMemo(() => {
    const lineas = (lineasQuery.data?.etiquetas ?? []).map((l) => ({
      clave: l.id,
      etiqueta: l.grupo ? `${l.grupo} · ${l.nombre}` : l.nombre,
      conHorario: true,
      esLinea: true,
    }));
    return [
      { clave: CLAVE_BREAKING, etiqueta: "Última hora", conHorario: false, esLinea: false },
      ...lineas,
      { clave: CLAVE_EVERGREEN, etiqueta: "Evergreen", conHorario: true, esLinea: false },
    ];
  }, [lineasQuery.data]);

  const [filas, setFilas] = React.useState<Record<string, Fila>>({});
  const [redes, setRedes] = React.useState<Set<string>>(new Set());
  const [inicializado, setInicializado] = React.useState(false);
  const [nuevaLinea, setNuevaLinea] = React.useState("");
  const [estadoGuardado, setEstadoGuardado] = React.useState<EstadoGuardado>("reposo");

  const claveLineas = ["etiquetas", "categoria", marca] as const;
  const crearLinea = useMutation({
    mutationFn: (nombre: string) =>
      api.crearEtiqueta({ nombre: nombre.trim(), clase: "categoria", marca }),
    onSuccess: () => {
      setNuevaLinea("");
      void queryClient.invalidateQueries({ queryKey: claveLineas });
      toast.success("Línea añadida.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const quitarLinea = useMutation({
    // Desactiva la etiqueta Y borra sus franjas (relee fresco para no dejar huérfanas).
    mutationFn: async (id: string) => {
      await api.actualizarEtiqueta(id, { activo: false });
      const datos = await api.franjas();
      const suyas = (datos.franjas ?? []).filter((f) => f.marca === marca && f.categoria === id);
      await Promise.all(suyas.map((f) => api.eliminarFranja(f.id)));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: claveLineas });
      void queryClient.invalidateQueries({ queryKey: ["franjas"] });
      toast.success("Línea quitada.");
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

  // Estado vivo para el guardado en diferido (lee siempre lo último, sin cerrar valores viejos).
  const filasRef = React.useRef(filas);
  const redesRef = React.useRef(redes);
  const filasPlanRef = React.useRef(filasPlan);
  React.useEffect(() => {
    filasRef.current = filas;
    redesRef.current = redes;
    filasPlanRef.current = filasPlan;
  });

  const guardandoRef = React.useRef(false);
  const pendienteRef = React.useRef(false);
  const debounceRef = React.useRef<number | undefined>(undefined);
  const reposoTimerRef = React.useRef<number | undefined>(undefined);

  // Guardado serializado: una escritura a la vez; si llega un cambio durante una, se reintenta al
  // acabar. Cada vuelta relee las franjas frescas para que el diff (altas/bajas) no las duplique.
  const ejecutarGuardado = React.useCallback(async () => {
    if (guardandoRef.current) {
      pendienteRef.current = true;
      return;
    }
    guardandoRef.current = true;
    try {
      do {
        pendienteRef.current = false;
        if (reposoTimerRef.current) window.clearTimeout(reposoTimerRef.current);
        setEstadoGuardado("guardando");
        try {
          const filasAhora = filasRef.current;
          const redesAhora = redesRef.current;
          const planAhora = filasPlanRef.current;

          const horasPorClave: Record<string, string[]> = {};
          for (const fila of planAhora) {
            if (!fila.conHorario) continue;
            const horas = parsearHoras(filasAhora[fila.clave]?.horas ?? "");
            if (horas === null) {
              throw new Error(`Horas inválidas en «${fila.etiqueta}»: usa HH:MM.`);
            }
            horasPorClave[fila.clave] = horas;
          }
          const partes = planAhora
            .map((fila) => [fila.clave, Number(filasAhora[fila.clave]?.cupo)] as const)
            .filter(([, n]) => Number.isInteger(n) && n > 0)
            .map(([clave, n]) => `${clave}:${n}`);
          await api.guardarAjuste({ clave: clavePlan, valor: partes.join(",") });
          const redesCsv = ORDEN_REDES.filter((id) => redesAhora.has(id)).join(",");
          await api.guardarAjuste({ clave: claveRedes, valor: redesCsv });

          // Franjas frescas del servidor: base del diff (evita duplicar entre guardados encadenados).
          const datos = await api.franjas();
          const franjasFrescas = (datos.franjas ?? []).filter(
            (f) => f.marca === marca && (f.categoria ?? "") !== "",
          );
          const vigentes = new Set(planAhora.map((f) => f.clave));
          const huerfanas = franjasFrescas.filter((f) => !vigentes.has(f.categoria));
          await Promise.all(huerfanas.map((f) => api.eliminarFranja(f.id)));
          for (const [clave, horasCdmx] of Object.entries(horasPorClave)) {
            const objetivo = new Set(horasCdmx.map(horaCdmxAUtc));
            const actuales = franjasFrescas.filter((f) => f.categoria === clave);
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

          void queryClient.invalidateQueries({ queryKey: ["franjas"] });
          void queryClient.invalidateQueries({ queryKey: ["ajustes"] });
          void queryClient.invalidateQueries({ queryKey: ["produccion"] });
          setEstadoGuardado("guardado");
          reposoTimerRef.current = window.setTimeout(() => setEstadoGuardado("reposo"), 1500);
        } catch (e) {
          toast.error(e instanceof Error ? e.message : mensajeError(e));
          setEstadoGuardado("reposo");
        }
      } while (pendienteRef.current);
    } finally {
      guardandoRef.current = false;
    }
  }, [marca, clavePlan, claveRedes, queryClient]);

  const programarGuardado = React.useCallback(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      void ejecutarGuardado();
    }, ESPERA_GUARDADO);
  }, [ejecutarGuardado]);

  React.useEffect(
    () => () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      if (reposoTimerRef.current) window.clearTimeout(reposoTimerRef.current);
    },
    [],
  );

  const total = filasPlan.reduce((acc, f) => acc + (Number(filas[f.clave]?.cupo) || 0), 0);
  const cargando =
    ajustes.isPending || franjasQuery.isPending || lineasQuery.isPending;

  return (
    <div>
      <p className="mb-5 text-xs text-muted-foreground">
        Cuántos contenidos al día publica cada línea y a qué horas (CDMX). Añade o quita líneas
        aquí mismo; los cambios se guardan solos. El hashtag de cada línea y sus palabras clave del
        clasificador se editan en la pestaña «Keywords».
      </p>
      {/* Solo aparece si la zona de visualización del usuario difiere de la operativa (CDMX). */}
      <AvisoZonaOperativa que="Las horas del plan" className="mb-5" />
      {cargando ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Spinner className="h-4 w-4" /> Cargando…
        </div>
      ) : (
        <div>
          {/* Redes que el plan espera por slot (el calendario las pinta como huecos por red).
              Selección sutil: la activa lleva relleno gris suave; el resto, texto apagado. */}
          <div className="mb-6 flex flex-wrap items-center gap-1">
            <span className="mr-2 text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">
              Redes
            </span>
            {ORDEN_REDES.map((id) => {
              const Icono = iconoRed(id);
              const activa = redes.has(id);
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={activa}
                  onClick={() => {
                    setRedes((prev) => {
                      const sig = new Set(prev);
                      if (sig.has(id)) sig.delete(id);
                      else sig.add(id);
                      return sig;
                    });
                    programarGuardado();
                  }}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-sm transition-colors",
                    activa
                      ? "bg-muted font-medium text-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-foreground",
                  )}
                >
                  <Icono className="h-3.5 w-3.5" />
                  {nombreRed(id)}
                </button>
              );
            })}
          </div>

          {/* Ledger: cabecera + una fila por línea (Línea · Al día · Horas · ×). */}
          <div className="grid grid-cols-[1fr_5rem_minmax(0,2fr)_2rem] items-center gap-4 border-b border-border px-1 pb-2">
            <span className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">
              Línea
            </span>
            <span className="text-right text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">
              Al día
            </span>
            <span className="text-xs font-medium uppercase tracking-[0.06em] text-muted-foreground">
              Horas
            </span>
            <span className="sr-only">Acciones</span>
          </div>

          {filasPlan.map((fila) => {
            const cupo = filas[fila.clave]?.cupo ?? "0";
            return (
              <div
                key={fila.clave}
                className="group grid grid-cols-[1fr_5rem_minmax(0,2fr)_2rem] items-center gap-4 border-b border-border px-1 py-2.5"
              >
                <Label className="text-sm font-medium">{fila.etiqueta}</Label>
                <Input
                  type="number"
                  min={0}
                  value={cupo}
                  onChange={(e) => {
                    setFilas((prev) => ({
                      ...prev,
                      [fila.clave]: {
                        ...(prev[fila.clave] ?? { cupo: "0", horas: "" }),
                        cupo: e.target.value,
                      },
                    }));
                    programarGuardado();
                  }}
                  aria-label={`Publicaciones al día de ${fila.etiqueta}`}
                  className={cn(
                    "h-8 w-16 justify-self-end border-0 bg-transparent px-2 text-right tabular-nums shadow-none hover:bg-muted/60 focus-visible:ring-1",
                    Number(cupo) > 0 ? "" : "text-muted-foreground",
                  )}
                />
                {fila.conHorario ? (
                  <SelectorHoras
                    value={filas[fila.clave]?.horas ?? ""}
                    onChange={(csv) => {
                      setFilas((prev) => ({
                        ...prev,
                        [fila.clave]: {
                          ...(prev[fila.clave] ?? { cupo: "0", horas: "" }),
                          horas: csv,
                        },
                      }));
                      programarGuardado();
                    }}
                    ariaLabel={`Horarios de ${fila.etiqueta} (hora CDMX)`}
                  />
                ) : (
                  <span className="text-xs text-muted-foreground">Sale al instante</span>
                )}
                {fila.esLinea ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="text-muted-foreground opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
                    aria-label={`Quitar ${fila.etiqueta}`}
                    disabled={quitarLinea.isPending}
                    onClick={() => quitarLinea.mutate(fila.clave)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                ) : (
                  <span />
                )}
              </div>
            );
          })}

          {/* Añadir una LÍNEA nueva a esta marca (la crea de verdad; aparece como fila). */}
          <div className="grid grid-cols-[1fr_5rem_minmax(0,2fr)_2rem] items-center gap-4 px-1 py-2.5">
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
            <span />
            <Button
              type="button"
              variant="outline"
              className="w-fit text-muted-foreground"
              disabled={!nuevaLinea.trim() || crearLinea.isPending}
              onClick={() => crearLinea.mutate(nuevaLinea)}
            >
              {crearLinea.isPending ? (
                <Spinner className="h-4 w-4" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Añadir
            </Button>
            <span />
          </div>

          <div className="mt-6 flex items-center justify-between border-t border-border pt-4">
            <span className="text-sm text-muted-foreground">
              Total: <span className="font-medium tabular-nums text-foreground">{total}</span>{" "}
              contenidos/día
            </span>
            {/* Donde antes estaba «Guardar»: el plan se guarda solo, esto solo lo confirma. */}
            <span
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
              aria-live="polite"
            >
              {estadoGuardado === "guardando" ? (
                <>
                  <Spinner className="h-3.5 w-3.5" /> Guardando…
                </>
              ) : estadoGuardado === "guardado" ? (
                <>
                  <Check className="h-3.5 w-3.5 text-emerald-600" /> Guardado
                </>
              ) : (
                <span className="text-muted-foreground/70">Se guarda solo</span>
              )}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
