# Verifying ArtGuard API endpoints with `curl`

Set your **HTTPS** API base (same host as the frontend when using CloudFront, or `https://api.example.com` with a custom domain):

```bash
export API_BASE="https://YOUR_CLOUDFRONT_OR_ALB_HOST"   # no trailing slash
```

All **authenticated** routes use:

```http
Authorization: Bearer <access_token>
```

Get a token from `POST /auth/login` or `POST /auth/signup`.

---

## Public (no auth)

**Health**

```bash
curl -sS "${API_BASE}/health"
```

**API info**

```bash
curl -sS "${API_BASE}/"
```

---

## Auth (JSON)

**Sign up**

```bash
curl -sS -X POST "${API_BASE}/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"secret12"}'
```

**Log in** (save token)

```bash
export TOKEN=$(
  curl -sS -X POST "${API_BASE}/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"secret12"}' \
  | jq -r '.access_token'
)
echo "$TOKEN"
```

---

## Authenticated (Bearer)

**Current user**

```bash
curl -sS "${API_BASE}/auth/me" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Inference stats (count)**

```bash
curl -sS "${API_BASE}/inferences/stats" \
  -H "Authorization: Bearer ${TOKEN}"
```

**List inference history**

```bash
curl -sS "${API_BASE}/inferences?limit=10" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Get one inference** (replace `INFERENCE_ID`)

```bash
curl -sS "${API_BASE}/inferences/INFERENCE_ID" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Delete one inference**

```bash
curl -sS -X DELETE "${API_BASE}/inferences/INFERENCE_ID" \
  -H "Authorization: Bearer ${TOKEN}" \
  -w "\nHTTP %{http_code}\n"
```

**Delete all inferences** (optional confirmation in app; API is destructive)

```bash
curl -sS -X DELETE "${API_BASE}/inferences" \
  -H "Authorization: Bearer ${TOKEN}"
```

---

## `POST /inference` (multipart)

Form fields:

| Field          | Type   | Notes                          |
|----------------|--------|--------------------------------|
| `file`         | file   | Image upload                   |
| `artist_name`  | string | Required, non-empty            |
| `artwork_name` | string | Required, non-empty            |

```bash
curl -sS -X POST "${API_BASE}/inference" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@/path/to/picture.jpg" \
  -F "artist_name=Artist Name" \
  -F "artwork_name=Artwork Title"
```

---

## Tips

- Use **`https://`** for the same origin as the browser to avoid mixed content; match **`VITE_API_URL`**.
- If you get **301/302**, ensure the URL has no trailing slash on `API_BASE` or follow redirects: `curl -L`.
- Pretty JSON: pipe through **`jq`**.
- **401**: missing/expired token or wrong `Authorization` header.
- **403** from CloudFront/S3: you hit a path routed to the wrong origin; API paths must be the ones configured in CloudFront (e.g. `/auth/*`, `/inference*`, `/inferences*`).

---

## One-liner: health + login + me

```bash
API_BASE="https://dxxxx.cloudfront.net"   # edit
curl -sS "${API_BASE}/health" | jq .
TOKEN=$(curl -sS -X POST "${API_BASE}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"yourpassword"}' | jq -r '.access_token')
curl -sS "${API_BASE}/auth/me" -H "Authorization: Bearer ${TOKEN}" | jq .
```
