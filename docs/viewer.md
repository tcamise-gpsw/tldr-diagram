# Viewer

The viewer is a React + TypeScript SPA that renders architecture diagrams on an HTML5 canvas.

## Features

- **Navigable views** — click the expand icon on a group node (or double-click) to drill into its view. Breadcrumb navigation and browser back button to go up.
- **Pan and zoom** — drag to pan, scroll wheel to zoom. Fit button resets the view.
- **Node selection** — click a node to see its details and connectors in the side panel.
- **External stubs** — dashed rays showing connections to elements outside the current view. Toggle with the toolbar button.
- **Side panel** — collapsible, resizable. Shows element name, kind, description, technology. Connector table with 5 sortable columns: Direction, Target, Module, Relationship, View. Click a connector row to navigate to the target.
- **Transition animations** — smooth camera transitions when drilling in and out of views.
- **Dark theme** — GitHub Dark palette.

## Development

```bash
cd frontend
npm install
npm run dev       # Vite dev server on http://localhost:5173
npm test          # Vitest unit tests
npm run test:watch
npm run build:app # Production build → dist/
```

The `public/` directory contains sample `elements.yaml` and `connectors.yaml` — the dev server serves these for local development.

## Tech Stack

- React 18, TypeScript 5, Vite 6
- dagre for graph layout
- js-yaml for YAML parsing
- Canvas 2D API for rendering (not SVG/DOM)
- Vitest for unit tests, Playwright for E2E

## File Structure

```
frontend/src/
├── main.tsx                  # Entry point
├── App.tsx                   # Root component, state, navigation
├── theme.ts                  # Colors, dimensions, fonts
├── styles.css                # Layout, panel, breadcrumb styles
├── data/
│   ├── types.ts              # DiagramData, Element, Connector, ViewTree
│   └── loader.ts             # YAML fetch, parse, ViewTree construction
├── canvas/
│   ├── CanvasViewport.tsx     # Canvas wrapper, RAF loop, mouse events
│   ├── layout.ts             # dagre layout computation + caching
│   ├── renderer.ts           # Draw nodes, connectors, stubs
│   ├── camera.ts             # Pan, zoom, fitToContent
│   ├── hitTest.ts            # Click/hover detection
│   ├── animation.ts          # Drill-in/out transitions
│   └── stubs.ts              # External connector visualization
└── components/
    ├── SidePanel.tsx          # Panel UI
    ├── SidePanel.logic.ts     # Connector resolution, sorting
    ├── Toolbar.tsx            # Fit + external stubs toggle
    └── Tooltip.tsx            # Hover tooltip
```
