# Testing

## Overview

The ArtGuard frontend uses **Vitest** with **jsdom**, **Testing Library** (React + user-event + jest-dom matchers), and **Playwright** for end-to-end flows. Unit and component tests live under `tests/app/`; Playwright specs live under `tests/e2e/`. As of the last full run, there are **247** unit/component tests across **29** files (see `vite.config.ts` for includes and coverage settings).

Unit tests run in CI via **`frontend-test.yml`** (with **`frontend-coverage.yml`** for coverage badges and reports). E2E runs in the same workflow against a **Vite preview** build, with optional **full-stack** tests when a real FastAPI backend is available.

All commands below assume the current working directory is `src/apps/frontend`.

```bash
# Unit / component tests (Vitest)
npm test

# Watch mode
npm run test:watch

# With coverage (thresholds in vite.config.ts)
npm run test:coverage

# TypeScript (often run with coverage in CI)
npm run typecheck

# End-to-end (Playwright; starts preview server per playwright.config.mjs)
npm run test:e2e

# Single Vitest file
npx vitest run tests/app/pages/ResultsPage.test.tsx
```

---

## Test Architecture

```
tests/
├── setup.ts                      # Shared setup: jest-dom, jsdom polyfills, canvas mock
├── app/
│   ├── App.test.tsx              # Root app shell
│   ├── routes.test.tsx           # Route table / navigation wiring
│   ├── api/
│   │   ├── analysis.test.ts      # Analyze flow (mock + real response mapping)
│   │   ├── backendApi.test.ts    # Backend URL helpers
│   │   ├── client.test.ts        # Fetch wrapper, auth headers, errors
│   │   └── inferencesApi.test.ts # History CRUD, stats, pagination
│   ├── components/
│   │   ├── BrushDivider.test.tsx
│   │   ├── ErrorBoundary.test.tsx
│   │   ├── Header.test.tsx
│   │   ├── PageHeader.test.tsx
│   │   ├── PatchOverlay.test.tsx
│   │   ├── ProtectedRoute.test.tsx
│   │   ├── RootLayout.test.tsx
│   │   └── ui/
│   │       ├── use-mobile.test.ts
│   │       └── utils.test.ts
│   ├── contexts/
│   │   └── AuthContext.test.tsx  # Mock + API auth, validation, localStorage users
│   ├── lib/
│   │   ├── analysisDisplay.test.ts
│   │   ├── artAssets.test.ts
│   │   ├── env.test.ts
│   │   ├── pdfReport.test.ts
│   │   └── uploadLimits.test.ts
│   ├── pages/
│   │   ├── HistoryPage.test.tsx
│   │   ├── HomePage.test.tsx
│   │   ├── LoginPage.test.tsx
│   │   ├── ProfilePage.test.tsx
│   │   ├── ResultsPage.test.tsx
│   │   ├── SignUpPage.test.tsx
│   │   └── UploadPage.test.tsx
│   └── types/
│       └── index.test.ts
└── e2e/
    ├── auth-helpers.ts           # Shared sign-up / login helpers for Playwright
    ├── fixtures/
    │   └── tiny.png              # Minimal PNG used by upload-related specs
    ├── auth.spec.ts              # Signup, login, protected routes
    ├── fullstack.spec.ts         # Live API pipeline (skipped without backend URL)
    ├── history.spec.ts           # History list and interactions in mock mode
    ├── navigation.spec.ts        # Home, header, 404
    ├── profile.spec.ts           # Profile forms in mock mode
    ├── smoke.spec.ts             # Basic load and routing smoke
    └── upload.spec.ts            # Upload, validation, results, heatmap label
```

---

## What We Test

### Page and layout tests

Rendered with **`MemoryRouter`**, **`AuthProvider`**, and route stubs where needed. Typical coverage includes:

- **Forms and validation** — required fields, client-side rules, disabled submit states, and error messages surfaced from context or API-shaped errors.
- **Protected flows** — redirects when unauthenticated, visible content when authenticated.
- **Data-driven UI** — history filters, sorting, pagination controls, empty states, and mock vs API branches where applicable.
- **Results** — `localStorage` snapshot for latest analysis, score/verdict/explanation display, patch overlay when `patchData` exists, download/print hook.

### API and data-layer tests

`fetch` and environment flags are stubbed with **`vi.stubGlobal`** / spies. These tests assert:

- **Request shape** — method, URL, headers (including JWT), and JSON bodies where relevant.
- **Response mapping** — normalization of backend JSON (e.g. snake_case → camelCase, optional fields).
- **Errors** — non-OK HTTP status, network failures, and user-visible error extraction.
- **Mock analysis pipeline** — image dimension loading, delays, and failure paths used when `VITE_API_URL` is unset.

### Component and library tests

- **Shared UI** — header, layout, error boundary, small presentational components.
- **`PatchOverlay`** — image load, overlay toggle, tooltips, canvas draw guards (with mocked canvas context).
- **Pure utilities** — `analysisDisplay`, `uploadLimits`, `env`, `pdfReport`, `artAssets`, `cn` / UI helpers.

### Context tests (`AuthContext`)

Exercises both **mock mode** (localStorage-backed users) and **API mode** (mocked `fetch`): sign up, login, logout, session persistence, profile updates, password change, and shared validation rules.

### End-to-end tests (Playwright)

- **Default configuration** — `playwright.config.mjs` builds the app, serves **`vite preview`** on `127.0.0.1:4173`, and runs **Chromium** only.
- **Mock-mode specs** — Most files under `e2e/` assume **no** `VITE_API_URL` in the built bundle (pure frontend + localStorage). CI runs these with `--grep-invert "Full-stack"`.
- **`fullstack.spec.ts`** — Hits a **real** backend (`VITE_API_URL` / `E2E_BACKEND_URL`). Skipped locally when those are unset; in CI the workflow starts **`scripts/start_e2e_backend.py`** and runs tests matching **`Full-stack`**.

---

## How the DOM and browser APIs are stubbed

Vitest uses the **jsdom** environment. `tests/setup.ts` provides:

- **`@testing-library/jest-dom`** matchers registered for Vitest.
- **`ResizeObserver`** — no-op stub (used by layout-sensitive components).
- **`crypto.subtle`** — minimal mock when missing (password hashing paths).
- **Pointer capture and `scrollIntoView`** — stubs for Radix and similar primitives.
- **`HTMLCanvasElement.prototype.getContext`** — returns a mock 2D context so canvas-based code does not throw; individual tests may override `getContext` for branch coverage.

**`fileParallelism: false`** in `vite.config.ts` reduces flaky **localStorage** interactions across files that exercise `AuthContext`.

---

## Coverage

Coverage is produced by **`npm run test:coverage`** using the **v8** provider. Configuration in **`vite.config.ts`**:

- **Included:** `src/app/**/*.{ts,tsx}` except generated-style UI primitives under `src/app/components/ui/**` (excluded from thresholds).
- **Thresholds (enforced):** **100%** lines and statements, **86%** branches, **93%** functions — adjust only when intentionally changing scope.

Reports: **text**, **html**, **json-summary** (badge pipeline), **lcov** (PR comments via org workflows).

---

## CI/CD Integration

The **`frontend-test.yml`** GitHub Actions workflow:

1. **Unit job** — `npm run typecheck && npm run test:coverage` in `src/apps/frontend` on pushes and pull requests to `main`.
2. **E2E job** — Installs Python deps, starts the **moto-backed** FastAPI app, installs Playwright Chromium, then:
   - `npm run test:e2e -- --grep-invert "Full-stack"` for mock-mode UI tests.
   - `npm run test:e2e -- --grep "Full-stack"` with `VITE_API_URL` / `E2E_BACKEND_URL` pointing at the local API.

The **`frontend-coverage.yml`** workflow updates the frontend coverage badge and uploads the HTML report from the same Vitest coverage output.

```yaml
# .github/workflows/frontend-test.yml (excerpt)
npm run typecheck && npm run test:coverage
npm run test:e2e -- --grep-invert "Full-stack"
# … with backend env …
npm run test:e2e -- --grep "Full-stack"
```
