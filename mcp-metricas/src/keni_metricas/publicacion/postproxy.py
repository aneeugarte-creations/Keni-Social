"""Adaptador de PUBLICACION / PROGRAMACION via **Postproxy** (canal alternativo).

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ESTO PUBLICA. LEER ANTES DE TOCAR.                            ║
║                                                                            ║
║  `programar(borrador, dry_run=True)` corre en DRY-RUN POR DEFECTO,         ║
║   EXACTAMENTE como el adaptador de Metricool:                              ║
║   - En dry-run NO se hace NINGUNA petición de red: se devuelve la petición ║
║     EXACTA que se enviaría (`PeticionProgramada`), con el cuerpo completo  ║
║     pero SIN la api_key (que va en la cabecera `Authorization: Bearer`,    ║
║     NUNCA en el body ni en params).                                        ║
║   - Una petición REAL (POST) ocurre SOLO si `dry_run=False` Y hay api_key. ║
║     Si falta, se lanza `ProgramacionNoConfigurada` ANTES de tocar la red.  ║
║                                                                            ║
║  El GATE de publicación real es el MISMO que el de Metricool: el parámetro ║
║  `dry_run`. Quien orquesta (la Consola: `programador.py`) lo deriva de     ║
║  `KENI_PUBLICAR_REAL` y se lo pasa a este adaptador. Este módulo NO lee esa║
║  env por su cuenta (igual que `publicacion.metricool`): respeta el flag    ║
║  vía el `dry_run` que recibe.                                              ║
╚══════════════════════════════════════════════════════════════════════════╝

Contrato de la API (Postproxy, header `Authorization: Bearer <api_key>`):

    POST /api/posts
    Body:
      {
        "post": {"body": "...", "scheduled_at": "2026-..Z"|omitido, "draft": bool},
        "profiles": ["<profile_id o platform>", ...],
        "media": ["https://..."]
      }

Mapeo `Borrador` -> body:
  - `post.body`     = `borrador.texto_final()` (texto + hashtags).
  - `post.scheduled_at` = ISO-8601 UTC si hay `publicar_en`; si no, se OMITE
    (Postproxy publica de inmediato al recibirlo).
  - `post.draft`    = `borrador.borrador` (guardar como borrador sin publicar).
  - `profiles`      = lista de profile_ids de Postproxy o, en su defecto, nombres de
    plataforma (Postproxy acepta ambos). Por defecto `[borrador.cuenta]`; el llamante
    (el programador) puede pasar VARIOS via el parámetro `profiles=`.
  - `media`         = URLs de `borrador.media` (solo URL; nunca binarios).

Resultado (`ResultadoProgramacion`, el MISMO tipo que devuelve el adaptador de
Metricool, para que el programador consuma `id_post`/`redes`/`estados` por un único
camino): en dry-run trae la `peticion` exacta (sin api_key) y `estados={}`; en el camino
real parsea la respuesta para extraer el `id` del post (alias `id`/`post_id`/`data.id`) y
los estados por perfil (o, si la respuesta no los trae, marca cada perfil "programado").

REUTILIZA `Borrador`, `MediaRef`, `PeticionProgramada`, `ResultadoProgramacion` y
`ProgramacionNoConfigurada` de los modelos / del adaptador de Metricool (NO se duplican).
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ..fuentes._http import cliente_http, log, post_json
from .metricool import (
    PeticionProgramada,
    ProgramacionNoConfigurada,
    ResultadoProgramacion,
)
from .modelos import Borrador

BASE = "https://api.postproxy.dev/api"
ENDPOINT_PUBLICAR = "/posts"

# Estado por defecto de un perfil cuando la respuesta de Postproxy no desglosa estados.
ESTADO_DEFECTO = "programado"


def _parsear_id_post(resp: object) -> str | None:
    """Extrae el id del post creado de la respuesta de Postproxy (alias defensivos).

    Acepta `id`/`post_id` en la raíz, o anidados bajo `data`/`post`. None si no aparece.
    """
    if not isinstance(resp, dict):
        return None
    for contenedor in (resp, resp.get("data"), resp.get("post")):
        if not isinstance(contenedor, dict):
            continue
        for clave in ("id", "post_id", "postId"):
            valor = contenedor.get(clave)
            if valor not in (None, ""):
                return str(valor)
    return None


def _parsear_estados(resp: object, profiles: list[str]) -> dict[str, str]:
    """Mapa perfil/red -> estado a partir de la respuesta; default `programado` por perfil.

    Si la respuesta trae una lista de perfiles con su estado (`profiles`/`results`/`posts`
    con `platform`/`profile`/`status`), se usa; si no, se marca cada `profiles` solicitado
    como `programado` (entrega aceptada, sin desglose). Parseo DEFENSIVO: nunca lanza.
    """
    estados: dict[str, str] = {}
    contenedor = resp if isinstance(resp, dict) else {}
    lista: object = None
    for clave in ("profiles", "results", "posts", "data"):
        valor = contenedor.get(clave)
        if isinstance(valor, list):
            lista = valor
            break
    if isinstance(lista, list):
        for el in lista:
            if not isinstance(el, dict):
                continue
            clave = None
            for k in ("platform", "profile", "profile_id", "network", "name"):
                v = el.get(k)
                if v not in (None, ""):
                    clave = str(v)
                    break
            if clave is None:
                continue
            estado = el.get("status") or el.get("state") or ESTADO_DEFECTO
            estados[clave] = str(estado)
    if not estados:
        # Sin desglose: la entrega se aceptó; marcamos cada perfil solicitado.
        estados = {p: ESTADO_DEFECTO for p in profiles}
    return estados


class AdaptadorPublicacionPostproxy:
    """Construye y (opcionalmente) ejecuta la publicación de un borrador via Postproxy.

    MISMA forma de resultado que `AdaptadorPublicacionMetricool.programar`
    (`ResultadoProgramacion`): dry-run por defecto, nunca toca la red salvo
    `dry_run=False` + api_key presente.

    Credencial: una `api_key` GLOBAL (header Bearer). A qué destino(s) va el post lo
    decide el `Borrador` (`cuenta`) o el parámetro `profiles=` (múltiples perfiles).
    """

    def __init__(self, api_key: str | None = None, cliente: httpx.Client | None = None):
        self._api_key = str(api_key or "")
        self._cli_externo = cliente
        self._cli = cliente

    # --- disponibilidad -----------------------------------------------------
    def disponible(self) -> bool:
        """Hay api_key => se PODRÍA publicar de verdad. Dry-run no la necesita."""
        return bool(self._api_key)

    # --- construcción del cuerpo (sin red) ----------------------------------
    def _profiles_de(self, b: Borrador, profiles: list[str] | None) -> list[str]:
        """Perfiles destino: los explícitos (no vacíos) o, por defecto, `[b.cuenta]`."""
        if profiles:
            limpios = [str(p).strip() for p in profiles if str(p).strip()]
            if limpios:
                return limpios
        return [b.cuenta]

    def cuerpo_para(self, b: Borrador, profiles: list[str] | None = None) -> dict:
        """Construye el body EXACTO de `POST /api/posts` para el borrador. SIN red.

        `profiles`: lista de profile_ids/plataformas destino. Por defecto `[b.cuenta]`.
        """
        # `Borrador` (Meta) no trae `borrador`/`publicar_en`; un `BorradorMetricool` u
        # otro modelo compatible sí. Se leen con getattr para aceptar ambos sin acoplar.
        post: dict = {"body": b.texto_final(), "draft": bool(getattr(b, "borrador", False))}
        # `scheduled_at`: ISO-8601 UTC con sufijo Z. Si el borrador no agenda, se OMITE.
        cuando = getattr(b, "publicar_en", None)
        if cuando is not None:
            if cuando.tzinfo is not None:
                cuando = cuando.astimezone(UTC)
            else:
                cuando = cuando.replace(tzinfo=UTC)
            post["scheduled_at"] = (
                cuando.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            )
        cuerpo: dict = {"post": post, "profiles": self._profiles_de(b, profiles)}
        if b.media:
            cuerpo["media"] = [m.url for m in b.media]
        return cuerpo

    def peticion_para(
        self, b: Borrador, profiles: list[str] | None = None
    ) -> PeticionProgramada:
        return PeticionProgramada(
            metodo="POST",
            url=f"{BASE}{ENDPOINT_PUBLICAR}",
            params={},
            body=self.cuerpo_para(b, profiles),
        )

    # --- programación -------------------------------------------------------
    def programar(
        self,
        borrador: Borrador,
        *,
        dry_run: bool = True,
        profiles: list[str] | None = None,
    ) -> ResultadoProgramacion:
        """Programa/publica un borrador via Postproxy. DRY-RUN POR DEFECTO (no toca red).

        - dry_run=True (defecto): devuelve `ResultadoProgramacion(dry_run=True, …)` con la
          `peticion` EXACTA que se enviaría. CERO red. El body NO incluye la api_key
          (viaja en la cabecera, que solo se añade en el POST real).
        - dry_run=False: ejecuta el POST real. Requiere api_key; si falta, lanza
          `ProgramacionNoConfigurada` ANTES de cualquier llamada de red. Parsea la
          respuesta para `id_post` + `estados` por perfil.

        `redes` = la lista de perfiles destino (lo que viaja en `profiles`).
        """
        peticion = self.peticion_para(borrador, profiles)
        redes = list(peticion.body.get("profiles") or [])

        if dry_run:
            log.info("DRY-RUN publicación Postproxy: 1 petición, sin red")
            return ResultadoProgramacion(dry_run=True, redes=redes, peticion=peticion)

        # --- camino REAL: solo aquí se toca la red ---------------------------
        if not self.disponible():
            raise ProgramacionNoConfigurada(
                "Publicación real pedida (dry_run=False) pero falta la API key de "
                "Postproxy. Configúrala o usa dry_run=True."
            )
        cli = self._cliente()
        resp = post_json(
            cli,
            peticion.url,
            json=peticion.body,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        id_post = _parsear_id_post(resp)
        estados = _parsear_estados(resp, redes)
        return ResultadoProgramacion(
            dry_run=False,
            redes=redes,
            peticion=peticion,
            respuesta=resp if isinstance(resp, dict) else None,
            id_post=id_post,
            estados=estados,
        )

    def _cliente(self) -> httpx.Client:
        if self._cli is None:
            self._cli = self._cli_externo or cliente_http(
                timeout=httpx.Timeout(60.0, connect=10.0)
            )
        return self._cli
