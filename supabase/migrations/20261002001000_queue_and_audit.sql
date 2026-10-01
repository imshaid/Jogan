-- Jogan: roles, the recommendation queue and the append-only audit log (DECISIONS.md D-022).
--
-- This project does not expose new tables to the Data API automatically, so every grant is
-- explicit, and row-level security is enabled on every table even though the project also
-- enables it by default. Users read through RLS; every write goes through a function:
--   publish_plan          service_role only: the API writes the model's plan for a day
--   decide_recommendation approvers only: one transaction updates the row and appends audit
-- Recommendations cannot be deleted or edited except for that one decision, and the audit
-- log cannot be updated, deleted or truncated, not even with the secret key.

-- Roles --------------------------------------------------------------------------------------

create table public.user_roles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  role text not null check (role in ('analyst', 'approver')),
  created_at timestamptz not null default now()
);

-- The caller's role, or null. Security definer so policies can read user_roles under RLS.
create function public.app_role()
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select role from public.user_roles where user_id = (select auth.uid())
$$;

-- Recommendations ----------------------------------------------------------------------------

create table public.recommendations (
  id bigint generated always as identity primary key,
  bundle_id text not null,
  plan_date date not null,
  agent_id text not null,
  territory text not null,
  runner_id text not null,
  action text not null default 'visit' check (action in ('visit')),
  target_cash_tk numeric(14, 2) not null,
  value_tk numeric(14, 2) not null,
  evidence jsonb not null,
  trace jsonb not null,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  decided_by uuid,
  decided_at timestamptz,
  decision_note text check (char_length(decision_note) <= 500),
  created_at timestamptz not null default now(),
  unique (bundle_id, plan_date, agent_id)
);

-- Audit log ----------------------------------------------------------------------------------

create table public.audit_log (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  actor uuid, -- null for the system (the API publishing a plan)
  actor_role text not null check (actor_role in ('system', 'analyst', 'approver')),
  action text not null,
  recommendation_id bigint references public.recommendations (id),
  detail jsonb not null default '{}'::jsonb
);

-- Guards -------------------------------------------------------------------------------------

create function public.audit_log_append_only()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception 'audit_log is append-only' using errcode = '42501';
end;
$$;

create trigger audit_log_no_update_or_delete
before update or delete on public.audit_log
for each row execute function public.audit_log_append_only();

create trigger audit_log_no_truncate
before truncate on public.audit_log
for each statement execute function public.audit_log_append_only();

-- A recommendation is decided once; nothing else about it ever changes.
create function public.recommendations_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  decision_fields text[] := array['status', 'decided_by', 'decided_at', 'decision_note'];
begin
  if tg_op <> 'UPDATE' then
    raise exception 'recommendations cannot be deleted' using errcode = '42501';
  end if;
  if old.status <> 'pending' then
    raise exception 'recommendation % is already decided', old.id using errcode = '55000';
  end if;
  if (to_jsonb(new) - decision_fields) is distinct from (to_jsonb(old) - decision_fields) then
    raise exception 'only the decision of a recommendation can change' using errcode = '42501';
  end if;
  return new;
end;
$$;

create trigger recommendations_guard
before update or delete on public.recommendations
for each row execute function public.recommendations_guard();

create trigger recommendations_no_truncate
before truncate on public.recommendations
for each statement execute function public.recommendations_guard();

-- Writes -------------------------------------------------------------------------------------

-- Insert a day's plan once; a second publish of the same bundle and day does nothing.
create function public.publish_plan(
  p_bundle_id text,
  p_plan_date date,
  p_rows jsonb,
  p_trace jsonb
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  inserted integer;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_bundle_id || '/' || p_plan_date::text, 0));
  if exists (
    select 1 from public.recommendations
    where bundle_id = p_bundle_id and plan_date = p_plan_date
  ) then
    return 0;
  end if;
  insert into public.recommendations (
    bundle_id, plan_date, agent_id, territory, runner_id, target_cash_tk, value_tk, evidence,
    trace
  )
  select p_bundle_id, p_plan_date, r.agent_id, r.territory, r.runner_id, r.target_cash_tk,
    r.value_tk, r.evidence, p_trace
  from jsonb_to_recordset(p_rows) as r(
    agent_id text, territory text, runner_id text, target_cash_tk numeric, value_tk numeric,
    evidence jsonb
  );
  get diagnostics inserted = row_count;
  if inserted > 0 then
    insert into public.audit_log (actor, actor_role, action, detail)
    values (
      null, 'system', 'plan.published',
      jsonb_build_object(
        'bundle_id', p_bundle_id, 'plan_date', p_plan_date, 'recommendations', inserted
      )
    );
  end if;
  return inserted;
end;
$$;

-- Approve or reject a pending recommendation and append the audit row, atomically.
create function public.decide_recommendation(
  p_id bigint,
  p_decision text,
  p_note text default null
)
returns public.recommendations
language plpgsql
security definer
set search_path = ''
as $$
declare
  caller_role text := public.app_role();
  note text := nullif(btrim(p_note), '');
  rec public.recommendations;
begin
  if caller_role is distinct from 'approver' then
    raise exception 'only an approver can decide' using errcode = '42501';
  end if;
  if p_decision is null or p_decision not in ('approved', 'rejected') then
    raise exception 'decision must be approved or rejected' using errcode = '22023';
  end if;
  if char_length(note) > 500 then
    raise exception 'note is too long' using errcode = '22001';
  end if;
  update public.recommendations
  set status = p_decision, decided_by = (select auth.uid()), decided_at = now(),
    decision_note = note
  where id = p_id and status = 'pending'
  returning * into rec;
  if not found then
    if exists (select 1 from public.recommendations where id = p_id) then
      raise exception 'recommendation % is already decided', p_id using errcode = '55000';
    end if;
    raise exception 'recommendation % not found', p_id using errcode = 'P0002';
  end if;
  insert into public.audit_log (actor, actor_role, action, recommendation_id, detail)
  values (
    (select auth.uid()), caller_role, 'recommendation.' || p_decision, p_id,
    jsonb_build_object(
      'note', note, 'agent_id', rec.agent_id, 'plan_date', rec.plan_date,
      'bundle_id', rec.bundle_id
    )
  );
  return rec;
end;
$$;

-- Row-level security -------------------------------------------------------------------------

alter table public.user_roles enable row level security;
alter table public.recommendations enable row level security;
alter table public.audit_log enable row level security;

create policy "users read their own role"
on public.user_roles for select to authenticated
using (user_id = (select auth.uid()));

create policy "staff read the queue"
on public.recommendations for select to authenticated
using ((select public.app_role()) is not null);

create policy "staff read the audit log"
on public.audit_log for select to authenticated
using ((select public.app_role()) is not null);

-- Grants -------------------------------------------------------------------------------------

revoke all on public.user_roles, public.recommendations, public.audit_log
from public, anon, authenticated, service_role;

grant select on public.user_roles, public.recommendations, public.audit_log to authenticated;
-- the secret key manages roles and reads everything, but writes plans only via publish_plan
grant select, insert, update, delete on public.user_roles to service_role;
grant select on public.recommendations, public.audit_log to service_role;

revoke execute on function
  public.app_role(),
  public.publish_plan(text, date, jsonb, jsonb),
  public.decide_recommendation(bigint, text, text),
  public.audit_log_append_only(),
  public.recommendations_guard()
from public, anon, authenticated, service_role;

grant execute on function public.app_role() to authenticated, service_role;
grant execute on function public.decide_recommendation(bigint, text, text) to authenticated;
grant execute on function public.publish_plan(text, date, jsonb, jsonb) to service_role;
