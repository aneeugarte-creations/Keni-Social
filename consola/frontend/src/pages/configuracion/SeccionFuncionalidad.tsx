import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AjusteAdmin, RespuestaAjustes } from "@/types";

import { useSesion } from "@/hooks/sesion-contexto";

import { CLAVE_AJUSTES, GRUPOS_INVESTIGACION, GRUPOS_MAQUINA, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/** Una fila de ajuste: toggle (bool), número (int/float) o selector (select).
 *
 * `bloqueado` (solo bool): la fila se muestra APAGADA y deshabilitada porque otro control la
 * gobierna (p. ej. una excepción por marca cuyo maestro de etapa está OFF). `notaBloqueo` es la
 * etiqueta corta que explica por qué. No cambia el valor guardado: solo refleja que no aplica.
 *
 * Exportado: la página de detalle de un daemon (`AgenteDetalle`) reutiliza esta misma fila para
 * editar in-place los ajustes que gobiernan ese daemon (mismo control por tipo, misma UX). */
export function FilaAjuste({
  ajuste,
  onGuardar,
  guardando,
  bloqueado = false,
  notaBloqueo,
}: {
  ajuste: AjusteAdmin;
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  bloqueado?: boolean;
  notaBloqueo?: string;
}) {
  const [num, setNum] = React.useState(String(ajuste.valor));
  React.useEffect(() => {
    setNum(String(ajuste.valor));
  }, [ajuste.valor]);

  const cabecera = (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{ajuste.etiqueta}</span>
        {ajuste.peligroso && (
          <Badge variant="destructive" className="text-[10px]">
            Publica de verdad
          </Badge>
        )}
        {bloqueado && notaBloqueo && (
          <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            · {notaBloqueo}
          </span>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{ajuste.ayuda}</p>
    </div>
  );

  if (ajuste.tipo === "bool") {
    // Si está bloqueado por su maestro, se ve apagado pase lo que pase (el daemon no corre).
    const activo = bloqueado ? false : Boolean(ajuste.valor);
    const onToggle = async (valor: boolean) => {
      // Encender un flag PELIGROSO (publicación real) pide confirmación explícita.
      if (valor && ajuste.peligroso) {
        if (
          await confirmar({
            titulo: "Activar publicación real",
            mensaje: "Esto publicará realmente en las redes. ¿Estás seguro?",
            destructivo: true,
            textoConfirmar: "Sí, publicar de verdad",
          })
        )
          onGuardar({ clave: ajuste.clave, valor: true });
        return;
      }
      onGuardar({ clave: ajuste.clave, valor });
    };
    return (
      <div
        className={cn(
          "flex items-center justify-between gap-4 border-b border-border/50 py-3 last:border-0",
          bloqueado && "opacity-50",
        )}
      >
        {cabecera}
        <Switch
          checked={activo}
          onCheckedChange={(v) => void onToggle(v)}
          disabled={guardando || bloqueado}
          aria-label={ajuste.etiqueta}
        />
      </div>
    );
  }

  if (ajuste.tipo === "select") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 py-3 last:border-0 sm:gap-4">
        {cabecera}
        <Select
          value={String(ajuste.valor) || "_vacio"}
          onValueChange={(valor) =>
            onGuardar({ clave: ajuste.clave, valor: valor === "_vacio" ? "" : valor })
          }
          disabled={guardando}
        >
          <SelectTrigger className="w-[160px]" aria-label={ajuste.etiqueta}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(ajuste.opciones ?? []).map((o) => (
              <SelectItem key={o.id || "_vacio"} value={o.id || "_vacio"}>
                {o.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    );
  }

  // texto (p. ej. el plan editorial diario): se guarda al salir del campo si cambió.
  if (ajuste.tipo === "texto") {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 py-3 last:border-0 sm:gap-4">
        {cabecera}
        <Input
          type="text"
          value={num}
          placeholder="categoria:n, categoria:n…"
          onChange={(e) => setNum(e.target.value)}
          onBlur={() => {
            if (num !== String(ajuste.valor ?? "")) {
              onGuardar({ clave: ajuste.clave, valor: num.trim() });
            }
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          }}
          disabled={guardando}
          className="w-[260px] font-mono text-xs"
          aria-label={ajuste.etiqueta}
        />
      </div>
    );
  }

  // int / float: se guarda al salir del campo (blur) si cambió.
  const guardarNumero = () => {
    if (num !== String(ajuste.valor) && num.trim() !== "") {
      onGuardar({ clave: ajuste.clave, valor: Number(num) });
    }
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 py-3 last:border-0 sm:gap-4">
      {cabecera}
      <Input
        type="number"
        value={num}
        min={ajuste.min}
        max={ajuste.max}
        step={ajuste.tipo === "float" ? "0.1" : "1"}
        onChange={(e) => setNum(e.target.value)}
        onBlur={guardarNumero}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
        disabled={guardando}
        className="w-[120px] tabular-nums"
        aria-label={ajuste.etiqueta}
      />
    </div>
  );
}

/** Una excepción por marca: el conmutador de UNA etapa de UNA marca, con su etiqueta corta.
 *  `bloqueado` (el maestro global de esa etapa/publicación está OFF) lo muestra apagado y
 *  deshabilitado: la excepción no aplica hasta encender el maestro. */
function ConmutadorMarca({
  ajuste,
  etiqueta,
  onGuardar,
  guardando,
  bloqueado,
}: {
  ajuste: AjusteAdmin;
  /** Etiqueta corta del conmutador (la etapa); vacía cuando la marca tiene un único control. */
  etiqueta: string;
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  bloqueado: boolean;
}) {
  const activo = bloqueado ? false : Boolean(ajuste.valor);
  return (
    <label
      className={cn("flex items-center gap-2", bloqueado && "opacity-50")}
      title={bloqueado ? "El maestro de esta etapa está apagado: la excepción no aplica." : undefined}
    >
      {etiqueta && <span className="text-xs text-muted-foreground">{etiqueta}</span>}
      <Switch
        checked={activo}
        onCheckedChange={(v) => onGuardar({ clave: ajuste.clave, valor: v })}
        disabled={guardando || bloqueado}
        aria-label={ajuste.etiqueta}
      />
    </label>
  );
}

/** EXCEPCIONES POR MARCA — patrón ÚNICO de las desviaciones `::marca` en toda la consola: una
 *  fila por marca con sus conmutadores a la derecha (TODAS las marcas a la vista, sin pestañas).
 *  Sin tocar, cada marca SIGUE el valor global; encender/apagar aquí la DESVÍA. Sirve igual para
 *  las etapas (Generar/Arte, en el Monitor) que para la publicación real (en Programación).
 *
 *  Cada ajuste tiene clave `BASE::marca`; agrupamos por marca (orden de aparición). La etiqueta
 *  "Marca · Etapa" (Generar/Arte) da el nombre y la etiqueta corta del conmutador; si no trae
 *  " · " (publicación) es un único conmutador sin etiqueta. `maestros` mapea la clave BASE de cada
 *  ajuste (p. ej. `KENI_GENERAR`, `KENI_PUBLICAR_REAL`) a si su maestro global está ON: con el
 *  maestro OFF, la excepción se ve apagada y deshabilitada (consistente entre Generar/Arte y
 *  Publicación). */
export function ExcepcionesPorMarca({
  ajustes,
  onGuardar,
  guardando,
  maestros,
}: {
  ajustes: AjusteAdmin[];
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  maestros: Record<string, boolean>;
}) {
  const porMarca = React.useMemo(() => {
    const orden: string[] = [];
    const mapa = new Map<string, { nombre: string; controles: { ajuste: AjusteAdmin; etapa: string }[] }>();
    for (const a of ajustes) {
      const marcaId = a.clave.split("::")[1] ?? a.clave;
      const [nombre, etapa] = a.etiqueta.split(" · ");
      if (!mapa.has(marcaId)) {
        mapa.set(marcaId, { nombre: nombre || marcaId, controles: [] });
        orden.push(marcaId);
      }
      mapa.get(marcaId)!.controles.push({ ajuste: a, etapa: etapa ?? "" });
    }
    return orden.map((id) => ({ id, ...mapa.get(id)! }));
  }, [ajustes]);

  if (!porMarca.length) return null;
  return (
    <div>
      {porMarca.map((m) => (
        <div
          key={m.id}
          className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 border-b border-border/50 py-2.5 last:border-0"
        >
          <span className="text-sm font-medium">{m.nombre}</span>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
            {m.controles.map(({ ajuste, etapa }) => (
              <ConmutadorMarca
                key={ajuste.clave}
                ajuste={ajuste}
                etiqueta={etapa}
                onGuardar={onGuardar}
                guardando={guardando}
                bloqueado={maestros[ajuste.clave.split("::")[0]] === false}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Mutación ÚNICA de guardado de un ajuste, COMPARTIDA por Configuración y el Monitor (el
 *  panel de la máquina Y los toggles de daemons): una sola implementación del control.
 *
 *  Tras guardar: (1) parche optimista del ajuste devuelto, (2) INVALIDACIÓN del catálogo
 *  completo —los toggles por marca sin override heredan su valor del MAESTRO, así que cambiar
 *  un maestro cambia el valor efectivo de otras filas que el parche puntual no toca— y (3)
 *  invalidación de las vistas que DERIVAN de estos toggles (Pipelines pinta «saltada» por
 *  etapa/marca; el Monitor pinta el estado de los daemons), para que el cambio se vea al
 *  instante sin esperar su polling ni recargar. */
export function useGuardarAjuste() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cuerpo: { clave: string; valor?: boolean | number | string }) =>
      api.guardarAjuste(cuerpo),
    onSuccess: (res) => {
      // Sustituye el ajuste en la caché (respuesta inmediata, sin parpadeo)…
      queryClient.setQueryData<RespuestaAjustes>(CLAVE_AJUSTES, (prev) =>
        prev
          ? {
              grupos: prev.grupos.map((g) => ({
                ...g,
                ajustes: g.ajustes.map((a) => (a.clave === res.ajuste.clave ? res.ajuste : a)),
              })),
            }
          : prev,
      );
      // …y re-lee la verdad del backend: el resto de filas dependientes (defectos por marca
      // que siguen al maestro) y las vistas derivadas (Pipelines, daemons del Monitor).
      void queryClient.invalidateQueries({ queryKey: CLAVE_AJUSTES });
      void queryClient.invalidateQueries({ queryKey: ["pipelines"] });
      void queryClient.invalidateQueries({ queryKey: ["actividad", "cola"] });
      toast.success(`«${res.ajuste.etiqueta}» actualizado.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
}

/** Query de ajustes + la mutación compartida de guardado (Configuración y panel de máquina). */
function useAjustesAdmin() {
  const query = useQuery({
    queryKey: CLAVE_AJUSTES,
    queryFn: ({ signal }) => api.ajustes(signal),
  });
  const guardar = useGuardarAjuste();
  return { ...query, guardar };
}

/** Render del mapa de grupos de ajustes con su casuística por grupo (maestros de etapa, excepciones
 *  por marca, publicación, automatismos, topes…). `grupos` ya viene FILTRADO por el contenedor
 *  (Configuración pinta lo global; el Monitor pinta la máquina de contenido). */
function GruposAjustes({
  grupos,
  onGuardar,
  guardando,
  mostrarTitulos = true,
  gruposMaestros,
}: {
  grupos: RespuestaAjustes["grupos"];
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  /** Pinta el título de cada grupo como sub-cabecera. Se apaga cuando el área envuelve UN solo
   *  grupo: la cabecera de la sección ya lo nombra y repetirlo sobra. */
  mostrarTitulos?: boolean;
  /** De dónde leer los MAESTROS de etapa para atenuar excepciones. Por defecto, de los propios
   *  `grupos`; el Monitor lo pasa aparte porque sus maestros se pintan en la tira del pipeline
   *  (fuera de este render) y aun así gobiernan las excepciones por marca del drawer. */
  gruposMaestros?: RespuestaAjustes["grupos"];
}) {
  // Maestros (Investigación/Producción/Arte) por su clave ENV -> bool. Atenúa las excepciones
  // por marca cuyo maestro está OFF.
  const maestros: Record<string, boolean> = {};
  for (const gid of ["maestros_investigacion", "maestros_produccion"])
    for (const m of (gruposMaestros ?? grupos).find((g) => g.id === gid)?.ajustes ?? [])
      maestros[m.clave] = Boolean(m.valor);

  // Sub-cabecera de grupo (uppercase fino). Se omite cuando el área tiene un solo grupo: la
  // cabecera de la sección colapsable ya lo nombra. NO crea ninguna caja: solo una etiqueta.
  const subtitulo = (texto: string) =>
    mostrarTitulos ? (
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {texto}
      </h4>
    ) : null;

  return (
    <div className="space-y-5">
      {grupos.map((grupo) => {
        const filas = grupo.ajustes.map((ajuste) => (
          <FilaAjuste key={ajuste.clave} ajuste={ajuste} onGuardar={onGuardar} guardando={guardando} />
        ));

        // Excepciones por marca (Generar/Arte): patrón único `ExcepcionesPorMarca` (fila por marca,
        // todas a la vista). Sin tocar, cada marca sigue el maestro global de la etapa.
        if (grupo.id.startsWith("automatizacion_marca")) {
          return (
            <div key={grupo.id} className="space-y-1.5">
              {subtitulo(grupo.titulo)}
              <p className="text-xs text-muted-foreground">
                Sin tocar, cada marca sigue el global. Apágala para desviarse.
              </p>
              <ExcepcionesPorMarca
                ajustes={grupo.ajustes}
                onGuardar={onGuardar}
                guardando={guardando}
                maestros={maestros}
              />
            </div>
          );
        }

        // Publicación: el maestro del paso final (postea de verdad). Mismo patrón maestro+excepción
        // (el maestro autoriza el posteo real global; debajo, las excepciones por marca lo restan).
        // Su peligrosidad la señala el acento ámbar de la SECCIÓN y el badge «Publica de verdad» de
        // la fila: una franja a la izquierda, NO una caja anidada. `publicacion_marca` se pinta aquí.
        if (grupo.id === "pieza") {
          const maestroPub = grupo.ajustes[0];
          const maestroPubOn = Boolean(maestroPub?.valor);
          const exMarca = grupos.find((g) => g.id === "publicacion_marca")?.ajustes ?? [];
          // Mismo patrón que las etapas: el maestro de publicación es el «master» de estas
          // excepciones (clave BASE = `KENI_PUBLICAR_REAL`), así que con él apagado se ven
          // apagadas/deshabilitadas igual que Generar/Arte.
          const maestrosPub = maestroPub ? { [maestroPub.clave]: maestroPubOn } : {};
          return (
            <div key={grupo.id} className="space-y-3 border-l-2 border-[hsl(var(--aviso-borde))] pl-3">
              <div>{filas}</div>
              {exMarca.length > 0 && (
                <div className="space-y-1.5">
                  <h4 className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Excepciones por marca
                  </h4>
                  <p className="text-xs text-muted-foreground">
                    Apágala para no publicar aunque el maestro sí publique.
                  </p>
                  <ExcepcionesPorMarca
                    ajustes={exMarca}
                    onGuardar={onGuardar}
                    guardando={guardando}
                    maestros={maestrosPub}
                  />
                </div>
              )}
            </div>
          );
        }
        // Las excepciones de publicación se pintan dentro del bloque «pieza» de arriba.
        if (grupo.id === "publicacion_marca") return null;

        // Resto (maestros de etapa, automatismos, topes, noticias, técnico, tuning…): sub-cabecera
        // (si procede) + lista plana de filas. SIN cajas ni colapsables anidados: capa base.
        return (
          <div key={grupo.id} className="space-y-1">
            {subtitulo(grupo.titulo)}
            <div>{filas}</div>
          </div>
        );
      })}
    </div>
  );
}

/** Estados de carga/error compartidos del panel de ajustes. */
function EstadoAjustes({
  isError,
  error,
  refetch,
  isFetching,
}: {
  isError: boolean;
  error: unknown;
  refetch: () => void;
  isFetching: boolean;
}) {
  if (isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar los ajustes"
        mensaje={mensajeError(error)}
        onReintentar={() => void refetch()}
        cargando={isFetching}
      />
    );
  }
  return (
    <div className="space-y-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}

/** Área (sección colapsable de CAPA BASE) con uno o varios grupos del catálogo, para montar EN
 * LA PÁGINA A LA QUE AFECTA (reparto contextual: el motor de noticias en Noticias, la publicación
 * en Programación, el sistema en el Monitor…). `grupos` es una lista ORDENADA de ids: se pintan
 * en ese orden y, si hay más de uno, cada uno lleva su sub-cabecera. Se AUTO-GUARDA por rol: si la
 * sesión no es admin no monta nada (el endpoint /api/ajustes exige admin). Mismo motor y misma
 * mutación en caliente en todas las páginas. */
export function PanelAjustes({
  grupos: ids,
  titulo,
  descripcion,
  abiertaInicial = false,
  acento,
}: {
  /** Ids de grupo del catálogo, EN EL ORDEN en que se quieren pintar dentro de la sección. */
  grupos: readonly string[];
  titulo: string;
  descripcion?: React.ReactNode;
  abiertaInicial?: boolean;
  acento?: "amber";
}) {
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  const { data, isPending, isError, error, refetch, isFetching, guardar } = useAjustesAdmin();
  if (!esAdmin) return null;
  const orden = new Map(ids.map((id, i) => [id, i]));
  const grupos = (data?.grupos ?? [])
    .filter((g) => orden.has(g.id))
    .sort((a, b) => orden.get(a.id)! - orden.get(b.id)!);
  if (!isPending && !isError && grupos.length === 0) return null;
  return (
    <SeccionColapsable
      titulo={titulo}
      abiertaInicial={abiertaInicial}
      descripcion={descripcion}
      acento={acento}
    >
      {isPending || isError ? (
        <EstadoAjustes isError={isError} error={error} refetch={refetch} isFetching={isFetching} />
      ) : (
        <GruposAjustes
          grupos={grupos}
          onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
          guardando={guardar.isPending}
          mostrarTitulos={ids.length > 1}
        />
      )}
    </SeccionColapsable>
  );
}

/** Sección «Investigación» del drawer del MONITOR (Fase 3: UN solo sitio para los ajustes de la
 * máquina): el motor de noticias completo (entrada al pool, rendimiento, producción automática
 * y técnico), antes en el menú ⋮ de Noticias. Ni el MAESTRO «Investigación» ni las EXCEPCIONES
 * por marca se pintan aquí: los switches de etapa (Selección/Validación) viven en la tira
 * «Pipeline en vivo» del propio Monitor y las excepciones por marca, en el diálogo de cada
 * etapa de esa tira (sin duplicar el control). Mismo motor (`/api/ajustes`); aplican en
 * caliente. */
export function PanelInvestigacion() {
  const { data, isPending, isError, error, refetch, isFetching, guardar } = useAjustesAdmin();
  const orden = new Map<string, number>(GRUPOS_INVESTIGACION.map((id, i) => [id, i]));
  const grupos = (data?.grupos ?? [])
    .filter(
      (g) =>
        orden.has(g.id) &&
        g.id !== "maestros_investigacion" &&
        g.id !== "automatizacion_marca_investigacion",
    )
    .sort((a, b) => orden.get(a.id)! - orden.get(b.id)!);

  return (
    <SeccionColapsable
      titulo="Investigación"
      descripcion={
        <>
          El motor de noticias (entrada, rendimiento, producción automática). Los switches de
          etapa y sus excepciones por marca están en la tira «Pipeline en vivo». Los cambios
          aplican <strong>en caliente</strong>.
        </>
      }
    >
      {isPending || isError ? (
        <EstadoAjustes isError={isError} error={error} refetch={refetch} isFetching={isFetching} />
      ) : (
        <GruposAjustes
          grupos={grupos}
          onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
          guardando={guardar.isPending}
        />
      )}
    </SeccionColapsable>
  );
}

/** Controles de la MÁQUINA DE CONTENIDO, para el drawer del MONITOR: la admisión del flujo
 * continuo y la economía de tokens (`pipeline_topes`). El interruptor general «Máquina»
 * (`maquina_global`) vive en la cabecera de la tira «Pipeline en vivo»; los maestros de etapa
 * (`maestros_produccion`), en la propia tira; y las excepciones por marca, en el diálogo de
 * cada etapa (sin duplicar el control aquí). Mismo motor que Configuración (`/api/ajustes`);
 * aplican en caliente. */
export function PanelMaquinaPublicacion() {
  const { data, isPending, isError, error, refetch, isFetching, guardar } = useAjustesAdmin();
  const grupos = (data?.grupos ?? []).filter(
    (g) =>
      GRUPOS_MAQUINA.has(g.id) &&
      g.id !== "maquina_global" &&
      g.id !== "maestros_produccion" &&
      g.id !== "automatizacion_marca_produccion",
  );

  return (
    <SeccionColapsable
      titulo="Máquina de contenido"
      abiertaInicial
      descripcion={
        <>
          Admisión del flujo y economía de tokens. El maestro «Máquina», los switches de etapa y
          sus excepciones por marca están en la tira «Pipeline en vivo». Los cambios aplican{" "}
          <strong>en caliente</strong>.
        </>
      }
    >
      {isPending || isError ? (
        <EstadoAjustes isError={isError} error={error} refetch={refetch} isFetching={isFetching} />
      ) : (
        <GruposAjustes
          grupos={grupos}
          onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
          guardando={guardar.isPending}
        />
      )}
    </SeccionColapsable>
  );
}
