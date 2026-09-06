FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Make scripts executable
RUN chmod +x scripts/*.py 2>/dev/null || true

EXPOSE 8000

CMD ["python", "app.py"]
