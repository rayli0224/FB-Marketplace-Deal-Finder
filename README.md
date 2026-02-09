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
