/**
 * Sección "Publicidad (Meta Ads)": el INORGÁNICO del periodo a nivel marca.
 *
 * Lista las campañas de pago (impresiones, gasto, clics) con sus totales, claramente
 * separadas de lo orgánico. Sólo aparece si hubo inversión con entrega en el periodo
 * (si no, no ensucia el dashboard). Reusa el stack del resto de Métricas: encuadre
 * uniforme `Seccion` + editor de columnas + tabla ordenable, con estados honestos
 * (carga / error / vacío).
 *
 * Cuando la fuente las trae, ofrece columnas de rendimiento (CTR/CPC/CPM/Conversiones)
 * y un filtro por red; y al expandir una campaña con `provider_campaign_id`, su desglose
 * en conjuntos de anuncios y anuncios. Todo aditivo: si el dato no viene, no se muestra.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Megaphone } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { nombreRed, numeroCompacto, numeroCompleto, porcentaje } from "@/lib/formato";
import type { AdCreativoAds, AdGroupAds, CampaniaAdsMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import type { ColumnaMeta } from "./columnasMeta";
import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

const TODAS = "__todas__";

function dinero(v: number, moneda: string): string {
  return `${v.toLocaleString("es-MX", { maximumFractionDigits: 0 })} ${moneda}`.trim();
}

/** Coste unitario (CPC/CPM): importes pequeños que pierden sentido sin decimales. */
function dineroFino(v: number, moneda: string): string {
  return `${v.toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${moneda}`.trim();
}

type ClaveOrden = "impresiones" | "gasto" | "clics" | "ctr" | "cpc" | "cpm" | "conversiones";

// Accesores de orden a nivel módulo: identidad estable entre renders. Los avanzados
// devuelven `null` cuando la fuente no los trae (van al final del orden).
const ACCESORES: Record<ClaveOrden, (a: CampaniaAdsMetrica) => number | null> = {
  impresiones: (a) => a.impresiones,
  gasto: (a) => a.gasto,
  clics: (a) => a.clics,
  ctr: (a) => a.ctr ?? null,
  cpc: (a) => a.cpc ?? null,
  cpm: (a) => a.cpm ?? null,
  conversiones: (a) => a.conversiones ?? null,
};

/** Columnas FIJAS de la tabla de campañas de Ads (orden base + etiquetas legibles). */
const COLUMNAS: ColumnaMeta[] = [
  { id: "campania", etiqueta: "Campaña" },
  { id: "red", etiqueta: "Red" },
  { id: "impresiones", etiqueta: "Impresiones" },
  { id: "gasto", etiqueta: "Gasto" },
  { id: "clics", etiqueta: "Clics" },
];

/** Columnas de rendimiento: solo se ofrecen si la fuente las trae en el periodo (CTR/CPC/CPM
 * y conversiones llegan de Meta Ads y no siempre vienen). */
const COLUMNAS_AVANZADAS: ColumnaMeta[] = [
  { id: "ctr", etiqueta: "CTR" },
  { id: "cpc", etiqueta: "CPC" },
  { id: "cpm", etiqueta: "CPM" },
  { id: "conversiones", etiqueta: "Conversiones" },
];

/** ¿La columna es una métrica ordenable (cabecera con clic)? */
function esOrdenable(id: string): id is ClaveOrden {
  return id in ACCESORES;
}

export function SeccionAds({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "ads", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasAds({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const ads = React.useMemo(() => data?.ads ?? [], [data]);

  // Filtro LOCAL por red sobre las campañas ya cargadas (encima del selector global de
  // Métricas): solo aparece si hay 2+ redes con pauta en el periodo.
  const [redFiltro, setRedFiltro] = React.useState<string>(TODAS);
  const redesPresentes = React.useMemo(() => [...new Set(ads.map((a) => a.red).filter(Boolean))], [ads]);
  React.useEffect(() => {
    if (redFiltro !== TODAS && !redesPresentes.includes(redFiltro)) setRedFiltro(TODAS);
  }, [redesPresentes, redFiltro]);
  const adsFiltradas = React.useMemo(
    () => (redFiltro === TODAS ? ads : ads.filter((a) => a.red === redFiltro)),
    [ads, redFiltro],
  );

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CampaniaAdsMetrica, ClaveOrden>(
    adsFiltradas,
    ACCESORES,
    { clave: "impresiones", direccion: "desc" },
  );

  // Las columnas de rendimiento solo entran (orden base + editor de campos) si alguna campaña
  // las trae; si no, la tabla se ve exactamente como antes.
  const hayAvanzadas = React.useMemo(
    () => ads.some((a) => a.ctr != null || a.cpc != null || a.cpm != null || a.conversiones != null),
    [ads],
  );
  const columnasMeta = hayAvanzadas ? [...COLUMNAS, ...COLUMNAS_AVANZADAS] : COLUMNAS;
  const idsBase = columnasMeta.map((c) => c.id);

  const cfgGuardada = useVistaConfig((s) => s.columnas["ads"]);
  const cfg = cfgGuardada ?? { orden: idsBase, ocultas: [] };
  const columnas = columnasVisibles(idsBase, cfg);

  // Campaña expandida (drill-down): una a la vez, identificada por su id de proveedor.
  const [expandida, setExpandida] = React.useState<string | null>(null);

  // Sin inversión con entrega en el periodo (o sin Ads conectado): no se muestra la sección.
  if (!isPending && !isError && (data?.total.campanias ?? 0) === 0) return null;

  const total = data?.total;
  const etiquetaDe = (id: string) => columnasMeta.find((c) => c.id === id)?.etiqueta ?? id;
  const padding = (idx: number) =>
    [idx === 0 ? "pl-6" : "", idx === columnas.length - 1 ? "pr-6" : ""].filter(Boolean).join(" ");

  const encabezado = (id: string, idx: number) => {
    const clase = padding(idx) || undefined;
    if (esOrdenable(id)) {
      return (
        <CabeceraOrdenable
          key={id}
          activa={estado.clave === id}
          direccion={estado.direccion}
          onClick={() => alClicar(id)}
          alinear="right"
          className={clase}
        >
          {etiquetaDe(id)}
        </CabeceraOrdenable>
      );
    }
    return (
      <TableHead key={id} className={clase}>
        {etiquetaDe(id)}
      </TableHead>
    );
  };

  const vacia = <span className="text-muted-foreground">—</span>;

  const celda = (a: CampaniaAdsMetrica, id: string, idx: number) => {
    const borde = padding(idx);
    if (id === "campania") {
      const idProveedor = a.provider_campaign_id ?? null;
      const abierta = idProveedor != null && expandida === idProveedor;
      return (
        <TableCell key={id} className={borde || undefined}>
          <div className="flex items-center gap-1.5">
            {idProveedor != null && (
              <button
                type="button"
                onClick={() => setExpandida(abierta ? null : idProveedor)}
                aria-label={abierta ? "Ocultar desglose" : "Ver desglose"}
                aria-expanded={abierta}
                className="shrink-0 text-muted-foreground hover:text-foreground"
              >
                {abierta ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
            )}
            <span className="block max-w-[28rem] truncate font-medium" title={a.nombre}>
              {a.nombre}
            </span>
          </div>
        </TableCell>
      );
    }
    if (id === "red") {
      return (
        <TableCell key={id} className={borde || undefined}>
          <Badge variant="outline">{nombreRed(a.red)}</Badge>
        </TableCell>
      );
    }
    const claseNum = `text-right tabular-nums ${borde}`.trim();
    if (id === "impresiones") {
      return (
        <TableCell key={id} className={claseNum} title={numeroCompleto(a.impresiones)}>
          {numeroCompacto(a.impresiones)}
        </TableCell>
      );
    }
    if (id === "gasto") {
      return (
        <TableCell key={id} className={claseNum}>
          {dinero(a.gasto, a.moneda)}
        </TableCell>
      );
    }
    if (id === "clics") {
      return (
        <TableCell key={id} className={claseNum}>
          {numeroCompacto(a.clics)}
        </TableCell>
      );
    }
    if (id === "ctr") {
      return (
        <TableCell key={id} className={claseNum}>
          {a.ctr != null ? porcentaje(a.ctr) : vacia}
        </TableCell>
      );
    }
    if (id === "cpc") {
      return (
        <TableCell key={id} className={claseNum}>
          {a.cpc != null ? dineroFino(a.cpc, a.moneda) : vacia}
        </TableCell>
      );
    }
    if (id === "cpm") {
      return (
        <TableCell key={id} className={claseNum}>
          {a.cpm != null ? dineroFino(a.cpm, a.moneda) : vacia}
        </TableCell>
      );
    }
    if (id === "conversiones") {
      return (
        <TableCell key={id} className={claseNum} title={a.conversiones != null ? numeroCompleto(a.conversiones) : undefined}>
          {a.conversiones != null ? numeroCompacto(a.conversiones) : vacia}
        </TableCell>
      );
    }
    return null;
  };

  // Filtro por red, a la izquierda del editor de campos (solo con varias redes).
  const acciones =
    redesPresentes.length > 1 ? (
      <Select value={redFiltro} onValueChange={setRedFiltro}>
        <SelectTrigger className="h-8 w-[150px] text-xs" aria-label="Filtrar por red">
          <SelectValue placeholder="Red" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODAS}>Todas las redes</SelectItem>
          {redesPresentes.map((r) => (
            <SelectItem key={r} value={r}>
              {nombreRed(r)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    ) : undefined;

  return (
    <Seccion
      id="ads"
      titulo="Publicidad"
      icono={Megaphone}
      descripcion="Campañas de pago"
      acciones={acciones}
      tablaId="ads"
      columnas={columnasMeta}
    >
      <Card className="overflow-hidden py-2">
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : isError ? (
          <p className="p-6 text-sm text-muted-foreground">No se pudieron cargar las campañas de Ads.</p>
        ) : (
          <>
            {total && (
              <div className="flex flex-wrap gap-x-8 gap-y-2 border-b px-6 py-4">
                {/* `total.visualizaciones` es la SUMA de la columna Impresiones (no son
                    vistas orgánicas): el término correcto en Ads es "Impresiones". */}
                <Kpi etiqueta="Impresiones" valor={numeroCompacto(total.visualizaciones)} titulo={numeroCompleto(total.visualizaciones)} />
                <Kpi etiqueta="Gasto" valor={dinero(total.gasto, total.moneda)} />
                <Kpi etiqueta="Campañas" valor={String(total.campanias)} />
                <Kpi etiqueta="Clics" valor={numeroCompacto(total.clics)} />
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>{columnas.map(encabezado)}</TableRow>
              </TableHeader>
              <TableBody>
                {filasOrdenadas.map((a, i) => {
                  // Clave estable ante reordenaciones: nombre+red+inicio identifica la
                  // campaña; el índice solo entra si `inicio` llega vacío.
                  const clave = `${a.nombre}-${a.red}-${a.inicio || i}`;
                  const idProveedor = a.provider_campaign_id ?? null;
                  const abierta = idProveedor != null && expandida === idProveedor;
                  return (
                    <React.Fragment key={clave}>
                      <TableRow>{columnas.map((id, idx) => celda(a, id, idx))}</TableRow>
                      {abierta && idProveedor != null && (
                        <TableRow>
                          <TableCell colSpan={columnas.length} className="bg-muted/30 p-0">
                            <DesgloseAdsFila providerCampaignId={idProveedor} marca={marca_} moneda={a.moneda} />
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </>
        )}
      </Card>
    </Seccion>
  );
}

/** Desglose de una campaña pagada en conjuntos de anuncios y anuncios (drill-down). Carga
 * perezosamente al expandir; si el endpoint no existe (404) o no hay datos, degrada en
 * silencio sin romper la tabla padre. */
function DesgloseAdsFila({
  providerCampaignId,
  marca,
  moneda,
}: {
  providerCampaignId: string;
  marca?: string;
  moneda: string;
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "ads", "desglose", providerCampaignId, marca ?? "todas"],
    queryFn: ({ signal }) => api.metricasAdsDesglose(providerCampaignId, { marca }, signal),
    staleTime: 2 * 60_000,
  });

  if (isPending) {
    return (
      <div className="p-4">
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
    );
  }
  const adgroups = data?.adgroups ?? [];
  const ads = data?.ads ?? [];
  if (isError || (adgroups.length === 0 && ads.length === 0)) {
    return <p className="px-6 py-3 text-xs text-muted-foreground">Sin desglose disponible para esta campaña.</p>;
  }
  return (
    <div className="space-y-4 px-6 py-4">
      {adgroups.length > 0 && <SubTablaAdgroups filas={adgroups} moneda={moneda} />}
      {ads.length > 0 && <SubTablaCreativos filas={ads} moneda={moneda} />}
    </div>
  );
}

/** Conjuntos de anuncios de la campaña (compacta). */
function SubTablaAdgroups({ filas, moneda }: { filas: AdGroupAds[]; moneda: string }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-muted-foreground">Conjuntos de anuncios</p>
      <div className="overflow-hidden rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Conjunto</TableHead>
              <TableHead className="text-right">Impresiones</TableHead>
              <TableHead className="text-right">Clics</TableHead>
              <TableHead className="text-right">Gasto</TableHead>
              <TableHead className="pr-4 text-right">Conversiones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.map((g, i) => (
              <TableRow key={`${g.nombre}-${i}`}>
                <TableCell className="pl-4">
                  <span className="block max-w-[20rem] truncate" title={g.nombre}>
                    {g.nombre || "—"}
                  </span>
                </TableCell>
                <TableCell className="text-right tabular-nums" title={numeroCompleto(g.impresiones)}>
                  {numeroCompacto(g.impresiones)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{numeroCompacto(g.clics)}</TableCell>
                <TableCell className="text-right tabular-nums">{dinero(g.gasto, g.moneda ?? moneda)}</TableCell>
                <TableCell className="pr-4 text-right tabular-nums">
                  {g.conversiones != null ? numeroCompacto(g.conversiones) : <span className="text-muted-foreground">—</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

/** Anuncios (creativos) de la campaña, con miniatura si la fuente la trae (compacta). */
function SubTablaCreativos({ filas, moneda }: { filas: AdCreativoAds[]; moneda: string }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-muted-foreground">Anuncios</p>
      <div className="overflow-hidden rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-4">Anuncio</TableHead>
              <TableHead>Conjunto</TableHead>
              <TableHead className="text-right">Impresiones</TableHead>
              <TableHead className="text-right">Clics</TableHead>
              <TableHead className="pr-4 text-right">Gasto</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.map((ad, i) => (
              <TableRow key={`${ad.nombre}-${i}`}>
                <TableCell className="pl-4">
                  <span className="flex items-center gap-2">
                    {ad.thumbnail_url ? (
                      <img
                        src={ad.thumbnail_url}
                        alt=""
                        loading="lazy"
                        className="h-8 w-8 shrink-0 rounded object-cover"
                      />
                    ) : null}
                    <span className="block max-w-[18rem] truncate" title={ad.nombre}>
                      {ad.nombre || "—"}
                    </span>
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  <span className="block max-w-[12rem] truncate" title={ad.adgroup ?? undefined}>
                    {ad.adgroup || "—"}
                  </span>
                </TableCell>
                <TableCell className="text-right tabular-nums" title={numeroCompleto(ad.impresiones)}>
                  {numeroCompacto(ad.impresiones)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{numeroCompacto(ad.clics)}</TableCell>
                <TableCell className="pr-4 text-right tabular-nums">{dinero(ad.gasto, ad.moneda ?? moneda)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function Kpi({ etiqueta, valor, titulo }: { etiqueta: string; valor: string; titulo?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs text-muted-foreground">{etiqueta}</p>
      <p className="text-lg font-semibold tabular-nums" title={titulo ?? valor}>
        {valor}
      </p>
    </div>
  );
}
