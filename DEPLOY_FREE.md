# Put SkillForge AI online for free (beginner guide)

This guide puts SkillForge AI on the internet using only free plans. You don't need a credit card,
a server or a domain name. It takes about **1.5–2 hours** the first time.

You will create **5 free accounts** and copy a few values between them. Do the parts **in order**:
each part gives you something that a later part needs.

| Part | Service | What it does for SkillForge | Time |
|---|---|---|---|
| 1 | Supabase | Database + user login | 20 min |
| 2 | Google AI Studio | AI mentor, code review, viva questions | 5 min |
| 3 | RapidAPI (Judge0) | Safely runs learners' code | 10 min |
| 4 | Render | Runs the backend (Python API) | 25 min |
| 5 | Vercel | Runs the website | 15 min |
| 6 | Connect them + make yourself admin | Final wiring | 15 min |
| 7 | UptimeRobot (optional) | Keeps the free servers awake | 5 min |

> **Before you start:** open a plain notepad file called `skillforge-secrets.txt` **on your own
> computer**. Every time this guide says **📋 Save**, paste the value there with its name.
> **Never** upload this file, commit it to GitHub, or paste it into a chat. Anyone who has these
> values can use your accounts.

> **Screens change.** If a button has a slightly different name than below, look for the closest
> match. If a site asks for a credit card, **stop** — you are on a paid plan by mistake.

---

## Part 1 — Supabase (database + login)

### 1.1 Create the account and project
1. Go to **https://supabase.com** → click **Start your project** → sign in with **GitHub**.
2. Click **New project**.
3. Fill in:
   - **Name:** `skillforge`
   - **Database Password:** click **Generate a password**. **📋 Save** it as `DB_PASSWORD`.
   - **Region:** choose the one closest to you (for example *Mumbai* for India).
   - **Plan:** **Free**.
4. Click **Create new project** and wait 1–2 minutes until the dashboard loads.

### 1.2 Copy the database connection string
1. At the top of the project page click **Connect**.
2. Find **Session pooler** (not "Direct connection" — Render's free plan can't use that one).
3. Copy the URI. It looks like:
   `postgresql://postgres.abcdefgh:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres`
4. Replace `[YOUR-PASSWORD]` (including the brackets) with your `DB_PASSWORD`.
5. **📋 Save** the result as `DATABASE_URL`.

> ⚠️ If your password contains `@`, `#`, `/` or `:`, the URL breaks. Easiest fix: in Supabase go to
> **Project Settings → Database → Reset database password**, generate a new one with only letters
> and numbers, and redo step 4.

### 1.3 Copy the project URL and public key
1. Left sidebar → **Project Settings** (gear icon) → **API** (or **Data API**).
2. Copy **Project URL** (like `https://abcdefgh.supabase.co`). **📋 Save** as `SUPABASE_URL`.
3. Copy the **anon / public** key (a long text starting with `eyJ` or `sb_publishable_`).
   **📋 Save** as `SUPABASE_ANON_KEY`. (This one is safe to put in a website; the `service_role`
   / secret key is **not** — never copy that one anywhere.)
4. Optional: if **Project Settings → JWT Keys** shows a **Legacy JWT secret**, you may also save it
   as `SUPABASE_JWT_SECRET`. SkillForge works with either the new keys or the legacy secret.

✅ **Checkpoint:** your notes now contain `DB_PASSWORD`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.

---

## Part 2 — Google Gemini (the AI)

1. Go to **https://aistudio.google.com/apikey** and sign in with a Google account.
2. Click **Create API key** (accept the terms if asked; choose or create any project).
3. Copy the key (starts with `AIza`). **📋 Save** as `GEMINI_API_KEY`.

> On the free tier Google may use what you send to improve its products. Don't put private personal
> data into learner code or mentor chats.

✅ **Checkpoint:** you have `GEMINI_API_KEY`.

---

## Part 3 — Judge0 on RapidAPI (safe code runner)

Learners' code must never run on your own server, so a separate sandbox runs it.

1. Go to **https://rapidapi.com** → **Sign Up** (Google or GitHub is fine).
2. In the search bar type **Judge0 CE** and open the API published by **Judge0**.
3. Click **Pricing** → under the **Basic** plan (price **$0**) click **Subscribe** / **Start Free Plan**.
   Note the daily limit shown (it is small, around 50 requests per day).
4. Click the **Endpoints** tab. On the right side, under **Code Snippets**, find the header
   `X-RapidAPI-Key: ...`. Copy that value. **📋 Save** as `RAPIDAPI_KEY`.

> One mission **submission** uses 1 request; each **Run** button press uses 1 request. With ~50/day
> this is enough for you and a few testers, not for a class of students.

✅ **Checkpoint:** you have `RAPIDAPI_KEY`.

---

## Part 4 — Render (the backend)

### 4.1 Create the service from the blueprint
1. Go to **https://render.com** → **Get Started** → sign up with **GitHub**.
2. When asked, allow Render to access your repository **skill-AI** (you can choose "Only select
   repositories" and pick just that one).
3. In the dashboard click **New +** → **Blueprint**.
4. Choose the **skill-AI** repository → Render finds the `render.yaml` file → click **Apply** /
   **Deploy Blueprint**.
5. Render asks for the values marked as secret. Fill in:

| Name | Value from your notes |
|---|---|
| `DATABASE_URL` | `DATABASE_URL` |
| `SUPABASE_URL` | `SUPABASE_URL` |
| `GEMINI_API_KEY` | `GEMINI_API_KEY` |
| `JUDGE0_API_KEY` | `RAPIDAPI_KEY` |
| `CORS_ORIGINS` | type `https://example.com` for now — you fix it in Part 6 |

   (`JWT_SECRET` is generated automatically. `APP_ENV`, `JUDGE0_URL`, `ALLOW_LOCAL_RUNNER` and
   `SEED_DEMO_DATA` are already filled in.)
6. Click **Apply**. The first build takes **5–10 minutes**. Watch the **Logs** tab.
7. Optional: if you saved `SUPABASE_JWT_SECRET`, open the service → **Environment** → **Add
   Environment Variable** → add it.

### 4.2 Check it works
1. When the log shows `SkillForge ready`, copy the URL at the top of the service page, like
   `https://skillforge-api.onrender.com`. **📋 Save** as `BACKEND_URL`.
2. Open `BACKEND_URL/api/health` in your browser, e.g.
   `https://skillforge-api.onrender.com/api/health`. You should see something like:
   ```json
   {"status":"ok","database":"ok","llm":"gemini:gemini-2.5-flash","execution":"judge0"}
   ```

✅ **Checkpoint:** `database` is `ok`, `llm` starts with `gemini`, `execution` is `judge0`.

**If it fails:**
- `database: unreachable` or the build fails at `alembic upgrade head` → your `DATABASE_URL` is wrong.
  Re-check Part 1.2 (Session pooler, password filled in, no brackets). Edit it under **Environment**,
  then **Manual Deploy → Deploy latest commit**.
- `llm: deterministic-fallback` → `GEMINI_API_KEY` is missing or has a typo.
- The page takes ~1 minute the first time → normal, the free server was asleep.

---

## Part 5 — Vercel (the website)

1. Go to **https://vercel.com** → **Sign Up** → **Hobby** → continue with **GitHub**.
2. Click **Add New…** → **Project** → find **skill-AI** → **Import**.
3. **Root Directory:** click **Edit** → choose **frontend** → **Continue**.
   (Framework should show **Next.js** automatically.)
4. Open **Environment Variables** and add these three:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | your `BACKEND_URL` (no `/` at the end) |
| `NEXT_PUBLIC_SUPABASE_URL` | your `SUPABASE_URL` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | your `SUPABASE_ANON_KEY` |

5. Click **Deploy** and wait 2–4 minutes.
6. Click **Continue to Dashboard** → copy the **Domains** URL, like `https://skill-ai.vercel.app`.
   **📋 Save** as `WEBSITE_URL`.

✅ **Checkpoint:** opening `WEBSITE_URL` shows the SkillForge landing page.

---

## Part 6 — Connect everything

### 6.1 Allow the website to talk to the backend
1. Render → your **skillforge-api** service → **Environment**.
2. Edit `CORS_ORIGINS` → set it to your `WEBSITE_URL` (no `/` at the end) → **Save Changes**.
   Render redeploys automatically (2–5 min).

### 6.2 Tell Supabase where your website is
1. Supabase → **Authentication** → **URL Configuration**.
2. **Site URL:** your `WEBSITE_URL`. Click **Save**.
3. Under **Redirect URLs** click **Add URL** → `WEBSITE_URL/**` (e.g. `https://skill-ai.vercel.app/**`) → **Save**.

### 6.3 Create your account and make yourself admin
1. Open `WEBSITE_URL` → **Get started** → register with **your real email**.
2. Supabase sends a confirmation email (check spam). Click the link, then **sign in**.
3. Supabase → **SQL Editor** → **New query** → paste, with your email:
   ```sql
   update public.users set role = 'admin' where email = 'you@example.com';
   ```
   → **Run**. It should say `1 row affected` (`Success. No rows returned` is also fine).
4. In SkillForge click **Sign out**, then sign in again. You now land on the **Admin** page.
5. Check **Integrations**: you want `llm: gemini…`, `execution: judge0`, `database: postgresql`,
   `vector search: pgvector`. (`queue: in-process` is expected on the free plan.)
6. **Security check (important):** Supabase → **Advisors** → **Security Advisor** → **Refresh**.
   There must be **no** "RLS Disabled in Public" errors. SkillForge turns Row Level Security on for
   all its tables automatically, which stops anyone from reading your data with the public anon key.
   If you do see that error for a table, copy the message and ask for help before inviting users.

### 6.4 Test like a learner
Use a **second email** (for example a Gmail `+` address: `you+learner@gmail.com`):
1. Register → confirm the email → sign in → finish **onboarding**.
2. **Skill DNA** → take a **Concept check**.
3. **Missions** → open a coding mission → press **Run**, then **Submit**.
4. Open your **Public ledger** link from the sidebar in a private browser window.

✅ **Done — SkillForge AI is live.**

---

## Part 7 — Keep it awake (optional, recommended)

Free Render servers sleep after ~15 minutes without visitors (the next visit takes ~1 minute), and
free Supabase projects **pause after 7 days** without activity.

1. Go to **https://uptimerobot.com** → free sign-up.
2. **Add New Monitor** → type **HTTP(s)** → URL: `BACKEND_URL/api/health` → interval **5 minutes** → **Create**.

This visits your backend every 5 minutes, which also runs a tiny database query, so both stay awake.
(Render's free plan includes enough hours per month for one always-on service.)

---

## Everyday tasks

**Update the live site after changing code:** push to GitHub — Render and Vercel redeploy automatically.
```bash
git add -A
git commit -m "describe the change"
git push
```

**If a secret leaks** (you pasted it somewhere public): create a new one in that service, update it
in Render/Vercel, and delete the old one. For `JWT_SECRET`, use Render → Environment → **Generate**
(this signs everyone out).

**Free-plan limits to remember**
- ~50 code executions per day (Judge0 free plan).
- Supabase sends only a few confirmation emails per hour on the free plan; if testers don't get
  emails, wait or turn off **Confirm email** under Authentication → Sign In / Providers → Email
  (less secure — only for testing).
- Vercel Hobby is for personal, non-commercial use. If you start charging money, you must upgrade.
- 500 MB database — plenty for hundreds of learners.

## Troubleshooting

| What you see | What to do |
|---|---|
| Website says *Cannot reach the SkillForge API* | Wait 1 minute (server waking up). Still failing → check `NEXT_PUBLIC_API_URL` in Vercel equals `BACKEND_URL`; after changing it, Vercel → **Deployments** → **⋯** → **Redeploy**. |
| Sign-in works but then *Could not link your Supabase account* | `SUPABASE_URL` missing/wrong in **Render** (not only Vercel). |
| *Check your inbox to confirm your email* | Click the email link first; check spam. |
| Browser console shows a **CORS** error | `CORS_ORIGINS` in Render must exactly equal `WEBSITE_URL` — `https://`, no `/` at the end. |
| Submissions say *Code execution engine unavailable* | Daily Judge0 limit reached, or `JUDGE0_API_KEY` wrong. Check usage in the RapidAPI dashboard. |
| Supabase dashboard says **Paused** | Click **Restore project**, then set up Part 7. |
| Render build fails | Open **Logs**, copy the last 30 lines, and ask for help. |
