-- L11: bucket private-docs is public (planted); private-ok is private with an owner-scoped SELECT policy.
-- Objects are uploaded by labctl from storage/ after this file runs; seed.sql sets their owners.
INSERT INTO storage.buckets (id, name, public) VALUES
  ('private-docs', 'private-docs', true),
  ('private-ok', 'private-ok', false);
CREATE POLICY "private-ok owner read" ON storage.objects FOR SELECT TO authenticated
  USING (bucket_id = 'private-ok' AND owner_id = auth.uid()::text);
