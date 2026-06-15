import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Info,
  Loader2,
  Plus,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { iconoPlataforma, nombrePlataforma, PLATAFORMAS_POSTPROXY } from "@/pages/marcas/plataformas";
import type { CanalPublicacion, MarcaPostproxy } from "@/types";

import { CLAVE_POSTPROXY, mensajeError } from "./lib";
import { SeccionColapsable } from "./SeccionColapsable";

/** Una opción del selector segmentado de canal. */
const CANALES: { id: CanalPublicacion; etiqueta: string }[] = [
  { id: "metricool", etiqueta: "Metricool" },
  { id: "postproxy", etiqueta: "Postproxy" },
];

/**
 * Control segmentado «Publicar por: ( Metricool | Postproxy )». La opción Postproxy
 * se deshabilita (con tooltip) hasta que la marca tenga su grupo de perfiles, para
 * no fijar un canal sin redes conectadas.
 */
function SelectorCanal({
  canal,
  postproxyDisponible,
  deshabilitado,
  onCambiar,
}: {
  canal: CanalPublicacion;
  postproxyDisponible: boolean;
  deshabilitado: boolean;
  onCambiar: (canal: CanalPublicacion) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Publicar por:</span>
      <div className="inline-flex rounded-md border border-border p-0.5">
        {CANALES.map((opcion) => {
          const activo = canal === opcion.id;
          const bloqueado = opcion.id === "postproxy" && !postproxyDisponible;
          const boton = (
            <button
              type="button"
              role="radio"
              aria-checked={activo}
              disabled={deshabilitado || bloqueado || activo}
              onClick={() => onCambiar(opcion.id)}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                activo
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
                bloqueado && "cursor-not-allowed opacity-50",
              )}
            >
              {opcion.etiqueta}
            </button>
          );
          return bloqueado ? (
            <Tooltip key={opcion.id} label="Crea el grupo y conecta al menos una red para publicar por Postproxy.">
              {boton}
            </Tooltip>
          ) : (
            <React.Fragment key={opcion.id}>{boton}</React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Fila de UNA marca dentro de Postproxy. Postproxy agrupa los perfiles de una marca
 * en un «grupo de perfiles»: si la marca aún no tiene grupo, primero se crea; luego
 * se conecta cada red por OAuth (el back devuelve la URL a abrir en una pestaña).
 * El `redirect_url` es la ruta ACTUAL (volvemos aquí tras el OAuth).
 */
function FilaMarcaPostproxy({ marca, deshabilitado }: { marca: MarcaPostproxy; deshabilitado: boolean }) {
  const queryClient = useQueryClient();
  const tieneGrupo = !!marca.profile_group_id;

  const crearGrupo = useMutation({
    mutationFn: () => api.grupoPostproxy(marca.marca),
    onSuccess: (res) => {
      toast.success(res.mensaje || `Grupo creado para ${marca.etiqueta}.`);
      void queryClient.invalidateQueries({ queryKey: CLAVE_POSTPROXY });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const conectar = useMutation({
    mutationFn: (platform: string) =>
      api.conectarPostproxy(marca.marca, {
        platform,
        // Volvemos a la ruta actual tras completar el OAuth de la red.
        redirect_url: window.location.origin + window.location.pathname + window.location.search,
      }),
    onSuccess: (res) => {
      // El back devuelve la URL del OAuth; la abrimos en pestaña nueva.
      window.open(res.url, "_blank", "noopener,noreferrer");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cambiarCanal = useMutation({
    mutationFn: (canal: CanalPublicacion) => api.canalPostproxy(marca.marca, canal),
    onSuccess: (res) => {
      toast.success(res.mensaje || `Canal de ${marca.etiqueta}: ${res.canal}.`);
      void queryClient.invalidateQueries({ queryKey: CLAVE_POSTPROXY });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const ocupado =
    deshabilitado || crearGrupo.isPending || conectar.isPending || cambiarCanal.isPending;

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium">{marca.etiqueta}</span>
        {tieneGrupo ? (
          <Badge variant="ok">Grupo listo</Badge>
        ) : (
          <Badge variant="secondary">Sin grupo</Badge>
        )}
      </div>

      {/* Selector de canal de PUBLICACIÓN: por dónde salen las piezas de la marca.
          Postproxy se deshabilita hasta que la marca tenga su grupo de perfiles. */}
      <SelectorCanal
        canal={marca.canal}
        postproxyDisponible={tieneGrupo}
        deshabilitado={ocupado}
        onCambiar={(c) => cambiarCanal.mutate(c)}
      />

      {tieneGrupo ? (
        <div className="flex flex-wrap items-center gap-2">
          {PLATAFORMAS_POSTPROXY.map((plataforma) => {
            const Icono = iconoPlataforma(plataforma);
            return (
              <Button
                key={plataforma}
                size="sm"
                variant="outline"
                onClick={() => conectar.mutate(plataforma)}
                disabled={ocupado}
                title={`Conectar ${nombrePlataforma(plataforma)}`}
              >
                <Icono className="h-4 w-4" aria-hidden="true" />
                {nombrePlataforma(plataforma)}
              </Button>
            );
          })}
        </div>
      ) : (
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            Crea el grupo de perfiles para empezar a conectar redes.
          </p>
          <Button size="sm" onClick={() => crearGrupo.mutate()} disabled={ocupado}>
            {crearGrupo.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear grupo
          </Button>
        </div>
      )}
    </div>
  );
}

/** Guard por rol: los secretos de conexión son de admin (sesión null = modo local). */
export function SeccionPostproxy() {
  const { usuario } = useSesion();
  if (usuario !== null && usuario.rol !== "admin") return null;
  return <SeccionPostproxyAdmin />;
}

function SeccionPostproxyAdmin() {
  const queryClient = useQueryClient();
  const [apiKey, setApiKey] = React.useState("");
  const [confirmarQuitar, setConfirmarQuitar] = React.useState(false);
  const [resultadoPrueba, setResultadoPrueba] = React.useState<{ ok: boolean; mensaje: string } | null>(
    null,
  );

  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_POSTPROXY,
    queryFn: ({ signal }) => api.conexionesPostproxy(signal),
  });

  const guardar = useMutation({
    mutationFn: () => api.guardarPostproxy({ api_key: apiKey }),
    onSuccess: (res) => {
      toast.success(res.mensaje || "API key de Postproxy guardada.");
      setApiKey(""); // La clave nunca se conserva en cliente.
      setResultadoPrueba(null);
      void queryClient.invalidateQueries({ queryKey: CLAVE_POSTPROXY });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarPostproxy(),
    onSuccess: (res) => {
      setResultadoPrueba({ ok: res.ok, mensaje: res.mensaje });
      if (res.ok) toast.success(res.mensaje || "Conexión correcta.");
      else toast.error(res.mensaje || "La prueba falló.");
    },
    onError: (e) => {
      setResultadoPrueba({ ok: false, mensaje: mensajeError(e) });
      toast.error(mensajeError(e));
    },
  });

  const quitar = useMutation({
    mutationFn: () => api.eliminarPostproxy(),
    onSuccess: (res) => {
      toast.success(res?.mensaje ?? "Conexión de Postproxy eliminada.");
      setApiKey("");
      setResultadoPrueba(null);
      setConfirmarQuitar(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_POSTPROXY });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const configurado = data?.configurado ?? false;
  const ocupado = guardar.isPending || probar.isPending || quitar.isPending;
  const puedeGuardar = apiKey.trim() !== "";

  return (
    <SeccionColapsable
      titulo="Conexiones · Publicación (Postproxy)"
      contentClassName="space-y-4"
      descripcion="Una API key global de Postproxy y un grupo de perfiles por marca para publicar en cada red."
    >
      <div className="flex items-start gap-3 rounded-lg border border-border bg-primary/5 p-3">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          La API key es global (no por marca). Cada red se conecta por OAuth desde su marca.
        </p>
      </div>

      {/* API key GLOBAL (write-only): solo se envía; del servidor llega el estado + una pista. */}
      <div className="space-y-2 rounded-lg border border-border p-3">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="pp-apikey" className="text-sm font-medium">
            API key de Postproxy
          </Label>
          {configurado ? (
            <Badge variant="ok">Configurada</Badge>
          ) : (
            <Badge variant="secondary">Sin configurar</Badge>
          )}
        </div>
        <Input
          id="pp-apikey"
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={
            configurado
              ? `•••••••••• ${data?.pista ? `(${data.pista})` : ""} — escribe para reemplazar`
              : "Pega la API key aquí"
          }
          disabled={ocupado}
        />

        {resultadoPrueba && (
          <p
            className={cn(
              "flex items-center gap-1.5 text-sm",
              resultadoPrueba.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive",
            )}
          >
            {resultadoPrueba.ok ? (
              <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <X className="h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            {resultadoPrueba.mensaje}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => guardar.mutate()} disabled={ocupado || !puedeGuardar}>
            {guardar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {guardar.isPending ? "Guardando…" : configurado ? "Reemplazar" : "Guardar"}
          </Button>
          {configurado && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => probar.mutate()}
                disabled={ocupado}
              >
                {probar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ShieldCheck className="h-4 w-4" />
                )}
                {probar.isPending ? "Probando…" : "Probar"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setConfirmarQuitar(true)}
                disabled={ocupado}
              >
                <Trash2 className="h-4 w-4" /> Quitar
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Marcas: grupo de perfiles + conexión de redes por OAuth. */}
      {isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : isError ? (
        <BloqueError
          titulo="No se pudo cargar el estado de Postproxy"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : !configurado ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          Configura la API key para conectar las redes de cada marca.
        </p>
      ) : data.marcas.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">
          No hay marcas disponibles para conectar.
        </p>
      ) : (
        <div className="space-y-3">
          {data.marcas.map((marca) => (
            <FilaMarcaPostproxy key={marca.marca} marca={marca} deshabilitado={ocupado} />
          ))}
        </div>
      )}

      <Dialog open={confirmarQuitar} onOpenChange={setConfirmarQuitar}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Quitar conexión de Postproxy</DialogTitle>
            <DialogDescription>
              Se eliminará la API key global de Postproxy. Las redes ya conectadas dejarán de poder
              publicar hasta que vuelvas a configurarla. ¿Quieres continuar?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmarQuitar(false)} disabled={quitar.isPending}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => quitar.mutate()} disabled={quitar.isPending}>
              {quitar.isPending ? "Quitando…" : "Quitar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SeccionColapsable>
  );
}
