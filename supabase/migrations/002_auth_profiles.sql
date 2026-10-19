-- =============================================================================
-- Migration 002: user accounts, roles, per-user detections, security audit log
-- Web-Based Calamansi Leaf Damage Detection Using Image Classification
--
-- Run once in: Supabase Dashboard -> SQL Editor -> New query -> paste -> Run.
-- Requires schema.sql (migration 001) to have been run before.
-- Safe to re-run. Nothing is dropped or deleted.
--
-- Architecture: Supabase Auth (auth.users) holds e-mail, password hashes,
-- e-mail verification and the one-time codes (stored hashed, expiring,
-- single-use, replaced when a new one is sent). Therefore this migration does
-- NOT create email_verifications / password_reset_requests tables; that would
-- duplicate Supabase Auth. The FastAPI backend adds login lockout, code-attempt
-- limits and resend cooldowns, recorded in security_audit_logs.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Profiles (one row per auth.users row)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
    id                uuid primary key references auth.users (id) on delete cascade,
    full_name         text not null check (char_length(full_name) between 1 and 100),
    username          text not null check (username ~ '^[a-z0-9_]{3,30}$'),
    role              text not null default 'user' check (role in ('user', 'admin')),
    account_status    text not null default 'active' check (account_status in ('active', 'suspended')),
    email_verified_at timestamptz,             -- mirrors auth.users.email_confirmed_at
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create unique index if not exists profiles_username_lower_key on public.profiles (lower(username));

comment on table public.profiles is 'Public account data. Role/status can only be changed by the backend (service role) or SQL.';

-- Create the profile automatically when Supabase Auth creates a user.
-- The role is ALWAYS 'user' here: user metadata is chosen by the user, so it must never set the role.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
    insert into public.profiles (id, full_name, username, email_verified_at)
    values (
        new.id,
        coalesce(nullif(btrim(new.raw_user_meta_data ->> 'full_name'), ''), split_part(new.email, '@', 1)),
        lower(coalesce(nullif(btrim(new.raw_user_meta_data ->> 'username'), ''),
                       'user_' || substr(replace(new.id::text, '-', ''), 1, 12))),
        new.email_confirmed_at
    )
    on conflict (id) do nothing;
    return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users for each row execute function public.handle_new_user();

-- Keep the verification timestamp in sync when the user confirms the e-mail code.
create or replace function public.sync_email_verified()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
    update public.profiles set email_verified_at = new.email_confirmed_at where id = new.id;
    return new;
end $$;

drop trigger if exists on_auth_user_email_confirmed on auth.users;
create trigger on_auth_user_email_confirmed
    after update of email_confirmed_at on auth.users for each row execute function public.sync_email_verified();

-- Users may edit their own name/username, never their role, status or verification.
create or replace function public.protect_profile_privileges()
returns trigger language plpgsql set search_path = '' as $$
begin
    if (new.role is distinct from old.role
        or new.account_status is distinct from old.account_status
        or new.email_verified_at is distinct from old.email_verified_at
        or new.id is distinct from old.id)
       and coalesce(auth.role(), '') <> 'service_role'
       and current_user not in ('postgres', 'supabase_admin') then
        raise exception 'Only the server can change role, account status or verification'
            using errcode = '42501';
    end if;
    new.updated_at := now();
    return new;
end $$;

drop trigger if exists protect_profile_privileges on public.profiles;
create trigger protect_profile_privileges
    before update on public.profiles for each row execute function public.protect_profile_privileges();

-- Helper used by RLS policies (security definer so it can read profiles without recursion).
create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = '' as $$
    select exists (
        select 1 from public.profiles
        where id = (select auth.uid()) and role = 'admin' and account_status = 'active'
    );
$$;
revoke all on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated, service_role;

alter table public.profiles enable row level security;
revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;
grant update (full_name, username) on public.profiles to authenticated;

drop policy if exists "profiles: read own or admin" on public.profiles;
create policy "profiles: read own or admin" on public.profiles
    for select to authenticated using ((select auth.uid()) = id or public.is_admin());

drop policy if exists "profiles: update own name" on public.profiles;
create policy "profiles: update own name" on public.profiles
    for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

-- Profiles for users that already exist (none at the time of writing; harmless otherwise).
insert into public.profiles (id, full_name, username, email_verified_at)
select u.id, split_part(u.email, '@', 1), 'user_' || substr(replace(u.id::text, '-', ''), 1, 12), u.email_confirmed_at
from auth.users u
on conflict (id) do nothing;

-- ---------------------------------------------------------------------------
-- 2. Detections belong to a user
--    Existing rows keep user_id = NULL (created before accounts existed); only admins see them.
-- ---------------------------------------------------------------------------
alter table public.detection_logs
    add column if not exists user_id uuid references auth.users (id) on delete set null;
create index if not exists detection_logs_user_created_idx on public.detection_logs (user_id, created_at desc);

-- RLS stays enabled (migration 001). The backend inserts with the service role; direct API
-- access by signed-in users is read-only and limited to their own rows (admins: all rows).
grant select on public.detection_logs to authenticated;
drop policy if exists "detections: read own or admin" on public.detection_logs;
create policy "detections: read own or admin" on public.detection_logs
    for select to authenticated using (user_id = (select auth.uid()) or public.is_admin());

-- ---------------------------------------------------------------------------
-- 3. Security audit log (server-only; never contains passwords, codes or tokens)
-- ---------------------------------------------------------------------------
create table if not exists public.security_audit_logs (
    id           bigint generated always as identity primary key,
    user_id      uuid references auth.users (id) on delete set null,
    event_type   text not null check (event_type ~ '^[a-z_]{3,40}$'),
    event_status text not null check (event_status in ('success', 'failure', 'blocked')),
    email_hash   text,   -- keyed hash of the normalised e-mail (lets the server count attempts without storing e-mails)
    ip_hash      text,   -- keyed hash of the client IP
    metadata     jsonb not null default '{}'::jsonb,
    created_at   timestamptz not null default now()
);
create index if not exists security_audit_email_idx on public.security_audit_logs (email_hash, event_type, created_at desc);
create index if not exists security_audit_ip_idx    on public.security_audit_logs (ip_hash, event_type, created_at desc);
create index if not exists security_audit_user_idx  on public.security_audit_logs (user_id, created_at desc);

alter table public.security_audit_logs enable row level security;
revoke all on public.security_audit_logs from anon, authenticated;   -- no policies: service role only

-- ---------------------------------------------------------------------------
-- 4. Server-only helper: does an e-mail have an account, and is it verified?
--    Used to reject duplicate registrations. Not callable by browsers.
-- ---------------------------------------------------------------------------
create or replace function public.auth_email_status(p_email text)
returns text language sql stable security definer set search_path = '' as $$
    select case
        when u.id is null then 'none'
        when u.email_confirmed_at is null then 'unverified'
        else 'verified'
    end
    from (select 1) as one
    left join auth.users u on lower(u.email) = lower(btrim(p_email));
$$;
revoke all on function public.auth_email_status(text) from public, anon, authenticated;
grant execute on function public.auth_email_status(text) to service_role;

-- ---------------------------------------------------------------------------
-- 5. Make an account an administrator (run manually, with the real e-mail):
--    update public.profiles set role = 'admin'
--    where id = (select id from auth.users where email = 'your-email@example.com');
-- ---------------------------------------------------------------------------
