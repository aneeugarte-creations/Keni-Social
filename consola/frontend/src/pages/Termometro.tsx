import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, Loader2, RefreshCw, Save, Sparkles } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { TermometroPreview } from "@/components/generaciones/TermometroPreview";
import { BloqueError } from "@/components/comunes/BloqueError";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { desdeNinguna, ningunaParam } from "@/components/comunes/selectores";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError } from "@/lib/api";
import type { ItemRss, RespuestaTermometro } from "@/types";

/** Clave de sessionStorage para reanudar la generación en curso al volver a la página. */
const CLAVE_GEN_TERMOMETRO = "keni:generacion-termometro";

const CLAVE_TERMOMETRO = ["termometro"] as const;

const CABECERA = {
  titulo: "Termómetro mundial",
  descripcion:
    "El posteo de galería con las 5–8 noticias internacionales más importantes del día, una por región. Pega las notas, jerarquízalas y arma el copy del posteo listo para revisar.",
};

/** Opciones del número de slides (coinciden con el backend). */
const OPCIONES_NUMERO = ["5", "6", "7", "8"] as const;

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Formatea un item de RSS como una línea de noticia para el textarea. */
function formatearItem(item: ItemRss): string {
  let linea = `- ${item.titulo}`;
  if (item.fuente_nombre) linea += ` (${item.fuente_nombre})`;
  if (item.enlace) linea += ` [${item.enlace}]`;
  return linea;
}

/**
 * Termómetro mundial. Página dedicada: configura el termómetro (número de slides,
 * regiones, hora del cron de las 7:00 y marca) y genera el posteo de galería con el
 * prompt base del Termómetro (Biblioteca). Reutiliza el motor de generación en segundo plano
 * (`useGeneracion` + `ProgresoGeneracion`) y muestra el resultado como PORTADA + SLIDES
 * en miniatura con `TermometroPreview` (máquina de estados: armar → generando → revisar →
 * guardar). El guardado multi-red sigue el mismo contrato neutro `{ redes: [...] }`.
 */
export default function Termometro() {
  const query = useQuery({
    queryKey: CLAVE_TERMOMETRO,
    queryFn: ({ signal }) => api.termometro(signal),
  });

  return (
    <>
      <PageHeader {...CABECERA} />
      {query.isPending ? (
        <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
          <Skeleton className="h-72 w-full rounded-md" />
          <Skeleton className="h-96 w-full rounded-md" />
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el termómetro"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
          <PanelConfig datos={query.data} />
          <PanelGenerar datos={query.data} />
        </div>
      )}
    </>
  );
}

// --- Configuración (panel izquierdo) --------------------------------------

function PanelConfig({ datos }: { datos: RespuestaTermometro }) {
  const queryClient = useQueryClient();
  const [numero, setNumero] = React.useState(String(datos.config.numero));
  const [regiones, setRegiones] = React.useState(datos.config.regiones);
  const [hora, setHora] = React.useState(datos.config.hora);
  const [marca, setMarca] = React.useState(datos.config.marca);

  const guardar = useMutation({
    mutationFn: () =>
      api.guardarTermometro({
        numero: Number(numero),
        regiones: regiones.trim(),
        hora,
        marca,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TERMOMETRO });
      toast.success("Configuración guardada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="h-4 w-4" />
          Configuración
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="term-marca">Marca por defecto</Label>
          {/* Marca OPCIONAL ("" = sin fijar): el centinela NINGUNA se traduce a
              "" en el estado con `ningunaParam`/`desdeNinguna`. Sin "Todas". */}
          <SelectorMarca
            id="term-marca"
            marcas={datos.marcas}
            valor={desdeNinguna(marca)}
            onCambio={(v) => setMarca(ningunaParam(v))}
            incluirTodas={false}
            incluirNinguna
            etiquetaNinguna="Sin fijar"
            placeholder="Elige una marca"
            ariaLabel="Marca por defecto"
            className="w-full"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="term-numero">Número de slides</Label>
          <Select value={numero} onValueChange={setNumero}>
            <SelectTrigger id="term-numero">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {OPCIONES_NUMERO.map((n) => (
                <SelectItem key={n} value={n}>
                  {n} noticias
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="term-regiones">
            Regiones <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="term-regiones"
            value={regiones}
            onChange={(e) => setRegiones(e.target.value)}
            placeholder={datos.regiones_sugeridas.join(", ")}
          />
          <p className="text-xs text-muted-foreground">
            Separadas por coma. Vacío = reparto por defecto priorizando la diversidad.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="term-hora">Hora de la generación programada</Label>
          <Input
            id="term-hora"
            type="time"
            value={hora}
            onChange={(e) => setHora(e.target.value)}
            className="w-36"
          />
          <p className="text-xs text-muted-foreground">
            La usa el cron <code>keni-termometro</code> (ver docs). La consola no programa sola.
          </p>
        </div>
        <div className="flex justify-end">
          <Button size="sm" onClick={() => guardar.mutate()} disabled={guardar.isPending}>
            {guardar.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Guardar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Indicador de la máquina de estados (visual) --------------------------

/**
 * Muestra el avance del termómetro como una secuencia de pasos:
 * Armar → Generando → Revisar → Guardar. Resalta el paso ACTIVO según el estado
 * (`generando`/`completado`). Es solo orientación visual; los botones siguen siendo
 * la acción real.
 */
function PasosTermometro({ generando, completado }: { generando: boolean; completado: boolean }) {
  // Índice del paso activo: 0 armar · 1 generando · 2 revisar/guardar.
  const activo = generando ? 1 : completado ? 2 : 0;
  const pasos = ["Armar", "Generando", "Revisar y guardar"] as const;
  return (
    <ol className="flex items-center gap-1.5 text-xs" aria-label="Estado del termómetro">
      {pasos.map((p, i) => {
        const esActivo = i === activo;
        const hecho = i < activo;
        return (
          <li key={p} className="flex items-center gap-1.5">
            <span
              aria-current={esActivo ? "step" : undefined}
              className={
                esActivo
                  ? "rounded-full bg-primary px-2 py-0.5 font-medium text-primary-foreground"
                  : hecho
                    ? "rounded-full bg-muted px-2 py-0.5 text-foreground"
                    : "rounded-full px-2 py-0.5 text-muted-foreground"
              }
            >
              {p}
            </span>
            {i < pasos.length - 1 && <span className="text-muted-foreground">→</span>}
          </li>
        );
      })}
    </ol>
  );
}

// --- Generación (panel derecho) -------------------------------------------

function PanelGenerar({ datos }: { datos: RespuestaTermometro }) {
  const queryClient = useQueryClient();
  const marcaInicial = datos.config.marca || datos.marcas[0]?.id || "";
  const [marca, setMarca] = React.useState(marcaInicial);
  const [numero, setNumero] = React.useState(String(datos.config.numero));
  const [regiones] = React.useState(datos.config.regiones);
  const [fecha, setFecha] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [noticias, setNoticias] = React.useState("");
  const [trayendo, setTrayendo] = React.useState(false);

  const { generacion, ejecutando, iniciar, cancelar, cancelando } =
    useGeneracion(CLAVE_GEN_TERMOMETRO);

  const generar = useMutation({
    mutationFn: () =>
      api.generarTermometro({ marca, noticias, numero, regiones: regiones.trim(), fecha }),
    onSuccess: (data) => iniciar(data.generacion),
    onError: (e) => toast.error(mensajeError(e)),
  });

  async function traerDelRss() {
    setTrayendo(true);
    try {
      const r = await api.itemsRss(undefined, true);
      const lineas = r.items.slice(0, 25).map(formatearItem);
      if (lineas.length === 0) {
        toast.message("No hay noticias en los feeds RSS. Da de alta feeds en Fuentes.");
        return;
      }
      setNoticias((prev) => (prev.trim() ? `${prev}\n${lineas.join("\n")}` : lineas.join("\n")));
      toast.success(`${lineas.length} ${lineas.length === 1 ? "titular traído" : "titulares traídos"} del RSS`);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setTrayendo(false);
    }
  }

  const generando = generar.isPending || ejecutando;
  const puedeGenerar = datos.skill_disponible && marca !== "" && noticias.trim().length > 0 && !generando;
  const resultado = generacion?.resultado;
  const completado = generacion?.estado === "completado" && resultado?.documento !== undefined;
  const nombreMarca = (id: string) => datos.marcas.find((m) => m.id === id)?.nombre ?? id;

  // Al completarse una generación nueva, refrescamos el termómetro para que `datos.ultimo`
  // (el resultado PERSISTENTE leído del historial) refleje ya esta galería: así al navegar
  // fuera y volver se repinta sin depender del estado de cliente.
  React.useEffect(() => {
    if (completado) void queryClient.invalidateQueries({ queryKey: CLAVE_TERMOMETRO });
  }, [completado, queryClient]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            Armar el termómetro de hoy
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!datos.skill_disponible && (
            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
              Falta el prompt base del Termómetro en la Biblioteca, así que ahora mismo no se puede
              generar. Restáuralo desde la semilla para volver a habilitarlo.
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="gen-marca">Marca</Label>
              {/* Marca OBLIGATORIA: sin "Todas" ni "Sin marca". */}
              <SelectorMarca
                id="gen-marca"
                marcas={datos.marcas}
                valor={marca}
                onCambio={setMarca}
                incluirTodas={false}
                placeholder="Elige una marca"
                ariaLabel="Marca"
                className="w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="gen-numero">Slides</Label>
              <Select value={numero} onValueChange={setNumero}>
                <SelectTrigger id="gen-numero">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OPCIONES_NUMERO.map((n) => (
                    <SelectItem key={n} value={n}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="gen-fecha">Fecha</Label>
              <Input id="gen-fecha" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="gen-noticias">Noticias internacionales del día</Label>
              <Button variant="outline" size="sm" onClick={() => void traerDelRss()} disabled={trayendo}>
                {trayendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Traer del RSS
              </Button>
            </div>
            <Textarea
              id="gen-noticias"
              value={noticias}
              onChange={(e) => setNoticias(e.target.value)}
              placeholder="Pega aquí las notas candidatas (titulares, links o resúmenes), una por línea. El termómetro se arma SOLO con esto."
              className="min-h-[12rem]"
            />
            <p className="text-xs text-muted-foreground">
              La materia prima del termómetro. No inventa nada fuera de aquí: jerarquiza estas notas y
              elige el top por región.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => generar.mutate()} disabled={!puedeGenerar}>
              {generando ? <Loader2 className="h-4 w-4 animate-spin" /> : <MarcaIA />}
              {generando ? "Generando…" : completado ? "Regenerar termómetro" : "Generar termómetro"}
            </Button>
            <PasosTermometro generando={generando} completado={completado} />
          </div>
        </CardContent>
      </Card>

      {/* Progreso en vivo (texto token a token + métricas) mientras corre o si falla. */}
      {generacion && (ejecutando || generacion.estado === "error") && (
        <ProgresoGeneracion generacion={generacion} onCancelar={cancelar} cancelando={cancelando} />
      )}

      {/* Resultado de la galería (estado "revisar"/"guardar"), con la PORTADA + SLIDES en
          miniatura y el guardado multi-red. Prioriza el resultado en vivo recién generado;
          si no lo hay, repinta el último termómetro del historial (`ultimo`): fuente
          PERSISTENTE que sobrevive a navegaciones y recargas hasta que otro lo reemplace o
          se borre del historial. */}
      {completado && resultado?.documento !== undefined ? (
        <TermometroPreview
          documento={resultado.documento}
          historialId={resultado.historial_id ?? ""}
          marca={nombreMarca(marca)}
        />
      ) : datos.ultimo ? (
        <TermometroPreview
          documento={datos.ultimo.documento}
          historialId={datos.ultimo.historial_id}
          marca={nombreMarca(datos.ultimo.marca)}
        />
      ) : null}
    </div>
  );
}

