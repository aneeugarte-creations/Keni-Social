import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RotateCcw, Settings, ShieldAlert } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { type AjusteConfig } from "@/types";

import {
  CLAVE_CONFIG_USUARIOS,
  CLAVE_MFA,
  CLAVE_MFA_ADMIN,
  CLAVE_PASSWORD_MIN,
  CLAVE_SESION_HORAS,
  CLAVE_SESION_MAX_HORAS,
} from "./tipos";

/** Secciones de la página: cada una agrupa un conjunto explícito de claves (no usa `grupo`). */
const SECCIONES: { titulo: string; descripcion: string; claves: string[] }[] = [
  {
    titulo: "Acceso",
    descripcion: "Obligatoriedad del segundo factor (passkey).",
    claves: [CLAVE_MFA, CLAVE_MFA_ADMIN],
  },
  {
    titulo: "Sesión",
    descripcion: "Cuánto dura una sesión iniciada.",
    claves: [CLAVE_SESION_HORAS, CLAVE_SESION_MAX_HORAS],
  },
  {
    titulo: "Contraseñas",
    descripcion: "Política de contraseñas del equipo.",
    claves: [CLAVE_PASSWORD_MIN],
  },
];

/** Etiqueta + estilo del origen del valor (de dónde sale lo que se aplica hoy). */
function FuenteBadge({ fuente }: { fuente: AjusteConfig["fuente"] }) {
  if (fuente === "store") {
    return (
      <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
        Personalizado
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-normal text-muted-foreground">
      Por defecto
    </Badge>
  );
}

/** Fila de un ajuste BOOL: etiqueta + ayuda + switch + origen/restablecer. */
function AjusteBool({
  ajuste,
  onGuardar,
  onReset,
  ocupado,
}: {
  ajuste: AjusteConfig;
  onGuardar: (clave: string, valor: unknown) => void;
  onReset: (clave: string) => void;
  ocupado: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 space-y-0.5">
        <Label htmlFor={`cfg-${ajuste.clave}`} className="text-sm font-normal">
          {ajuste.etiqueta}
        </Label>
        <p className="text-xs text-muted-foreground">{ajuste.ayuda}</p>
        <CabeceraFuente ajuste={ajuste} onReset={onReset} ocupado={ocupado} />
      </div>
      <Switch
        id={`cfg-${ajuste.clave}`}
        aria-label={ajuste.etiqueta}
        checked={Boolean(ajuste.valor)}
        disabled={ocupado}
        onCheckedChange={(v) => onGuardar(ajuste.clave, v)}
      />
    </div>
  );
}

/** Fila de un ajuste NUMÉRICO (int): etiqueta + ayuda + input + origen/restablecer. */
function AjusteNumero({
  ajuste,
  onGuardar,
  onReset,
  ocupado,
}: {
  ajuste: AjusteConfig;
  onGuardar: (clave: string, valor: unknown) => void;
  onReset: (clave: string) => void;
  ocupado: boolean;
}) {
  const [valor, setValor] = React.useState(String(ajuste.valor));
  React.useEffect(() => {
    setValor(String(ajuste.valor));
  }, [ajuste.valor]);

  const comprometer = () => {
    const limpio = valor.trim();
    const n = Number(limpio);
    if (limpio === "" || Number.isNaN(n)) {
      setValor(String(ajuste.valor)); // entrada inválida: revertimos
      return;
    }
    if (n === Number(ajuste.valor)) return; // sin cambios
    onGuardar(ajuste.clave, n);
  };

  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 space-y-0.5">
        <Label htmlFor={`cfg-${ajuste.clave}`} className="text-sm font-normal">
          {ajuste.etiqueta}
        </Label>
        <p className="text-xs text-muted-foreground">{ajuste.ayuda}</p>
        <CabeceraFuente ajuste={ajuste} onReset={onReset} ocupado={ocupado} />
      </div>
      <Input
        id={`cfg-${ajuste.clave}`}
        type="number"
        inputMode="numeric"
        className="h-9 w-24 shrink-0"
        value={valor}
        min={ajuste.min}
        max={ajuste.max}
        disabled={ocupado}
        onChange={(e) => setValor(e.target.value)}
        onBlur={comprometer}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        }}
      />
    </div>
  );
}

/** Origen del valor + botón de restablecer (solo si el valor está personalizado en el store). */
function CabeceraFuente({
  ajuste,
  onReset,
  ocupado,
}: {
  ajuste: AjusteConfig;
  onReset: (clave: string) => void;
  ocupado: boolean;
}) {
  return (
    <div className="flex items-center gap-2 pt-0.5">
      <FuenteBadge fuente={ajuste.fuente} />
      {ajuste.fuente === "store" && (
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-1.5 text-xs text-muted-foreground hover:text-foreground"
          disabled={ocupado}
          onClick={() => onReset(ajuste.clave)}
        >
          <RotateCcw className="h-3 w-3" />
          Restablecer
        </Button>
      )}
    </div>
  );
}

/**
 * Subpágina de configuración GLOBAL de seguridad (`/usuarios/configuracion`). Lee los ajustes
 * efectivos del equipo y los presenta en secciones (Acceso · Sesión · Contraseñas); cada cambio
 * guarda al instante (PATCH) y refresca. Muestra el ORIGEN de cada valor (personalizado / por
 * defecto) con un botón para restablecerlo. Solo superadmin (el backend devuelve 403 como red de
 * seguridad si se llega por URL).
 */
export default function ConfiguracionGlobal() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { usuario: actual, cargando } = useSesion();
  const esSuperadmin = actual?.es_superadmin === true;
  const volver = () => navigate("/usuarios");

  const query = useQuery({
    queryKey: CLAVE_CONFIG_USUARIOS,
    queryFn: ({ signal }) => api.configuracionUsuarios(signal),
    enabled: esSuperadmin,
  });

  const guardar = useMutation({
    mutationFn: (cuerpo: { clave: string; valor?: unknown; reset?: boolean }) =>
      api.actualizarConfiguracionUsuarios(cuerpo),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CONFIG_USUARIOS });
      toast.success("Configuración guardada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const onGuardar = (clave: string, valor: unknown) => guardar.mutate({ clave, valor });
  const onReset = (clave: string) => guardar.mutate({ clave, reset: true });

  const porClave = React.useMemo(() => {
    const mapa = new Map<string, AjusteConfig>();
    for (const a of query.data?.ajustes ?? []) mapa.set(a.clave, a);
    return mapa;
  }, [query.data]);

  if (!cargando && !esSuperadmin) {
    return (
      <>
        <TituloPagina titulo="Configuración global" icono={Settings} onAtras={volver} />
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      </>
    );
  }

  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;

  return (
    <>
      <TituloPagina titulo="Configuración global" icono={Settings} onAtras={volver} />

      {esProhibido ? (
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      ) : query.isPending ? (
        <Skeleton className="h-80 w-full rounded-md" />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar la configuración"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : (
        <div className="mx-auto max-w-2xl space-y-4 pb-10">
          {actual?.mfa_habilitado === false && (
            <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-500" />
              <p className="text-muted-foreground">
                La maquinaria de verificación en dos pasos no está activa en el servidor (falta la
                clave de firma). Aunque exijas passkey aquí, la obligatoriedad no surtirá efecto
                hasta configurarla.
              </p>
            </div>
          )}

          {SECCIONES.map((seccion) => {
            const ajustes = seccion.claves
              .map((c) => porClave.get(c))
              .filter((a): a is AjusteConfig => Boolean(a));
            if (ajustes.length === 0) return null;
            return (
              <Card key={seccion.titulo}>
                <CardHeader>
                  <CardTitle>{seccion.titulo}</CardTitle>
                  <p className="text-sm text-muted-foreground">{seccion.descripcion}</p>
                </CardHeader>
                <CardContent className="space-y-5">
                  {ajustes.map((a) =>
                    a.tipo === "bool" ? (
                      <AjusteBool
                        key={a.clave}
                        ajuste={a}
                        onGuardar={onGuardar}
                        onReset={onReset}
                        ocupado={guardar.isPending}
                      />
                    ) : (
                      <AjusteNumero
                        key={a.clave}
                        ajuste={a}
                        onGuardar={onGuardar}
                        onReset={onReset}
                        ocupado={guardar.isPending}
                      />
                    ),
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
