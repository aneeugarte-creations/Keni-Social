import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BadgeCheck,
  Copy,
  ExternalLink,
  Gauge,
  KeyRound,
  LogOut,
  RefreshCw,
  UserCog,
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { CLAVE_USO_CUENTA, useUsoCuenta } from "@/hooks/use-uso-cuenta";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHoraCorta, haceSegundos } from "@/lib/fecha";
import { limiteMasUrgente, type PrediccionUso } from "@/lib/uso-burn";
import { cn } from "@/lib/utils";
import type {
  CuentaAuth,
  CuentaMarcaAsignacion,
  CuentaUso,
  MedidorUso,
  RespuestaCuentaMarcas,
} from "@/types";

import { colorUso } from "./lib";

// El estado de cuenta + medidor `/usage` se refresca cada HORA: leerlo ejecuta `claude -p
// /usage` en el servidor (subproceso + roundtrip a Anthropic), y el uso casi no cambia en
// minutos. Para verlo al momento está el botón de refresco.
const INTERVALO_CUENTA_MS = 60 * 60 * 1000;

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
    return <Badge variant="ok">Cuenta conectada</Badge>;
  }
  return <Badge variant="outline">Sin cuenta</Badge>;
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
      {(m.reset_iso || m.reset) && (
        <p className="text-xs text-muted-foreground">
          Se renueva: {m.reset_iso ? formatearFechaHoraCorta(m.reset_iso) : m.reset}
        </p>
      )}
    </div>
  );
}

/** Bloque del medidor de uso. NUNCA muestra la frase pelada: si la lectura actual no trae
 *  medidor, se sirve el último cacheado ("última lectura con datos hace X"). */
function BloqueUso({ uso }: { uso: CuentaUso | undefined }) {
  if (!uso) return null;
  if (!uso.medidores.length) {
    // Ni medidor ni cache aún: estado neutro mientras llega el primero (no la frase pelada).
    return <p className="text-sm text-muted-foreground">Obteniendo medidor de uso…</p>;
  }
  return (
    <div className="space-y-3">
      {uso.cacheado && uso.actualizado != null && (
        <p className="text-xs text-muted-foreground/80">
          Última lectura con datos: {haceSegundos(Date.now() / 1000 - uso.actualizado)}.
        </p>
      )}
      {uso.medidores.map((m) => (
        <Medidor key={m.etiqueta} m={m} />
      ))}
    </div>
  );
}

/** Selector de cuenta de Claude del servidor. "a" = cuenta histórica; "b" = segunda cuenta
 *  (split por marcas: unotv / nacion-gamer / unotv-us). */
type Cuenta = "a" | "b";

/** Flujo de conectar/cambiar cuenta: obtener URL → abrir/copiar → pegar código → confirmar. */
function DialogoCambiarCuenta({
  cuenta,
  conectado,
  onCambiada,
}: {
  cuenta: Cuenta;
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
    mutationFn: () => api.cuentaLoginIniciar({ console: usarConsola }, cuenta),
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
      <Button variant="outline" size="sm" onClick={() => setAbierto(true)}>
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
            <Label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={usarConsola}
                onChange={(e) => setUsarConsola(e.target.checked)}
              />
              Usar consola de Anthropic (facturación por API) en vez de suscripción
            </Label>
            <DialogFooter>
              <Button onClick={() => iniciar.mutate()} disabled={iniciar.isPending}>
                {iniciar.isPending ? (
                  <Spinner className="mr-2 h-4 w-4" />
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
                  <Spinner className="mr-2 h-4 w-4" />
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
function BotonLogout({ cuenta, onHecho }: { cuenta: Cuenta; onHecho: () => void }) {
  const logout = useMutation({
    mutationFn: () => api.cuentaLogout(cuenta),
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

/** Tarjeta de UNA cuenta de Claude del servidor: estado de auth, uso y cambio de cuenta. */
/** Selector MÚLTIPLE de marcas de UNA cuenta: un chip por marca; activo = la sirve esta cuenta.
 *  Togglear mueve la marca entre cuentas (una sola cuenta sirve cada marca). Admin-only: solo se
 *  pinta si el reparto cargó. */
function SelectorMarcas({
  cuenta,
  marcas,
  onMover,
  marcaPendiente,
}: {
  cuenta: Cuenta;
  marcas: CuentaMarcaAsignacion[];
  onMover: (marca: string, cuenta: Cuenta) => void;
  marcaPendiente: string | undefined;
}) {
  const otra: Cuenta = cuenta === "a" ? "b" : "a";
  return (
    <div role="group" aria-label="Marcas de esta cuenta" className="flex flex-wrap gap-1.5">
      {marcas.map((m) => {
        const aqui = m.cuenta === cuenta;
        const ocupada = marcaPendiente === m.id;
        return (
          <Button
            key={m.id}
            type="button"
            size="sm"
            // Activo = la sirve esta cuenta: relleno sólido. Inactivo: outline apagado. El
            // contraste deja claro de un vistazo qué marcas pertenecen a la cuenta.
            variant={aqui ? "default" : "outline"}
            aria-pressed={aqui}
            disabled={marcaPendiente != null}
            onClick={() => onMover(m.id, aqui ? otra : cuenta)}
            title={
              aqui
                ? `Quitar «${m.nombre}» de esta cuenta (mover a la cuenta ${otra.toUpperCase()})`
                : `Mover «${m.nombre}» a esta cuenta`
            }
            className={cn(
              "h-7 rounded-full px-3 text-xs",
              !aqui && "text-muted-foreground",
            )}
          >
            {ocupada && <Spinner className="mr-1.5 h-3 w-3" />}
            {m.nombre}
          </Button>
        );
      })}
    </div>
  );
}

/** Tiempo legible hasta el 100 %: «ya», «<1 h», «~N h» o «~N d». */
function tiempoBurn(horas: number): string {
  if (horas <= 0) return "ya";
  if (horas < 1) return "<1 h";
  if (horas < 48) return `~${Math.round(horas)} h`;
  return `~${Math.round(horas / 24)} d`;
}

/** Predicción de burn rate: qué límite (5h / Semana / Sonnet) llegará ANTES al 100 %. `null` si no
 *  hay datos suficientes para predecir. */
function LineaBurnRate({ prediccion }: { prediccion: PrediccionUso | null }) {
  if (!prediccion) return null;
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Gauge className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      Primero al 100 %:{" "}
      <span className="font-medium text-foreground">{prediccion.etiqueta}</span>
      <span className="tabular-nums">{tiempoBurn(prediccion.horas)}</span>
    </p>
  );
}

function TarjetaCuenta({
  cuenta,
  titulo,
  descripcion,
  reparto,
  onMover,
  marcaPendiente,
  prediccion,
}: {
  cuenta: Cuenta;
  titulo: string;
  descripcion?: string;
  reparto: RespuestaCuentaMarcas | undefined;
  onMover: (marca: string, cuenta: Cuenta) => void;
  marcaPendiente: string | undefined;
  prediccion: PrediccionUso | null;
}) {
  const query = useQuery({
    queryKey: ["sistema", "cuenta", cuenta],
    queryFn: ({ signal }) => api.sistemaCuenta(cuenta, signal),
    // Cada hora, y NO al reenfocar la ventana: leerlo es caro (`claude -p /usage`). Para
    // verlo al instante, el botón de refresco de la cabecera.
    refetchInterval: INTERVALO_CUENTA_MS,
    refetchOnWindowFocus: false,
  });

  if (query.isPending) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo={`No se pudo leer ${titulo}`}
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
            {titulo}
          </span>
          <span className="flex items-center gap-2">
            {data.disponible && <BadgeAuth auth={data.auth} />}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={refrescar}
              disabled={query.isFetching}
              title="Actualizar estado y uso ahora"
            >
              <RefreshCw
                className={cn("h-4 w-4", query.isFetching && "animate-spin")}
                aria-hidden="true"
              />
            </Button>
          </span>
        </CardTitle>
        {descripcion && (
          <p className="pt-1 text-xs text-muted-foreground">{descripcion}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        {!data.disponible ? (
          <Aviso>
            No se pudo contactar el servicio de generación (daemons).{" "}
            {data.error ?? "Reintenta en unos segundos."}
          </Aviso>
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
            <DialogoCambiarCuenta cuenta={cuenta} conectado={false} onCambiada={refrescar} />
          </div>
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1">
                <dt className="text-muted-foreground">Cuenta</dt>
                <dd className="truncate font-medium">{data.auth?.email ?? "—"}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-3 border-b border-border/50 py-1">
                <dt className="text-muted-foreground">Plan</dt>
                <dd className="font-medium capitalize">
                  {data.auth?.plan ?? metodoLegible(data.auth?.metodo ?? null)}
                </dd>
              </div>
            </dl>

            <BloqueUso uso={data.uso} />
            <LineaBurnRate prediccion={prediccion} />

            <div className="flex items-center gap-2 pt-1">
              <DialogoCambiarCuenta cuenta={cuenta} conectado onCambiada={refrescar} />
              <BotonLogout cuenta={cuenta} onHecho={refrescar} />
            </div>
          </>
        )}

        {/* Reparto de marcas dentro de la propia tarjeta (qué marcas sirve esta cuenta). Solo si el
            reparto cargó (admin); el routing es independiente de que la cuenta esté conectada. */}
        {reparto && (
          <div className="border-t border-border/50 pt-3">
            <SelectorMarcas
              cuenta={cuenta}
              marcas={reparto.marcas}
              onMover={onMover}
              marcaPendiente={marcaPendiente}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Título de cada tarjeta de cuenta (las marcas que sirve se ven en su selector, no en el texto). */
const TARJETAS: Record<Cuenta, { titulo: string }> = {
  a: { titulo: "Cuenta A" },
  b: { titulo: "Cuenta B" },
};

/** Clave de caché del reparto marca→cuenta. */
const CLAVE_CUENTA_MARCAS = ["sistema", "cuenta-marcas"] as const;

/** Sección de las cuentas de Claude del servidor: cuenta A y cuenta B. Cada tarjeta lleva su
 *  estado/uso, login/logout y, dentro, el SELECTOR DE MARCAS de esa cuenta (admin): qué marcas
 *  sirve, movibles entre cuentas. (Antes había un panel «Marcas por cuenta» aparte; ahora vive en
 *  la propia tarjeta.)
 *
 *  Respeta el SELECTOR DE MARCA global (`useMarcaActiva`): en "Todas" (`marcaActiva === null`)
 *  muestra AMBAS tarjetas; con una marca concreta, solo la de su cuenta (mapeo reutilizado del
 *  endpoint de uso). El reparto marca→cuenta (`cuenta-marcas`, admin-only) se carga aquí y se pasa
 *  a cada tarjeta; si responde 403/falla, las tarjetas no pintan el selector. */
export function SeccionCuentaClaude() {
  const { marcaActiva } = useMarcaActiva();
  const { data } = useUsoCuenta();
  const qc = useQueryClient();

  const repartoQuery = useQuery({
    queryKey: CLAVE_CUENTA_MARCAS,
    queryFn: ({ signal }) => api.cuentaMarcas(signal),
    retry: false,
    refetchOnWindowFocus: false,
  });
  const asignar = useMutation({
    mutationFn: (datos: { marca: string; cuenta: string }) => api.asignarCuentaMarca(datos),
    onSuccess: (mapa) => {
      qc.setQueryData(CLAVE_CUENTA_MARCAS, mapa);
      void qc.invalidateQueries({ queryKey: CLAVE_USO_CUENTA });
      toast.success("Reparto de marcas actualizado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cuentas = React.useMemo<Cuenta[]>(() => {
    if (marcaActiva === null) return ["a", "b"];
    const cuenta = data?.cuentas.find((c) => c.marcas.includes(marcaActiva))?.cuenta;
    if (cuenta === "a" || cuenta === "b") return [cuenta];
    return ["a", "b"];
  }, [marcaActiva, data]);

  const marcaPendiente = asignar.isPending ? asignar.variables?.marca : undefined;

  // Burn rate por cuenta: reutiliza el snapshot de uso (`/sistema/uso`) que ya consume esta sección.
  const prediccion = (cuenta: Cuenta): PrediccionUso | null => {
    const uso = data?.cuentas.find((c) => c.cuenta === cuenta);
    return uso ? limiteMasUrgente(uso) : null;
  };

  return (
    <div className="space-y-4">
      {cuentas.map((cuenta) => (
        <TarjetaCuenta
          key={cuenta}
          cuenta={cuenta}
          titulo={TARJETAS[cuenta].titulo}
          reparto={repartoQuery.data}
          onMover={(marca, c) => asignar.mutate({ marca, cuenta: c })}
          marcaPendiente={marcaPendiente}
          prediccion={prediccion(cuenta)}
        />
      ))}
    </div>
  );
}
