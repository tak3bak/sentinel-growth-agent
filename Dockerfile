FROM python:3.14-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose port 8080 (distinct from your core API on 8000)
EXPOSE 8080

CMD ["uvicorn", "growth_agent_api:app", "--host", "0.0.0.0", "--port", "8080"]
