-- Row-level security, grants and the audit trail, checked as each role (scripts/test-db.sh).
-- Any failed check raises, and psql stops with a non-zero exit code.
\set ON_ERROR_STOP 1
\set QUIET 1

-- fails unless running sql raises the SQLSTATE state
create function pg_temp.expect_error(sql text, state text) returns void
language plpgsql as $$
begin
  execute sql;
  raise exception 'no error from: %', sql using errcode = 'XX000';
exception when others then
  if sqlstate <> state then
    raise exception 'expected SQLSTATE %, got % (%) from: %', state, sqlstate, sqlerrm, sql;
  end if;
end;
$$;
grant execute on function pg_temp.expect_error(text, text) to public;

insert into auth.users values
  ('00000000-0000-0000-0000-00000000000a', 'analyst@example.com'),
  ('00000000-0000-0000-0000-00000000000b', 'approver@example.com'),
  ('00000000-0000-0000-0000-00000000000c', 'nobody@example.com');

-- the secret key: assigns roles and publishes plans, but cannot write the tables directly
set role service_role;
insert into public.user_roles values
  ('00000000-0000-0000-0000-00000000000a', 'analyst'),
  ('00000000-0000-0000-0000-00000000000b', 'approver');
do $$
begin
  assert public.publish_plan('b1', '2026-05-07', '[
    {"agent_id": "DHK-001", "territory": "DHK", "runner_id": "R1", "target_cash_tk": 1000.5,
     "value_tk": 42.1, "evidence": {"p_stockout_cash": 0.3}},
    {"agent_id": "DHK-002", "territory": "DHK", "runner_id": "R1", "target_cash_tk": 900,
     "value_tk": 10, "evidence": {}}]', '{"bundle_id": "b1"}') = 2, 'first publish inserts';
  assert public.publish_plan('b1', '2026-05-07', '[]', '{}') = 0, 'second publish is ignored';
  assert (select count(*) from public.audit_log where action = 'plan.published') = 1;
end $$;
select pg_temp.expect_error($$insert into public.recommendations (bundle_id, plan_date,
  agent_id, territory, runner_id, target_cash_tk, value_tk, evidence, trace)
  values ('x', '2026-01-01', 'a', 't', 'r', 1, 1, '{}', '{}')$$, '42501');
select pg_temp.expect_error($$insert into public.audit_log (actor_role, action)
  values ('system', 'forged')$$, '42501');
select pg_temp.expect_error($$update public.recommendations set status = 'approved'$$, '42501');
reset role;

-- anonymous callers see nothing and can call nothing
set role anon;
select pg_temp.expect_error('select * from public.recommendations', '42501');
select pg_temp.expect_error('select * from public.audit_log', '42501');
select pg_temp.expect_error($$select public.decide_recommendation(1, 'approved')$$, '42501');
reset role;

-- a signed-in user without a role sees no rows
set role authenticated;
set request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000c"}';
do $$
begin
  assert (select count(*) from public.recommendations) = 0, 'no role, no queue';
  assert (select count(*) from public.audit_log) = 0, 'no role, no audit';
  assert (select count(*) from public.user_roles) = 0, 'no role row';
end $$;
select pg_temp.expect_error($$select public.decide_recommendation(1, 'approved')$$, '42501');
reset role;

-- an analyst reads the queue and the audit log but cannot decide or write
set role authenticated;
set request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000a"}';
do $$
begin
  assert public.app_role() = 'analyst';
  assert (select count(*) from public.recommendations) = 2, 'analyst reads the queue';
  assert (select count(*) from public.audit_log) = 1, 'analyst reads the audit log';
  assert (select count(*) from public.user_roles) = 1, 'only their own role';
end $$;
select pg_temp.expect_error($$select public.decide_recommendation(1, 'approved')$$, '42501');
select pg_temp.expect_error($$update public.recommendations set status = 'approved'$$, '42501');
select pg_temp.expect_error($$select public.publish_plan('b1', '2026-05-08', '[]', '{}')$$, '42501');
select pg_temp.expect_error($$insert into public.user_roles values
  ('00000000-0000-0000-0000-00000000000c', 'approver')$$, '42501');
reset role;

-- an approver decides once; the decision and its audit row land together
set role authenticated;
set request.jwt.claims = '{"sub": "00000000-0000-0000-0000-00000000000b"}';
do $$
declare
  rec public.recommendations;
begin
  rec := public.decide_recommendation(1, 'approved', '  checked the drain  ');
  assert rec.status = 'approved' and rec.decision_note = 'checked the drain';
  assert rec.decided_by = '00000000-0000-0000-0000-00000000000b';
  assert (select count(*) from public.audit_log where action = 'recommendation.approved'
          and recommendation_id = 1 and actor = rec.decided_by) = 1, 'decision is audited';
end $$;
select pg_temp.expect_error($$select public.decide_recommendation(1, 'rejected')$$, '55000');
select pg_temp.expect_error($$select public.decide_recommendation(99, 'rejected')$$, 'P0002');
select pg_temp.expect_error($$select public.decide_recommendation(2, 'maybe')$$, '22023');
select pg_temp.expect_error(
  $$select public.decide_recommendation(2, 'rejected', repeat('x', 501))$$, '22001');
reset role;

-- not even the table owner can rewrite history
select pg_temp.expect_error($$update public.audit_log set action = 'x'$$, '42501');
select pg_temp.expect_error('delete from public.audit_log', '42501');
select pg_temp.expect_error('truncate public.audit_log', '42501');
select pg_temp.expect_error('update public.recommendations set value_tk = 1 where id = 2', '42501');
select pg_temp.expect_error($$update public.recommendations set status = 'pending'
  where id = 1$$, '55000');
select pg_temp.expect_error('delete from public.recommendations where id = 2', '42501');
select pg_temp.expect_error('truncate public.recommendations cascade', '42501');
do $$
begin
  assert (select count(*) from public.audit_log) = 2, 'publish + one decision';
end $$;

\echo 'database checks passed'
