import { useMutation } from "@tanstack/react-query";
import {
  CalendarClock,
  Copyright,
  ExternalLink,
  Info,
  Loader2,
  MapPin,
  ScanSearch,
  ShieldAlert,
  ShieldQuestion,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGeneracion } from "@/hooks/use-generacion";
import { api } from "@/lib/api";
import type {
  PaisOrigen,
  ReporteVerificacion,
  RespuestaGeneracion,
  SenalesCopyright,
  SenalVerificacion,
} from "@/types";

/** Clave de sessionStorage para reanudar la verificación en curso al volver a la página. */
const CLAVE_GEN_VERIF = "keni:generacion-verificacion";

/** Variante de Badge para cada nivel de señal. */
function variantePorNivel(nivel: string): "error" | "aviso" | "secondary" {
  if (nivel === "alto") return "error";
  if (nivel === "medio") return "aviso";
  return "secondary";
}

/** Etiquetas legibles de cada buscador de imágenes inversa. */
const ETIQUETA_ENLACE: Record<string, string> = {
  tineye_mas_antiguo: "TinEye (más antiguo)",
  google_lens: "Google Lens",
  yandex: "Yandex",
  bing: "Bing",
};

function Senales({ senales }: { senales: SenalVerificacion[] }) {
  if (!senales?.length) return null;
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">Señales</h4>
      <ul className="space-y-2">
        {senales.map((s, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Badge variant={variantePorNivel(s.nivel)} className="mt-0.5 shrink-0 uppercase">
              {s.nivel}
            </Badge>
            <span className="text-muted-foreground">{s.texto}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Indicios de copyright / derechos de agencia: lo primero, para evitar strikes. */
function SeccionCopyright({ datos }: { datos?: SenalesCopyright }) {
  if (!datos) return null;
  const hay = datos.tiene_indicios && datos.agencias_detectadas.length > 0;
  return (
    <div
      className={
        hay
          ? "space-y-2 rounded-md border border-amber-400/60 bg-amber-50/60 p-3 dark:border-amber-500/40 dark:bg-amber-950/30"
          : "space-y-2"
      }
    >
      <h4 className="flex items-center gap-1.5 text-sm font-medium">
        {hay ? (
          <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-hidden />
        ) : (
          <Copyright className="h-4 w-4 text-muted-foreground" aria-hidden />
        )}
        Derechos / copyright
      </h4>
      <p className="text-sm text-muted-foreground">{datos.resumen}</p>
      {hay && (
        <ul className="space-y-1.5">
          {datos.agencias_detectadas.map((a, i) => (
            <li key={i} className="flex flex-wrap items-center gap-1.5 text-sm">
              <Badge variant={variantePorNivel(a.nivel_confianza)} className="uppercase">
                {a.nivel_confianza}
              </Badge>
              <span className="font-medium">{a.agencia}</span>
              <span className="text-muted-foreground">
                · vía {a.fuente}
                {a.patron_detectado ? ` ("${a.patron_detectado}")` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">
        Detección local (OCR, título, dominio): puede no ver una marca de agua tapada o una
        licencia sin texto. Ante la duda, confirma la licencia antes de publicar.
      </p>
    </div>
  );
}

/** Hipótesis de país de origen + fuentes de confirmación dirigidas. */
function SeccionPais({ datos }: { datos?: PaisOrigen }) {
  if (!datos) return null;
  const hayHipotesis = Boolean(datos.pais_hipotesis);
  return (
    <div className="space-y-2">
      <h4 className="flex items-center gap-1.5 text-sm font-medium">
        <MapPin className="h-4 w-4 text-muted-foreground" aria-hidden />
        País de origen
      </h4>
      <p className="flex flex-wrap items-center gap-1.5 text-sm">
        {hayHipotesis ? (
          <>
            <span className="font-medium">{datos.pais_hipotesis}</span>
            {datos.codigo_iso && (
              <Badge variant="secondary" className="uppercase">
                {datos.codigo_iso}
              </Badge>
            )}
            <Badge variant="outline">confianza {datos.confianza}</Badge>
          </>
        ) : (
          <span className="text-muted-foreground">
            Señal insuficiente para inferir el país (confianza {datos.confianza}).
          </span>
        )}
      </p>
      {datos.senales_detectadas && datos.senales_detectadas.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Señales: {datos.senales_detectadas.join(", ")}
        </p>
      )}
      {datos.fuentes_confirmacion.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-foreground">
            Confírmalo en estas fuentes (haz clic; tú juzgas):
          </p>
          <ul className="space-y-1">
            {datos.fuentes_confirmacion.map((f, i) => (
              <li key={i} className="flex items-start gap-1.5 text-sm">
                <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <a
                  href={f.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  {f.descripcion}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
      {datos.nota && <p className="text-xs text-muted-foreground">{datos.nota}</p>}
    </div>
  );
}

function BusquedaInversa({ reporte }: { reporte: ReporteVerificacion }) {
  const enlaces = reporte.busqueda_inversa?.enlaces ?? {};
  const claves = Object.keys(enlaces);
  if (claves.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No hay miniatura pública para la búsqueda inversa automática. Abre Google Lens o Yandex
        y arrastra ahí un fotograma del video.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">Búsqueda inversa — haz clic para confirmar si ya circulaba</h4>
      <div className="flex flex-wrap gap-2">
        {claves.map((k) => (
          <Button
            key={k}
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => window.open(enlaces[k], "_blank", "noopener,noreferrer")}
          >
            {ETIQUETA_ENLACE[k] ?? k}
            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
          </Button>
        ))}
      </div>
      {reporte.busqueda_inversa?.fotogramas_guardados_en && (
        <p className="text-xs text-muted-foreground">
          Para afinar, arrastra a Google Lens / Yandex los fotogramas guardados en{" "}
          <code className="rounded bg-muted px-1 py-0.5">
            {reporte.busqueda_inversa.fotogramas_guardados_en}
          </code>
          .
        </p>
      )}
    </div>
  );
}

function ResultadoVerificacion({ reporte }: { reporte: ReporteVerificacion }) {
  const m = reporte.metadatos ?? {};
  const ocr = reporte.ocr ?? {};
  const fechasOcr = [...(ocr.anios ?? []).map(String), ...(ocr.fechas ?? [])];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ScanSearch className="h-4 w-4" aria-hidden />
          Evidencia de procedencia
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Resumen de metadatos */}
        <div className="space-y-1.5 text-sm">
          {m.error && <p className="text-amber-600 dark:text-amber-500">{m.error}</p>}
          {m.titulo && (
            <p>
              <span className="text-muted-foreground">Título: </span>
              {m.titulo}
            </p>
          )}
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="inline-flex items-center gap-1.5">
              <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden />
              <span className="text-muted-foreground">Subido:</span>
              <span className="font-medium">{m.subido_iso || "desconocido"}</span>
            </span>
            {m.plataforma && (
              <span>
                <span className="text-muted-foreground">Plataforma: </span>
                {m.plataforma}
              </span>
            )}
            {m.autor && (
              <span>
                <span className="text-muted-foreground">Autor: </span>
                {m.autor}
              </span>
            )}
          </p>
          <p className="text-xs text-muted-foreground">
            La fecha de subida es cuándo se publicó <em>esta copia</em>, no cuándo se grabó: un
            video viejo puede subirse hoy.
          </p>
        </div>

        {/* Fechas/años en pantalla (OCR) */}
        {fechasOcr.length > 0 && (
          <div className="space-y-1.5">
            <h4 className="text-sm font-medium">Fechas en pantalla (OCR)</h4>
            <div className="flex flex-wrap gap-1.5">
              {fechasOcr.map((f) => (
                <Badge key={f} variant="secondary" className="font-mono">
                  {f}
                </Badge>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              El OCR puede equivocarse (un marcador o un dorsal puede parecer un año):
              confírmalo mirando el fotograma antes de darlo por bueno.
            </p>
          </div>
        )}

        <SeccionCopyright datos={reporte.senales_copyright} />

        <SeccionPais datos={reporte.pais_origen} />

        <Senales senales={reporte.senales ?? []} />

        <BusquedaInversa reporte={reporte} />

        {/* Verificaciones previas (Fact Check) */}
        {(reporte.fact_check?.resultados?.length ?? 0) > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">Verificaciones previas</h4>
            <ul className="space-y-1 text-sm">
              {reporte.fact_check.resultados!.map((r, i) => (
                <li key={i}>
                  <a
                    href={r.url ?? "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary underline underline-offset-2"
                  >
                    {r.verificador || "Verificador"}
                  </a>
                  {r.veredicto ? ` — ${r.veredicto}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Avisos del análisis */}
        {(reporte.avisos?.length ?? 0) > 0 && (
          <ul className="space-y-1 text-xs text-muted-foreground">
            {reporte.avisos!.map((a, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                {a}
              </li>
            ))}
          </ul>
        )}

        {/* Aviso honesto: esto asiste, no dictamina */}
        <p className="flex items-start gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
          <ShieldQuestion className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Esto reúne evidencia para datar el video; <strong>no es un veredicto automático</strong>.
          La prueba de fuego es la búsqueda inversa (haz clic arriba). Nada se publica ni se sube.
          La decisión de retomar o descartar es tuya.
        </p>
      </CardContent>
    </Card>
  );
}

export default function Verificacion() {
  const [enlace, setEnlace] = React.useState("");
  const [contexto, setContexto] = React.useState("");

  // Verificación en segundo plano (reanudable al cambiar de pestaña y volver).
  const { generacion, ejecutando, iniciar } = useGeneracion(CLAVE_GEN_VERIF);

  const mutacion = useMutation<RespuestaGeneracion, Error>({
    mutationFn: () => api.verificar({ enlace: enlace.trim(), contexto: contexto.trim() || undefined }),
    onSuccess: (data) => {
      iniciar(data.generacion);
      toast.success("Verificación en curso. Puedes seguirla aquí o cambiar de pestaña.");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "No se pudo verificar el video.");
    },
  });

  const puedeVerificar = enlace.trim().length > 0 && !ejecutando && !mutacion.isPending;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeVerificar) return;
    mutacion.mutate();
  }

  const reporte: ReporteVerificacion | null =
    generacion?.estado === "completado" ? generacion.resultado?.verificacion ?? null : null;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        titulo="Verificación de video"
        descripcion="Pega el enlace de un video viral y comprueba si es nuevo o si ya circulaba desde antes (reciclado), antes de decidir si retomarlo."
      />

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">¿De cuándo es este video?</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="enlace">Enlace del video (o ruta local)</Label>
              <Input
                id="enlace"
                value={enlace}
                onChange={(e) => setEnlace(e.target.value)}
                placeholder="https://x.com/…/status/…  ·  tiktok / facebook / instagram / youtube"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="contexto">Qué se afirma del video (opcional)</Label>
              <Input
                id="contexto"
                value={contexto}
                onChange={(e) => setContexto(e.target.value)}
                placeholder="supuestamente del sismo de hoy / dicen que es de las protestas de mayo"
              />
              <p className="text-xs text-muted-foreground">
                Ayuda a comparar contra la fecha real. El análisis corre en local; solo se leen
                metadatos públicos.
              </p>
            </div>
            <Button type="submit" disabled={!puedeVerificar} className="gap-1.5">
              {ejecutando || mutacion.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <ScanSearch className="h-4 w-4" aria-hidden />
              )}
              Verificar
            </Button>
          </form>
        </CardContent>
      </Card>

      {generacion && (ejecutando || generacion.estado === "error") && (
        <ProgresoGeneracion
          generacion={generacion}
          onReintentar={() => mutacion.mutate()}
          className="mt-6"
        />
      )}

      {reporte && (
        <div className="mt-6">
          <ResultadoVerificacion reporte={reporte} />
        </div>
      )}
    </div>
  );
}
