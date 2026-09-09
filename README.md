# OAU Thesis Bank — Refactored Frontend

This is a structural refactor of the supplied 45-screen TSX prototype.

## What changed
- Split the 45 screen components into individual files.
- Moved shared UI, layouts, mock data, routing context, and animation variants into `src/components/shared.tsx`.
- Added a clean Vite + React + TypeScript entry point.
- Added Tailwind/PostCSS configuration.
- Preserved the existing custom screen-ID navigation so the UI flow remains intact.
- Fixed the shared Button API to support the existing `size="sm"` usage.

## Run
```bash
npm install
npm run dev
```

Then open the local Vite URL shown in the terminal.

## Screen files
`src/screens/Screen01.tsx` through `src/screens/Screen45.tsx`.

This is intentionally a frontend refactor first. Backend/API/database integration should be done after the frontend builds cleanly.
