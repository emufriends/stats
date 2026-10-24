FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY gateway.py /app/gateway.py
COPY http_limits.py /app/http_limits.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "/app/gateway.py"]
