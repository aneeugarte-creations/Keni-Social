import { Loader2, LogIn, ShieldCheck } from "lucide-react";
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
  const { iniciarSesion, verificarMfa } = useSesion();
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [enviando, setEnviando] = React.useState(false);
  // Paso 2 (MFA): cuando el backend pide segundo factor, mostramos la entrada del código TOTP
  // en lugar del formulario de usuario/contraseña. La sesión NO existe hasta verificar.
  const [pidiendoMfa, setPidiendoMfa] = React.useState(false);
  const [codigoMfa, setCodigoMfa] = React.useState("");

  const puedeEnviar = usuario.trim().length > 0 && password.length > 0 && !enviando;
  const puedeVerificar = codigoMfa.trim().length > 0 && !enviando;

  async function alEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeEnviar) return;
    setEnviando(true);
    setError(null);
    try {
      const { mfaRequerido } = await iniciarSesion(usuario.trim(), password);
      if (mfaRequerido) {
        // Pasamos al paso del código; limpiamos la contraseña de memoria.
        setPidiendoMfa(true);
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

  async function alVerificarMfa(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeVerificar) return;
    setEnviando(true);
    setError(null);
    try {
      await verificarMfa(codigoMfa.trim());
      // En éxito, el provider re-renderiza con la sesión y desmonta esta pantalla.
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Código inválido/caducado o sesión de verificación expirada (mensaje del backend).
        setError(err.message);
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("No se pudo verificar el código. Vuelve a intentarlo.");
      }
      setEnviando(false);
    }
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
              Introduce el código de tu app de autenticación (o un código de recuperación).
            </p>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={alVerificarMfa} noValidate>
              <div className="space-y-1.5">
                <Label htmlFor="mfa-codigo">Código</Label>
                <Input
                  id="mfa-codigo"
                  name="one-time-code"
                  autoComplete="one-time-code"
                  inputMode="numeric"
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

              <Button type="submit" className="w-full" disabled={!puedeVerificar}>
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
                  setPidiendoMfa(false);
                  setCodigoMfa("");
                  setError(null);
                }}
              >
                Volver
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1.5 text-center">
          <div className="flex justify-center">
            <span className="text-sm font-normal tracking-wider text-foreground">KENI</span>
          </div>
          <CardTitle className="text-xl">Consola</CardTitle>
          <p className="text-sm text-muted-foreground">Inicia sesión para continuar.</p>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={alEnviar} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="login-usuario">Usuario</Label>
              <Input
                id="login-usuario"
                name="username"
                autoComplete="username"
                autoFocus
                value={usuario}
                onChange={(e) => setUsuario(e.target.value)}
                disabled={enviando}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="login-password">Contraseña</Label>
              <Input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={enviando}
              />
            </div>

            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={!puedeEnviar}>
              {enviando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <LogIn className="h-4 w-4" />
              )}
              Entrar
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
