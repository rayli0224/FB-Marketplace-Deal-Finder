# ============================================
# Unified Dockerfile for FB Marketplace Deal Finder
# Includes Python (API + Scrapers) + Node.js (Frontend)
# ============================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99 \
    NODE_VERSION=20

# Install system dependencies and Node.js in one layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For Node.js installation
    curl \
    gnupg \
    # For Playwright and Chrome
    wget \
    unzip \
    # Virtual display
    xvfb \
    # Playwright dependencies
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    # Chrome dependencies
    fonts-liberation \
    fonts-dejavu-core \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy frontend package files first
COPY frontend/package.json frontend/pnpm-lock.yaml* ./frontend/

# Install Frontend dependencies
WORKDIR /app/frontend
RUN pnpm install

# Copy rest of frontend code (this won't overwrite node_modules if it doesn't exist locally)
WORKDIR /app
COPY src/ ./src/
COPY frontend/ ./frontend/

# Verify critical dependencies are installed
WORKDIR /app/frontend
RUN ls -la node_modules/@hookform 2>/dev/null || (echo "⚠️  @hookform/resolvers not found, reinstalling..." && pnpm install @hookform/resolvers react-hook-form zod)

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 3000 8000

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Copy start scripts
COPY docker/start/ /app/docker/start/
RUN chmod +x /app/docker/start/*.sh

# Copy and install ahoy wrapper script
COPY docker/ahoy /usr/local/bin/ahoy
RUN chmod +x /usr/local/bin/ahoy

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]

