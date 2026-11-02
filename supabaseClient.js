import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

const SUPABASE_URL = 'https://iwrkbbrjbffkhfrvydnu.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml3cmtiYnJqYmZma2hmcnZ5ZG51Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk2MDM3MjksImV4cCI6MjEwNTE3OTcyOX0.A7I8XmEWFfU6iU_JB7MPkfiOfuwrUHx6Vs9fxxenvhA';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
