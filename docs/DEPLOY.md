# Configuration and deployment

## Environment variables

Read from the environment or a local `.env` file (see `.env.example`).

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required. |
| `DEBUG` | `true` for local development. Defaults to false. |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Comma-separated lists. |
| `BEHIND_PROXY` | `true` behind a TLS-terminating proxy such as Render. Trusts `X-Forwarded-Proto`. |
| `SERVE_MEDIA` | `true` to serve uploaded profile pictures through Django when `DEBUG=false`. Demo only: the files sit on the host's disk, which is ephemeral on Render. |
| `SECURE_SSL` | Defaults to true when `DEBUG=false`: secure cookies, HTTPS redirect and a one-hour HSTS header. Set `false` to run a production-mode build over plain http locally. |
| `DEMO_MODE` | `true` turns the site into a read-only portfolio demo (see below). Defaults to false. |
| `GOOGLE_MAPS_FRONTEND_KEY`, `GOOGLE_MAPS_BACKEND_KEY` | Optional. Enable maps and geocoding. Without them geocoding is skipped and maps show a placeholder. |
| `EMAIL_USER`, `EMAIL_PASS` | Optional. Without them password-reset emails print to the console. |

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Demo data

`python population_script.py` seeds 10 bands, 30 musicians, gigs, applications and reviews. It downloads profile pictures from picsum.photos and skips them when offline.

- It only seeds when no non-admin users exist. `--reset` deletes all non-admin users first.
- Only `band_user_1` and `musician_1` can log in (password `Password123!`). All other seeded users have unusable passwords.

## Read-only portfolio demo

With `DEMO_MODE=true` (off by default; `render.yaml` does not set it, so add it as an environment variable in the Render dashboard to turn the demo on):

- Anyone can browse gigs, musicians and bands without an account. A banner labels everything as generated sample data.
- "Try as musician" / "Try as band" sign the visitor in as the seeded `musician_1` or `band_user_1` to show both dashboards.
- The server rejects every non-GET request (HTTP 403) except demo sign-in and sign-out, for all visitors including real accounts and the admin. Sign-up, password login, profile edits, applications, reviews and listing changes therefore cannot run, nothing is written to the shared database, and one visitor cannot change what another sees. Edits do not persist.
- Maps need no key: without `GOOGLE_MAPS_FRONTEND_KEY` the gig page shows a "Map not configured" placeholder.
- Cold start: `render.yaml` runs `migrate` and `population_script.py` on every start. The seed uses a fixed random seed and skips if users exist. Set `SEED_SKIP_IMAGES=true` to skip the picture downloads.

## Production-mode run

```bash
python manage.py collectstatic --noinput   # hashed, compressed files served by WhiteNoise
python manage.py migrate
gunicorn find_my_gig.wsgi
```

Set `SECURE_SSL=false` if you are not behind HTTPS.

## Render

`render.yaml` builds with `pip install`, `collectstatic`, `migrate` and the population script. On every start it runs `migrate --noinput` and the population script, then `gunicorn find_my_gig.wsgi`. Set `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the Maps keys in the Render dashboard. `DEMO_MODE` is not set in `render.yaml`: set `DEMO_MODE=true` in the Render dashboard to turn the read-only demo on (and redeploy), and leave it unset for a normal site.

SQLite and uploaded media live on Render's ephemeral disk, so all data, including the demo data, resets on each deploy and restart. That suits a demo and not real use.
