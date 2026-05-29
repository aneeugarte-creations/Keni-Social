/**
 * Controles del dashboard: selector de rango y re-export del selector de marca
 * compartido.
 *
 * El selector de marca vive ahora en `@/components/comunes/SelectorMarca`
 * (un único componente y un único centinela `MARCA_TODAS`). Aquí se re-exporta
 * para no cambiar los imports de Métricas / Comparar periodos. `SelectorRango`
 * es específico de Métricas y se mantiene local.
 */
import * as React from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { RangoMetrica } from "@/types";

import {
  type ModoTiempo,
  modoDesdeToken,
  partesMes,
  partesRango,
  tokenMes,
  tokenRango,
} from "./rango";

export { SelectorMarca } from "@/components/comunes/SelectorMarca";
export { MARCA_TODAS } from "@/components/comunes/selectores";

interface SelectorRangoProps {
  rangos: RangoMetrica[];
  valor: string;
  onCambio: (valor: string) => void;
  id?: string;
  ariaLabel?: string;
}

export function SelectorRango({ rangos, valor, onCambio, id, ariaLabel }: SelectorRangoProps) {
  return (
    <Select value={valor} onValueChange={onCambio}>
      <SelectTrigger id={id} className="w-full sm:w-[200px]" aria-label={ariaLabel ?? "Rango"}>
        <SelectValue placeholder="Rango" />
      </SelectTrigger>
      <SelectContent>
        {rangos.map((r) => (
          <SelectItem key={r.id} value={r.id}>
            {r.etiqueta}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// Meses en es-MX para el selector de "mes concreto".
const MESES_ES = [
  "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
  "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
];

/** Años elegibles en el selector de mes: el actual y los 3 anteriores. */
function aniosRecientes(): number[] {
  const actual = new Date().getFullYear();
  return [0, 1, 2, 3].map((d) => actual - d);
}

/**
 * Selector de tiempo del dashboard: presets (atajos) · mes concreto · personalizado.
 *
 * Emite un "token de rango" (`mes:AAAA-MM` / `rango:AAAA-MM-DD_AAAA-MM-DD` / preset)
 * que viaja al backend sin tocar la capa de datos. Mantiene `SelectorRango` (presets)
 * intacto para la comparativa de periodos. Minimalista: una fila, un control por modo.
 */
export function SelectorTiempo({
  rangos,
  valor,
  onCambio,
}: {
  rangos: RangoMetrica[];
  valor: string;
  onCambio: (token: string) => void;
}) {
  const [modo, setModo] = React.useState<ModoTiempo>(() => modoDesdeToken(valor));

  // Preset por defecto al volver a "Atajos" (el valor actual si es preset, si no el 1º).
  const presetActual = modoDesdeToken(valor) === "atajos" ? valor : (rangos[0]?.id ?? "mes");

  const mesActual = partesMes(valor);
  const hoy = new Date();
  const anio = mesActual?.anio ?? hoy.getFullYear();
  const mes = mesActual?.mes ?? hoy.getMonth() + 1;

  const rangoActual = partesRango(valor);
  const [desde, setDesde] = React.useState(rangoActual?.desde ?? "");
  const [hasta, setHasta] = React.useState(rangoActual?.hasta ?? "");

  function cambiarModo(nuevo: ModoTiempo) {
    setModo(nuevo);
    // Al cambiar de modo, emite un token coherente con el nuevo modo de inmediato.
    if (nuevo === "atajos") onCambio(presetActual);
    else if (nuevo === "mes") onCambio(tokenMes(anio, mes));
    else if (desde && hasta) onCambio(tokenRango(desde, hasta));
  }

  function aplicarPersonalizado(d: string, h: string) {
    setDesde(d);
    setHasta(h);
    if (d && h && d <= h) onCambio(tokenRango(d, h));
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Select value={modo} onValueChange={(v) => cambiarModo(v as ModoTiempo)}>
        <SelectTrigger className="w-full sm:w-[140px]" aria-label="Modo de tiempo">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="atajos">Atajos</SelectItem>
          <SelectItem value="mes">Mes concreto</SelectItem>
          <SelectItem value="personalizado">Personalizado</SelectItem>
        </SelectContent>
      </Select>

      {modo === "atajos" && (
        <SelectorRango rangos={rangos} valor={presetActual} onCambio={onCambio} />
      )}

      {modo === "mes" && (
        <div className="flex gap-2">
          <Select value={String(mes)} onValueChange={(m) => onCambio(tokenMes(anio, Number(m)))}>
            <SelectTrigger className="w-[140px]" aria-label="Mes">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MESES_ES.map((nombre, i) => (
                <SelectItem key={nombre} value={String(i + 1)}>
                  {nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={String(anio)} onValueChange={(a) => onCambio(tokenMes(Number(a), mes))}>
            <SelectTrigger className="w-[100px]" aria-label="Año">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {aniosRecientes().map((a) => (
                <SelectItem key={a} value={String(a)}>
                  {a}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {modo === "personalizado" && (
        <div className="flex items-center gap-2">
          <Input
            type="date"
            value={desde}
            max={hasta || undefined}
            onChange={(e) => aplicarPersonalizado(e.target.value, hasta)}
            aria-label="Desde"
            className="w-[150px]"
          />
          <span className="text-muted-foreground">–</span>
          <Input
            type="date"
            value={hasta}
            min={desde || undefined}
            onChange={(e) => aplicarPersonalizado(desde, e.target.value)}
            aria-label="Hasta"
            className="w-[150px]"
          />
        </div>
      )}
    </div>
  );
}
