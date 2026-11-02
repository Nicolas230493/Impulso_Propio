import { cargarMetas } from './dataService.js';
import { dinero, esc, enARS, totales, gastosPorCategoria, delMes, saldoCuenta, sumarMesesAMes } from './utils.js';

let chartDonas, chartBarras;

const TIPOS_CUENTA = { efectivo: 'Efectivo', tarjeta: 'Tarjeta', transferencia: 'Transferencia' };

const nombreCuenta = (cuentas, id) => cuentas.find(c => c.id === id)?.nombre ?? '—';
const etiquetaCuenta = c => `${c.nombre}${c.moneda === 'USD' ? ' (USD)' : ''}`;

export function inicializarGraficos() {
    chartDonas = new Chart(document.getElementById('chart-donas'), {
        type: 'doughnut',
        data: { labels: [], datasets: [{ data: [] }] },
        options: { plugins: { title: { display: true, text: 'Gastos por Categoría' } } }
    });

    chartBarras = new Chart(document.getElementById('chart-barras'), {
        type: 'bar',
        data: { labels: ['Ingresos', 'Gastos'], datasets: [{ data: [] }] },
        options: { plugins: { title: { display: true, text: 'Balance' }, legend: { display: false } } }
    });
}

export function actualizarGraficos(transacciones) {
    const porCategoria = gastosPorCategoria(transacciones);
    const { ingresos, gastos } = totales(transacciones);

    chartDonas.data.labels = Object.keys(porCategoria);
    chartDonas.data.datasets[0].data = Object.values(porCategoria);
    chartDonas.update();

    chartBarras.data.datasets[0].data = [ingresos, gastos];
    chartBarras.update();
}

export function actualizarResumenFinanciero(transacciones) {
    const { ingresos, gastos } = totales(transacciones);
    document.getElementById('total-ingresos').textContent = dinero(ingresos);
    document.getElementById('total-gastos').textContent = dinero(gastos);
    document.getElementById('saldo-total').textContent = dinero(ingresos - gastos);
}

export function renderizarTablaTransacciones(transacciones, cuentas) {
    const tbody = document.getElementById('transacciones-body');
    if (!tbody) return;

    tbody.innerHTML = transacciones.map(t => `
        <tr class="border-b">
            <td class="p-2 text-sm whitespace-nowrap">${esc(t.fecha)}</td>
            <td class="p-2 text-sm">
                <span class="px-2 py-1 rounded text-white text-xs ${t.tipo === 'ingreso' ? 'bg-green-500' : 'bg-red-500'}">
                    ${t.tipo.toUpperCase()}
                </span>
            </td>
            <td class="p-2 text-sm">${esc(t.categoria)}</td>
            <td class="p-2 text-sm">${esc(nombreCuenta(cuentas, t.cuenta_id))}</td>
            <td class="p-2 text-sm">${esc(t.descripcion) || '-'}</td>
            <td class="p-2 text-sm font-bold whitespace-nowrap ${t.tipo === 'ingreso' ? 'text-green-600' : 'text-red-600'}">
                ${dinero(t.monto, t.moneda)}
                ${t.moneda === 'USD' ? `<div class="text-xs font-normal text-gray-500">${dinero(enARS(t))} · TC ${esc(t.tipo_cambio)}</div>` : ''}
            </td>
            <td class="p-2">
                <button data-id="${esc(t.id)}" data-grupo="${esc(t.grupo_id)}" data-cuotas="${esc(t.cuotas)}"
                    class="btn-eliminar-trans text-red-500 hover:underline text-sm">Eliminar</button>
            </td>
        </tr>
    `).join('');
}

// Alerta al 80 % y 100 % del tope mensual, siempre sobre el mes en curso.
export function renderizarAlertaPresupuesto(transacciones, categorias, mes) {
    const alerta = document.getElementById('budget-alert');
    const gastado = gastosPorCategoria(delMes(transacciones, mes));

    const avisos = categorias
        .filter(c => Number(c.tope_mensual) > 0)
        .map(c => ({ c, gastado: gastado[c.nombre] || 0, pct: (gastado[c.nombre] || 0) / Number(c.tope_mensual) * 100 }))
        .filter(a => a.pct >= 80)
        .sort((a, b) => b.pct - a.pct);

    if (!avisos.length) {
        alerta.classList.add('hidden');
        return;
    }

    const superado = avisos[0].pct >= 100;
    alerta.className = `mb-4 p-4 rounded font-semibold ${superado ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'}`;
    alerta.innerHTML = avisos.map(a => `
        <div>${a.pct >= 100 ? '🔴 Tope superado' : '🟡 Cerca del tope'} en ${esc(a.c.nombre)}:
        ${a.pct.toFixed(0)}% (${dinero(a.gastado)} de ${dinero(a.c.tope_mensual)})</div>
    `).join('');
}

function variacion(actual, anterior) {
    if (!anterior) return actual ? '<span class="text-gray-500">nuevo</span>' : '—';
    const pct = (actual - anterior) / anterior * 100;
    return `<span class="${pct > 0 ? 'text-red-600' : 'text-green-600'}">${pct > 0 ? '+' : ''}${pct.toFixed(0)}%</span>`;
}

export function renderizarReportes(transacciones, mes) {
    const anterior = sumarMesesAMes(mes, -1);
    const actual = gastosPorCategoria(delMes(transacciones, mes));
    const previo = gastosPorCategoria(delMes(transacciones, anterior));
    const categorias = [...new Set([...Object.keys(actual), ...Object.keys(previo)])]
        .sort((a, b) => (actual[b] || 0) - (actual[a] || 0));
    const totalActual = Object.values(actual).reduce((a, b) => a + b, 0);
    const totalPrevio = Object.values(previo).reduce((a, b) => a + b, 0);

    document.getElementById('reporte-categorias').innerHTML = categorias.map(c => `
        <tr class="border-b">
            <td class="p-2">${esc(c)}</td>
            <td class="p-2 text-right">${dinero(actual[c] || 0)}</td>
            <td class="p-2 text-right">${dinero(previo[c] || 0)}</td>
            <td class="p-2 text-right">${variacion(actual[c] || 0, previo[c] || 0)}</td>
        </tr>
    `).join('') + `
        <tr class="font-bold">
            <td class="p-2">Total</td>
            <td class="p-2 text-right">${dinero(totalActual)}</td>
            <td class="p-2 text-right">${dinero(totalPrevio)}</td>
            <td class="p-2 text-right">${variacion(totalActual, totalPrevio)}</td>
        </tr>`;

    // Últimos 6 meses hasta el seleccionado
    const filas = [];
    for (let i = 5; i >= 0; i--) {
        const m = sumarMesesAMes(mes, -i);
        const { ingresos, gastos } = totales(delMes(transacciones, m));
        const gastosAnterior = totales(delMes(transacciones, sumarMesesAMes(m, -1))).gastos;
        filas.push(`
            <tr class="border-b ${m === mes ? 'bg-blue-50' : ''}">
                <td class="p-2">${m}</td>
                <td class="p-2 text-right text-green-600">${dinero(ingresos)}</td>
                <td class="p-2 text-right text-red-600">${dinero(gastos)}</td>
                <td class="p-2 text-right">${variacion(gastos, gastosAnterior)}</td>
            </tr>`);
    }
    document.getElementById('reporte-meses').innerHTML = filas.join('');
}

export function renderizarCategorias(categorias) {
    document.getElementById('categorias-lista').innerHTML = categorias.map(c => `
        <div class="fila-categoria grid grid-cols-2 md:grid-cols-4 gap-2 items-center mb-2" data-id="${esc(c.id)}" data-nombre="${esc(c.nombre)}">
            <input class="cat-nombre p-1 border rounded" value="${esc(c.nombre)}">
            <input class="cat-tope p-1 border rounded" type="number" step="0.01" min="0" placeholder="Sin tope" value="${esc(c.tope_mensual)}">
            <button class="btn-guardar-cat bg-blue-500 text-white p-1 rounded text-sm">Guardar</button>
            <button class="btn-eliminar-cat text-red-500 hover:underline text-sm">Eliminar</button>
        </div>
    `).join('');
}

export function renderizarCuentas(cuentas, transacciones) {
    const opcionesTipo = actual => Object.entries(TIPOS_CUENTA)
        .map(([valor, texto]) => `<option value="${valor}" ${valor === actual ? 'selected' : ''}>${texto}</option>`).join('');
    const opcionesMoneda = actual => ['ARS', 'USD']
        .map(m => `<option ${m === actual ? 'selected' : ''}>${m}</option>`).join('');

    document.getElementById('cuentas-lista').innerHTML = cuentas.map(c => `
        <div class="fila-cuenta grid grid-cols-2 md:grid-cols-7 gap-2 items-center mb-2" data-id="${esc(c.id)}">
            <input class="cuenta-nombre p-1 border rounded" value="${esc(c.nombre)}">
            <select class="cuenta-tipo p-1 border rounded">${opcionesTipo(c.tipo)}</select>
            <select class="cuenta-moneda p-1 border rounded">${opcionesMoneda(c.moneda)}</select>
            <input class="cuenta-saldo-inicial p-1 border rounded" type="number" step="0.01" title="Saldo inicial" value="${esc(c.saldo_inicial)}">
            <span class="font-bold text-right">${dinero(saldoCuenta(c, transacciones), c.moneda)}</span>
            <button class="btn-guardar-cuenta bg-blue-500 text-white p-1 rounded text-sm">Guardar</button>
            <button class="btn-eliminar-cuenta text-red-500 hover:underline text-sm">Eliminar</button>
        </div>
    `).join('');
}

export function renderizarRecurrentes(recurrentes, cuentas) {
    const contenedor = document.getElementById('recurrentes-lista');
    if (!recurrentes.length) {
        contenedor.innerHTML = '<p class="text-sm text-gray-500">No hay movimientos recurrentes. Marcá "Repetir todos los meses" al cargar uno.</p>';
        return;
    }
    contenedor.innerHTML = recurrentes.map(r => `
        <div class="flex justify-between items-center border-b py-2 text-sm" data-id="${esc(r.id)}">
            <span>Día ${esc(r.dia)} · ${esc(r.descripcion || r.categoria)} · ${esc(nombreCuenta(cuentas, r.cuenta_id))}</span>
            <span class="flex gap-4 items-center">
                <b class="${r.tipo === 'ingreso' ? 'text-green-600' : 'text-red-600'}">${dinero(r.monto, r.moneda)}</b>
                <button class="btn-eliminar-recurrente text-red-500 hover:underline">Dejar de repetir</button>
            </span>
        </div>
    `).join('');
}

// Rellena los selects del formulario conservando la selección actual.
export function llenarSelects(categorias, cuentas) {
    const selCategoria = document.getElementById('trans-categoria');
    const selCuenta = document.getElementById('trans-cuenta');
    const categoriaActual = selCategoria.value;
    const cuentaActual = selCuenta.value;

    selCategoria.innerHTML = '<option value="" disabled selected>Categoría</option>' +
        categorias.map(c => `<option value="${esc(c.nombre)}">${esc(c.nombre)}</option>`).join('');
    selCuenta.innerHTML = cuentas.map(c => `<option value="${esc(c.id)}">${esc(etiquetaCuenta(c))}</option>`).join('');

    if (categorias.some(c => c.nombre === categoriaActual)) selCategoria.value = categoriaActual;
    if (cuentas.some(c => c.id === cuentaActual)) selCuenta.value = cuentaActual;
}

export function descargarCSV(transacciones, cuentas, nombreArchivo) {
    // Formato para Excel en español: separador ';', coma decimal y BOM para los acentos.
    const numero = n => (Math.round(Number(n) * 100) / 100).toFixed(2).replace('.', ',');
    const campo = v => {
        const s = String(v ?? '');
        return /[;"\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };

    const filas = [
        ['Fecha', 'Tipo', 'Categoría', 'Cuenta', 'Descripción', 'Moneda', 'Monto', 'Tipo de cambio', 'Monto ARS'],
        ...transacciones.map(t => [
            t.fecha, t.tipo, t.categoria, nombreCuenta(cuentas, t.cuenta_id), t.descripcion,
            t.moneda, numero(t.monto), numero(t.tipo_cambio), numero(enARS(t)),
        ]),
    ];
    const csv = '﻿' + filas.map(f => f.map(campo).join(';')).join('\r\n');

    const enlace = document.createElement('a');
    enlace.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    enlace.download = nombreArchivo;
    enlace.click();
    URL.revokeObjectURL(enlace.href);
}

export async function renderizarMetas() {
    const { data: metas, error } = await cargarMetas();
    if (error) {
        console.error("Error al cargar metas:", error);
        return;
    }

    const container = document.getElementById('metas-container');
    if (!container) return;

    container.innerHTML = '';

    metas.forEach(meta => {
        const porcentaje = Math.min((meta.monto_actual / meta.monto_objetivo) * 100, 100);

        const div = document.createElement('div');
        div.className = 'bg-white p-4 rounded shadow mb-4';
        div.innerHTML = `
            <h3 class="font-bold text-lg">${esc(meta.titulo)}</h3>
            <p class="text-sm italic text-gray-600">Por qué: ${esc(meta.por_que)}</p>
            <div class="w-full bg-gray-200 rounded-full h-2.5 mt-2">
                <div class="bg-green-500 h-2.5 rounded-full" style="width: ${porcentaje}%"></div>
            </div>
            <p class="text-xs text-right mt-1">${porcentaje.toFixed(0)}% completado</p>
        `;
        container.appendChild(div);
    });
}
