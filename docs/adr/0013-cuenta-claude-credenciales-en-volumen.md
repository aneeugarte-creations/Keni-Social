# ADR 0013 — Cuenta de Claude gestionable desde el panel (credenciales en /data)

- **Estado:** Aceptado (implementado)
- **Fecha:** 2026-06-15
- **Decisores:** equipo keni-social
- **Componente:** `keni-consola` (`cuenta_claude.py`, `control.py`, `daemons.py`, `api/sistema/cuenta.py`, frontend `pages/sistema/SeccionCuentaClaude.tsx`), `deploy/` (`docker-compose.yml`, `deploy.sh`, `.env.example`)
- **Relación:** la generación corre `claude -p` con la cuenta de la máquina (ADR 0001); esto define CÓMO se configura y se cambia esa cuenta. Se apoya en el split de procesos (back encola / worker+daemons ejecutan, ADR 0002 Fase B/Fase 3).

---

## Contexto

La cuenta de Claude del servidor se configuraba por un token OAuth inyectado por entorno
desde un secreto del host. Problemas:

1. **Cambiar de cuenta era una operación de host:** editar el secreto + reiniciar
   `worker`+`daemons` (el token solo se leía al arrancar el proceso). No había forma desde la
   consola.
2. **El medidor de uso no estaba disponible.** Verificado en el servidor (claude 2.1.173):
   con un token por entorno, `claude -p /usage` devuelve solo una frase genérica; el medidor
   detallado (sesión 5 h / semana) **solo aparece con auth por credenciales** (`claude auth
   login`). Con login de suscripción, `claude -p /usage` sí imprime el medidor completo.
3. El `back` **no tiene `claude`** (solo encola): no puede ejecutar auth/login/logout/usage.

El CLI sí ofrece lo necesario (verificado): `claude auth status --json`
(`{loggedIn, authMethod, apiProvider}`; no da email), `claude auth login
[--claudeai|--console] [--email] [--sso]` (imprime una URL, lee el código por stdin),
`claude auth logout`, y `claude -p /usage` (medidor, con auth por credenciales).

## Decisión

1. **Credenciales en el volumen COMPARTIDO `/data`, como ÚNICA fuente de la cuenta.**
   `CLAUDE_CONFIG_DIR=/data/claude-cfg` en `worker` y `daemons` (mismo volumen `keni-data`).
   La cuenta se fija con `claude auth login` desde el panel; las credenciales que escribe las
   releen **ambos** procesos en cada invocación, así que cambiar de cuenta aplica **en
   caliente, sin reiniciar**. No se inyecta token por entorno (antes `claude` escribía en
   `$HOME/.claude`, en el overlay EFÍMERO del contenedor, no compartido). `ANTHROPIC_API_KEY`
   queda como alternativa OPCIONAL por API key (vacía por defecto).
2. **Listener de control en `daemons`.** El cambio de cuenta ejecuta `claude`; el `back` no
   lo tiene. El `daemons` (imagen del worker, con `claude`; **instancia única**, no escala
   como el worker) levanta un Starlette mínimo (`control.py`) en la red interna, protegido por
   `KENI_CONTROL_BEARER`. El login interactivo (URL → pegar código) mantiene un proceso
   `claude auth login` vivo en un **PTY** entre dos peticiones (`cuenta_claude.py`).
3. **El `back` proxea, admin-gated.** `/api/sistema/cuenta/*` exige sesión admin y reenvía al
   control con el bearer. Sin bearer configurado, la sección degrada a "no configurada".
4. **`/usage` como medidor.** Se parsea la salida de `claude -p /usage` a campos
   estructurados (sesión / semana / Sonnet, con sus resets). La identidad de la cuenta
   (email/org) NO la expone el CLI por ningún medio headless: no se muestra.

## Consecuencias

- **+** Cambiar de cuenta sin SSH ni reinicio; medidor de uso real en el panel.
- **+** Credenciales persistentes (sobreviven a recreate de contenedor) y compartidas; la
  cuenta se fija por login, no por secreto del host.
- **−** `worker` y `daemons` comparten el config dir de `claude` en `/data`. `claude` ya
  tolera procesos concurrentes (el worker corre `KENI_MAX_JOBS` en paralelo); añadir
  `daemons` es bajo riesgo. El refresco de credenciales OAuth escribe el fichero: si diera
  problemas de carrera, aislar el config dir por proceso y compartir solo `.credentials.json`.
- **Riesgo no cubierto por CI:** el handshake del PTY de `claude auth login` (parseo de URL +
  envío de código) se validó en un contenedor local con una cuenta de prueba; no es
  ejercitable en CI sin una cuenta real.
- **Apagado por defecto:** sin `KENI_CONTROL_BEARER`, el listener no se monta y la sección
  degrada a "no configurada".
