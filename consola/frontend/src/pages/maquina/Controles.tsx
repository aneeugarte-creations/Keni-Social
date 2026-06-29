/**
 * Controles (`/maquina/controles`): mando único de la máquina de contenido.
 *
 * Reúne en una sola página los interruptores que antes estaban dispersos: el maestro
 * y la pausa (Estado global), las cuentas de Claude (Cuentas), los switches del
 * pipeline (Investigación / Producción) y los toggles avanzados (colapsado por defecto).
 *
 * Solo accesible como admin (mismo gate que /sistema). Un 403 en /api/ajustes muestra
 * estado restringido en lugar de un crash.
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, Cog, Info, ShieldAlert } from "lucide-react";
import * as React from "react";

import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_AJUSTES } from "@/pages/configuracion/lib";
import {
  ExcepcionesPorMarca,
  useGuardarAjuste,
} from "@/pages/configuracion/SeccionFuncionalidad";
import type { AjusteAdmin } from "@/types";

// Clave del interruptor general de la máquina.
const CLAVE_MAQUINA = "KENI_MAQUINA";
// Clave de la pausa de emergencia global.
const CLAVE_PAUSA = "KENI_GENERACION_PAUSADA";

// Claves de los maestros virtuales: no se surfacean como switches, pero
// son la clave BASE de las excepciones por marca de sus etapas seguidoras.
const MAESTRO_INV = "KENI_INVESTIGACION";
const MAESTRO_PROD = "KENI_PRODUCCION";

interface EtapaConfig {
  clave: string;
  nombre: string;
  es_ia: boolean;
  ayuda: string;
  /** Clave BASE de las excepciones por marca (prefijo de los ajustes `::marca`). */
  excepBase?: string;
}

// Etapas reales del pipeline de investigación con flag físico propio.
const ETAPAS_INVESTIGACION: EtapaConfig[] = [
  {
    clave: "KENI_PIPELINE_RECOLECTAR",
    nombre: "Recolectar",
    es_ia: false,
    ayuda: "Recolecta artículos de las fuentes y agrupa las notas idénticas (misma url o titular)",
    excepBase: MAESTRO_INV,
  },
  {
    clave: "KENI_PIPELINE_VERIFICAR",
    nombre: "Verificar",
    es_ia: true,
    ayuda: "Contrasta las fuentes antes de pasar a la mesa",
    excepBase: MAESTRO_INV,
  },
  {
    clave: "KENI_TRENDS",
    nombre: "Google Trends",
    es_ia: false,
    ayuda: "Ingiere las tendencias de Google al pool, como fuente extra junto a las fuentes RSS",
  },
];

// Etapas reales del pipeline de producción con flag físico propio.
const ETAPAS_PRODUCCION: EtapaConfig[] = [
  {
    clave: "KENI_PIPELINE_REDACTAR",
    nombre: "Redactar",
    es_ia: true,
    ayuda: "Redacta el copy que convierte la noticia verificada en pieza y revisa su voz y calidad antes de avanzar",
    excepBase: MAESTRO_PROD,
  },
  {
    clave: "KENI_PIPELINE_ILUSTRAR",
    nombre: "Ilustrar",
    es_ia: true,
    ayuda: "Genera imagen por IA para los temas con copy y sin imagen",
    excepBase: "KENI_PIPELINE_ILUSTRAR",
  },
  {
    clave: "KENI_PIPELINE_STOCK",
    nombre: "Stock",
    es_ia: false,
    ayuda: "Adjunta una foto de stock como referencia sin licencia para los temas sin imagen",
  },
  {
    clave: "KENI_PIPELINE_SUGERIR_HASHTAGS",
    nombre: "Keywords",
    es_ia: true,
    ayuda: "Propone los hashtags habituales de la marca y la imagen clave que alimenta el buscador de stock",
  },
  {
    clave: "KENI_CRITICA_IA",
    nombre: "Crítica",
    es_ia: true,
    ayuda: "Tras los dos OK humanos, revisa con visión la pieza terminada antes de auto-programar",
  },
];

// Toggles avanzados: infrecuentes o posiblemente ausentes del catálogo.
// Los ausentes del catálogo se renderizan como filas informativas.
const ETAPAS_AVANZADO: EtapaConfig[] = [
  {
    clave: "KENI_PIPELINE_FUSIONAR",
    nombre: "Fusionar",
    es_ia: true,
    ayuda: "Funde las notas del mismo hecho y agrupa las de un mismo gran evento",
  },
  {
    clave: "KENI_CLASIFICAR_MARCA_IA",
    nombre: "Clasificar",
    es_ia: true,
    ayuda: "Asigna marca a las notas de últimas horas",
  },
  {
    clave: "KENI_PRIORIZAR_PERFIL_IA",
    nombre: "Priorizar",
    es_ia: true,
    ayuda: "Ordena por relevancia para tu marca",
  },
  {
    clave: "KENI_PIPELINE_DECISOR",
    nombre: "Decisor",
    es_ia: true,
    ayuda: "Elige el camino de la pieza —foto o carrusel— antes de redactarla",
  },
  {
    clave: "KENI_PIPELINE_REVISAR",
    nombre: "Revisar",
    es_ia: true,
    ayuda: "Revisión final de la pieza antes de aprobar",
  },
  {
    clave: "KENI_AUTO_PROGRAMAR",
    nombre: "Auto-programar",
    es_ia: false,
    ayuda: "Programa la publicación automáticamente según el horario definido",
  },
  {
    clave: "KENI_AUTO_PREAPROBACION",
    nombre: "Pre-aprobación",
    es_ia: false,
    ayuda: "Pre-aprueba las piezas de bajo riesgo sin revisión humana",
  },
];

/** Devuelve el ajuste efectivo para una clave: la variante por marca si existe, si no la global. */
function ajusteEfectivo(
  claveGlobal: string,
  marcaActiva: string | null,
  porClave: Map<string, AjusteAdmin>,
): AjusteAdmin | undefined {
  if (marcaActiva) {
    const conMarca = porClave.get(`${claveGlobal}::${marcaActiva}`);
    if (conMarca) return conMarca;
  }
  return porClave.get(claveGlobal);
}

/** Switch inline que escribe un ajuste con su propia mutación. */
function SwitchAjuste({
  ajuste,
  ariaLabel,
  tono,
}: {
  ajuste: AjusteAdmin;
  ariaLabel: string;
  tono?: "neutro" | "estado";
}) {
  const guardar = useGuardarAjuste();
  return (
    <Switch
      checked={Boolean(ajuste.valor)}
      disabled={guardar.isPending}
      onCheckedChange={(v) => guardar.mutate({ clave: ajuste.clave, valor: v })}
      aria-label={ariaLabel}
      tono={tono}
    />
  );
}

/** Excepciones por marca de la pausa, con su propia mutación (aislada para seguir las
 *  reglas de los hooks). Solo se monta cuando hay excepciones. */
function ExcepcionesPausa({
  ajustes,
  pausada,
}: {
  ajustes: AjusteAdmin[];
  pausada: boolean;
}) {
  const guardar = useGuardarAjuste();
  return (
    <ExcepcionesPorMarca
      ajustes={ajustes}
      onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
      guardando={guardar.isPending}
      maestros={{ [CLAVE_PAUSA]: pausada }}
    />
  );
}

/** Fila de una etapa del pipeline: icono de tipo, nombre, ayuda, switch (o info-env) y las
 *  excepciones por marca colapsables. */
function FilaEtapa({
  etapa,
  ajuste,
  deEtapa,
  maestroEfectivo,
}: {
  etapa: EtapaConfig;
  ajuste: AjusteAdmin | undefined;
  deEtapa: AjusteAdmin[];
  maestroEfectivo: boolean;
}) {
  const guardar = useGuardarAjuste();
  const [excAbierta, setExcAbierta] = React.useState(false);
  const tieneExcepciones = deEtapa.length > 0;

  return (
    <div
      className="border-b border-border/50 last:border-0"
      data-testid={`fila-etapa-${etapa.clave}`}
    >
      <div className="flex items-center justify-between gap-3 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            {etapa.es_ia ? (
              <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="IA" />
            ) : (
              <Cog className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label="determinista" />
            )}
            <span className="truncate">{etapa.nombre}</span>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{etapa.ayuda}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {tieneExcepciones && (
            <button
              type="button"
              aria-expanded={excAbierta}
              onClick={() => setExcAbierta((v) => !v)}
              className="flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground"
            >
              {deEtapa.length} {deEtapa.length === 1 ? "excepción" : "excepciones"}
              <ChevronDown
                className={cn("h-3 w-3 transition-transform", excAbierta && "rotate-180")}
                aria-hidden
              />
            </button>
          )}
          {ajuste ? (
            <SwitchAjuste
              ajuste={ajuste}
              ariaLabel={`${etapa.nombre} (${etapa.clave})`}
            />
          ) : (
            <span
              className="flex items-center gap-1 text-xs text-muted-foreground"
              title="Controlado por variable de entorno; no editable desde aquí."
              data-testid="info-env"
            >
              <Info className="h-3.5 w-3.5" aria-hidden="true" />
              vía env
            </span>
          )}
        </div>
      </div>
      {excAbierta && tieneExcepciones && (
        <div className="mb-3 rounded-md border border-border/60 bg-muted/30 px-3 pb-1 pt-2">
          <ExcepcionesPorMarca
            ajustes={deEtapa}
            onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
            guardando={guardar.isPending}
            maestros={etapa.excepBase ? { [etapa.excepBase]: maestroEfectivo } : {}}
          />
        </div>
      )}
    </div>
  );
}

/** Lista de filas de etapas con resolución de ajuste efectivo por marca. */
function GrupoEtapas({
  etapas,
  porClave,
  porMarca,
  marcaActiva,
}: {
  etapas: EtapaConfig[];
  porClave: Map<string, AjusteAdmin>;
  porMarca: AjusteAdmin[];
  marcaActiva: string | null;
}) {
  return (
    <div>
      {etapas.map((etapa) => {
        const ajuste = ajusteEfectivo(etapa.clave, marcaActiva, porClave);
        const deEtapa = etapa.excepBase
          ? porMarca.filter((a) => a.clave.startsWith(`${etapa.excepBase}::`))
          : [];
        return (
          <FilaEtapa
            key={etapa.clave}
            etapa={etapa}
            ajuste={ajuste}
            deEtapa={deEtapa}
            maestroEfectivo={Boolean(ajuste?.valor)}
          />
        );
      })}
    </div>
  );
}

export default function Controles() {
  const { marcaActiva } = useMarcaActiva();

  const { data, isPending, isError, error } = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
  });

  const [avanzadoAbierto, setAvanzadoAbierto] = React.useState(false);

  const es403 = isError && error instanceof ApiError && error.status === 403;

  const porClave = React.useMemo(() => {
    const mapa = new Map<string, AjusteAdmin>();
    for (const g of data?.grupos ?? []) {
      for (const a of g.ajustes) mapa.set(a.clave, a);
    }
    return mapa;
  }, [data]);

  const porMarca = React.useMemo(
    () =>
      (data?.grupos ?? [])
        .filter((g) => g.id.startsWith("automatizacion_marca"))
        .flatMap((g) => g.ajustes),
    [data],
  );

  if (es403) {
    return <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />;
  }

  if (isPending) {
    return (
      <div className="space-y-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-xl" />
        ))}
      </div>
    );
  }

  const maquina = porClave.get(CLAVE_MAQUINA);
  const pausaEfectiva = ajusteEfectivo(CLAVE_PAUSA, marcaActiva, porClave);
  const excepcionesPausa = porMarca.filter((a) =>
    a.clave.startsWith(`${CLAVE_PAUSA}::`),
  );

  return (
    <div className="space-y-6">
      {/* 1. ESTADO GLOBAL */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Estado global</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {maquina && (
            <Label className="flex items-center justify-between gap-3 text-sm">
              <div>
                <span className="font-medium">{maquina.etiqueta}</span>
                <p className="text-xs font-normal text-muted-foreground">
                  Apagado, nada se auto-genera. Los pipelines quedan detenidos.
                </p>
              </div>
              <SwitchAjuste
                ajuste={maquina}
                ariaLabel="Máquina (auto): interruptor general de la auto-producción"
                tono="estado"
              />
            </Label>
          )}
          {pausaEfectiva && (
            <div className="space-y-2">
              <Label className="flex items-center justify-between gap-3 text-sm">
                <div>
                  <span className="font-medium">{pausaEfectiva.etiqueta}</span>
                  <p className="text-xs font-normal text-muted-foreground">
                    Pausa de emergencia
                    {marcaActiva ? ` de ${marcaActiva}` : " global"}: corta toda
                    la generación, incluida la manual.
                  </p>
                </div>
                <SwitchAjuste
                  ajuste={pausaEfectiva}
                  ariaLabel="Pausa de emergencia: corta toda la generación, incluida la manual"
                />
              </Label>
              {excepcionesPausa.length > 0 && (
                <div className="rounded-md border border-border/60 bg-muted/30 px-3 pb-1 pt-2">
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Excepciones por marca
                  </p>
                  <ExcepcionesPausa
                    ajustes={excepcionesPausa}
                    pausada={Boolean(pausaEfectiva.valor)}
                  />
                </div>
              )}
            </div>
          )}
          <p
            className="text-xs text-muted-foreground/70"
            data-testid="nota-manual"
          >
            El empuje manual desde Noticias ignora «Encendida/apagada» (genera aunque la máquina
            esté apagada); solo lo detiene la pausa de emergencia.
          </p>
        </CardContent>
      </Card>

      {/* 2. INVESTIGACIÓN */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Investigación</CardTitle>
          <p className="text-xs text-muted-foreground">
            Pipeline automático de investigación: entrada al pool y contraste de fuentes.
          </p>
        </CardHeader>
        <CardContent className="pt-0">
          <GrupoEtapas
            etapas={ETAPAS_INVESTIGACION}
            porClave={porClave}
            porMarca={porMarca}
            marcaActiva={marcaActiva}
          />
        </CardContent>
      </Card>

      {/* 4. PRODUCCIÓN */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Producción</CardTitle>
          <p className="text-xs text-muted-foreground">
            Pipeline automático de producción: copy, imagen y revisión final.
          </p>
        </CardHeader>
        <CardContent className="pt-0">
          <GrupoEtapas
            etapas={ETAPAS_PRODUCCION}
            porClave={porClave}
            porMarca={porMarca}
            marcaActiva={marcaActiva}
          />
        </CardContent>
      </Card>

      {/* 5. AVANZADO (colapsado por defecto) */}
      <Card data-testid="seccion-avanzado">
        <button
          type="button"
          aria-expanded={avanzadoAbierto}
          onClick={() => setAvanzadoAbierto((v) => !v)}
          className="flex w-full items-start justify-between gap-3 p-4 text-left"
        >
          <div>
            <p className="text-sm font-semibold">Avanzado</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Toggles infrecuentes. Los marcados «vía env» no están en el catálogo y se
              controlan con variable de entorno.
            </p>
          </div>
          <ChevronDown
            className={cn(
              "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform",
              avanzadoAbierto && "rotate-180",
            )}
            aria-hidden
          />
        </button>
        {avanzadoAbierto && (
          <CardContent className="pt-0">
            <GrupoEtapas
              etapas={ETAPAS_AVANZADO}
              porClave={porClave}
              porMarca={porMarca}
              marcaActiva={marcaActiva}
            />
          </CardContent>
        )}
      </Card>
    </div>
  );
}
