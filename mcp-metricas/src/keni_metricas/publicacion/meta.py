"""Adaptador de PUBLICACION en Meta (Facebook Pages + Instagram).

╔══════════════════════════════════════════════════════════════════════════╗
║  SEGURIDAD — ESTO PUBLICA. LEER ANTES DE TOCAR.                            ║
║                                                                            ║
║  `publicar(borrador, dry_run=True)` corre en DRY-RUN POR DEFECTO.          ║
║   - En dry-run NO se hace NINGUNA peticion de red: se devuelve la(s)       ║
║     peticion(es) EXACTA(S) que se enviarian (`PeticionPublicacion`).       ║
║   - Una peticion REAL (POST) ocurre SOLO si `dry_run=False` Y hay un token ║
║     real configurado. Si falta el token, se lanza error ANTES de tocar la  ║
║     red. Ningun camino alcanzable por defecto o por los tests llega a un    ║
║     endpoint en vivo.                                                       ║
║                                                                            ║
║  Postura del producto: el humano aprueba; nada se publica solo.            ║
╚══════════════════════════════════════════════════════════════════════════╝

Mapeo a Graph API v21.0:
- Facebook Page:
    * solo texto      -> POST /{page_id}/feed        {message}
    * imagen          -> POST /{page_id}/photos       {url, caption}
    * video           -> POST /{page_id}/videos       {file_url, description}
- Instagram (dos pasos, porque IG no publica de un tiro):
    1) POST /{ig_user_id}/media          {image_url|video_url, caption}  -> creation_id
    2) POST /{ig_user_id}/media_publish  {creation_id}                   -> id

El token usado es el de las credenciales de Meta; se admite y se recomienda un
token de System User de Business Manager (`tipo_token == "system_user"`), que no
caduca. Ver docs/credenciales.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

# NO se modifica `_http.py`: se importa de solo lectura.
from ..fuentes._http import cliente_http, log, post_json

# Fuente unica de verdad de la version de Graph API y del tipo de token de
# System User: viven en el adaptador de LECTURA (`fuentes.meta`) y se reexportan
# aqui para no duplicar la version del endpoint ni la constante de credenciales.
from ..fuentes.meta import BASE, TIPO_SYSTEM_USER
from ..schema import Plataforma
from .modelos import Borrador, TipoMedia


@dataclass
class PeticionPublicacion:
    """Una unica peticion HTTP que se enviaria a Graph API.

    Es lo que devuelve el dry-run: el `metodo`, la `url` y el `data` (form-encoded
    que recibiria `post_json`). El `paso` describe su rol (p.ej. "ig_container").
    El token se omite del `data` que se muestra en dry-run para no filtrar
    secretos en logs/consola.
    """

    metodo: str
    url: str
    paso: str
    data: dict = field(default_factory=dict)

    def como_dict(self) -> dict:
        return {"metodo": self.metodo, "url": self.url, "paso": self.paso, "data": dict(self.data)}


@dataclass
class ResultadoPublicacion:
    """Resultado de `publicar(...)`: si fue dry-run, que peticiones se armaron y,
    si fue real, las respuestas de la API."""

    dry_run: bool
    plataforma: Plataforma
    cuenta: str
    peticiones: list[PeticionPublicacion]
    respuestas: list[dict] = field(default_factory=list)
    id_publicacion: str | None = None

    def como_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "plataforma": self.plataforma.value,
            "cuenta": self.cuenta,
            "peticiones": [p.como_dict() for p in self.peticiones],
            "respuestas": self.respuestas,
            "id_publicacion": self.id_publicacion,
        }


class PublicacionNoConfigurada(RuntimeError):
    """Se pidio una publicacion REAL (dry_run=False) sin token configurado."""


class AdaptadorPublicacionMeta:
    """Construye y (opcionalmente) ejecuta las peticiones de publicacion en Meta.

    `publicar(borrador, dry_run=True)` -> `ResultadoPublicacion`.
    Por defecto NO toca la red. Ver el banner de SEGURIDAD del modulo.
    """

    def __init__(self, creds: dict | None = None, cliente: httpx.Client | None = None):
        creds = creds or {}
        self._creds = creds
        self._token = creds.get("access_token")
        self._es_system_user = creds.get("tipo_token") == TIPO_SYSTEM_USER
        # El cliente solo se crea/usa en el camino real. En dry-run no se toca.
        self._cli_externo = cliente
        self._cli = cliente

    # --- disponibilidad -----------------------------------------------------
    def disponible(self) -> bool:
        """Hay token => se PODRIA publicar de verdad. Dry-run no lo necesita."""
        return bool(self._token)

    # --- construccion de peticiones (sin red) -------------------------------
    def peticiones_para(self, borrador: Borrador) -> list[PeticionPublicacion]:
        """Devuelve la(s) peticion(es) EXACTA(S) para el borrador. SIN red.

        Es el corazon del dry-run y tambien lo que el camino real ejecuta. El
        token NO se incluye en `data` aqui (se inyecta justo antes del POST real).
        """
        if borrador.plataforma is Plataforma.facebook:
            return self._peticiones_facebook(borrador)
        if borrador.plataforma is Plataforma.instagram:
            return self._peticiones_instagram(borrador)
        # El modelo ya valida que sea Meta; defensa en profundidad.
        raise ValueError(f"Plataforma no publicable por Meta: {borrador.plataforma.value!r}")

    def _peticiones_facebook(self, b: Borrador) -> list[PeticionPublicacion]:
        texto = b.texto_final()
        # Tomamos el primer asset: una publicacion de feed/photo/video lleva uno.
        media = b.media[0] if b.media else None
        if media is None:
            return [
                PeticionPublicacion(
                    metodo="POST",
                    url=f"{BASE}/{b.cuenta}/feed",
                    paso="fb_feed",
                    data={"message": texto},
                )
            ]
        if media.tipo is TipoMedia.imagen:
            return [
                PeticionPublicacion(
                    metodo="POST",
                    url=f"{BASE}/{b.cuenta}/photos",
                    paso="fb_photo",
                    data={"url": media.url, "caption": texto},
                )
            ]
        # video
        return [
            PeticionPublicacion(
                metodo="POST",
                url=f"{BASE}/{b.cuenta}/videos",
                paso="fb_video",
                data={"file_url": media.url, "description": texto},
            )
        ]

    def _peticiones_instagram(self, b: Borrador) -> list[PeticionPublicacion]:
        # IG exige media. Sin asset no hay publicacion posible.
        if not b.media:
            raise ValueError("Instagram exige media: el borrador no referencia ningun asset")
        media = b.media[0]
        caption = b.texto_final()
        clave_url = "image_url" if media.tipo is TipoMedia.imagen else "video_url"
        contenedor_data = {clave_url: media.url, "caption": caption}
        if media.tipo is TipoMedia.video:
            # IG clasifica el video como REELS en la API actual.
            contenedor_data["media_type"] = "REELS"
        # Paso 1: contenedor. Paso 2: publicar. El creation_id del paso 1 alimenta
        # el paso 2; en dry-run se muestra el placeholder "{creation_id}".
        return [
            PeticionPublicacion(
                metodo="POST",
                url=f"{BASE}/{b.cuenta}/media",
                paso="ig_container",
                data=contenedor_data,
            ),
            PeticionPublicacion(
                metodo="POST",
                url=f"{BASE}/{b.cuenta}/media_publish",
                paso="ig_publish",
                data={"creation_id": "{creation_id}"},
            ),
        ]

    # --- publicacion --------------------------------------------------------
    def publicar(self, borrador: Borrador, dry_run: bool = True) -> ResultadoPublicacion:
        """Publica un borrador. DRY-RUN POR DEFECTO (no toca la red).

        - dry_run=True (defecto): devuelve las peticiones que se enviarian. CERO red.
        - dry_run=False: ejecuta los POST reales. Requiere token; si falta, lanza
          `PublicacionNoConfigurada` ANTES de cualquier llamada de red.
        """
        peticiones = self.peticiones_para(borrador)

        if dry_run:
            log.info(
                "DRY-RUN publicacion %s/%s: %d peticion(es), sin red",
                borrador.plataforma.value,
                borrador.cuenta,
                len(peticiones),
            )
            return ResultadoPublicacion(
                dry_run=True,
                plataforma=borrador.plataforma,
                cuenta=borrador.cuenta,
                peticiones=peticiones,
            )

        # --- camino REAL: solo aqui se toca la red ---------------------------
        if not self.disponible():
            raise PublicacionNoConfigurada(
                "Publicacion real pedida (dry_run=False) pero no hay access_token de Meta. "
                "Configura credenciales.meta o usa dry_run=True."
            )
        if borrador.plataforma is Plataforma.instagram:
            return self._ejecutar_instagram(borrador, peticiones)
        return self._ejecutar_facebook(borrador, peticiones)

    def _cliente(self) -> httpx.Client:
        if self._cli is None:
            self._cli = self._cli_externo or cliente_http()
        return self._cli

    def _ejecutar_facebook(
        self, borrador: Borrador, peticiones: list[PeticionPublicacion]
    ) -> ResultadoPublicacion:
        cli = self._cliente()
        pet = peticiones[0]
        datos = {**pet.data, "access_token": self._token}
        resp = post_json(cli, pet.url, data=datos)
        return ResultadoPublicacion(
            dry_run=False,
            plataforma=borrador.plataforma,
            cuenta=borrador.cuenta,
            peticiones=peticiones,
            respuestas=[resp],
            id_publicacion=resp.get("id") or resp.get("post_id"),
        )

    def _ejecutar_instagram(
        self, borrador: Borrador, peticiones: list[PeticionPublicacion]
    ) -> ResultadoPublicacion:
        cli = self._cliente()
        contenedor, publicar = peticiones[0], peticiones[1]
        # Paso 1: crear contenedor.
        r1 = post_json(cli, contenedor.url, data={**contenedor.data, "access_token": self._token})
        creation_id = r1.get("id")
        if not creation_id:
            raise RuntimeError(f"IG: el contenedor no devolvio creation_id: {r1!r}")
        # Paso 2: publicar el contenedor.
        r2 = post_json(
            cli,
            publicar.url,
            data={"creation_id": creation_id, "access_token": self._token},
        )
        return ResultadoPublicacion(
            dry_run=False,
            plataforma=borrador.plataforma,
            cuenta=borrador.cuenta,
            peticiones=peticiones,
            respuestas=[r1, r2],
            id_publicacion=r2.get("id"),
        )
