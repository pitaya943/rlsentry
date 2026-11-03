insert into public.diary_entries (id, owner_id, body) values
  ('5ce01012-0000-4000-8000-000000000001', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'diary of a'),
  ('5ce01012-0000-4000-8000-000000000002', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'diary of b');
insert into public.audit_log (id, actor_id, action) values
  ('5ce01012-0000-4000-8000-000000000003', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'login');
