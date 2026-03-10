# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev      # Start dev server at http://localhost:3000
npm run build    # Production build
npm run lint     # Run ESLint
```

No test framework is configured yet.

## Architecture

Next.js 16 app using the App Router (`app/` directory), React 19, TypeScript, and Tailwind CSS v4.

- `app/layout.tsx` — Root layout with Geist font setup and global metadata
- `app/page.tsx` — Home page (currently the default scaffold)
- `app/globals.css` — Global styles (Tailwind base)

This project is a fresh scaffold. Application code for "market-radar" has not been built yet.
