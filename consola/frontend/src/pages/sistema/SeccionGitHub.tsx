import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BadgeCheck,
  Copy,
  ExternalLink,
  Github,
  KeyRound,
  LogOut,
  RefreshCw,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { api, mensajeError } from "@/lib/api";
import type { GithubAuth } from "@/types";

// El estado de GitHub apenas cambia (solo al conectar/desconectar): refresco perezoso, con botón
// manual para verlo al momento. Leerlo ejecuta `gh auth status` en el servidor.
const INTERVALO_GITHUB_MS = 60 * 60 * 1000;

/** Badge del estado de sesión de GitHub. */
function BadgeAuth({ auth }: { auth: GithubAuth | undefined }) {
  if (!auth) {
    return <Badge variant="secondary">Desconocido</Badge>;
  }
  if (auth.logueado) {
    return <Badge variant="ok">GitHub conectado</Badge>;
  }
  return <Badge variant="outline">Sin conectar</Badge>;
}

/**
 * Flujo de conectar GitHub por device flow de `gh`: obtener código → abrir GitHub, pegar el
 * one-time code y autorizar → esperar a que `gh` complete el polling. No se pega ningún código de
 * vuelta en la consola: `gh` detecta la autorización por su cuenta.
 */
function DialogoConectar({ conectado, onConectado }: { conectado: boolean; onConectado: () => void }) {
  const verbo = conectado ? "Reconectar" : "Conectar GitHub";
  const [abierto, setAbierto] = React.useState(false);
  const [sesion, setSesion] = React.useState<string | null>(null);
  const [codigo, setCodigo] = React.useState<string | null>(null);
  const [url, setUrl] = React.useState<string | null>(null);

  const reset = React.useCallback(() => {
    setSesion(null);
    setCodigo(null);
    setUrl(null);
  }, []);

  const iniciar = useMutation({
    mutationFn: () => api.githubLoginIniciar(),
    onSuccess: (r) => {
      if (r.sesion && r.codigo && r.url) {
        setSesion(r.sesion);
        setCodigo(r.codigo);
        setUrl(r.url);
      } else {
        toast.error("No se pudo iniciar el acceso a GitHub.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const confirmar = useMutation({
    mutationFn: () => api.githubLoginConfirmar(sesion as string),
    onSuccess: (r) => {
      if (r.ok) {
        toast.success("GitHub conectado en el servidor.");
        setAbierto(false);
        reset();
        onConectado();
      } else {
        toast.error(r.mensaje ?? "La autorización terminó con error.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cerrar = (v: boolean) => {
    if (!v) {
      // Si había un login a medias, cancélalo en el servidor (mata el proceso `gh`).
      if (sesion) void api.githubLoginCancelar(sesion).catch(() => {});
      reset();
    }
    setAbierto(v);
  };

  const copiarCodigo = async () => {
    if (!codigo) return;
    try {
      await navigator.clipboard.writeText(codigo);
      toast.success("Código copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar el código.");
    }
  };

  return (
    <Dialog open={abierto} onOpenChange={cerrar}>
      <Button variant="outline" size="sm" onClick={() => setAbierto(true)}>
        <Github className="mr-2 h-4 w-4" aria-hidden="true" />
        {verbo}
      </Button>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Conectar la cuenta de GitHub del servidor</DialogTitle>
          <DialogDescription>
            La credencial con la que el motor de auto-desarrollo empuja a GitHub. Aplica en
            caliente, sin reiniciar.
          </DialogDescription>
        </DialogHeader>

        {!codigo || !url ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Obtén un código de un solo uso para autorizar el acceso en GitHub.
            </p>
            <DialogFooter>
              <Button onClick={() => iniciar.mutate()} disabled={iniciar.isPending}>
                {iniciar.isPending ? (
                  <Spinner className="mr-2 h-4 w-4" />
                ) : (
                  <KeyRound className="mr-2 h-4 w-4" aria-hidden="true" />
                )}
                Obtener código de acceso
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">1. Copia este código de un solo uso:</p>
              <div className="flex items-center gap-2">
                <Input
                  readOnly
                  value={codigo}
                  className="text-center font-mono text-lg tracking-[0.3em]"
                />
                <Button variant="outline" size="icon" onClick={copiarCodigo} title="Copiar código">
                  <Copy className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                2. Abre GitHub, pega el código y autoriza el acceso:
              </p>
              <Button variant="outline" asChild className="w-full justify-center">
                <a href={url} target="_blank" rel="noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" aria-hidden="true" />
                  {url}
                </a>
              </Button>
            </div>
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                3. Cuando lo hayas autorizado en GitHub, espera a que el servidor lo confirme:
              </p>
              <DialogFooter>
                <Button onClick={() => confirmar.mutate()} disabled={confirmar.isPending}>
                  {confirmar.isPending ? (
                    <Spinner className="mr-2 h-4 w-4" />
                  ) : (
                    <BadgeCheck className="mr-2 h-4 w-4" aria-hidden="true" />
                  )}
                  {confirmar.isPending ? "Esperando autorización…" : "Esperar autorización"}
                </Button>
              </DialogFooter>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Botón de desconectar GitHub con confirmación (deja al servidor sin credencial gh). */
function BotonLogout({ onHecho }: { onHecho: () => void }) {
  const logout = useMutation({
    mutationFn: () => api.githubLogout(),
    onSuccess: (r) => {
      if (r.ok) {
        toast.success("GitHub desconectado en el servidor.");
        onHecho();
      } else {
        toast.error(r.mensaje ?? "No se pudo desconectar.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive">
          <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
          Desconectar
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>¿Desconectar GitHub del servidor?</AlertDialogTitle>
          <AlertDialogDescription>
            El motor de auto-desarrollo no podrá empujar a GitHub hasta que vuelvas a conectar una
            cuenta.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancelar</AlertDialogCancel>
          <AlertDialogAction onClick={() => logout.mutate()}>Desconectar</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Sección del proveedor GitHub del servidor: estado de auth y conexión vía device flow de `gh`. */
export function SeccionGitHub() {
  const query = useQuery({
    queryKey: ["sistema", "github"],
    queryFn: ({ signal }) => api.githubEstado(signal),
    refetchInterval: INTERVALO_GITHUB_MS,
    refetchOnWindowFocus: false,
  });

  if (query.isPending) {
    return <Skeleton className="h-40 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el estado de GitHub"
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
            <Github className="h-4 w-4" aria-hidden="true" />
            GitHub del servidor
          </span>
          <span className="flex items-center gap-2">
            {data.disponible && <BadgeAuth auth={data.auth} />}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={refrescar}
              disabled={query.isFetching}
              title="Actualizar estado ahora"
            >
              <RefreshCw
                className={query.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"}
                aria-hidden="true"
              />
            </Button>
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        {!data.disponible ? (
          <Aviso>
            No se pudo contactar el servicio de control (daemons). Reintenta en unos segundos.
          </Aviso>
        ) : !conectado ? (
          <div className="space-y-3">
            <p className="text-sm">
              <span className="font-medium">No hay ninguna cuenta de GitHub conectada.</span>{" "}
              <span className="text-muted-foreground">
                El motor de auto-desarrollo no podrá empujar a GitHub hasta conectar una.
              </span>
            </p>
            <DialogoConectar conectado={false} onConectado={refrescar} />
          </div>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1">
                <dt className="text-muted-foreground">Usuario</dt>
                <dd className="truncate font-medium">{data.auth?.usuario ?? "—"}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1">
                <dt className="text-muted-foreground">Scopes</dt>
                <dd className="truncate font-medium">
                  {data.auth?.scopes && data.auth.scopes.length > 0
                    ? data.auth.scopes.join(", ")
                    : "—"}
                </dd>
              </div>
            </dl>

            <div className="flex items-center gap-2 pt-1">
              <DialogoConectar conectado onConectado={refrescar} />
              <BotonLogout onHecho={refrescar} />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
