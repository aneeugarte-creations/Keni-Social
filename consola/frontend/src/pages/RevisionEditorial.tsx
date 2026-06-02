import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Languages,
  Loader2,
  Scale,
  ScanText,
  ShieldQuestion,
  SpellCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/Markdown";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  HallazgoQaEditorial,
  InformeQaEditorial,
  RespuestaGeneracion,
  TipoHallazgoQa,
  Veredicto,
} from "@/types";

/** Clave de sessionStorage para reanudar la revisión en curso al volver a la página. */
const CLAVE_GEN_QA = "keni:generacion-qa-editorial";

/** Centinela del selector de plataforma para "sin plataforma" (no validar límite). */
const SIN_PLATAFORMA = "__sin_plataforma__";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "No se pudo revisar el copy. Vuelve a intentarlo.";
}

/**
 * Veredicto del informe con su semáforo 🟢/🟡/🔴 y leyenda, consistente con el
 * resto del producto (mismos valores `listo`/`revisar`/`no_publicar` que las
 * publicaciones). Abre el informe: lo primero que se ve, sin scroll.
 */
function META_VERDICTO(
  verdicto: Veredicto,
): { circulo: string; titulo: string; variante: "ok" | "aviso" | "error"; Icono: LucideIcon } {
  if (verdicto === "no_publicar")
    return { circulo: "🔴", titulo: "No publicar", variante: "error", Icono: XCircle };
  if (verdicto === "revisar")
    return { circulo: "🟡", titulo: "Revisar antes de publicar", variante: "aviso", Icono: AlertTriangle };
  // "listo" o "" (sin hallazgos): se trata como listo para aprobar.
  return { circulo: "🟢", titulo: "Listo para aprobar", variante: "ok", Icono: CheckCircle2 };
}

function VeredictoYLeyenda({ informe }: { informe: InformeQaEditorial }) {
  const m = META_VERDICTO(informe.verdicto);
  const cls =
    m.variante === "error"
      ? "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300"
      : m.variante === "aviso"
        ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300"
        : "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  return (
    <div className={cn("space-y-2 rounded-md border p-4", cls)}>
      <div className="flex items-center gap-2">
        <span className="text-xl leading-none" aria-hidden>
          {m.circulo}
        </span>
        <m.Icono className="h-5 w-5 shrink-0" aria-hidden />
        <span className="text-base font-semibold">{m.titulo}</span>
      </div>
      {informe.resumen && <p className="text-sm">{informe.resumen}</p>}
      <p className="text-xs opacity-80">
        Leyenda: 🟢 sin problemas · 🟡 revísalo tú antes de publicar · 🔴 problema serio, no
        publicar.
      </p>
    </div>
  );
}

/** Metadatos de cada tipo de hallazgo: etiqueta humana e icono. */
const META_TIPO: Record<TipoHallazgoQa, { etiqueta: string; Icono: LucideIcon }> = {
  ortografia: { etiqueta: "Ortografía", Icono: SpellCheck },
  dato: { etiqueta: "Dato", Icono: ScanText },
  legal: { etiqueta: "Legal", Icono: Scale },
  voz: { etiqueta: "Voz", Icono: Languages },
};

function TarjetaHallazgo({ hallazgo }: { hallazgo: HallazgoQaEditorial }) {
  const meta = META_TIPO[hallazgo.tipo] ?? { etiqueta: hallazgo.tipo, Icono: HelpCircle };
  const esError = hallazgo.gravedad === "error";
  return (
    <li className="space-y-2 rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="gap-1">
          <meta.Icono className="h-3.5 w-3.5" aria-hidden />
          {meta.etiqueta}
        </Badge>
        <Badge variant={esError ? "error" : "aviso"} className="uppercase">
          {esError ? "Corregir" : "Revisar"}
        </Badge>
        {hallazgo.no_verificable && (
          <Badge variant="secondary" className="gap-1">
            <ShieldQuestion className="h-3.5 w-3.5" aria-hidden />
            No verificable
          </Badge>
        )}
      </div>
      {hallazgo.fragmento && (
        <blockquote className="border-l-2 border-border pl-3 text-sm italic text-muted-foreground">
          “{hallazgo.fragmento}”
        </blockquote>
      )}
      {hallazgo.explicacion && <p className="text-sm">{hallazgo.explicacion}</p>}
      {hallazgo.sugerencia && (
        <p className="text-sm">
          <span className="font-medium text-foreground">
            {hallazgo.no_verificable ? "Qué comprobar: " : "Sugerencia: "}
          </span>
          <span className="text-muted-foreground">{hallazgo.sugerencia}</span>
        </p>
      )}
    </li>
  );
}

function Informe({ informe }: { informe: InformeQaEditorial }) {
  const [verTexto, setVerTexto] = React.useState(false);
  const hallazgos = informe.hallazgos ?? [];
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ScanText className="h-4 w-4" aria-hidden />
          Informe de QA editorial
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <VeredictoYLeyenda informe={informe} />

        {hallazgos.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No encontré problemas en el copy. Aun así, revísalo tú antes de aprobarlo: la
            decisión final es del equipo.
          </p>
        ) : (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">
              {hallazgos.length} {hallazgos.length === 1 ? "hallazgo" : "hallazgos"}
            </h4>
            <ul className="space-y-2">
              {hallazgos.map((h, i) => (
                <TarjetaHallazgo key={i} hallazgo={h} />
              ))}
            </ul>
          </div>
        )}

        {informe.informe_texto && (
          <div className="space-y-2">
            <Button variant="outline" size="sm" onClick={() => setVerTexto((v) => !v)}>
              {verTexto ? "Ocultar" : "Ver"} informe completo
            </Button>
            {verTexto && (
              <div className="max-h-[28rem] overflow-auto rounded-md border border-border bg-muted/20 p-4 leading-relaxed">
                <Markdown>{informe.informe_texto}</Markdown>
              </div>
            )}
          </div>
        )}

        {/* Aviso honesto: esto SEÑALA, no decide ni publica. */}
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          <ShieldQuestion className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Esto <strong>señala</strong> lo que conviene revisar; no reescribe el copy ni lo
          publica. Las correcciones son sugerencias: tú decides cuáles aceptar y apruebas el
          texto final.
        </p>
      </CardContent>
    </Card>
  );
}

export default function RevisionEditorial() {
  const [marca, setMarca] = React.useState("");
  const [plataforma, setPlataforma] = React.useState(SIN_PLATAFORMA);
  const [texto, setTexto] = React.useState("");
  const [contexto, setContexto] = React.useState("");

  // Catálogo para el formulario (marcas, plataformas, si la skill está instalada).
  const opcionesQuery = useQuery({
    queryKey: ["qa-editorial", "opciones"],
    queryFn: ({ signal }) => api.qaEditorialOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];
  const plataformas = opcionesQuery.data?.plataformas ?? [];
  const skillDisponible = opcionesQuery.data?.skill_disponible ?? true;

  // Revisión en segundo plano (reanudable al cambiar de pestaña y volver).
  const { generacion, ejecutando, iniciar, cancelar, cancelando } = useGeneracion(CLAVE_GEN_QA);

  const mutacion = useMutation<RespuestaGeneracion, Error>({
    mutationFn: () =>
      api.revisarQaEditorial({
        marca,
        texto: texto.trim(),
        plataforma: plataforma === SIN_PLATAFORMA ? undefined : plataforma,
        contexto: contexto.trim() || undefined,
      }),
    onSuccess: (data) => {
      iniciar(data.generacion);
      toast.success("Revisión en curso. Puedes seguirla aquí o cambiar de pestaña.");
    },
    onError: (err) => toast.error(mensajeError(err)),
  });

  const puedeRevisar =
    marca !== "" && texto.trim().length > 0 && !ejecutando && !mutacion.isPending;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeRevisar) return;
    mutacion.mutate();
  }

  const informe: InformeQaEditorial | null =
    generacion?.estado === "completado" ? generacion.resultado?.informe ?? null : null;

  return (
    <div>
      <PageHeader
        titulo="Revisión editorial"
        descripcion="Pega el copy que escribió el community manager y obtén un veredicto con typos, datos sospechosos, reglas legales y desviaciones de la voz de marca. Señala; no reescribe ni publica."
      />

      {!skillDisponible && (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
          La skill de QA editorial no está instalada en este equipo. Actualiza el plugin de
          skills de Keni para usar la revisión.
        </div>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Revisar un copy</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="qa-marca">Marca</Label>
                <SelectorMarca
                  id="qa-marca"
                  marcas={marcas}
                  valor={marca}
                  onCambio={setMarca}
                  incluirTodas={false}
                  placeholder="Elige la marca"
                  ariaLabel="Marca del copy a revisar"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="qa-plataforma">Plataforma (opcional)</Label>
                <Select value={plataforma} onValueChange={setPlataforma}>
                  <SelectTrigger id="qa-plataforma" aria-label="Plataforma del copy">
                    <SelectValue placeholder="Sin plataforma" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={SIN_PLATAFORMA}>Sin plataforma</SelectItem>
                    {plataformas.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="qa-texto">Copy a revisar</Label>
              <Textarea
                id="qa-texto"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder="Pega aquí el copy que escribió el community manager, tal cual."
                className="min-h-[10rem] font-mono text-sm leading-relaxed"
                autoFocus
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="qa-contexto">Contexto / fuente (opcional)</Label>
              <Textarea
                id="qa-contexto"
                value={contexto}
                onChange={(e) => setContexto(e.target.value)}
                placeholder="Pega la nota o los datos de origen para comprobar fechas, nombres y cifras."
                className="min-h-[5rem] text-sm leading-relaxed"
              />
              <p className="text-xs text-muted-foreground">
                Sin fuente, los datos solo se marcan como “no verificables”: nunca se inventan.
                Solo el texto llega al asistente; nada se publica.
              </p>
            </div>

            <Button type="submit" disabled={!puedeRevisar} className="gap-1.5">
              {ejecutando || mutacion.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <ScanText className="h-4 w-4" aria-hidden />
              )}
              Revisar
            </Button>
          </form>
        </CardContent>
      </Card>

      {generacion && (ejecutando || generacion.estado === "error") && (
        <ProgresoGeneracion
          generacion={generacion}
          onReintentar={() => mutacion.mutate()}
          onCancelar={cancelar}
          cancelando={cancelando}
          className="mt-6"
        />
      )}

      {informe && (
        <div className="mt-6">
          <Informe informe={informe} />
        </div>
      )}
    </div>
  );
}
