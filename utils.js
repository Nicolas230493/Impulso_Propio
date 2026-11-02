// Funciones puras: fechas, moneda, cuotas y recurrentes. Sin DOM ni Supabase.

const pad = n => String(n).padStart(2, '0');

// --- Fechas ---
// Todas las fechas se manejan como strings 'YYYY-MM-DD' / 'YYYY-MM' en hora local:
// new Date('YYYY-MM-DD') se interpreta como UTC y en UTC-3 corre los días.

// Devuelve 'YYYY-MM'; mes0 es 0-11 y puede desbordar (-1 = diciembre del año anterior).
export function aMesISO(anio, mes0) {
    const d = new Date(anio, mes0, 1);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}

export function hoyISO() {
    const d = new Date();
    return `${aMesISO(d.getFullYear(), d.getMonth())}-${pad(d.getDate())}`;
}

export function mesActual() {
    return hoyISO().slice(0, 7);
}

export function sumarMesesAMes(mes, n) {
    const [anio, m] = mes.split('-').map(Number);
    return aMesISO(anio, m - 1 + n);
}

// Día `dia` del mes, recortado al último día (31 en febrero -> 28/29).
export function fechaEnMes(mes, dia) {
    const [anio, m] = mes.split('-').map(Number);
    const ultimoDia = new Date(anio, m, 0).getDate();
    return `${mes}-${pad(Math.min(dia, ultimoDia))}`;
}

export function sumarMeses(fecha, n) {
    return fechaEnMes(sumarMesesAMes(fecha.slice(0, 7), n), Number(fecha.slice(8, 10)));
}

// --- Moneda ---

export function enARS(t) {
    return Number(t.monto) * (t.moneda === 'USD' ? Number(t.tipo_cambio) : 1);
}

export function enMonedaDeCuenta(t, cuenta) {
    const monto = Number(t.monto);
    if (t.moneda === cuenta.moneda) return monto;
    return cuenta.moneda === 'ARS' ? monto * Number(t.tipo_cambio) : monto / Number(t.tipo_cambio);
}

export function dinero(n, moneda = 'ARS') {
    const simbolo = moneda === 'USD' ? 'US$ ' : '$ ';
    return simbolo + Number(n).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// --- Agregados ---

export function totales(transacciones) {
    let ingresos = 0;
    let gastos = 0;
    transacciones.forEach(t => {
        if (t.tipo === 'ingreso') ingresos += enARS(t);
        else gastos += enARS(t);
    });
    return { ingresos, gastos };
}

// { categoria: total de gastos en ARS }
export function gastosPorCategoria(transacciones) {
    const suma = {};
    transacciones.forEach(t => {
        if (t.tipo === 'ingreso') return;
        suma[t.categoria] = (suma[t.categoria] || 0) + enARS(t);
    });
    return suma;
}

export function delMes(transacciones, mes) {
    return transacciones.filter(t => t.fecha.slice(0, 7) === mes);
}

// Saldo a hoy: no cuenta cuotas ni movimientos con fecha futura.
export function saldoCuenta(cuenta, transacciones, hoy = hoyISO()) {
    return transacciones
        .filter(t => t.cuenta_id === cuenta.id && t.fecha <= hoy)
        .reduce((saldo, t) => saldo + (t.tipo === 'ingreso' ? 1 : -1) * enMonedaDeCuenta(t, cuenta), Number(cuenta.saldo_inicial));
}

// --- Cuotas y recurrentes ---

// Divide un gasto en cuotas mensuales; la última absorbe el redondeo.
export function filasCuotas(base, monto, fecha, cuotas, grupoId) {
    if (cuotas <= 1) return [{ ...base, monto, fecha }];
    const montoCuota = Math.floor(monto * 100 / cuotas) / 100;
    return Array.from({ length: cuotas }, (_, i) => ({
        ...base,
        grupo_id: grupoId,
        cuota: i + 1,
        cuotas,
        monto: i === cuotas - 1 ? Math.round((monto - montoCuota * (cuotas - 1)) * 100) / 100 : montoCuota,
        fecha: sumarMeses(fecha, i),
        descripcion: `${base.descripcion || base.categoria} (${i + 1}/${cuotas})`,
    }));
}

// Movimientos que un recurrente todavía no generó, hasta hoy inclusive.
export function pendientesRecurrente(r, hoy = hoyISO()) {
    const filas = [];
    let ultimoMes = r.ultimo_mes;
    for (let mes = sumarMesesAMes(r.ultimo_mes, 1); mes <= hoy.slice(0, 7); mes = sumarMesesAMes(mes, 1)) {
        const fecha = fechaEnMes(mes, r.dia);
        if (fecha > hoy) break;
        filas.push({
            tipo: r.tipo, monto: r.monto, categoria: r.categoria, cuenta_id: r.cuenta_id,
            moneda: r.moneda, tipo_cambio: r.tipo_cambio, descripcion: r.descripcion,
            fecha, recurrente_id: r.id,
        });
        ultimoMes = mes;
    }
    return { filas, ultimoMes };
}

// --- HTML ---

export function esc(texto) {
    return String(texto ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}
