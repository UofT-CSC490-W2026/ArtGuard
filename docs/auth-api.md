# ArtGuard API authentication

## Environment (backend)

| Variable | Description |
|----------|-------------|
| `DDB_USERS_TABLE` | DynamoDB users table name (already set on ECS from Terraform). |
| `JWT_SECRET_KEY` | Secret for HS256 JWT signing. In AWS: injected from Secrets Manager (`JWT_SECRET_KEY`). Local dev: set explicitly or rely on insecure default only when `ENVIRONMENT=dev`. |
| `JWT_ACCESS_TOKEN_EXPIRE_SECONDS` | Optional. Default `3600` (1 hour). |
| `CORS_ALLOW_ORIGINS` | Optional. Comma-separated origins or `*` (default). |
| `S3_INFERENCE_PRESIGN_EXPIRES` | Optional. Presigned GET TTL in seconds for inference thumbnails (default `86400`). |
| `INFERENCE_TTL_DAYS` | Optional. DynamoDB `ttl` attribute for inference rows (default `90`). |

## Local Python deps

```bash
pip install -r requirements.txt
```

(Docker installs the same file.)

## Endpoints

| Method | Path | Auth | Body | Response |
|--------|------|------|------|----------|
| POST | `/auth/signup` | — | `{ username, email, password }` | `{ access_token, token_type, user }` |
| POST | `/auth/login` | — | `{ email, password }` | `{ access_token, token_type, user }` |
| GET | `/auth/me` | Bearer | — | `{ id, username, email }` |
| PUT | `/auth/profile` | Bearer | `{ username, email }` | `{ access_token, token_type, user }` |
| POST | `/auth/change-password` | Bearer | `{ currentPassword, newPassword }` | `200` `{ "ok": true }` |

`user.id` is the DynamoDB `user_id`.

## Terraform

- New secret: `artguard/jwt-secret-<env>` — **replace the placeholder value** in AWS Secrets Manager after first apply with a long random string (32+ bytes).

## Frontend

- Set `VITE_API_URL` to the API base URL (no trailing slash). If CloudFront forwards `/api/*` to the ALB, set the base to that origin (e.g. `https://dxxxx.cloudfront.net/api`) so paths like `/inference` resolve correctly.
- Access token is stored in `localStorage` (`artguard_access_token`) and sent as `Authorization: Bearer …` on API calls (except login/signup which use `skipAuth`).
- **Upload / batch analysis:** `POST /inference` with **Bearer** auth and multipart fields `file`, `artist_name`, `artwork_name` (see `src/apps/frontend/src/app/api/analysis.ts`). Response may include `image_url` (presigned GET).
- **History:** `GET /inferences` (paginated), `GET /inferences/stats`, `GET /inferences/{id}`, `DELETE /inferences/{id}`, `DELETE /inferences` (clear all). Each list/detail item includes `image_url` (presigned).
- **Developer tools (authenticated):** route `/developer` in the SPA calls `GET /health`, `POST /process_data`, `POST /rag-query`, `POST /train`, and `POST /evaluate` via `src/apps/frontend/src/app/api/backendApi.ts`.

### Other backend routes (reference)

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| GET | `/health` | — | Health check |
| POST | `/inference` | Bearer | multipart `file`, `artist_name`, `artwork_name` |
| GET | `/inferences` | Bearer | query `limit`, `cursor`; presigned `image_url` per item |
| GET | `/inferences/stats` | Bearer | `{ count }` |
| GET | `/inferences/{id}` | Bearer | single item + presigned `image_url` |
| DELETE | `/inferences/{id}` | Bearer | `204` |
| DELETE | `/inferences` | Bearer | `{ deleted }` clears all for user |
| POST | `/process_data` | — | Spawns ECS pipeline (AWS config required) |
| POST | `/rag-query` | — | JSON `{ "query": "..." }`; Bedrock KB |
| POST | `/train` | — | JSON `{ "variant": "tiny"\|"base", "config"?: {} }` |
| POST | `/evaluate` | — | JSON `{ "variant", "checkpoint": "/checkpoints/..." }` |
