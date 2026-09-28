# Document Console frontend

Vue 3, TypeScript and Vite implementation of the Document Console UI.

The production build is served by FastAPI at `/`. During development, Vite serves
the same application under `/web/dist/` and proxies API requests to FastAPI.

## Development

Start FastAPI on port 8000, then:

```bash
npm install
npm run dev
```

Open `http://localhost:5173/web/dist/`. Vite proxies `/api` to FastAPI.

## Checks

```bash
npm ci
npx playwright install chromium
npm run type-check
npm test
npm run test:e2e
npm run build
```

Use Node.js 24, matching the Docker frontend build. On Linux CI, use
`npx playwright install --with-deps chromium` to install browser system libraries.

`npm test` runs Vitest component, store, API-client and composable tests.
Playwright starts Vite automatically on port 5173 and uses mock API responses;
the backend and AI services are not required. Its screenshots and failure traces
are written to `test-results/playwright/`. In CI it also creates an HTML report
in `playwright-report/`.

`npm run build` type-checks application code, unit tests, configuration and E2E
tests, then writes the production frontend to `app/web/dist`. These checks run
automatically in [GitHub Actions](../.github/workflows/ci.yml).
