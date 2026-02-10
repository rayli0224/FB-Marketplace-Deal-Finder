# FB Marketplace Deal Finder - Dev Setup

## Prerequisites

- Docker and Docker Compose

## Setup Instructions

### 1. Start with Docker

```bash
./docker/restart.sh
```

Enter the container:
```bash
./docker/into.sh
```

Inside the container, start services in separate terminals:

**Terminal 1 - API:**
```bash
./docker/into.sh
ahoy plunder
```

**Terminal 2 - Frontend:**
```bash
./docker/into.sh
ahoy show_loot
```

Access:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

When you first open the app, you’ll be guided to connect your Facebook account (one-time setup so the app can search Marketplace).

### Debug mode (developers)

To inspect what the backend is doing during a search, start the API with the debug flag:

```bash
ahoy plunder --debug
```

With the API running in debug mode, the frontend shows an expandable **Debug** panel below the main content (during and after a search). The panel includes:

- **Search request** — query, zip, radius, max listings, threshold, and options used for the run
- **Facebook query details** — raw data retrieved from Marketplace for each listing (title, price, location, url, description)
- **Generated eBay query** — the eBay search query produced by the API for each listing

The panel resets when you start a new search. If the API is not started with `--debug`, the debug panel does not appear.
