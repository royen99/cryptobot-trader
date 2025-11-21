# CryptoBot Dashboard 📊
# Lightweight FastAPI web UI for monitoring and configuring the trading bot

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY templates/ templates/
COPY static/ static/

# Expose port (because dashboards need to be accessible 🌐)
EXPOSE 8000

# Health check (keeps Docker happy)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()"

# Run the dashboard
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
