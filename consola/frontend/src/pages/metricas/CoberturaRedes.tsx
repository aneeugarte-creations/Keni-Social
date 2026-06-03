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
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

/** Metadatos de presentación por estado de cobertura (etiqueta + color del punto). */
const ESTADO: Record<string, { etiqueta: string; texto: string; punto: string }> = {
  con_datos: {
    etiqueta: "Con datos",
    texto: "text-emerald-700 dark:text-emerald-400",
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
    texto: "text-rose-700 dark:text-rose-400",
    punto: "bg-rose-500",
  },
  no_configurada: {
    etiqueta: "No configurada",
    texto: "text-muted-foreground",
    punto: "bg-muted-foreground/40",
  },
  sin_credenciales: {
    etiqueta: "Sin credenciales",
    texto: "text-rose-700 dark:text-rose-400",
    punto: "bg-rose-500",
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

/** Resumen "3/5 con datos" para la cabecera de cada marca. */
function conteo(redes: RedCobertura[]): string {
  const con = redes.filter((r) => r.estado === "con_datos").length;
  return `${con}/${redes.length} con datos`;
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

export function CoberturaRedes({ marcas }: { marcas: MarcaCobertura[] }) {
  if (!marcas || marcas.length === 0) {
    return null;
  }
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Cobertura por marca y red</CardTitle>
        <p className="text-sm text-muted-foreground">
          Todas las redes de cada marca y por qué aportan (o no) datos en este rango.
        </p>
      </CardHeader>
      <CardContent className="space-y-8 p-0 pb-2">
        {marcas.map((m) => (
          <div key={m.marca_id}>
            <div className="flex items-baseline justify-between gap-3 px-6 pb-2">
              <h3 className="text-sm font-semibold text-foreground">{m.marca}</h3>
              <span className="shrink-0 text-xs text-muted-foreground">{conteo(m.redes)}</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Red</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Vistas</TableHead>
                  <TableHead className="text-right">Interacciones</TableHead>
                  <TableHead className="text-right">Engagement</TableHead>
                  <TableHead className="pr-6">Motivo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {m.redes.map((r) => (
                  <FilaRed key={r.red} r={r} />
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
