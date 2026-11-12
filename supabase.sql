-- Tabla de registros del bot de WhatsApp de CREAR.
-- Pégalo en Supabase → SQL Editor → Run.

create table if not exists public.registros (
  id            bigint generated always as identity primary key,
  creado        timestamptz not null default now(),
  tipo          text not null,          -- llegada_tarde, salida_temprana, almuerzo, certificado, lista_espera
  telefono      text,
  nombre_perfil text,
  estudiante    text,
  grado         text,
  datos         jsonb not null default '{}'::jsonb,
  estado        text not null default 'pendiente'  -- la plataforma de certificados lo cambiará a 'hecho'
);

create index if not exists registros_creado_idx on public.registros (creado desc);
create index if not exists registros_tipo_idx   on public.registros (tipo, estado);

-- Seguridad: sin políticas públicas. Solo el servidor (con la service_role key) lee y escribe.
alter table public.registros enable row level security;
