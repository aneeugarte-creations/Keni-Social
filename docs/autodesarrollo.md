# Auto-desarrollo del buzón de sugerencias (#109)

> **⚠️ FUNCIÓN PELIGROSA. Apagada por defecto.** Cuando se activa, la consola puede
> **implementar una sugerencia con IA y mergearla sola a `main`**. Hay un suelo de
> seguridad de 6 gates, pero el **riesgo residual existe**: revisa siempre lo que se
> mergea y desactívala al terminar. Lee la sección «Riesgo residual» antes de activarla.

El **buzón de sugerencias** (página *Sugerencias*, grupo *Ajustes*) siempre ha servido
para que el equipo deje ideas y mejoras. El **auto-desarrollo** cierra el lazo que
faltaba: que la propia consola **implemente** una de esas sugerencias con `claude -p` y,
**solo si todo pasa**, la **mergee a `main`**. Por defecto el lazo está **DESACTIVADO**:
sin activarlo, el buzón se comporta como siempre (solo recoge sugerencias).

---

## Los 6 gates de seguridad (suelo innegociable)

Ningún camino mergea sin **todos** estos gates. Si cualquiera no se cumple, la sugerencia
queda **parked** (necesita revisión humana) o **rechazada**, y se registra en la auditoría.

1. **Default OFF + kill switch.** El lazo vive tras un flag apagado por defecto. Se activa
   con la variable de entorno `KENI_AUTODESARROLLO=1` (kill switch en caliente, manda
   sobre todo) o guardándolo desde la UI (config local `autodesarrollo.toml`). Con el flag
   OFF, disparar una implementación responde 409 y no se hace nada.
2. **Ejecución aislada.** Cada sugerencia se implementa en un **git worktree efímero** en
   una carpeta temporal del sistema, **nunca** en el árbol vivo ni en el repo del operador.
   El worktree se borra siempre al terminar (éxito o fallo).
3. **CI-verde-o-no-merge.** Tras generar, se corre el **mirror local de CI** (comando del
   operador en `KENI_AUTODESARROLLO_CI`). Solo si **todo pasa en verde** se mergea; si la
   CI falla —o si no hay mirror configurado— la sugerencia queda **parked**.
4. **Caps de alcance.** Si el diff toca **rutas sensibles** se **rechaza** (nunca mergea):
   `secretos*`, persistencia base (`db.py`/`ficheros.py`/`repos.py`/`estados.py`/
   `indice.py`), credenciales/auth (`conexiones`, `asistente.py`), `.github/`,
   `keni-shared/`, y dependencias (`pyproject.toml`, locks). Hay además un **cap de tamaño**
   de diff (`KENI_AUTODESARROLLO_CAP_LINEAS`, 400 líneas por defecto): si lo supera, parked.
5. **Sin secretos.** El `claude -p` lanzado recibe un **entorno saneado** (se eliminan
   `*_API_KEY`, `*_TOKEN`, `*_SECRET`, `KENI_CONSOLA_SECRETOS`, tokens de git, etc.) y su
   cwd es el clon efímero, que **no contiene `secretos.toml`** (ese vive en `~/.config`).
6. **Kill switch + auditoría.** El flag desactiva el lazo en caliente; cada intento se
   escribe en un **log de auditoría persistente** (`autodesarrollo-auditoria.jsonl`) con
   sugerencia → rama/worktree → resultado de CI → estado final (mergeado/parked/rechazado)
   y su **SHA o motivo**.

---

## Cómo se activa

Por seguridad, la activación es **deliberada**:

- **Desde la UI** (recomendado): abre *Sugerencias*, en el panel *Auto-desarrollo* pulsa
  **Activar**, marca la casilla **«Entiendo el riesgo»** y confirma. Para implementar una
  idea concreta, usa **«Implementar con IA»** en su tarjeta. El resultado (mergeado /
  parked / rechazado) aparece en la **auditoría reciente** del panel.
- **Por entorno** (kill switch): arranca la consola con `KENI_AUTODESARROLLO=1` (o `0`
  para forzar el apagado). El entorno **manda sobre la config**; con el flag fijado por
  entorno, la UI no puede cambiarlo y lo advierte.
- **Mirror de CI** (obligatorio para que algo pueda mergear): define el comando del mirror
  local en `KENI_AUTODESARROLLO_CI`. **Sin él, el CI se trata como NO verde** y nunca se
  mergea por accidente. Ejemplo (ajústalo a tu entorno):

  ```
  export KENI_AUTODESARROLLO_CI='cd consola && ruff check . && pytest -q'
  ```

### Variables de entorno

| Variable | Para qué | Por defecto |
| --- | --- | --- |
| `KENI_AUTODESARROLLO` | Flag global (kill switch). `1`/`0`. | sin fijar (usa config) |
| `KENI_AUTODESARROLLO_CI` | Comando del mirror local de CI. | sin fijar → CI no verde |
| `KENI_AUTODESARROLLO_CAP_LINEAS` | Cap de líneas de diff. | `400` |
| `KENI_AUTODESARROLLO_REPO` | Raíz del repo a usar. | autodetección (`.git`) |
| `KENI_AUTODESARROLLO_CONFIG` | Ruta del `autodesarrollo.toml`. | `~/.config/keni-social/` |
| `KENI_AUTODESARROLLO_AUDITORIA` | Ruta del log de auditoría JSONL. | `~/.config/keni-social/` |

---

## Estados de un intento

- **mergeada** — generada, diff seguro, CI verde y fast-forward a `main`. Lleva el **SHA**.
- **parked** — generada pero algo no llegó al listón (CI roja, sin cambios, supera el cap,
  fallo del asistente o del merge): **necesita revisión humana**. No se mergea.
- **rechazada** — el diff tocó **rutas sensibles**: viola el alcance, no se mergea.
- **bloqueada** — el flag estaba OFF: no se intentó nada.
- **error** — fallo inesperado (git/CI). Nunca mergea.

---

## Riesgo residual (léelo)

Los gates reducen el riesgo, **no lo eliminan**:

- **El merge es real.** Con el flag activo y la CI en verde, el lazo hace `git push
  origin HEAD:main` **sin intervención humana**. La calidad del cambio depende del modelo
  y de la cobertura de tu mirror de CI: una CI floja deja pasar cambios flojos.
- **El cap de alcance es por ruta y tamaño, no semántico.** Un cambio dentro del alcance
  permitido puede aun así ser indeseable; revísalo.
- **El mirror local no es la CI remota.** Si tu mirror difiere de lo que valida el equipo,
  «verde» local no garantiza «verde» en remoto.
- **Recomendación.** Actívalo solo durante sesiones supervisadas, con un mirror de CI
  estricto, y **desactívalo al terminar**. Trata la auditoría como un registro a revisar.

La lógica vive en `consola/src/keni_consola/autodesarrollo.py` (dominio, con los 6 gates)
y `consola/src/keni_consola/api/autodesarrollo.py` (HTTP). Los tests
(`consola/tests/test_autodesarrollo.py`, `test_api_autodesarrollo.py`) verifican los gates
**sin** llamar a `claude`, sin git real y sin tocar `main`.
