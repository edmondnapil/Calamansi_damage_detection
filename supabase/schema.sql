-- =============================================================================
-- Web-Based Calamansi Leaf Damage Detection Using Image Classification
-- Supabase schema. Run once in: Supabase Dashboard -> SQL Editor -> New query.
-- Safe to re-run (idempotent).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Detection records
-- ---------------------------------------------------------------------------
create table if not exists public.detection_logs (
    id                uuid primary key default gen_random_uuid(),
    predicted_class   text        not null check (predicted_class in ('Healthy', 'Damaged')),
    -- Convention: confidence = model probability of the PREDICTED class, 0..1
    -- (e.g. 0.987 is shown as 98.7%). Always >= 0.5 for a binary sigmoid model.
    confidence        numeric(7,6) not null check (confidence >= 0 and confidence <= 1),
    prob_healthy      numeric(7,6) check (prob_healthy  >= 0 and prob_healthy  <= 1),
    prob_damaged      numeric(7,6) check (prob_damaged  >= 0 and prob_damaged  <= 1),
    -- Object path inside the private 'leaf-images' Storage bucket (null if not retained)
    image_path        text,
    original_filename text check (char_length(original_filename) <= 255),
    model_version     text        not null,
    created_at        timestamptz not null default now()
);

comment on table  public.detection_logs is 'One row per leaf image classified by the trained model (written only by the FastAPI backend).';
comment on column public.detection_logs.confidence is 'Probability (0..1) of predicted_class as output by the model.';

create index if not exists detection_logs_created_at_idx       on public.detection_logs (created_at desc);
create index if not exists detection_logs_class_created_at_idx on public.detection_logs (predicted_class, created_at desc);

-- ---------------------------------------------------------------------------
-- 2. Row Level Security
--    RLS is ON and no policies are granted to the 'anon' or 'authenticated'
--    roles, so the public anon key can neither read nor write this table.
--    The FastAPI backend uses the service-role key (server-side only), which
--    bypasses RLS. Predictions therefore can only be created from real model
--    output computed on the server.
-- ---------------------------------------------------------------------------
alter table public.detection_logs enable row level security;
revoke all on public.detection_logs from anon, authenticated;

-- ---------------------------------------------------------------------------
-- 3. Private Storage bucket for retained leaf images (max 5 MB, images only)
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('leaf-images', 'leaf-images', false, 5242880, array['image/jpeg', 'image/png', 'image/webp'])
on conflict (id) do update
    set public = false,
        file_size_limit = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;

-- No storage.objects policies are created for anon/authenticated users, so the
-- bucket is private. The backend uploads with the service-role key and gives the
-- browser short-lived (1 hour) signed URLs for thumbnails.
