# FB Marketplace Deal Finder - Dev Setup

## Prerequisites

- Docker and Docker Compose
- Facebook cookies for authentication

## Setup Instructions

### 1. Set Up Facebook Authentication

Facebook Marketplace requires authentication. Export your Facebook cookies:

1. Install a browser extension like [Cookie-Editor](https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
2. Log into Facebook in your browser
3. Export cookies as JSON
4. Create `cookies` directory and save cookies:
   ```bash
   mkdir cookies
   # Save exported cookies as cookies/facebook_cookies.json
   ```

### 2. Start with Docker

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
