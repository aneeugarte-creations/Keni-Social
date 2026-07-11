import { AlertTriangle, Camera } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";

/**
 * Autorización del escritorio keni-fotos (lado-nube del login OPCIONAL, flujo loopback).
 *
 * La app de escritorio abre `https://social.kenitech.io/fotos/autorizar?cb=<loopback>&state=<azar>`
 * y espera un redirect del navegador a `cb?token=&state=`. Esta página vive DETRÁS de la puerta de
 * sesión (igual que el resto del SPA): si no hay sesión, se ve el login y al entrar se vuelve aquí
 * con `cb`/`state` intactos en la URL. Al pulsar «Autorizar» pedimos a `POST /api/fotos/autorizar`
 * que emita el token y nos dé la URL loopback de retorno, y redirigimos el navegador allí; la app
 * captura el token y lo guarda en su keychain.
 *
 * Vive FUERA del AppShell (sin sidebar): es una pantalla mínima de una sola acción.
 */

// Hosts loopback admitidos para el callback (espejo de `_HOSTS_LOOPBACK` en `api/fotos.py`): el
// token solo se entrega a un servidor de la propia máquina, nunca a un host remoto.
const HOSTS_LOOPBACK = new Set(["127.0.0.1", "localhost"]);

function cbLoopbackValido(cb: string | null): cb is string {
  if (!cb) return false;
  try {
    const url = new URL(cb);
    return url.protocol === "http:" && HOSTS_LOOPBACK.has(url.hostname);
  } catch {
    return false;
  }
}

/** Tarjeta centrada a pantalla completa: el marco común de los dos estados (error / autorizar). */
function Marco({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm rounded-xl border bg-card p-8 text-center">
        {children}
      </div>
    </div>
  );
}

export default function FotosAutorizar() {
  const { usuario } = useSesion();
  const params = new URLSearchParams(window.location.search);
  const cb = params.get("cb");
  const state = params.get("state");
  const valido = cbLoopbackValido(cb) && !!state;

  const [autorizando, setAutorizando] = React.useState(false);
  const [error, setError] = React.useState("");

  async function autorizar() {
    if (!valido) return;
    setAutorizando(true);
    setError("");
    try {
      const { redirect } = await api.autorizarFotos({ cb: cb!, state: state! });
      // Redirige el navegador al servidor loopback de la app, que captura el token y cierra.
      window.location.href = redirect;
    } catch (e) {
      setAutorizando(false);
      setError(mensajeError(e));
    }
  }

  // Petición inválida (sin `cb`/`state` o `cb` no loopback): no emitimos nada, lo decimos claro.
  if (!valido) {
    return (
      <Marco>
        <AlertTriangle className="mx-auto h-10 w-10 text-amber-500" aria-hidden="true" />
        <h1 className="mt-4 text-lg font-semibold">Solicitud no válida</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Abre esta página desde la app keni-fotos. El enlace de autorización no es correcto.
        </p>
      </Marco>
    );
  }

  const nombre = usuario?.nombre || usuario?.usuario || "tu cuenta";

  return (
    <Marco>
      <Camera className="mx-auto h-10 w-10 text-primary" aria-hidden="true" />
      <h1 className="mt-4 text-lg font-semibold">Autorizar keni-fotos</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Conecta la app de escritorio con keni-social como{" "}
        <span className="font-medium text-foreground">{nombre}</span>. Solo tú, en este equipo,
        podrás usar la app con tu cuenta.
      </p>
      {error ? (
        <p className="mt-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mt-6 flex flex-col gap-2">
        <Button onClick={autorizar} disabled={autorizando}>
          {autorizando ? (
            <>
              <Spinner className="h-4 w-4" aria-hidden="true" />
              Conectando…
            </>
          ) : (
            "Autorizar"
          )}
        </Button>
        <Button
          variant="ghost"
          onClick={() => window.location.assign("/")}
          disabled={autorizando}
        >
          Cancelar
        </Button>
      </div>
    </Marco>
  );
}
