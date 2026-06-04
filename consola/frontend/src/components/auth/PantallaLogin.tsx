import { Loader2, LogIn } from "lucide-react";
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
  const { iniciarSesion } = useSesion();
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [enviando, setEnviando] = React.useState(false);

  const puedeEnviar = usuario.trim().length > 0 && password.length > 0 && !enviando;

  async function alEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeEnviar) return;
    setEnviando(true);
    setError(null);
    try {
      await iniciarSesion(usuario.trim(), password);
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
