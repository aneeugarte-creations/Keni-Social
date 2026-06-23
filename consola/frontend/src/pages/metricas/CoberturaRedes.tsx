/**
 * Auditoría de cobertura por marca y red.
 *
 * Muestra, por cada marca del reporte, TODAS las redes sociales medibles (X,
 * Instagram, Facebook, TikTok, YouTube) — aunque no tengan datos — con su estado y el
 * MOTIVO de por qué aporta (o no) datos. Responde a "¿por qué en esta marca solo veo
 * 1 red?": las demás aparecen aquí con su causa explícita (no conectada, conectada
 * pero sin métricas en el rango, no dada de alta, etc.), en vez de ocultarse.
 *
 * Los datos vienen de `/api/metricas/reporte` › `cobertura_redes`, que el backend
 * deriva de la cobertura que ya trae el resumen (sin llamadas extra). Una métrica
 * `null` se pinta "—" (la red no respondió: no se inventa un 0 falso).
 *
 * La sección filtra client-side por marca; el foco de red lo manda el selector GLOBAL
 * de la cabecera (solo se muestran las redes seleccionadas). Qué columnas se ven y en
 * qué orden lo decide el editor de campos de la sección (`vistaConfig.columnas.cobertura`),
 * aplicado a cada bloque de marca. Ordena las redes (por vistas / interacciones /
 * engagement) con un orden global elegido por el usuario que se aplica dentro de cada bloque.
 */
import { Radar } from "lucide-react";
import * as React from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { nombreRed, numeroCompleto, porcentaje, redEnFoco } from "@/lib/formato";
import type { MarcaCobertura, RedCobertura } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import type { ColumnaMeta } from "./columnasMeta";
import { Seccion } from "./Seccion";
import type { DireccionOrden } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

/** Id de tabla de esta sección (clave en `vistaConfig.columnas`). */
const TABLA = "cobertura";

/** Catálogo de columnas de la tabla por marca, en su orden base. */
const COLUMNAS: ColumnaMeta[] = [
  { id: "red", etiqueta: "Red" },
  { id: "estado", etiqueta: "Estado" },
  { id: "visualizaciones", etiqueta: "Vistas" },
  { id: "interacciones", etiqueta: "Interacciones" },
  { id: "engagement_pct", etiqueta: "Engagement" },
  { id: "stories", etiqueta: "Stories" },
  { id: "motivo", etiqueta: "Motivo" },
];

const IDS_BASE = COLUMNAS.map((c) => c.id);

/** Metadatos de presentación por estado de cobertura (etiqueta + color del punto). */
const ESTADO: Record<string, { etiqueta: string; texto: string; punto: string }> = {
  con_datos: {
    etiqueta: "Con datos",
    texto: "text-emerald-700 dark:text-emerald-300",
    punto: "bg-emerald-500",
  },
  sin_metricas: {
    etiqueta: "Sin métricas",
    texto: "text-amber-700 dark:text-amber-400",
    punto: "bg-amber-500",
  },
  no_conectada: {
    etiqueta: "No conectada",
    texto: "text-muted-foreground",
    punto: "bg-muted-foreground/40",
  },
  sin_lectura: {
    etiqueta: "Sin lectura",
    texto: "text-red-700 dark:text-red-300",
    punto: "bg-red-500",
  },
  no_configurada: {
    etiqueta: "No configurada",
    texto: "text-muted-foreground",
    punto: "bg-muted-foreground/40",
  },
  sin_credenciales: {
    etiqueta: "Sin credenciales",
    texto: "text-red-700 dark:text-red-300",
    punto: "bg-red-500",
  },
  presupuesto_agotado: {
    etiqueta: "Límite de API",
    texto: "text-amber-700 dark:text-amber-400",
    punto: "bg-amber-500",
  },
};

const ESTADO_FALLBACK = {
  etiqueta: "Desconocido",
  texto: "text-muted-foreground",
  punto: "bg-muted-foreground/40",
};

function metaEstado(estado: string) {
  return ESTADO[estado] ?? ESTADO_FALLBACK;
}

/**
 * Resumen "3/5 con datos" para la cabecera de cada marca, sobre las redes EN FOCO que se
 * muestran (cuando hay foco de red, el conteo describe lo seleccionado, no el universo).
 */
function conteo(redes: RedCobertura[]): string {
  const con = redes.filter((r) => r.estado === "con_datos").length;
  return `${con}/${redes.length} con datos`;
}

/** Centinela "sin filtro" para los selectores de red/marca. */
const TODAS = "__todas__";

/** Columnas numéricas ordenables de una red (orden global compartido entre bloques). */
type ClaveOrden = "visualizaciones" | "interacciones" | "engagement_pct";

const ACCESOR: Record<ClaveOrden, (r: RedCobertura) => number | null> = {
  visualizaciones: (r) => r.visualizaciones,
  interacciones: (r) => r.interacciones,
  engagement_pct: (r) => r.engagement_pct,
};

/** Etiqueta de cada columna numérica ordenable (la que pinta la cabecera). */
const ETIQUETA_ORDEN: Record<ClaveOrden, string> = {
  visualizaciones: "Vistas",
  interacciones: "Interacciones",
  engagement_pct: "Engagement",
};

function esClaveOrden(id: string): id is ClaveOrden {
  return id === "visualizaciones" || id === "interacciones" || id === "engagement_pct";
}

/**
 * Ordena las redes de un bloque según el orden global elegido (null/no finito al
 * final, igual que `useOrdenTabla`). Si no hay columna activa, respeta el orden
 * natural del backend.
 */
function ordenarRedes(
  redes: RedCobertura[],
  clave: ClaveOrden | null,
  direccion: DireccionOrden,
): RedCobertura[] {
  if (clave == null) return redes;
  const acceso = ACCESOR[clave];
  const signo = direccion === "asc" ? 1 : -1;
  return redes
    .map((red, i) => ({ red, i }))
    .sort((a, b) => {
      const va = acceso(a.red);
      const vb = acceso(b.red);
      const na = va == null || !Number.isFinite(va);
      const nb = vb == null || !Number.isFinite(vb);
      if (na && nb) return a.i - b.i;
      if (na) return 1;
      if (nb) return -1;
      const cmp = (va as number) - (vb as number);
      return cmp !== 0 ? cmp * signo : a.i - b.i;
    })
    .map((x) => x.red);
}

function BloqueMarca({
  marca,
  red,
  columnas,
  clave,
  direccion,
  alClicar,
}: {
  marca: MarcaCobertura;
  /** Foco de red global (`vistaConfig.red`, CSV): solo se muestran las redes en foco. */
  red: string | null;
  /** Ids de columna visibles, en su orden efectivo (mismo para todos los bloques). */
  columnas: string[];
  clave: ClaveOrden | null;
  direccion: DireccionOrden;
  alClicar: (clave: ClaveOrden) => void;
}) {
  // Solo las redes en foco (selector global) y luego el orden global.
  const enFoco = marca.redes.filter((r) => redEnFoco(red, r.red));
  const redes = ordenarRedes(enFoco, clave, direccion);
  if (redes.length === 0) return null;

  const encabezado = (id: string) => {
    if (id === "red") {
      return (
        <TableHead key={id} className="pl-6">
          Red
        </TableHead>
      );
    }
    if (id === "estado") {
      return <TableHead key={id}>Estado</TableHead>;
    }
    if (id === "stories") {
      return (
        <TableHead key={id} className="text-right">
          Stories
        </TableHead>
      );
    }
    if (id === "motivo") {
      return (
        <TableHead key={id} className="pr-6">
          Motivo
        </TableHead>
      );
    }
    const c = id as ClaveOrden;
    return (
      <CabeceraOrdenable
        key={id}
        activa={clave === c}
        direccion={direccion}
        onClick={() => alClicar(c)}
        alinear="right"
      >
        {ETIQUETA_ORDEN[c]}
      </CabeceraOrdenable>
    );
  };

  const celda = (r: RedCobertura, id: string) => {
    switch (id) {
      case "red":
        return (
          <TableCell key={id} className="pl-6 font-medium">
            {nombreRed(r.red)}
          </TableCell>
        );
      case "estado": {
        const meta = metaEstado(r.estado);
        return (
          <TableCell key={id}>
            <span className="inline-flex items-center gap-2">
              <span className={`h-2 w-2 shrink-0 rounded-full ${meta.punto}`} aria-hidden />
              <span className={`text-sm ${meta.texto}`}>{meta.etiqueta}</span>
            </span>
          </TableCell>
        );
      }
      case "visualizaciones":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {r.visualizaciones == null ? "—" : numeroCompleto(r.visualizaciones)}
          </TableCell>
        );
      case "interacciones":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {r.interacciones == null ? "—" : numeroCompleto(r.interacciones)}
          </TableCell>
        );
      case "engagement_pct":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {r.engagement_pct == null ? "—" : porcentaje(r.engagement_pct)}
          </TableCell>
        );
      case "stories":
        return (
          <TableCell key={id} className="text-right tabular-nums">
            {r.stories == null ? "—" : numeroCompleto(r.stories)}
          </TableCell>
        );
      case "motivo":
        return (
          <TableCell key={id} className="pr-6 text-sm text-muted-foreground">
            {r.motivo ?? "—"}
          </TableCell>
        );
      default:
        return null;
    }
  };

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 px-6 pb-2">
        <h3 className="text-sm font-semibold text-foreground">{marca.marca}</h3>
        <span className="shrink-0 text-xs text-muted-foreground">{conteo(enFoco)}</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>{columnas.map(encabezado)}</TableRow>
        </TableHeader>
        <TableBody>
          {redes.map((r) => (
            <TableRow key={r.red}>{columnas.map((id) => celda(r, id))}</TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function CoberturaRedes({ marcas }: { marcas: MarcaCobertura[] }) {
  // Orden global (una sola elección del usuario aplicada a cada bloque de marca).
  const [orden, setOrden] = React.useState<{ clave: ClaveOrden | null; direccion: DireccionOrden }>(
    { clave: null, direccion: "desc" },
  );
  const { clave, direccion } = orden;
  const alClicar = React.useCallback((c: ClaveOrden) => {
    setOrden((prev) =>
      prev.clave === c
        ? { clave: c, direccion: prev.direccion === "asc" ? "desc" : "asc" }
        : // Columna nueva: arrancamos en descendente (lo natural para métricas).
          { clave: c, direccion: "desc" },
    );
  }, []);

  // El foco de red lo manda el selector GLOBAL; aquí solo queda el filtro propio por marca.
  const red = useVistaConfig((s) => s.red);
  const [marcaFiltro, setMarcaFiltro] = React.useState(TODAS);

  // Columnas visibles (orden + ocultas) del editor de campos de la sección.
  const cfgGuardada = useVistaConfig((s) => s.columnas[TABLA]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);
  // Si el orden activo apunta a una columna ya oculta, no se pinta su cabecera ordenable.
  const claveEfectiva = clave != null && esClaveOrden(clave) && columnas.includes(clave) ? clave : null;

  const marcasDisp = React.useMemo(
    () => (marcas ?? []).map((m) => ({ id: m.marca_id, nombre: m.marca })),
    [marcas],
  );

  if (!marcas || marcas.length === 0) {
    return null;
  }

  const marcasVisibles = marcas.filter(
    (m) => marcaFiltro === TODAS || m.marca_id === marcaFiltro,
  );

  const acciones = (
    <Select value={marcaFiltro} onValueChange={setMarcaFiltro}>
      <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por marca">
        <SelectValue placeholder="Marca" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={TODAS}>Todas las marcas</SelectItem>
        {marcasDisp.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.nombre}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <Seccion
      id="cobertura"
      titulo="Cobertura por red"
      icono={Radar}
      acciones={acciones}
      tablaId={TABLA}
      columnas={COLUMNAS}
      contentClassName="space-y-8 p-0 pb-2"
    >
      {marcasVisibles.map((m) => (
        <BloqueMarca
          key={m.marca_id}
          marca={m}
          red={red}
          columnas={columnas}
          clave={claveEfectiva}
          direccion={direccion}
          alClicar={alClicar}
        />
      ))}
    </Seccion>
  );
}
