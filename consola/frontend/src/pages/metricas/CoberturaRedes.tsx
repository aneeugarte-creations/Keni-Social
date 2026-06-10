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
 * La sección es colapsable, filtra client-side por marca y por red, y ordena las
 * redes (por vistas / interacciones / engagement) con un orden global elegido por el
 * usuario que se aplica dentro de cada bloque de marca.
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
import { nombreRed, numeroCompleto, porcentaje } from "@/lib/formato";
import type { MarcaCobertura, RedCobertura } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { SeccionColapsable } from "./SeccionColapsable";
import type { DireccionOrden } from "./useOrdenTabla";

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
 * Resumen "3/5 con datos" para la cabecera de cada marca. Recibe SIEMPRE el universo
 * completo de redes de la marca (no la lista filtrada por el selector de red): el
 * conteo describe la cobertura real de la marca, no lo que la tabla muestra.
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

function FilaRed({ r }: { r: RedCobertura }) {
  const meta = metaEstado(r.estado);
  return (
    <TableRow>
      <TableCell className="pl-6 font-medium">{nombreRed(r.red)}</TableCell>
      <TableCell>
        <span className="inline-flex items-center gap-2">
          <span className={`h-2 w-2 shrink-0 rounded-full ${meta.punto}`} aria-hidden />
          <span className={`text-sm ${meta.texto}`}>{meta.etiqueta}</span>
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {r.visualizaciones == null ? "—" : numeroCompleto(r.visualizaciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {r.interacciones == null ? "—" : numeroCompleto(r.interacciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {r.engagement_pct == null ? "—" : porcentaje(r.engagement_pct)}
      </TableCell>
      <TableCell className="pr-6 text-sm text-muted-foreground">{r.motivo ?? "—"}</TableCell>
    </TableRow>
  );
}

function BloqueMarca({
  marca,
  redFiltro,
  clave,
  direccion,
  alClicar,
}: {
  marca: MarcaCobertura;
  redFiltro: string;
  clave: ClaveOrden | null;
  direccion: DireccionOrden;
  alClicar: (clave: ClaveOrden) => void;
}) {
  // Filtra por red dentro de la marca y luego aplica el orden global.
  const visibles = marca.redes.filter((r) => redFiltro === TODAS || r.red === redFiltro);
  const redes = ordenarRedes(visibles, clave, direccion);
  if (redes.length === 0) return null;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 px-6 pb-2">
        <h3 className="text-sm font-semibold text-foreground">{marca.marca}</h3>
        <span className="shrink-0 text-xs text-muted-foreground">{conteo(marca.redes)}</span>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-6">Red</TableHead>
            <TableHead>Estado</TableHead>
            <CabeceraOrdenable
              activa={clave === "visualizaciones"}
              direccion={direccion}
              onClick={() => alClicar("visualizaciones")}
              alinear="right"
            >
              Vistas
            </CabeceraOrdenable>
            <CabeceraOrdenable
              activa={clave === "interacciones"}
              direccion={direccion}
              onClick={() => alClicar("interacciones")}
              alinear="right"
            >
              Interacciones
            </CabeceraOrdenable>
            <CabeceraOrdenable
              activa={clave === "engagement_pct"}
              direccion={direccion}
              onClick={() => alClicar("engagement_pct")}
              alinear="right"
            >
              Engagement
            </CabeceraOrdenable>
            <TableHead className="pr-6">Motivo</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {redes.map((r) => (
            <FilaRed key={r.red} r={r} />
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

  // Filtros client-side por marca y por red, derivados del universo de marcas/redes.
  const [marcaFiltro, setMarcaFiltro] = React.useState(TODAS);
  const [redFiltro, setRedFiltro] = React.useState(TODAS);

  const marcasDisp = React.useMemo(
    () => (marcas ?? []).map((m) => ({ id: m.marca_id, nombre: m.marca })),
    [marcas],
  );
  const redesDisp = React.useMemo(
    () => Array.from(new Set((marcas ?? []).flatMap((m) => m.redes.map((r) => r.red)))),
    [marcas],
  );

  if (!marcas || marcas.length === 0) {
    return null;
  }

  const marcasVisibles = marcas.filter(
    (m) => marcaFiltro === TODAS || m.marca_id === marcaFiltro,
  );

  const acciones = (
    <>
      <Select value={redFiltro} onValueChange={setRedFiltro}>
        <SelectTrigger className="w-full sm:w-40" aria-label="Filtrar por red">
          <SelectValue placeholder="Red" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODAS}>Todas las redes</SelectItem>
          {redesDisp.map((r) => (
            <SelectItem key={r} value={r}>
              {nombreRed(r)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
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
    </>
  );

  return (
    <SeccionColapsable
      titulo="Cobertura por marca y red"
      icono={Radar}
      descripcion="Todas las redes de cada marca y por qué aportan (o no) datos en este periodo."
      acciones={acciones}
      contentClassName="space-y-8 p-0 pb-2"
    >
      {marcasVisibles.map((m) => (
        <BloqueMarca
          key={m.marca_id}
          marca={m}
          redFiltro={redFiltro}
          clave={clave}
          direccion={direccion}
          alClicar={alClicar}
        />
      ))}
    </SeccionColapsable>
  );
}
