import { useMutation } from "@tanstack/react-query";
import { Check, Copy, ExternalLink, Loader2, Save } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { PiezaGenerada, RespuestaEjecutarSkill, Veredicto } from "@/types";

import { iconoRed, metaRed, metaVeredicto, nombreRed } from "../publicaciones/meta";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Badge de veredicto editorial; no renderiza nada si no hay veredicto. */
function BadgeVeredicto({ veredicto }: { veredicto: Veredicto }) {
  const m = metaVeredicto(veredicto);
  if (!m) return null;
  return <Badge variant={m.variante}>{m.nombre}</Badge>;
}

/** Contador de caracteres con su límite; rojo si se pasa. */
function Contador({ caracteres, limite }: { caracteres: number; limite: number | null }) {
  const excede = limite !== null && caracteres > limite;
  return (
    <span
      className={cn(
        "text-xs tabular-nums",
        excede ? "font-medium text-red-600 dark:text-red-400" : "text-muted-foreground",
      )}
    >
      {caracteres.toLocaleString("es-MX")}
      {limite !== null && ` / ${limite.toLocaleString("es-MX")}`}
    </span>
  );
}

/** Enlace de éxito a Publicaciones que se muestra en el toast. */
function EnlacePublicaciones() {
  return (
    <Link to="/publicaciones" className="inline-flex items-center gap-1 underline">
      Ver en Publicaciones
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
}

/** Panel de una red: textarea editable, contador, veredicto y acciones. */
function PanelRed({
  red,
  contenido,
  onCambio,
  titulo,
  marca,
  veredicto,
  origen,
  onGuardado,
}: {
  red: string;
  contenido: string;
  onCambio: (valor: string) => void;
  titulo: string;
  marca: string;
  veredicto: Veredicto;
  origen: string;
  onGuardado: (red: string) => void;
}) {
  const [copiado, setCopiado] = React.useState(false);
  const limite = metaRed(red).limite;
  const caracteres = contenido.length;

  const guardar = useMutation({
    mutationFn: () =>
      api.crearPublicacion({
        titulo: titulo.trim() || `Borrador ${nombreRed(red)}`,
        marca,
        red,
        contenido,
        estado: "borrador",
        veredicto,
        origen,
      }),
    onSuccess: () => {
      onGuardado(red);
      toast.success(`Guardado en ${nombreRed(red)}`, { description: <EnlacePublicaciones /> });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  async function copiar() {
    try {
      await navigator.clipboard.writeText(contenido);
      setCopiado(true);
      toast.success("Copiado al portapapeles");
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <BadgeVeredicto veredicto={veredicto} />
        <Contador caracteres={caracteres} limite={limite} />
      </div>
      <Textarea
        value={contenido}
        onChange={(e) => onCambio(e.target.value)}
        className="min-h-[12rem] font-mono text-sm leading-relaxed"
        aria-label={`Contenido para ${nombreRed(red)}`}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => void copiar()}>
          {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copiado ? "Copiado" : "Copiar"}
        </Button>
        <Button
          size="sm"
          onClick={() => guardar.mutate()}
          disabled={guardar.isPending || contenido.trim().length === 0}
        >
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar como publicación
        </Button>
      </div>
    </div>
  );
}

/**
 * Resultado de la generación con una pestaña por red.
 *
 * Cada pestaña: contenido editable, contador con su límite, badge de veredicto
 * y botones Copiar / "Guardar como publicación". El botón global "Guardar
 * todas" usa el endpoint de lote. Si no hay piezas, el contenedor padre muestra
 * el `Resultado` simple en su lugar.
 */
export function ResultadoRedes({
  respuesta,
  titulo,
  marca,
}: {
  respuesta: RespuestaEjecutarSkill;
  titulo: string;
  marca: string;
}) {
  // Estado editable: una copia local del contenido por red, reiniciada cuando
  // llega una generación nueva (identificada por historial_id).
  const [contenidos, setContenidos] = React.useState<Record<string, string>>({});
  const [guardadas, setGuardadas] = React.useState<Set<string>>(new Set());

  React.useEffect(() => {
    const inicial: Record<string, string> = {};
    for (const p of respuesta.piezas) inicial[p.red] = p.contenido;
    setContenidos(inicial);
    setGuardadas(new Set());
  }, [respuesta]);

  const piezas = respuesta.piezas;
  const [activa, setActiva] = React.useState(piezas[0]?.red ?? "");

  React.useEffect(() => {
    if (piezas.length > 0 && !piezas.some((p) => p.red === activa)) {
      setActiva(piezas[0].red);
    }
  }, [piezas, activa]);

  const guardarTodas = useMutation({
    mutationFn: () =>
      api.crearPublicacionesLote({
        publicaciones: piezas.map((p) => ({
          titulo: titulo.trim() || `Borrador ${nombreRed(p.red)}`,
          marca,
          red: p.red,
          contenido: contenidos[p.red] ?? p.contenido,
          estado: "borrador" as const,
          veredicto: respuesta.verdicto,
          origen: respuesta.historial_id,
        })),
      }),
    onSuccess: (data) => {
      setGuardadas(new Set(piezas.map((p) => p.red)));
      const n = data?.publicaciones?.length ?? piezas.length;
      toast.success(`Se guardaron ${n} ${n === 1 ? "publicación" : "publicaciones"}`, {
        description: <EnlacePublicaciones />,
      });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function marcarGuardada(red: string) {
    setGuardadas((prev) => new Set(prev).add(red));
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <div className="space-y-1">
          <CardTitle className="text-base">Resultado por red</CardTitle>
          <Badge variant="aviso">Borrador · no se publica</Badge>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => guardarTodas.mutate()}
          disabled={guardarTodas.isPending}
        >
          {guardarTodas.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar todas
        </Button>
      </CardHeader>
      <CardContent>
        <Tabs value={activa} onValueChange={setActiva}>
          <TabsList className="flex-wrap">
            {piezas.map((p) => {
              const Icono = iconoRed(p.red);
              return (
                <TabsTrigger key={p.red} value={p.red} className="gap-1.5">
                  <Icono className="h-4 w-4" />
                  {nombreRed(p.red)}
                  {guardadas.has(p.red) && (
                    <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                  )}
                </TabsTrigger>
              );
            })}
          </TabsList>
          {piezas.map((p: PiezaGenerada) => (
            <TabsContent key={p.red} value={p.red}>
              <PanelRed
                red={p.red}
                contenido={contenidos[p.red] ?? p.contenido}
                onCambio={(valor) => setContenidos((prev) => ({ ...prev, [p.red]: valor }))}
                titulo={titulo}
                marca={marca}
                veredicto={respuesta.verdicto}
                origen={respuesta.historial_id}
                onGuardado={marcarGuardada}
              />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}
