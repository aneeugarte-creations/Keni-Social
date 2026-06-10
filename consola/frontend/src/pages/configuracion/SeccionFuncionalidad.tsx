import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { AjusteAdmin, RespuestaAjustes } from "@/types";

import { useSesion } from "@/hooks/sesion-contexto";

import { CLAVE_AJUSTES, GRUPOS_MAQUINA, mensajeError } from "./lib";
import { TarjetaColapsable } from "./TarjetaColapsable";

/** Una fila de ajuste: toggle (bool), número (int/float) o selector (select).
 *
 * `bloqueado` (solo bool): la fila se muestra APAGADA y deshabilitada porque otro control la
 * gobierna (p. ej. una excepción por marca cuyo maestro de etapa está OFF). `notaBloqueo` es la
 * etiqueta corta que explica por qué. No cambia el valor guardado: solo refleja que no aplica. */
function FilaAjuste({
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
  const [confirmar, setConfirmar] = React.useState(false);
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
    const onToggle = (valor: boolean) => {
      // Encender un flag PELIGROSO (publicación real) pide confirmación explícita.
      if (valor && ajuste.peligroso) {
        setConfirmar(true);
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
          onCheckedChange={onToggle}
          disabled={guardando || bloqueado}
          aria-label={ajuste.etiqueta}
        />
        <Dialog open={confirmar} onOpenChange={setConfirmar}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Activar publicación real</DialogTitle>
              <DialogDescription>
                «{ajuste.etiqueta}» hará que las piezas aprobadas y programadas se publiquen DE
                VERDAD en las redes (vía Metricool). Asegúrate de que es lo que quieres.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirmar(false)}>
                Cancelar
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  onGuardar({ clave: ajuste.clave, valor: true });
                  setConfirmar(false);
                }}
              >
                Sí, publicar de verdad
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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

/** Toggles de generación por MARCA (copy + arte), en una pestaña por marca (en vez de lista plana).
 *
 * Cada ajuste del grupo "Automatización por marca" tiene clave `ENV::marca` y etiqueta
 * "Nombre · Etapa"; agrupamos por marca (orden de aparición) y, dentro de su pestaña, la fila
 * muestra solo la ETAPA (el nombre ya lo da la pestaña). Reutiliza `FilaAjuste`. */
function AjustesPorMarca({
  ajustes,
  onGuardar,
  guardando,
  maestros,
}: {
  ajustes: AjusteAdmin[];
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
  /** Valor de cada maestro de etapa por su clave ENV (p. ej. `KENI_PIPELINE`). Si el maestro de
   *  la etapa está OFF, su excepción por marca se OCULTA (no se gestiona hasta encender la etapa). */
  maestros: Record<string, boolean>;
}) {
  const porMarca = React.useMemo(() => {
    const orden: string[] = [];
    const mapa = new Map<string, { nombre: string; ajustes: AjusteAdmin[] }>();
    for (const a of ajustes) {
      const marcaId = a.clave.split("::")[1] ?? a.clave;
      const [nombre, etapa] = a.etiqueta.split(" · ");
      if (!mapa.has(marcaId)) {
        mapa.set(marcaId, { nombre: nombre || marcaId, ajustes: [] });
        orden.push(marcaId);
      }
      // En la pestaña de la marca, la fila muestra solo la etapa (no repite el nombre).
      mapa.get(marcaId)!.ajustes.push({ ...a, etiqueta: etapa || a.etiqueta });
    }
    return orden.map((id) => ({ id, ...mapa.get(id)! }));
  }, [ajustes]);

  const { marcaActiva } = useMarcaActiva();
  const [activa, setActiva] = React.useState(
    (marcaActiva && porMarca.some((m) => m.id === marcaActiva) ? marcaActiva : porMarca[0]?.id) ?? "",
  );
  React.useEffect(() => {
    if (porMarca.length && !porMarca.some((m) => m.id === activa)) {
      setActiva(
        marcaActiva && porMarca.some((m) => m.id === marcaActiva) ? marcaActiva : porMarca[0].id,
      );
    }
  }, [porMarca, activa, marcaActiva]);

  if (!porMarca.length) return null;
  return (
    <Tabs value={activa} onValueChange={setActiva} className="mt-1">
      <TabsList className="flex-wrap">
        {porMarca.map((m) => (
          <TabsTrigger key={m.id} value={m.id}>
            {m.nombre}
          </TabsTrigger>
        ))}
      </TabsList>
      {porMarca.map((m) => {
        // Etapa = clave ENV antes de "::". Solo gestionamos excepciones de etapas ENCENDIDAS:
        // con el maestro OFF la excepción no aplica, así que ocultamos la fila (no la atenuamos).
        const visibles = m.ajustes.filter((a) => maestros[a.clave.split("::")[0]] !== false);
        return (
          <TabsContent key={m.id} value={m.id}>
            {visibles.length > 0 ? (
              visibles.map((a) => (
                <FilaAjuste key={a.clave} ajuste={a} onGuardar={onGuardar} guardando={guardando} />
              ))
            ) : (
              <p className="py-3 text-xs text-muted-foreground">
                Enciende el maestro de la etapa para gestionar excepciones por marca.
              </p>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
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
}: {
  grupos: RespuestaAjustes["grupos"];
  onGuardar: (cuerpo: { clave: string; valor?: boolean | number | string }) => void;
  guardando: boolean;
}) {
  // Maestros de etapa por su clave ENV -> bool. Atenúa las excepciones por marca cuyo maestro está OFF.
  const maestros: Record<string, boolean> = {};
  for (const m of grupos.find((g) => g.id === "maestros_etapa")?.ajustes ?? [])
    maestros[m.clave] = Boolean(m.valor);

  return (
    <>
      {grupos.map((grupo) => {
        const filas = grupo.ajustes.map((ajuste) => (
          <FilaAjuste key={ajuste.clave} ajuste={ajuste} onGuardar={onGuardar} guardando={guardando} />
        ));

        // Maestros de etapa (Fusión/Ranking/Selección/Validación/Copy/Arte IA): título + filas.
        if (grupo.id === "maestros_etapa") {
          return (
            <div key={grupo.id} className="space-y-1">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {grupo.titulo}
              </h4>
              <div>{filas}</div>
            </div>
          );
        }

        // Excepciones por marca: una pestaña por marca; atenuadas si su maestro está OFF.
        if (grupo.id === "automatizacion_marca") {
          return (
            <div key={grupo.id} className="space-y-1">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {grupo.titulo}
              </h4>
              <AjustesPorMarca
                ajustes={grupo.ajustes}
                onGuardar={onGuardar}
                guardando={guardando}
                maestros={maestros}
              />
            </div>
          );
        }

        // Publicación: el mega-maestro del paso final (postea de verdad), en su BLOQUE PROPIO
        // destacado (acento ámbar) por ser el más peligroso. Mismo patrón maestro+excepción:
        // el maestro autoriza el posteo real global; debajo, las excepciones por marca lo
        // restan (apagan una marca -> dry-run). El grupo `publicacion_marca` se pinta AQUÍ.
        if (grupo.id === "publicacion") {
          const maestroPub = grupo.ajustes[0];
          const maestroPubOn = Boolean(maestroPub?.valor);
          const exMarca = grupos.find((g) => g.id === "publicacion_marca")?.ajustes ?? [];
          return (
            <div
              key={grupo.id}
              className="space-y-2 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3"
            >
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                  {grupo.titulo} · publica de verdad
                </h4>
                <p className="text-xs text-muted-foreground">
                  Autoriza el posteo <strong>REAL</strong> a Metricool.
                </p>
              </div>
              <div>{filas}</div>
              {exMarca.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Excepciones por marca
                  </p>
                  <div>
                    {exMarca.map((a) => (
                      <FilaAjuste
                        key={a.clave}
                        ajuste={a}
                        onGuardar={onGuardar}
                        guardando={guardando}
                        bloqueado={!maestroPubOn}
                        notaBloqueo="maestro apagado"
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        }
        // Las excepciones de publicación se pintan dentro del bloque «publicacion» de arriba.
        if (grupo.id === "publicacion_marca") return null;

        // Automatismos generales: barridos del sistema; van en un colapsible para no confundir
        // con los controles de las etapas de la máquina de arriba.
        if (grupo.id === "automatismos_generales") {
          return (
            <TarjetaColapsable
              key={grupo.id}
              titulo={grupo.titulo}
              descripcion="Barridos del sistema sin dimensión por marca (radar, alertas, vencimientos, limpieza…)."
            >
              <div>{filas}</div>
            </TarjetaColapsable>
          );
        }

        // Cupos de producción por marca: overrides del cupo global. Colapsado: solo se tocan
        // al calibrar una marca a su cadencia real de publicación.
        if (grupo.id === "noticias_produccion_marca") {
          return (
            <TarjetaColapsable
              key={grupo.id}
              titulo={grupo.titulo}
              descripcion="Ajusta el volumen auto-producido de cada marca a su ritmo real de publicación. Sin tocar, cada marca usa el cupo global."
            >
              <div>{filas}</div>
            </TarjetaColapsable>
          );
        }

        // Técnico del motor de noticias: capacidad y ritmo. Colapsado para que la subpágina de
        // Noticias muestre solo lo editorial; los defectos van bien salvo problema de carga/coste.
        if (grupo.id === "noticias_tecnico") {
          return (
            <TarjetaColapsable
              key={grupo.id}
              titulo={grupo.titulo}
              descripcion="Cuánto trabajo hace el motor en cada ronda. Los valores por defecto van bien; tócalos solo si el motor se queda corto o gasta de más."
            >
              <div>{filas}</div>
            </TarjetaColapsable>
          );
        }

        // Resto (interruptor general, topes, ajustes finos): título + lista plana.
        return (
          <div key={grupo.id} className="space-y-1">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {grupo.titulo}
            </h4>
            <div>{filas}</div>
          </div>
        );
      })}
    </>
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

/** Panel GENÉRICO de ajustes del catálogo para montar EN LA PÁGINA A LA QUE AFECTAN
 * (reparto contextual: el motor de noticias en Noticias, la publicación en Programación,
 * el sistema en el Monitor…). Filtra los grupos del catálogo por id y se AUTO-GUARDA por
 * rol: si la sesión no es admin no monta nada (el endpoint /api/ajustes exige admin).
 * Mismo motor y misma mutación en caliente en todas las páginas. */
export function PanelAjustes({
  ids,
  titulo,
  descripcion,
  abiertaInicial = false,
}: {
  ids: ReadonlySet<string>;
  titulo: string;
  descripcion?: React.ReactNode;
  abiertaInicial?: boolean;
}) {
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  const { data, isPending, isError, error, refetch, isFetching, guardar } = useAjustesAdmin();
  if (!esAdmin) return null;
  const grupos = (data?.grupos ?? []).filter((g) => ids.has(g.id));
  if (!isPending && !isError && grupos.length === 0) return null;
  return (
    <TarjetaColapsable
      titulo={titulo}
      abiertaInicial={abiertaInicial}
      contentClassName="space-y-6 pt-0"
      descripcion={descripcion}
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
    </TarjetaColapsable>
  );
}

/** Secciones de ajustes A PÁGINA COMPLETA (sin tarjeta colapsable), para subpáginas dedicadas
 * (p. ej. «Ajustes del motor de noticias» del hub Investigación). Cada grupo del catálogo se
 * pinta como una sección con su título; mismo catálogo, query y mutación que `PanelAjustes`.
 * Solo admin: para el resto avisa en vez de desaparecer (la subpágina no debe quedar en blanco). */
export function SeccionesAjustes({ ids }: { ids: ReadonlySet<string> }) {
  const { usuario } = useSesion();
  const esAdmin = usuario === null || usuario.rol === "admin";
  const { data, isPending, isError, error, refetch, isFetching, guardar } = useAjustesAdmin();
  if (!esAdmin)
    return (
      <p className="text-sm text-muted-foreground">
        Estos ajustes solo los puede ver y editar un administrador.
      </p>
    );
  if (isPending || isError)
    return (
      <EstadoAjustes isError={isError} error={error} refetch={refetch} isFetching={isFetching} />
    );
  const grupos = (data?.grupos ?? []).filter((g) => ids.has(g.id));
  return (
    <div className="space-y-6">
      <GruposAjustes
        grupos={grupos}
        onGuardar={(cuerpo) => guardar.mutate(cuerpo)}
        guardando={guardar.isPending}
      />
    </div>
  );
}

/** Controles de la MÁQUINA DE CONTENIDO, para el MONITOR (junto a la cola que gobiernan): el
 * interruptor general, las etapas (Selección→Validación→Copy→Arte), sus excepciones por marca y la
 * admisión del flujo continuo. Mismo motor que Configuración (`/api/ajustes`); aplican en caliente. */
export function PanelMaquinaContenido() {
  const { data, isPending, isError, error, refetch, isFetching, guardar } = useAjustesAdmin();
  const grupos = (data?.grupos ?? []).filter((g) => GRUPOS_MAQUINA.has(g.id));

  return (
    <TarjetaColapsable
      titulo="Máquina de contenido"
      abiertaInicial
      contentClassName="space-y-6 pt-0"
      descripcion={
        <>
          Enciende/apaga las etapas (Selección→Validación→Copy→Arte), por marca, y regula la
          admisión del flujo continuo: solo entra lo que cabe en vuelo (in=out). Aplican{" "}
          <strong>en caliente</strong> (hasta ~1 minuto).
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
    </TarjetaColapsable>
  );
}
