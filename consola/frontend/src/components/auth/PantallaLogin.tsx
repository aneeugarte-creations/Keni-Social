import { Eye, EyeOff, Fingerprint, ShieldCheck } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
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
  const { iniciarSesion, verificarConPasskey, entrarConPasskey } = useSesion();
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [verPassword, setVerPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [enviando, setEnviando] = React.useState(false);
  // Paso 2 (MFA): cuando el backend pide segundo factor, mostramos la ceremonia de passkey en
  // lugar del formulario de usuario/contraseña. La sesión NO existe hasta verificar.
  const [pidiendoMfa, setPidiendoMfa] = React.useState(false);
  // Por defecto la passkey se dispara SOLA al entrar al paso MFA: el usuario no pulsa nada.
  // `mostrarOpciones` se enciende solo si la ceremonia falla/cancela; entonces aparece el
  // botón de reintento (no antes). `autoIntentado` evita re-disparar el auto en cada render.
  const [mostrarOpciones, setMostrarOpciones] = React.useState(false);
  const autoIntentado = React.useRef(false);

  const puedeEnviar = usuario.trim().length > 0 && password.length > 0 && !enviando;

  async function alEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!puedeEnviar) return;
    setEnviando(true);
    setError(null);
    try {
      const { mfaRequerido } = await iniciarSesion(usuario.trim(), password);
      if (mfaRequerido) {
        // Pasamos al paso de la passkey; limpiamos la contraseña de memoria. La ceremonia se
        // dispara SOLA (ver efecto): reseteamos los flags para que el auto-intento arranque.
        autoIntentado.current = false;
        setMostrarOpciones(false);
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

  async function alUsarPasskey(opciones?: { auto?: boolean }) {
    const auto = opciones?.auto ?? false;
    if (enviando) return;
    setEnviando(true);
    setError(null);
    try {
      await verificarConPasskey();
      // En éxito, el provider re-renderiza con la sesión y desmonta esta pantalla.
    } catch (err) {
      // Fallo/cancelación: revelamos el botón para reintentar la ceremonia de passkey.
      setEnviando(false);
      setMostrarOpciones(true);
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof DOMException && err.name === "NotAllowedError") {
        // En el AUTO-disparo el navegador puede rehusar sin un gesto del usuario (p. ej.
        // Safari): no es un error real, solo mostramos el botón para pulsarlo. En un intento
        // MANUAL sí fue una cancelación: mensaje suave.
        if (!auto) {
          setError("Verificación cancelada. Vuelve a intentarlo con tu llave de acceso.");
        }
      } else {
        setError("No se pudo usar la llave de acceso. Vuelve a intentarlo.");
      }
    }
  }

  async function alEntrarPasswordless() {
    if (enviando) return;
    setEnviando(true);
    setError(null);
    try {
      await entrarConPasskey();
      // En éxito, el provider re-renderiza con la sesión y desmonta esta pantalla.
    } catch (err) {
      setEnviando(false);
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        // Cancelado o sin gesto del usuario: no es un fallo real, solo un aviso suave.
        setError("Verificación cancelada. Vuelve a intentarlo o usa tu contraseña.");
      } else if (err instanceof ApiError && err.status === 401) {
        setError("No reconocimos ninguna llave de acceso. Entra con tu contraseña.");
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("No se pudo usar la llave de acceso. Vuelve a intentarlo.");
      }
    }
  }

  // Auto-disparo de la passkey al entrar al paso MFA: en cuanto se pide el segundo factor,
  // lanzamos la ceremonia sola, una sola vez.
  React.useEffect(() => {
    if (pidiendoMfa && !autoIntentado.current) {
      autoIntentado.current = true;
      void alUsarPasskey({ auto: true });
    }
    // `alUsarPasskey` se redefine cada render pero su efecto es idempotente por `autoIntentado`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pidiendoMfa]);

  function volverAlLogin() {
    setPidiendoMfa(false);
    setError(null);
    setMostrarOpciones(false);
    autoIntentado.current = false;
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
              Confirma con tu llave de acceso (Face ID, huella o tu teléfono).
            </p>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
              )}
              {enviando || !mostrarOpciones ? (
                // Por defecto: la passkey se está abriendo SOLA. Solo un indicador; el sistema
                // muestra el diálogo nativo (Face ID / huella / teléfono).
                <div className="flex items-center justify-center gap-2 py-2 text-sm text-muted-foreground">
                  <Spinner className="h-4 w-4" />
                  Esperando tu llave de acceso…
                </div>
              ) : (
                // Solo tras un fallo/cancelación: reintentar la ceremonia de passkey.
                <Button type="button" className="w-full" onClick={() => alUsarPasskey()}>
                  <Fingerprint className="h-4 w-4" />
                  Usar mi llave de acceso
                </Button>
              )}
            </div>
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
    <div className="flex min-h-dvh w-full items-center justify-center bg-background px-6">
      <div className="w-full max-w-sm">
        <h1 className="mb-14 text-center text-2xl font-light uppercase text-foreground">
          {/* El `tracking` añade espacio TRAS la última letra; con `text-center` eso descentra
              el wordmark. Lo aislamos en un inline-block y anulamos ese sobrante con un margen
              derecho negativo igual al tracking → KENI queda centrado EXACTO sobre el formulario. */}
          <span className="inline-block tracking-[0.3em] [margin-right:-0.3em]">KENI</span>
        </h1>
        <form className="space-y-9" onSubmit={alEnviar} noValidate>
          <div className="space-y-3">
            <Label
              htmlFor="login-usuario"
              className="text-xs font-light text-foreground"
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
              className="h-9 rounded-none border-x-0 border-t-0 border-b border-input bg-transparent px-0 text-foreground shadow-none transition-colors focus-visible:border-foreground focus-visible:ring-0"
            />
          </div>
          <div className="space-y-3">
            <Label
              htmlFor="login-password"
              className="text-xs font-light text-foreground"
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
                className="h-9 rounded-none border-x-0 border-t-0 border-b border-input bg-transparent px-0 pr-9 text-foreground shadow-none transition-colors focus-visible:border-foreground focus-visible:ring-0"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setVerPassword((v) => !v)}
                disabled={enviando}
                aria-pressed={verPassword}
                aria-label={verPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                {/* El icono refleja el ESTADO actual: oculta = ojo tachado (EyeOff), visible =
                    ojo abierto (Eye). Así por defecto se ve claramente que la contraseña NO se ve. */}
                {verPassword ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
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
            className="mt-3 h-11 w-full rounded-md border-foreground text-xs uppercase tracking-[0.28em] text-foreground shadow-none"
          >
            {enviando ? <Spinner className="h-4 w-4" /> : "Entrar"}
          </Button>

          {/* Atajo passwordless: la contraseña sigue siendo la base; esto entra directo con la
              llave de acceso (Face ID, huella o teléfono) sin teclear contraseña. */}
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            <span className="uppercase tracking-[0.2em]">o</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <Button
            type="button"
            variant="ghost"
            disabled={enviando}
            onClick={alEntrarPasswordless}
            className="h-11 w-full rounded-md text-xs uppercase tracking-[0.28em] text-muted-foreground hover:text-foreground"
          >
            <Fingerprint className="h-4 w-4" />
            Entrar con llave de acceso
          </Button>
        </form>
      </div>
    </div>
  );
}
