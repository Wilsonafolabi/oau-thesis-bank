# OAU Thesis Bank — Frontend

Production-oriented React/Vite/TypeScript frontend for the OAU Thesis Bank 45-screen product.

## Included
- Animated responsive public landing experience
- 45 product screens split into maintainable files
- Shared design system and responsive authenticated workspace
- Dedicated Admin Control Center for repository/platform monitoring
- Admin moderation and user management screens
- Direct `/admin` frontend demo access when no user session exists
- Frontend demo role flow; replace with backend authentication before production

## Run
```bash
npm install
npm run dev
npm run build
```

## Routes
- `/` — Landing page
- `/login` — Login
- `/admin` — Admin Control Center (frontend demo mode if no session exists)
- `/admin/moderation` — Content Moderation
- `/admin/users` — User Management

## Backend handoff
See `BACKEND_HANDOFF.md` for API responsibilities. Backend authentication and authorization must be enforced server-side; the frontend demo role is only for development and presentation.
