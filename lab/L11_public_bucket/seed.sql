-- L11: known owners for the uploaded objects (user_a / user_b ids from LAB_USERS).
UPDATE storage.objects SET owner = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', owner_id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
  WHERE bucket_id = 'private-docs' AND name = 'user_a/contract.pdf';
UPDATE storage.objects SET owner = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', owner_id = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
  WHERE bucket_id = 'private-ok' AND name = 'user_b/notes.pdf';
