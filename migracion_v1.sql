-- Migración v1: categorías con tope, cuentas, multimoneda, cuotas y recurrentes.
-- Correr una sola vez en Supabase > SQL Editor. Es idempotente (se puede volver a correr).

-- ===== Tablas nuevas =====

create table if not exists categorias (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    nombre text not null,
    tope_mensual numeric check (tope_mensual is null or tope_mensual > 0),
    creado timestamptz not null default now(),
    unique (user_id, nombre)
);

create table if not exists cuentas (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    nombre text not null,
    tipo text not null check (tipo in ('efectivo', 'tarjeta', 'transferencia')),
    moneda text not null default 'ARS' check (moneda in ('ARS', 'USD')),
    saldo_inicial numeric not null default 0,
    creado timestamptz not null default now(),
    unique (user_id, nombre)
);

create table if not exists recurrentes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    tipo text not null check (tipo in ('ingreso', 'gasto')),
    monto numeric not null check (monto > 0),
    categoria text not null,
    cuenta_id uuid references cuentas(id) on delete set null,
    moneda text not null default 'ARS' check (moneda in ('ARS', 'USD')),
    tipo_cambio numeric not null default 1 check (tipo_cambio > 0),
    descripcion text,
    dia int not null check (dia between 1 and 31),
    ultimo_mes text not null,  -- 'YYYY-MM' del último movimiento generado
    creado timestamptz not null default now()
);

-- ===== Columnas nuevas en transacciones =====

alter table transacciones
    add column if not exists cuenta_id uuid references cuentas(id) on delete set null,
    add column if not exists moneda text not null default 'ARS',
    add column if not exists tipo_cambio numeric not null default 1,
    add column if not exists grupo_id uuid,          -- agrupa las cuotas de un mismo gasto
    add column if not exists cuota int,
    add column if not exists cuotas int,
    add column if not exists recurrente_id uuid references recurrentes(id) on delete set null;

-- Las categorías pasan de valores fijos del HTML a nombres editables.
update transacciones set categoria = case categoria
    when 'alimentacion' then 'Alimentación'
    when 'transporte' then 'Transporte'
    when 'vivienda' then 'Vivienda'
    when 'salario' then 'Salario'
    when 'otros' then 'Otros'
    else categoria
end;

-- ===== RLS: cada usuario solo ve y modifica lo suyo =====

do $$
declare t text;
begin
    foreach t in array array['transacciones', 'metas', 'categorias', 'cuentas', 'recurrentes'] loop
        execute format('alter table %I enable row level security', t);
        execute format('drop policy if exists "solo_propios" on %I', t);
        execute format('create policy "solo_propios" on %I for all using (auth.uid() = user_id) with check (auth.uid() = user_id)', t);
    end loop;
end $$;

-- ===== Verificación =====
-- RLS activo (rowsecurity = true en las 5 tablas):
select tablename, rowsecurity from pg_tables
where schemaname = 'public' and tablename in ('transacciones', 'metas', 'categorias', 'cuentas', 'recurrentes');

-- Políticas: las políticas se suman (OR). Si aparece otra además de "solo_propios"
-- que no filtre por auth.uid() = user_id, borrarla o va a exponer datos ajenos.
select tablename, policyname, cmd, qual from pg_policies
where tablename in ('transacciones', 'metas', 'categorias', 'cuentas', 'recurrentes');
