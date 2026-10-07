# ASTRAVEL

Trip planner: build itineraries on a map, budget costs, share trips with friends. Live at https://astravel.pandeploy.dev

## Parts
- `web/`: static front end (vanilla JS, no build step) served by nginx. nginx also proxies `/api/` to the API.
- `api/`: FastAPI service. PostgreSQL for all data. Real accounts (email + password, Google sign-in), trips, wishlist, follows, reviews and an admin console with roles and permissions.

## What is real
- Accounts: argon2 password hashes, HttpOnly session cookies stored (hashed) in the database, login throttling, Google ID-token verification.
- Every write is checked on the server: a trip can only be changed by its owner or invited members, admin endpoints check the role's permission matrix, and the last Super Admin can't be removed.
- Admin console: dashboard (live request counts, service health), users (search, filter, change role/status, delete), reports (date range, CSV export), roles and permissions (saved and enforced), audit log, settings (including maintenance mode).
- Maps: Leaflet + OpenStreetMap tiles; place search and tap-to-add use OpenStreetMap Nominatim.

## Configuration (api container environment, never committed)
| Variable | Meaning |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (dedicated `astravel` database and role) |
| `SESSION_SECRET` | random string used to hash session tokens |
| `ADMIN_EMAILS` | comma-separated emails that become Super Admin after a verified Google sign-in |
| `GOOGLE_CLIENT_ID` | OAuth Web client ID (public value). Empty = Google button disabled |
| `COOKIE_SECURE` | `1` behind HTTPS |

## Deploy (as on the home server)
```
docker build -t astravel-api:1 api/
docker run -d --name astravel-api --network coolify --env-file astravel-api.env --read-only --tmpfs /tmp --cap-drop=ALL astravel-api:1
# web: copy web/site to a release folder web/site/v/<id>/ for js/css and point index.html at it (cache busting), then
docker build -t astravel:N web/ && docker run -d --name astravel --network coolify --read-only --tmpfs /tmp --tmpfs /var/cache/nginx --cap-drop=ALL astravel:N
```
Traefik routes `astravel.pandeploy.dev` to `http://astravel:8080`.
