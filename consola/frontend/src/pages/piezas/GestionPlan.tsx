/**
 * «Plan y horarios» de la página Programación: EL sitio donde se configura, por marca, qué
 * LÍNEAS publica, cuántos contenidos salen al día de cada una y a qué horas (CDMX). Es una
 * SECCIÓN INLINE del panel de ajustes (capa base, colapsable), no un diálogo.
 *
 * El conjunto de líneas es POR MARCA y editable (añadir/quitar): así Fundación lista sus
 * temáticas (salud, medio-ambiente…) y no las de UnoTV. Por debajo toca tres cosas:
 *   - el CONJUNTO de líneas (y su orden) escribe el ajuste `KENI_LINEAS::<marca>` (CSV de
 *     claves); solo lo lee este editor para decidir qué filas pintar;
 *   - la CANTIDAD escribe el ajuste `KENI_PLAN_DIA::<marca>` ("linea:n,…", el que lee la
 *     admisión del pipeline) vía la API admin de ajustes;
 *   - los HORARIOS sincronizan las franjas editoriales CON CATEGORÍA de la marca (7 días a
 *     la misma hora; el backend guarda UTC, aquí se edita en hora CDMX).
 * Una línea cuya clave es una categoría con feeds se auto-rellena; las demás (p. ej.
 * «evergreen») son cajones de publicación que nutre el equipo. «Breaking» no lleva horario:
 * sale al instante. Solo admin (la API de ajustes rechaza al resto).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Save, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, mensajeError } from "@/lib/api";
import { horaCdmxAUtc, horaUtcACdmx } from "@/lib/fecha";
import { CATALOGO_LINEAS, ETIQUETA_LINEA, resolverClaveLinea } from "@/lib/lineas";

import { SelectorHoras } from "./SelectorHoras";

/** Líneas que el editor muestra por defecto cuando la marca no tiene su conjunto guardado. */
const LINEAS_BASE = ["mx", "internacional", "breaking", "entretenimiento", "evergreen"];

const RE_HORA = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Etiqueta legible de una línea (fallback: la clave capitalizada). */
function etiqueta(linea: string): string {
  return ETIQUETA_LINEA[linea] ?? linea.charAt(0).toUpperCase() + linea.slice(1);
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

export function PanelPlan({
  marca,
}: {
  marca: string;
}) {
  const queryClient = useQueryClient();
  const clavePlan = `KENI_PLAN_DIA::${marca}`;
  const claveLineas = `KENI_LINEAS::${marca}`;

  // Sin gate `enabled`: esta sección solo se MONTA cuando el usuario la despliega (la sección
  // colapsable no pinta su contenido plegada), así que las queries arrancan justo entonces.
  const ajustes = useQuery({
    queryKey: ["ajustes"],
    queryFn: ({ signal }) => api.ajustes(signal),
  });
  const franjasQuery = useQuery({
    queryKey: ["franjas"],
    queryFn: ({ signal }) => api.franjas(signal),
  });

  // Estado del formulario, inicializado al montar desde el conjunto de líneas + plan + franjas.
  const [filas, setFilas] = React.useState<Record<string, FilaLinea>>({});
  const [orden, setOrden] = React.useState<string[]>([]);
  const [nuevaLinea, setNuevaLinea] = React.useState("");
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
  const valorLineas = valorAjuste(claveLineas);

  const franjasMarca = React.useMemo(
    () =>
      (franjasQuery.data?.franjas ?? []).filter(
        (f) => f.marca === marca && (f.categoria ?? "") !== "",
      ),
    [franjasQuery.data, marca],
  );

  React.useEffect(() => {
    if (inicializado || ajustes.isPending || franjasQuery.isPending) return;
    const plan = parsearPlan(valorPlan);
    const horasPorLinea = new Map<string, Set<string>>();
    for (const f of franjasMarca) {
      const set = horasPorLinea.get(f.categoria) ?? new Set<string>();
      set.add(horaUtcACdmx(f.hora));
      horasPorLinea.set(f.categoria, set);
    }
    const guardadas = valorLineas
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    const base = guardadas.length ? guardadas : LINEAS_BASE;
    // Une el conjunto guardado con lo que ya tenga datos, para no esconder líneas con plan/horario.
    const ordenInicial = [...new Set([...base, ...Object.keys(plan), ...horasPorLinea.keys()])];
    const inicializadas: Record<string, FilaLinea> = {};
    for (const linea of ordenInicial) {
      inicializadas[linea] = {
        cupo: String(plan[linea] ?? 0),
        horas: [...(horasPorLinea.get(linea) ?? [])].sort().join(", "),
      };
    }
    setFilas(inicializadas);
    setOrden(ordenInicial);
    setInicializado(true);
  }, [inicializado, ajustes.isPending, franjasQuery.isPending, valorPlan, valorLineas, franjasMarca]);

  const anadirLinea = () => {
    const clave = resolverClaveLinea(nuevaLinea);
    if (!clave) return;
    if (orden.includes(clave)) {
      toast.error(`«${etiqueta(clave)}» ya está en el plan.`);
      return;
    }
    setOrden((prev) => [...prev, clave]);
    setFilas((prev) => ({ ...prev, [clave]: { cupo: "0", horas: "" } }));
    setNuevaLinea("");
  };

  const quitarLinea = (linea: string) => {
    setOrden((prev) => prev.filter((l) => l !== linea));
    setFilas((prev) => {
      const sig = { ...prev };
      delete sig[linea];
      return sig;
    });
  };

  const guardar = useMutation({
    mutationFn: async () => {
      // 1) Valida horas de todas las líneas (antes de tocar nada).
      const horasPorLinea: Record<string, string[]> = {};
      for (const linea of orden) {
        if (linea === "breaking") continue; // sin horario: sale al instante
        const horas = parsearHoras(filas[linea]?.horas ?? "");
        if (horas === null) {
          throw new Error(
            `Horas inválidas en «${etiqueta(linea)}»: usa HH:MM separadas por comas.`,
          );
        }
        horasPorLinea[linea] = horas;
      }
      // 2) Conjunto de líneas de la marca (orden incluido): lo lee este editor.
      await api.guardarAjuste({ clave: claveLineas, valor: orden.join(",") });
      // 3) Plan (cantidad por línea): escribe el ajuste que lee la admisión.
      const partes = orden
        .map((linea) => [linea, Number(filas[linea]?.cupo)] as const)
        .filter(([, n]) => Number.isInteger(n) && n > 0)
        .map(([linea, n]) => `${linea}:${n}`);
      await api.guardarAjuste({ clave: clavePlan, valor: partes.join(",") });
      // 4) Limpia las franjas de líneas que ya no están en el plan (líneas quitadas).
      const vigentes = new Set(orden);
      const huerfanas = franjasMarca.filter((f) => !vigentes.has(f.categoria));
      await Promise.all(huerfanas.map((f) => api.eliminarFranja(f.id)));
      // 5) Horarios: sincroniza las franjas de cada línea (7 días por hora, en UTC).
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
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : mensajeError(e)),
  });

  const total = orden.reduce((acc, l) => acc + (Number(filas[l]?.cupo) || 0), 0);
  const sugerencias = CATALOGO_LINEAS.filter((l) => !orden.includes(l.clave));

  return (
    <div>
      <p className="mb-3 text-xs text-muted-foreground">
        Qué líneas publica esta marca, cuántos contenidos al día y a qué horas (CDMX).
      </p>
      {ajustes.isPending || franjasQuery.isPending ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </div>
      ) : (
        <div className="space-y-3">
          {orden.map((linea) => (
            <div
              key={linea}
              className="grid grid-cols-[8rem_5rem_minmax(0,1fr)_auto] items-center gap-3"
            >
              <Label className="text-sm">{etiqueta(linea)}</Label>
              <Input
                type="number"
                min={0}
                value={filas[linea]?.cupo ?? "0"}
                onChange={(e) =>
                  setFilas((prev) => ({
                    ...prev,
                    [linea]: { ...(prev[linea] ?? { cupo: "0", horas: "" }), cupo: e.target.value },
                  }))
                }
                aria-label={`Publicaciones al día de ${etiqueta(linea)}`}
                className="tabular-nums"
              />
              {linea === "breaking" ? (
                <span className="text-xs text-muted-foreground">
                  Sin horario: sale al instante.
                </span>
              ) : (
                <SelectorHoras
                  value={filas[linea]?.horas ?? ""}
                  onChange={(csv) =>
                    setFilas((prev) => ({
                      ...prev,
                      [linea]: { ...(prev[linea] ?? { cupo: "0", horas: "" }), horas: csv },
                    }))
                  }
                  ariaLabel={`Horarios de ${etiqueta(linea)} (hora CDMX)`}
                />
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => quitarLinea(linea)}
                aria-label={`Quitar ${etiqueta(linea)}`}
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}

          <div className="grid grid-cols-[8rem_minmax(0,1fr)_auto] items-center gap-3">
            <Label className="text-sm text-muted-foreground">Añadir línea</Label>
            <Input
              list="catalogo-lineas"
              value={nuevaLinea}
              placeholder="p. ej. Salud, Medio ambiente…"
              onChange={(e) => setNuevaLinea(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  anadirLinea();
                }
              }}
              aria-label="Nombre de la nueva línea"
            />
            <datalist id="catalogo-lineas">
              {sugerencias.map((l) => (
                <option key={l.clave} value={l.etiqueta} />
              ))}
            </datalist>
            <Button
              type="button"
              variant="outline"
              onClick={anadirLinea}
              disabled={!nuevaLinea.trim()}
            >
              <Plus className="h-4 w-4" />
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
