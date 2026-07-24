# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**seasons-landing** is the static marketing landing page for the Seasons streaming subscription management application. It's a simple, no-build HTML site that deploys automatically to GitHub Pages.

**Technology**: Static HTML, Tailwind CSS (via CDN), HubSpot Forms
**Domain**: getseasons.app (configured via CNAME)
**Deployment**: Automatic via GitHub Pages on push to main branch

## Architecture

This is a pure static site with no build process:
- Single-page application using vanilla HTML
- Tailwind CSS 2.2.19 loaded via CDN (no compilation needed)
- Google Fonts (Roboto, Poppins) loaded externally
- Third-party scripts: HubSpot forms, HubSpot analytics, Ahrefs analytics

### File Structure
```
seasons-landing/
├── index.html              # Main landing page
├── privacy.html            # Privacy policy page
├── terms.html              # Terms & conditions page
├── raffleterms.html        # Raffle-specific terms
├── raffleprivacy.html      # Raffle-specific privacy policy
├── CNAME                   # Domain configuration (getseasons.app)
└── [images]                # Logo, screenshots, app store badges, etc.
```

## Key Integration Points

### HubSpot Email Collection
The landing page includes a HubSpot embedded form for Android waitlist signups:
- Portal ID: `143716468`
- Form ID: `415cef43-1df1-4f94-9092-e75596c8a18f`
- Region: `eu1`

Located in index.html:114-121

### Analytics
- HubSpot tracking script (index.html:138)
- Ahrefs analytics with key: `Frzrh8qNZTzuh24CdTpoXQ` (index.html:141)

### External Links
- App Store: https://apps.apple.com/gb/app/seasons-streaming-companion/id6502302869
- Email: feedback@getseasons.app
- Social: Twitter (@getseasons), Facebook (getseasonssc)

## Development Workflow

### Local Development
No build process required. To preview changes:
```bash
# Option 1: Open directly in browser
open index.html

# Option 2: Use a simple HTTP server
python3 -m http.server 8000
# Then visit http://localhost:8000

# Option 3: Use npx serve
npx serve .
```

### Deployment
Push to main branch automatically deploys to GitHub Pages:
```bash
git add .
git commit -m "Update landing page"
git push origin main
```

Changes are live at getseasons.app within 1-2 minutes.

## Design System

### Color Scheme
- Primary brand: `#6C4EFF` (purple)
- Background: Dark with gradient overlay using header.png
- Text: Indigo-400, Purple-400, Purple-100, White
- Links: Blue-300 hover to Pink-500

### Typography
- Primary: Roboto (400-900 weights)
- Secondary: Poppins (400, 700)
- Fallback: System fonts

### Key Visual Elements
- Background image: header.png (full-page cover)
- Hero image: backgroundSite.png (responsive width: 100% → 50% on larger screens)
- App store badge: App Store.svg
- Social icons: Inline SVG

## Content Structure

### Main Landing Page (index.html)
1. Navigation bar with logo and social links
2. Hero section with tagline
3. Hero image showcase
4. App Store download button
5. HubSpot email signup form (Android waitlist)
6. Footer with copyright and attribution

### Static Pages
- **privacy.html**: Privacy policy (effective 2024-05-15)
- **terms.html**: Terms & conditions (effective 2024-05-15)
- **raffleterms.html**: Raffle-specific terms
- **raffleprivacy.html**: Raffle-specific privacy policy

## Relationship to Broader Seasons Ecosystem

This landing page is part of the larger Seasons monorepo:
- **Purpose**: Marketing and lead generation
- **Independence**: Completely standalone, no API integration
- **Goal**: Drive App Store downloads and collect Android waitlist emails
- **Branding**: Shares visual identity with iOS/Android apps

The landing page does NOT interact with the SeasonsBackend API or share authentication with mobile apps.

## Common Tasks

### Update App Store Link
Edit index.html:99-100

### Change Branding/Colors
- Brand color defined inline: index.html:36 (`#6C4EFF`)
- Tailwind colors used throughout (indigo, purple, pink)

### Modify Email Form
Replace HubSpot form embed code at index.html:114-121

### Update Social Links
Edit navigation section: index.html:40-64

### Add New Pages
1. Create new .html file
2. No linking required unless adding to navigation
3. Ensure consistent styling (copy header from index.html or privacy.html)

## Template Attribution

Based on Rainblur Landing Page template from Tailwind Toolbox (MIT License)
- Original template: https://www.tailwindtoolbox.com/templates/rainblur-landing-page
- See README.md for full attribution

## Contact & Legal

- **Copyright**: MYV Studios LTD - 2024
- **Support Email**: contact@myvstudios.com
- **Feedback Email**: feedback@getseasons.app
