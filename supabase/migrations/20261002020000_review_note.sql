-- Jogan: approving a recommendation flagged for manual review needs a note (DECISIONS.md D-023).
--
-- The served bundle marks a recommendation for manual review when its evidence is weak (a
-- forecast input outside the training range, a wide forecast interval, a data gap, a short
-- history) or when the advisory anomaly flag fired; the flag is stored in
-- evidence -> 'review' -> 'flag'. The rule lives here, not only in the API, because an approver
-- can call this function through the Data API directly. The audit row records the flag.
-- create or replace keeps the function's owner and grants.

create or replace function public.decide_recommendation(
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
  review boolean;
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
  select * into rec from public.recommendations where id = p_id for update;
  if not found then
    raise exception 'recommendation % not found', p_id using errcode = 'P0002';
  end if;
  if rec.status <> 'pending' then
    raise exception 'recommendation % is already decided', p_id using errcode = '55000';
  end if;
  review := coalesce((rec.evidence -> 'review' ->> 'flag')::boolean, false);
  if p_decision = 'approved' and review and note is null then
    raise exception 'a recommendation flagged for manual review needs a note to approve'
      using errcode = '22023';
  end if;
  update public.recommendations
  set status = p_decision, decided_by = (select auth.uid()), decided_at = now(),
    decision_note = note
  where id = p_id
  returning * into rec;
  insert into public.audit_log (actor, actor_role, action, recommendation_id, detail)
  values (
    (select auth.uid()), caller_role, 'recommendation.' || p_decision, p_id,
    jsonb_build_object(
      'note', note, 'agent_id', rec.agent_id, 'plan_date', rec.plan_date,
      'bundle_id', rec.bundle_id, 'manual_review', review
    )
  );
  return rec;
end;
$$;
