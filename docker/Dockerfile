FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

# Install Playwright browsers
RUN playwright install chromium

# Copy application code
COPY botengine/ botengine/
COPY recorder/ recorder/
COPY dashboard/ dashboard/
COPY flows/ flows/
COPY examples/ examples/

# Create runtime directories
RUN mkdir -p /app/.botflow/runs /app/.botflow/heals /app/.botflow/confidence /app/.botflow/screenshots

# Default environment
ENV PYTHONUNBUFFERED=1
ENV BOTFLOW_FLOWS_DIR=/app/flows
ENV BOTFLOW_DATA_DIR=/app/.botflow
ENV BOTFLOW_HEADLESS=true

# Default command: run the example bot
CMD ["python", "examples/betting_bot/bot.py"]
