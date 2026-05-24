// Metricas — JS propio de la feature (comparar periodos + descargas md/json).
// Vanilla, sin librerias ni red externa (privacidad por diseno). El dashboard
// embebido y el enlace CSV los maneja consola.js; aqui solo anadimos lo nuevo.
"use strict";

// Etiquetas legibles de cada metrica para la tabla comparativa.
var CMP_ETIQUETAS = {
  visualizaciones: "Visualizaciones",
  alcance: "Alcance",
  interacciones: "Interacciones",
  engagement_pct: "Engagement",
};

// Separador de miles estilo es-MX (punto), coherente con el reporte/dashboard.
function cmpMiles(n) {
  if (typeof n !== "number") return String(n);
  if (!Number.isInteger(n)) return String(n) + "%";
  return n.toLocaleString("es-MX");
}

// Texto de la diferencia segun la metrica (engagement va en puntos, %).
function cmpDiferencia(fila) {
  if (fila.metrica === "engagement_pct") {
    var pts = fila.diferencia;
    return (pts > 0 ? "+" : "") + pts + " pts";
  }
  var d = fila.diferencia;
  return (d > 0 ? "+" : "") + cmpMiles(d);
}

function cmpClase(valor) {
  if (valor > 0) return "cmp-sube";
  if (valor < 0) return "cmp-baja";
  return "cmp-neutra";
}

// Construye una <table> comparativa a partir de la lista de metricas.
function cmpTabla(metricas, etiquetaA, etiquetaB) {
  var filas = metricas
    .map(function (m) {
      var et = CMP_ETIQUETAS[m.metrica] || m.metrica;
      var valA = m.metrica === "engagement_pct" ? m.a + "%" : cmpMiles(m.a);
      var valB = m.metrica === "engagement_pct" ? m.b + "%" : cmpMiles(m.b);
      var dif = cmpDiferencia(m);
      var varPct = (m.variacion_pct > 0 ? "+" : "") + m.variacion_pct + "%";
      var clase = cmpClase(m.diferencia);
      return (
        "<tr><td>" +
        et +
        "</td><td>" +
        valA +
        "</td><td>" +
        valB +
        '</td><td class="' +
        clase +
        '">' +
        dif +
        '</td><td class="' +
        clase +
        '">' +
        varPct +
        "</td></tr>"
      );
    })
    .join("");
  return (
    '<table class="cmp-tabla"><thead><tr>' +
    "<th>Metrica</th><th>" +
    escaparHtml(etiquetaA) +
    " (A)</th><th>" +
    escaparHtml(etiquetaB) +
    " (B)</th><th>Diferencia</th><th>Variacion</th>" +
    "</tr></thead><tbody>" +
    filas +
    "</tbody></table>"
  );
}

// Escape minimo para textos que van al DOM via innerHTML.
function escaparHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Pinta la comparativa (total + por marca) en el contenedor.
function cmpRender(datos) {
  var cont = document.getElementById("cmp-resultado");
  if (!cont) return;
  var partes = [];
  partes.push("<h3>Total consolidado</h3>");
  partes.push(cmpTabla(datos.total.metricas, datos.etiqueta_a, datos.etiqueta_b));

  if (datos.por_marca && datos.por_marca.length) {
    partes.push("<h3>Por marca</h3>");
    datos.por_marca.forEach(function (marca) {
      partes.push("<h3>" + escaparHtml(marca.marca) + "</h3>");
      partes.push(cmpTabla(marca.comparativa, datos.etiqueta_a, datos.etiqueta_b));
    });
  }
  cont.innerHTML = partes.join("");
}

// Pide la comparativa al endpoint local y la pinta.
function compararPeriodos() {
  var cont = document.getElementById("cmp-resultado");
  var marcaSel = document.getElementById("cmp-marca");
  var rangoA = document.getElementById("cmp-rango-a");
  var rangoB = document.getElementById("cmp-rango-b");
  if (!cont || !rangoA || !rangoB) return;

  var params = new URLSearchParams();
  params.set("rango_a", rangoA.value);
  params.set("rango_b", rangoB.value);
  if (marcaSel && marcaSel.value) params.set("marca", marcaSel.value);

  cont.innerHTML = '<p class="cmp-vacio">Comparando...</p>';
  fetch("/metricas/comparar.json?" + params.toString())
    .then(function (resp) {
      return resp.json().then(function (datos) {
        return { ok: resp.ok, datos: datos };
      });
    })
    .then(function (r) {
      if (r.ok && !r.datos.error) {
        cmpRender(r.datos);
      } else {
        cont.innerHTML =
          '<p class="cmp-error">' +
          escaparHtml(r.datos.error || "No se pudo comparar.") +
          "</p>";
      }
    })
    .catch(function () {
      cont.innerHTML = '<p class="cmp-error">No se pudo comparar.</p>';
    });
}

// Mantiene los enlaces de descarga md/json en sintonia con marca/rango (igual
// que consola.js hace con el CSV). Re-leemos los selectores en cada cambio.
function actualizarDescargas() {
  var marcaSel = document.getElementById("sel-marca");
  var rangoSel = document.getElementById("sel-rango");
  var params = new URLSearchParams();
  params.set("rango", rangoSel ? rangoSel.value : "mes");
  if (marcaSel && marcaSel.value) params.set("marca", marcaSel.value);
  var sufijo = "?" + params.toString();
  var md = document.getElementById("enlace-md");
  var json = document.getElementById("enlace-json");
  if (md) md.href = "/metricas/export.md" + sufijo;
  if (json) json.href = "/metricas/export.json" + sufijo;
}

document.addEventListener("DOMContentLoaded", function () {
  var btn = document.getElementById("btn-comparar");
  if (btn) btn.addEventListener("click", compararPeriodos);

  var marcaSel = document.getElementById("sel-marca");
  var rangoSel = document.getElementById("sel-rango");
  if (marcaSel) marcaSel.addEventListener("change", actualizarDescargas);
  if (rangoSel) rangoSel.addEventListener("change", actualizarDescargas);
  actualizarDescargas();
});
