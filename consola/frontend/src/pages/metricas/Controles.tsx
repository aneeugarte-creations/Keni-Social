/**
 * Controles del dashboard: selector de rango/tiempo y re-export del centinela
 * `MARCA_TODAS`.
 *
 * Métricas NO tiene selector de marca propio: la marca la manda SIEMPRE el switch
 * global de la barra superior (`useMarcaActiva`). Aquí solo vive el selector de
 * RANGO/tiempo (`SelectorRango` / `SelectorTiempo`), específico de Métricas, más
 * el re-export de `MARCA_TODAS` (el centinela de "todas las marcas" que varios
 * sub-componentes usan para acotar sus consultas).
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
      <SelectTrigger id={id} className="h-8 w-full text-xs sm:w-[200px]" aria-label={ariaLabel ?? "Periodo"}>
        <SelectValue placeholder="Periodo" />
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
 * Selector de tiempo del dashboard: periodos comunes (presets) · mes · fechas exactas.
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

  // Preset por defecto al volver a "Periodos comunes" (el valor actual si es preset, si no el 1º).
  const presetActual = modoDesdeToken(valor) === "atajos" ? valor : (rangos[0]?.id ?? "mes");

  const mesActual = partesMes(valor);
  const hoy = new Date();
  const anio = mesActual?.anio ?? hoy.getFullYear();
  const mes = mesActual?.mes ?? hoy.getMonth() + 1;

  const rangoActual = partesRango(valor);
  const [desde, setDesde] = React.useState(rangoActual?.desde ?? "");
  const [hasta, setHasta] = React.useState(rangoActual?.hasta ?? "");

  // `valor` puede cambiar DESDE FUERA (p. ej. el comparador re-deriva el periodo A/B
  // cuando cambia el periodo visible arriba). Sin esto, modo/desde/hasta solo nacían
  // del valor inicial y el selector mostraba un periodo que NO era el consultado.
  React.useEffect(() => {
    setModo(modoDesdeToken(valor));
    const r = partesRango(valor);
    setDesde(r?.desde ?? "");
    setHasta(r?.hasta ?? "");
  }, [valor]);

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
        <SelectTrigger className="h-8 w-full text-xs sm:w-[200px]" aria-label="Tipo de periodo">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="atajos">Periodos comunes</SelectItem>
          <SelectItem value="mes">Mes</SelectItem>
          <SelectItem value="personalizado">Fechas exactas</SelectItem>
        </SelectContent>
      </Select>

      {modo === "atajos" && (
        <SelectorRango rangos={rangos} valor={presetActual} onCambio={onCambio} />
      )}

      {modo === "mes" && (
        // En móvil los dos selects comparten la fila a partes iguales (grid); en `sm+`
        // vuelven a sus anchos naturales. Antes los 140px+100px fijos desbordaban la barra.
        <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto">
          <Select value={String(mes)} onValueChange={(m) => onCambio(tokenMes(anio, Number(m)))}>
            <SelectTrigger className="h-8 w-full text-xs sm:w-[140px]" aria-label="Mes">
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
            <SelectTrigger className="h-8 w-full text-xs sm:w-[100px]" aria-label="Año">
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
        // En móvil las dos fechas comparten la fila a partes iguales; el guion solo se
        // pinta en `sm+` (en estrecho no aporta y robaba sitio a los inputs de 150px).
        <div className="grid w-full grid-cols-2 items-center gap-2 sm:flex sm:w-auto">
          <Input
            type="date"
            value={desde}
            max={hasta || undefined}
            onChange={(e) => aplicarPersonalizado(e.target.value, hasta)}
            aria-label="Desde"
            className="h-8 w-full text-xs sm:w-[150px]"
          />
          <span className="hidden text-muted-foreground sm:inline">–</span>
          <Input
            type="date"
            value={hasta}
            min={desde || undefined}
            onChange={(e) => aplicarPersonalizado(desde, e.target.value)}
            aria-label="Hasta"
            className="h-8 w-full text-xs sm:w-[150px]"
          />
        </div>
      )}
    </div>
  );
}
