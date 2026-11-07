// Interactividad mínima: campos condicionales del form de movimientos (Alpine) y gráficos (Chart.js).
// El servidor vuelve a validar todo; esto solo muestra u oculta campos.

document.addEventListener("alpine:init", () => {
  Alpine.data("movimientoForm", (idDatosCuentas) => ({
    cuentas: {},
    tipo: "gasto",
    cuenta: "",
    moneda: "ARS",

    init() {
      const datos = document.getElementById(idDatosCuentas);
      this.cuentas = datos ? JSON.parse(datos.textContent) : {};
      const form = this.$el;
      this.tipo = form.querySelector("[name=tipo]:checked")?.value ?? "gasto";
      this.cuenta = form.querySelector("[name=cuenta]")?.value ?? "";
      this.moneda = form.querySelector("[name=moneda]")?.value ?? "ARS";
    },

    elegirCuenta() {
      // Al cambiar de cuenta, la moneda pasa a ser la de la cuenta (como en la versión anterior).
      this.moneda = this.cuentas[this.cuenta]?.moneda ?? this.moneda;
    },

    get necesitaTC() {
      const monedaCuenta = this.cuentas[this.cuenta]?.moneda ?? "ARS";
      return this.moneda === "USD" || this.moneda !== monedaCuenta;
    },

    get admiteCuotas() {
      return this.tipo === "gasto" && this.cuentas[this.cuenta]?.tipo === "tarjeta";
    },
  }));
});

function formatoARS(valor) {
  return "$ " + Number(valor).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function dibujarGraficos() {
  const fuente = document.getElementById("datos-grafico");
  if (!fuente || typeof Chart === "undefined") return;
  const datos = JSON.parse(fuente.textContent);
  Chart.defaults.locale = "es-AR";
  Chart.defaults.aspectRatio = 1.6;
  const tooltip = { callbacks: { label: (ctx) => `${ctx.label}: ${formatoARS(ctx.raw)}` } };

  const dona = document.getElementById("chart-donas");
  if (dona) {
    new Chart(dona, {
      type: "doughnut",
      data: { labels: datos.categorias.etiquetas, datasets: [{ data: datos.categorias.valores }] },
      options: { plugins: { title: { display: true, text: "Gastos por categoría" }, legend: { position: "right" }, tooltip } },
    });
  }

  const barras = document.getElementById("chart-barras");
  if (barras) {
    new Chart(barras, {
      type: "bar",
      data: {
        labels: ["Ingresos", "Gastos"],
        datasets: [{ data: [datos.balance.ingresos, datos.balance.gastos], backgroundColor: ["#16a34a", "#dc2626"] }],
      },
      options: { plugins: { title: { display: true, text: "Balance" }, legend: { display: false }, tooltip } },
    });
  }
}

document.addEventListener("DOMContentLoaded", dibujarGraficos);
