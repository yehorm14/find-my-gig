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

## Production-mode run

```bash
python manage.py collectstatic --noinput   # hashed, compressed files served by WhiteNoise
python manage.py migrate
gunicorn find_my_gig.wsgi
```

Set `SECURE_SSL=false` if you are not behind HTTPS.

## Render

`render.yaml` builds with `pip install`, `collectstatic`, `migrate` and the population script, and starts `gunicorn find_my_gig.wsgi`. Set `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and the Maps keys in the Render dashboard.

SQLite and uploaded media live on Render's ephemeral disk, so all data, including the demo data, resets on each deploy and restart. That suits a demo and not real use.
