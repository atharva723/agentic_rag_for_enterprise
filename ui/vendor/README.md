# ui/vendor/

Code written by others, kept here so the pages need no CDN and no build step.

## supabase.js

The official browser build of `@supabase/supabase-js`, **unmodified**. Only `ui/auth.js` uses it (to sign in, sign up and sign out). It sets one global, `supabase`.

| | |
|---|---|
| Version | 2.119.2 |
| Source | the npm package `@supabase/supabase-js@2.119.2`, file `dist/umd/supabase.js` |
| SHA-384 (base64) | `A97u3Qnt9GZHURO9YJZRe7VQgGUeFzcv6I1oIGnUTxQrCxnpQMwR0/G8F2zt9abZ` |
| Licence | MIT, Supabase. The text is in `supabase-js.LICENSE` |

It also contains the Supabase packages it depends on (auth, functions, postgrest, realtime and storage). The app uses only the sign-in part. The data calls never run in the browser: they go through our own server.

### Check that it is the real file

```powershell
npm pack @supabase/supabase-js@2.119.2
tar -xzf supabase-supabase-js-2.119.2.tgz package/dist/umd/supabase.js
# the two hashes must be the same
[Convert]::ToBase64String([Security.Cryptography.SHA384]::Create().ComputeHash([IO.File]::ReadAllBytes("package/dist/umd/supabase.js")))
[Convert]::ToBase64String([Security.Cryptography.SHA384]::Create().ComputeHash([IO.File]::ReadAllBytes("ui/vendor/supabase.js")))
```

`.gitattributes` stops Git from changing line endings in `supabase.js`, so the hash stays the same on every machine.

### Update it

Run the same `npm pack` with the new version, copy `dist/umd/supabase.js` and `LICENSE` over the files here, and change the version and hash above. Then run `python -m app.supabase.check --full` and sign in once in the browser.
