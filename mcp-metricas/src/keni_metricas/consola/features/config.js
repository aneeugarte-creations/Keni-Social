// Feature Configuracion — JS vanilla. Solo fetch al endpoint local de guardado.
// Sin librerias ni red externa (coherente con privacidad por diseno).
"use strict";

async function configPostJSON(url, cuerpo) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  let datos = {};
  try {
    datos = await resp.json();
  } catch (e) {
    datos = {};
  }
  return { ok: resp.ok, datos };
}

function configFijarEstado(el, texto, clase) {
  if (!el) return;
  el.textContent = texto || "";
  el.className = "estado" + (clase ? " " + clase : "");
}

function configRecogerFuente(form) {
  const sel = form.querySelector("input[name=fuente]:checked");
  return sel ? sel.value : "";
}

function configRecogerMarcas(form) {
  const marcas = [];
  form.querySelectorAll("input[name=marca]:checked").forEach(function (el) {
    marcas.push(el.value);
  });
  return marcas;
}

async function guardarConfig(form) {
  const estado = form.querySelector(".estado");
  const boton = form.querySelector("button[type=submit]");
  boton.disabled = true;
  configFijarEstado(estado, "Guardando...", "");
  const { ok, datos } = await configPostJSON("/api/config/guardar", {
    fuente: configRecogerFuente(form),
    marcas: configRecogerMarcas(form),
  });
  boton.disabled = false;
  if (ok) {
    configFijarEstado(estado, datos.mensaje || "Configuracion guardada.", "ok");
  } else {
    configFijarEstado(estado, datos.error || "No se pudo guardar.", "error");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("form-config");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      guardarConfig(form);
    });
  }
});
