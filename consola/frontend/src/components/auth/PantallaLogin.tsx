import { Eye, EyeOff, Fingerprint, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useSesion } from "@/hooks/sesion-contexto";

/** Mensaje genérico de credenciales inválidas (no revelamos qué falló). */
const ERROR_CREDENCIALES = "Usuario o contraseña incorrectos.";

/**
 * Pantalla de inicio de sesión: usuario + contraseña, botón "Entrar" y un error
 * genérico si las credenciales no son válidas. El login pone la cookie de sesión
 * en el backend; al tener éxito, el provider de sesión guarda el usuario y la
 * app continúa. Ocupa toda la pantalla (no muestra el shell hasta entrar).
 */
export function PantallaLogin() {
  const { iniciarSesion, verificarConPasskey, verificarConCodigo } = useSesion();
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [verPassword, setVerPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [enviando, setEnviando] = React.useState(false);
  // Paso 2 (MFA): cuando el backend pide segundo factor, mostramos la ceremonia de passkey en
  // lugar del formulario de usuario/contraseña. La sesión NO existe hasta verificar.
  const [pidiendoMfa, setPidiendoMfa] = React.useState(false);
  // Modo "código de recuperación": fallback cuando el usuario no tiene su passkey a mano.
  const [usandoCodigo, setUsandoCodigo] = React.useState(false);
  const [codigoMfa, setCodigoMfa] = React.useState("");

  const puedeEnviar = usuario.trim().length > 0 && password.length > 0 && !enviando;
  const puedeVerificarCodigo = codigoMfa.trim().length > 0 && !enviando;

  async function alEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeEnviar) return;
    setEnviando(true);
    setError(null);
    try {
      const { mfaRequerido } = await iniciarSesion(usuario.trim(), password);
      if (mfaRequerido) {
        // Pasamos al paso de la passkey; limpiamos la contraseña de memoria.
        setPidiendoMfa(true);
        setUsandoCodigo(false);
        setPassword("");
        setEnviando(false);
        return;
      }
      // En éxito, el provider re-renderiza con la sesión y desmonta esta pantalla.
    } catch (err) {
      // 401 = credenciales malas (mensaje genérico). Otros errores: mensaje del
      // backend o un fallback legible.
      if (err instanceof ApiError && err.status === 401) {
        setError(ERROR_CREDENCIALES);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("No se pudo iniciar sesión. Vuelve a intentarlo.");
      }
      setEnviando(false);
    }
  }

  async function alUsarPasskey() {
    if (enviando) return;
    setEnviando(true);
    setError(null);
    try {
      await verificarConPasskey();
      // En éxito, el provider re-renderiza con la sesión y desmonta esta pantalla.
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof DOMException && err.name === "NotAllowedError") {
        // El usuario canceló la ceremonia (o expiró): mensaje suave, puede reintentar.
        setError("Verificación cancelada. Vuelve a intentarlo con tu llave de acceso.");
      } else {
        setError("No se pudo usar la llave de acceso. Vuelve a intentarlo.");
      }
      setEnviando(false);
    }
  }

  async function alVerificarCodigo(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeVerificarCodigo) return;
    setEnviando(true);
    setError(null);
    try {
      await verificarConCodigo(codigoMfa.trim());
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("No se pudo verificar el código. Vuelve a intentarlo.");
      }
      setEnviando(false);
    }
  }

  function volverAlLogin() {
    setPidiendoMfa(false);
    setUsandoCodigo(false);
    setCodigoMfa("");
    setError(null);
  }

  if (pidiendoMfa) {
    return (
      <div className="flex min-h-dvh w-full items-center justify-center bg-background px-4">
        <Card className="w-full max-w-sm">
          <CardHeader className="space-y-1.5 text-center">
            <div className="flex justify-center">
              <ShieldCheck className="h-6 w-6 text-foreground" />
            </div>
            <CardTitle className="text-xl">Verificación en dos pasos</CardTitle>
            <p className="text-sm text-muted-foreground">
              {usandoCodigo
                ? "Introduce uno de tus códigos de recuperación."
                : "Confirma con tu llave de acceso (Face ID, huella o tu teléfono)."}
            </p>
          </CardHeader>
          <CardContent>
            {usandoCodigo ? (
              <form className="space-y-4" onSubmit={alVerificarCodigo} noValidate>
                <div className="space-y-1.5">
                  <Label htmlFor="mfa-codigo">Código de recuperación</Label>
                  <Input
                    id="mfa-codigo"
                    name="one-time-code"
                    autoComplete="one-time-code"
                    autoFocus
                    value={codigoMfa}
                    onChange={(e) => setCodigoMfa(e.target.value)}
                    disabled={enviando}
                  />
                </div>

                {error && (
                  <p role="alert" className="text-sm text-destructive">
                    {error}
                  </p>
                )}

                <Button type="submit" className="w-full" disabled={!puedeVerificarCodigo}>
                  {enviando ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <ShieldCheck className="h-4 w-4" />
                  )}
                  Verificar
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  disabled={enviando}
                  onClick={() => {
                    setUsandoCodigo(false);
                    setError(null);
                  }}
                >
                  Usar mi llave de acceso
                </Button>
              </form>
            ) : (
              <div className="space-y-4">
                {error && (
                  <p role="alert" className="text-sm text-destructive">
                    {error}
                  </p>
                )}
                <Button
                  type="button"
                  className="w-full"
                  disabled={enviando}
                  onClick={alUsarPasskey}
                >
                  {enviando ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Fingerprint className="h-4 w-4" />
                  )}
                  Usar mi llave de acceso
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full"
                  disabled={enviando}
                  onClick={() => {
                    setUsandoCodigo(true);
                    setError(null);
                  }}
                >
                  <KeyRound className="h-4 w-4" />
                  Usar un código de recuperación
                </Button>
              </div>
            )}
            <Button
              type="button"
              variant="ghost"
              className="mt-2 w-full"
              disabled={enviando}
              onClick={volverAlLogin}
            >
              Volver
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-white px-6">
      <div className="w-full max-w-sm">
        <h1 className="mb-14 text-center text-2xl font-light uppercase text-neutral-900">
          {/* El `tracking` añade espacio TRAS la última letra; con `text-center` eso descentra
              el wordmark. Lo aislamos en un inline-block y anulamos ese sobrante con un margen
              derecho negativo igual al tracking → KENI queda centrado EXACTO sobre el formulario. */}
          <span className="inline-block tracking-[0.3em] [margin-right:-0.3em]">KENI</span>
        </h1>
        <form className="space-y-9" onSubmit={alEnviar} noValidate>
          <div className="space-y-3">
            <Label
              htmlFor="login-usuario"
              className="text-xs font-light text-neutral-900"
            >
              Usuario
            </Label>
            <Input
              id="login-usuario"
              name="username"
              autoComplete="username"
              autoFocus
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              disabled={enviando}
              className="h-9 rounded-none border-x-0 border-t-0 border-b border-neutral-300 bg-transparent px-0 text-neutral-900 shadow-none transition-colors focus-visible:border-neutral-900 focus-visible:ring-0"
            />
          </div>
          <div className="space-y-3">
            <Label
              htmlFor="login-password"
              className="text-xs font-light text-neutral-900"
            >
              Contraseña
            </Label>
            <div className="relative">
              <Input
                id="login-password"
                name="password"
                type={verPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={enviando}
                className="h-9 rounded-none border-x-0 border-t-0 border-b border-neutral-300 bg-transparent px-0 pr-9 text-neutral-900 shadow-none transition-colors focus-visible:border-neutral-900 focus-visible:ring-0"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setVerPassword((v) => !v)}
                disabled={enviando}
                aria-pressed={verPassword}
                aria-label={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-neutral-400 transition-colors hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {verPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}

          <Button
            type="submit"
            variant="outline"
            disabled={!puedeEnviar}
            className="mt-3 h-11 w-full rounded-md border-neutral-900 text-xs uppercase tracking-[0.28em] text-neutral-900 shadow-none"
          >
            {enviando ? <Loader2 className="h-4 w-4 animate-spin" /> : "Entrar"}
          </Button>
        </form>
      </div>
    </div>
  );
}
