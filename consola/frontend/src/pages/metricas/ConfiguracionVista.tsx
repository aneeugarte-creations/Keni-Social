/**
 * Panel "Configurar vista" del dashboard de Métricas.
 *
 * Diálogo que controla la capa de PRESENTACIÓN (no los datos): qué secciones se
 * muestran y, por tabla, qué columnas se ven y en qué orden. Todo se persiste en
 * `vistaConfig` (localStorage), así que sobrevive a recargas y lo serializan las
 * vistas guardadas. "Restablecer" vuelve al estado por defecto (todo visible, todas
 * las redes, orden base de columnas).
 */
import { ChevronDown, ChevronUp, RotateCcw, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { TABLAS_CONFIG } from "./columnasMeta";
import { GRUPOS_SECCIONES } from "./seccionesMeta";
import { type ConfigColumnas, useVistaConfig } from "./vistaConfig";

/** Bloque de visibilidad de secciones (checkbox por sección, agrupadas). */
function SeccionesConfig() {
  const secciones = useVistaConfig((s) => s.secciones);
  const setSeccionVisible = useVistaConfig((s) => s.setSeccionVisible);

  return (
    <div className="space-y-5">
      {GRUPOS_SECCIONES.map((grupo) => (
        <fieldset key={grupo.titulo} className="space-y-2">
          <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {grupo.titulo}
          </legend>
          <div className="space-y-2">
            {grupo.secciones.map((s) => {
              const visible = secciones[s.id] !== false;
              const id = `sec-${s.id}`;
              return (
                <div key={s.id} className="flex items-center gap-2">
                  <Checkbox
                    id={id}
                    checked={visible}
                    onCheckedChange={(v) => setSeccionVisible(s.id, v)}
                    aria-label={s.etiqueta}
                  />
                  <Label htmlFor={id} className="cursor-pointer font-normal">
                    {s.etiqueta}
                  </Label>
                </div>
              );
            })}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

/** Orden COMPLETO de columnas (incluidas las ocultas): `orden` válido + base al final. */
function ordenCompleto(todas: string[], cfg: ConfigColumnas): string[] {
  return [
    ...cfg.orden.filter((id) => todas.includes(id)),
    ...todas.filter((id) => !cfg.orden.includes(id)),
  ];
}

/** Configuración de columnas de UNA tabla: mostrar/ocultar y reordenar (subir/bajar). */
function TablaColumnasConfig({
  tablaId,
  titulo,
  columnas,
}: {
  tablaId: string;
  titulo: string;
  columnas: { id: string; etiqueta: string }[];
}) {
  const cfgGuardada = useVistaConfig((s) => s.columnas[tablaId]);
  const setColumnas = useVistaConfig((s) => s.setColumnas);

  const base = columnas.map((c) => c.id);
  const cfg = cfgGuardada ?? { orden: base, ocultas: [] };
  const orden = ordenCompleto(base, cfg);
  const etiquetaDe = (id: string) => columnas.find((c) => c.id === id)?.etiqueta ?? id;

  const toggle = (id: string, visible: boolean) => {
    const ocultas = visible
      ? cfg.ocultas.filter((x) => x !== id)
      : [...cfg.ocultas, id];
    setColumnas(tablaId, { orden, ocultas });
  };

  const mover = (idx: number, delta: number) => {
    const destino = idx + delta;
    if (destino < 0 || destino >= orden.length) return;
    const nuevo = [...orden];
    [nuevo[idx], nuevo[destino]] = [nuevo[destino], nuevo[idx]];
    setColumnas(tablaId, { orden: nuevo, ocultas: cfg.ocultas });
  };

  return (
    <fieldset className="space-y-2">
      <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {titulo}
      </legend>
      <ul className="space-y-1">
        {orden.map((id, idx) => {
          const visible = !cfg.ocultas.includes(id);
          const checkId = `col-${tablaId}-${id}`;
          return (
            <li key={id} className="flex items-center gap-2">
              <Checkbox
                id={checkId}
                checked={visible}
                onCheckedChange={(v) => toggle(id, v)}
                aria-label={etiquetaDe(id)}
              />
              <Label htmlFor={checkId} className="flex-1 cursor-pointer font-normal">
                {etiquetaDe(id)}
              </Label>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => mover(idx, -1)}
                disabled={idx === 0}
                aria-label={`Subir ${etiquetaDe(id)}`}
              >
                <ChevronUp className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => mover(idx, 1)}
                disabled={idx === orden.length - 1}
                aria-label={`Bajar ${etiquetaDe(id)}`}
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

/** Configuración de columnas de todas las tablas configurables. */
function ColumnasConfig() {
  return (
    <div className="space-y-5">
      {TABLAS_CONFIG.map((t) => (
        <TablaColumnasConfig
          key={t.id}
          tablaId={t.id}
          titulo={t.titulo}
          columnas={t.columnas}
        />
      ))}
    </div>
  );
}

/** Botón "Configurar vista" + diálogo. Se monta en la cabecera de Analíticas. */
export function ConfiguracionVista() {
  const reset = useVistaConfig((s) => s.reset);

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 gap-1.5 text-xs">
          <SlidersHorizontal className="h-4 w-4" />
          Configurar vista
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Configurar vista</DialogTitle>
          <DialogDescription>
            Elige qué secciones y columnas se muestran. Los cambios se guardan en este
            navegador.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="secciones">
          <TabsList className="w-full">
            <TabsTrigger value="secciones" className="flex-1">
              Secciones
            </TabsTrigger>
            <TabsTrigger value="columnas" className="flex-1">
              Columnas
            </TabsTrigger>
          </TabsList>
          <TabsContent value="secciones">
            <SeccionesConfig />
          </TabsContent>
          <TabsContent value="columnas">
            <ColumnasConfig />
          </TabsContent>
        </Tabs>

        <div className="flex justify-end border-t pt-4">
          <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => reset()}>
            <RotateCcw className="h-4 w-4" />
            Restablecer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
