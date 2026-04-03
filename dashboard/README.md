# LLM Proxy Dashboard

A React-based web dashboard for monitoring and managing the LLM Proxy.

## Features

- **Real-time Metrics**: Request rates, latency, cache performance
- **A/B Testing Monitor**: Traffic split, variant performance comparison
- **Cache Insights**: Hit/miss rates, token savings
- **Template Management**: View available prompt templates
- **Live Logs**: Stream proxy logs in real-time

## Quick Start

### Option 1: Standalone (CDN-based, no build)

Simply open `public/index.html` in a browser after starting the LLM Proxy:

```bash
# Start the proxy
cd .. && python -m llmproxy.server

# Open dashboard
open dashboard/public/index.html
```

### Option 2: Docker Compose (Recommended)

The dashboard is served automatically when using docker-compose:

```bash
cd ..
docker-compose -f docker-compose.dev.yml up -d
```

Access dashboard at: http://localhost:8080/dashboard/

### Option 3: Build and Deploy

For production deployment with a proper build:

```bash
# Install dependencies
npm install

# Build
npm run build

# Serve build/
npx serve -s build -l 3000
```

## Screenshots

### Overview Tab
- Total requests, cache hit rate, latency, errors
- Request rate and latency charts
- A/B testing status
- Cache performance

### Metrics Tab
- Raw JSON metrics from `/metrics` endpoint
- Detailed statistics

### Templates Tab
- List of available prompt templates
- Variable counts and descriptions

### Logs Tab
- Live log streaming
- Filter and search capabilities

## API Endpoints Used

- `GET /health` - Health status
- `GET /metrics` - Proxy metrics
- `GET /metrics/prometheus` - Prometheus format
- `GET /ab-test/status` - A/B testing status
- `GET /templates` - Available templates

## Development

The dashboard uses:
- React 18 (CDN)
- Tailwind CSS (CDN)
- Chart.js for visualizations
- Font Awesome icons

No build step required for development - just edit `src/App.js` and refresh.

## Environment Variables

The dashboard auto-detects the API base URL from `window.location.origin`.

To override:
```javascript
const API_BASE = process.env.REACT_APP_API_URL || window.location.origin;
```

## License

MIT - Same as LLM Proxy
