# ArtGuard frontend

React 18 + TypeScript + Vite. See the repository root [README.md](../../../README.md) for full setup, environment variables, and deployment.

Running the Frontend Locally:

```bash
npm install
npm run dev
```

Scripts: `build`, `preview`, `typecheck`, `test`, `test:watch`, `test:coverage`, `test:e2e`.

Testing layout, commands, mocking, coverage thresholds, and CI are documented in [tests/README.md](tests/README.md).

## Features

- **Home (`/`)** — Hero, artwork mosaic (public-domain images from `public/art/`), short pipeline overview, and calls to action that depend on auth state (sign up, log in, or go to upload).
- **Sign up (`/signup`)** — Create an account; on success, redirects to login (or signs in when a real API is configured).
- **Login (`/login`)** — Email and password; redirects authenticated users to upload.
- **Upload (`/upload`, protected)** — Drag-and-drop or file picker, artist and artwork title, image preview, then runs analysis (real API when `VITE_API_URL` is set, otherwise a built-in mock pipeline). Results are stored in `localStorage` for the latest run; in mock mode, history is also appended per user.
- **Results (`/results`, protected)** — Shows the latest analysis from `localStorage` (written right after upload; see [Results page: local snapshot](#results-page-local-snapshot)): **prediction confidence** (mean of per-patch authenticity probabilities), verdict, RAG-style explanation when present, **per-patch authenticity heatmap** overlay when patch data is present, and **Download** (opens the browser print dialog for a simple printable view).
- **History (`/history`, protected)** — Lists past analyses from the backend (`GET` inferences with cursor pagination) or from `localStorage` in mock mode. **Search** by artist, artwork, or file name; **filter** by verdict-style buckets (e.g. authentic / uncertain / forged / failed inference); **sort** by date or score. Per-item delete and **clear all** with confirmation (mock mode clears local storage; API mode calls the backend).
- **Profile (`/profile`, protected)** — View/update username and email, change password (with separate validation), optional **analysis count** from `/inferences/stats` when the API exists (otherwise derived from local history). Success feedback uses toast notifications.
- **Global UI** — Shared header with navigation and account menu, route protection for authenticated sections, global error boundary, and **Sonner** toasts where used (e.g. profile).

## Results page: local snapshot

The **`/results`** route does **not** fetch the inference again from the API when you open it. After a successful upload, **`UploadPage`** writes the analysis payload to `localStorage` under `artguard_latest_result`, and **`ResultsPage`** only reads that key. If the key is missing or invalid, the user is sent back to `/upload`.

**Why it is done this way:** the upload flow already has the full response (from `POST /inference` when `VITE_API_URL` is set, or from the mock pipeline otherwise). Showing results from that snapshot avoids an extra round trip for the usual “I just ran an analysis” path.

**Tradeoffs:** `/results` is not a durable bookmark—new browser, cleared storage, or private mode means there is nothing to show. The screen also will not reflect later server-side changes to the same inference (for example, if the API ever returned an early state and completed asynchronously) unless the app is extended to poll or refetch. If you need **stable deep links** or **reload-by-id** behavior, introduce something like `/results/:inferenceId` and load with **`GET`** on mount (and optionally keep `localStorage` as a cache).

## User input validation

Validation is **not** handled by a separate schema library (no Zod/react-hook-form). It combines **HTML5 constraints**, **imperative checks in components**, and **shared rules in `AuthContext`**, with **API errors** normalized for display.

### HTML5 and forms

- **`required`** on important fields (e.g. username, email, password on auth forms).
- **`type="email"`** on email inputs so the browser enforces a basic email shape before submit.
- **Submit handlers** call `preventDefault()` and run additional checks where needed.

### Authentication (`src/app/contexts/AuthContext.tsx`)

Shared rules used for both **mock mode** (localStorage-backed users) and **API mode** (backend still enforces its own rules):

| Action | Rules |
|--------|--------|
| **Sign up** | Username length ≥ 3; email must match a simple pattern (`/^[^\s@]+@[^\s@]+\.[^\s@]+$/`); password length ≥ 6. Mock mode also rejects duplicate emails. |
| **Login** | Credentials checked against the API or stored users; failures surface as `Invalid email or password` in mock mode. |
| **Update profile** | Same username and email rules as sign up; mock mode rejects email already used by another user. |
| **Change password** | New password length ≥ 6 (also re-checked on the profile page together with confirm-password matching). |

The **sign up** and **login** pages rely on the context for semantic validation; **sign up** only adds `required` / `type="email"` at the markup level—if context throws, the page shows the message via `getErrorMessage()` in an alert.

### Profile page (`src/app/pages/ProfilePage.tsx`)

- **Profile form**: Username ≥ 3 characters; email must contain `@` (a lighter check than the context regex; the context still validates on save).
- **Password form**: Current password required; new password ≥ 6 characters; new and confirm fields must match.

### Upload page (`src/app/pages/UploadPage.tsx` + `src/app/lib/uploadLimits.ts`)

- **File extension** must be one of `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tiff`, `.webp` (case-insensitive), via `hasAllowedImageExtension()`—aligned with backend expectations.
- **MIME type** must start with `image/`.
- **Size** must not exceed **20 MB** (`MAX_UPLOAD_BYTES`), documented to match backend `MAX_UPLOAD_SIZE_BYTES`.
- **Artist name** and **artwork name** must be non-empty after trim.
- The submit button’s enabled state mirrors the same requirements (file + both names).

### Displaying errors

- `getErrorMessage()` in `src/app/types/index.ts` turns thrown `Error` instances, API-style objects with `message`, or unknown values into a string for alerts and inline error text.

For **production**, treat server-side validation as authoritative; the frontend rules mirror the main constraints so users get fast feedback before network calls.
