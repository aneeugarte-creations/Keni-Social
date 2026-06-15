import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BadgeCheck,
  Copy,
  ExternalLink,
  KeyRound,
  Loader2,
  LogOut,
  UserCog,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CuentaAuth, CuentaUso, MedidorUso } from "@/types";

import { INTERVALO_RECURSOS_MS, colorUso } from "./lib";

/** Etiqueta legible del método de auth que reporta el CLI. */
function metodoLegible(metodo: string | null): string {
  switch (metodo) {
    case "claudeai":
    case "subscription":
      return "Suscripción (login)";
    case "console":
    case "api_key":
      return "API (consola Anthropic)";
    default:
      return metodo ?? "—";
  }
}

/** Badge del estado de sesión. */
function BadgeAuth({ auth }: { auth: CuentaAuth | undefined }) {
  if (!auth || auth.logueado == null) {
    return <Badge variant="secondary">Desconocido</Badge>;
  }
  if (auth.logueado) {
    return (
      <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-400">
        Cuenta conectada
      </Badge>
    );
  }
  return <Badge variant="destructive">Sin cuenta</Badge>;
}

/** Barra + texto de un medidor de uso (sesión 5h / semana / …). */
function Medidor({ m }: { m: MedidorUso }) {
  const ancho = Math.min(100, Math.max(0, m.pct));
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-muted-foreground">{m.etiqueta}</span>
        <span className="font-medium tabular-nums">{m.pct}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", colorUso(m.pct))}
          style={{ width: `${ancho}%` }}
        />
      </div>
      {m.reset && (
        <p className="text-xs text-muted-foreground">Se renueva: {m.reset}</p>
      )}
    </div>
  );
}

/** Bloque del medidor de uso de la suscripción. */
function BloqueUso({ uso }: { uso: CuentaUso | undefined }) {
  if (!uso) return null;
  if (!uso.disponible) {
    return (
      <div className="space-y-1 rounded-lg border border-border/60 p-3">
        <p className="text-sm text-muted-foreground">
          {uso.mensaje || "El medidor de uso no está disponible."}
        </p>
        <p className="text-xs text-muted-foreground/80">
          El detalle de uso (sesión / semana) solo aparece con una cuenta de suscripción
          conectada.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {uso.medidores.map((m) => (
        <Medidor key={m.etiqueta} m={m} />
      ))}
    </div>
  );
}

/** Flujo de conectar/cambiar cuenta: obtener URL → abrir/copiar → pegar código → confirmar. */
function DialogoCambiarCuenta({
  conectado,
  onCambiada,
}: {
  conectado: boolean;
  onCambiada: () => void;
}) {
  const verbo = conectado ? "Cambiar cuenta" : "Conectar cuenta";
  const [abierto, setAbierto] = React.useState(false);
  const [sesion, setSesion] = React.useState<string | null>(null);
  const [url, setUrl] = React.useState<string | null>(null);
  const [codigo, setCodigo] = React.useState("");
  const [usarConsola, setUsarConsola] = React.useState(false);

  const reset = React.useCallback(() => {
    setSesion(null);
    setUrl(null);
    setCodigo("");
    setUsarConsola(false);
  }, []);

  const iniciar = useMutation({
    mutationFn: () => api.cuentaLoginIniciar({ console: usarConsola }),
    onSuccess: (r) => {
      if (r.url && r.sesion) {
        setSesion(r.sesion);
        setUrl(r.url);
      } else {
        toast.error(r.error ?? "No se pudo obtener el enlace de autorización.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const confirmar = useMutation({
    mutationFn: () => api.cuentaLoginCodigo(sesion as string, codigo),
    onSuccess: (r) => {
      if (r.ok) {
        toast.success("Cuenta de Claude conectada.");
        setAbierto(false);
        reset();
        onCambiada();
      } else {
        toast.error(r.mensaje ?? "El login terminó con error.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cerrar = (v: boolean) => {
    if (!v) {
      // Si había un login a medias, cancélalo en el servidor (mata el proceso).
      if (sesion) void api.cuentaLoginCancelar(sesion).catch(() => {});
      reset();
    }
    setAbierto(v);
  };

  const copiar = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Enlace copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar el enlace.");
    }
  };

  return (
    <Dialog open={abierto} onOpenChange={cerrar}>
      <Button variant={conectado ? "outline" : "default"} size="sm" onClick={() => setAbierto(true)}>
        <UserCog className="mr-2 h-4 w-4" aria-hidden="true" />
        {verbo}
      </Button>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{verbo === "Cambiar cuenta" ? "Cambiar la cuenta de Claude" : "Conectar una cuenta de Claude"}</DialogTitle>
          <DialogDescription>
            La cuenta que usa el servidor para generar contenido. Aplica en caliente, sin
            reiniciar.
          </DialogDescription>
        </DialogHeader>

        {!url ? (
          <div className="space-y-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={usarConsola}
                onChange={(e) => setUsarConsola(e.target.checked)}
              />
              Usar consola de Anthropic (facturación por API) en vez de suscripción
            </label>
            <DialogFooter>
              <Button onClick={() => iniciar.mutate()} disabled={iniciar.isPending}>
                {iniciar.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <KeyRound className="mr-2 h-4 w-4" aria-hidden="true" />
                )}
                Obtener enlace de acceso
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                1. Abre este enlace, inicia sesión con la cuenta deseada y copia el código que
                te dé:
              </p>
              <div className="flex items-center gap-2">
                <Input readOnly value={url} className="font-mono text-xs" />
                <Button variant="outline" size="icon" onClick={copiar} title="Copiar enlace">
                  <Copy className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button variant="outline" size="icon" asChild title="Abrir enlace">
                  <a href={url} target="_blank" rel="noreferrer">
                    <ExternalLink className="h-4 w-4" aria-hidden="true" />
                  </a>
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="codigo-auth">2. Pega aquí el código:</Label>
              <Input
                id="codigo-auth"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                placeholder="Código de autorización"
                className="font-mono"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                onClick={() => confirmar.mutate()}
                disabled={confirmar.isPending || !codigo.trim()}
              >
                {confirmar.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <BadgeCheck className="mr-2 h-4 w-4" aria-hidden="true" />
                )}
                Confirmar
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Botón de cerrar sesión con confirmación (deja al servidor sin cuenta hasta re-login). */
function BotonLogout({ onHecho }: { onHecho: () => void }) {
  const logout = useMutation({
    mutationFn: () => api.cuentaLogout(),
    onSuccess: (r) => {
      if (r.ok) {
        toast.success("Sesión de Claude cerrada en el servidor.");
        onHecho();
      } else {
        toast.error(r.mensaje ?? "No se pudo cerrar la sesión.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive">
          <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
          Cerrar sesión
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Cerrar la sesión de Claude del servidor?</AlertDialogTitle>
          <AlertDialogDescription>
            La generación de contenido dejará de funcionar hasta que inicies sesión con una
            cuenta de nuevo. Úsalo solo si vas a cambiar de cuenta.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={() => logout.mutate()}>
            Cerrar sesión
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Sección de la cuenta de Claude del servidor: estado de auth, uso y cambio de cuenta. */
export function SeccionCuentaClaude() {
  const query = useQuery({
    queryKey: ["sistema", "cuenta"],
    queryFn: ({ signal }) => api.sistemaCuenta(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  if (query.isPending) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer la cuenta de Claude"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const data = query.data;
  const refrescar = () => void query.refetch();
  const conectado = data.auth?.logueado === true;

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
          <span className="flex items-center gap-2">
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            Cuenta de Claude del servidor
          </span>
          {data.disponible && <BadgeAuth auth={data.auth} />}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        {!data.disponible ? (
          <p className="text-sm text-amber-600 dark:text-amber-400">
            No se pudo contactar el servicio de generación (daemons).{" "}
            {data.error ?? "Reintenta en unos segundos."}
          </p>
        ) : !conectado ? (
          // SIN CUENTA: dejarlo MUY claro y ofrecer SOLO conectar (nada de cerrar sesión).
          <div className="space-y-3">
            <p className="text-sm">
              <span className="font-medium">No hay ninguna cuenta de Claude conectada.</span>{" "}
              <span className="text-muted-foreground">
                La generación de contenido (copy y arte) no funcionará hasta conectar una.
              </span>
            </p>
            {data.auth?.error && (
              <p className="text-xs text-muted-foreground">{data.auth.error}</p>
            )}
            <DialogoCambiarCuenta conectado={false} onCambiada={refrescar} />
          </div>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1">
                <dt className="text-muted-foreground">Método</dt>
                <dd className="font-medium">{metodoLegible(data.auth?.metodo ?? null)}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1">
                <dt className="text-muted-foreground">Proveedor</dt>
                <dd className="font-medium">{data.auth?.proveedor ?? "—"}</dd>
              </div>
            </dl>

            <BloqueUso uso={data.uso} />

            <div className="flex items-center gap-2 pt-1">
              <DialogoCambiarCuenta conectado onCambiada={refrescar} />
              <BotonLogout onHecho={refrescar} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
