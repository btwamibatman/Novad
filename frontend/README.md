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
npm run type-check
npm test
npm run test:e2e
npm run build
```

The production build is written to `app/web/dist`.
