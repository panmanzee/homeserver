FROM python:3.12-slim
RUN useradd -m -u 10001 portal && mkdir /data && chown portal /data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
COPY static ./static
USER portal
EXPOSE 8100
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100", "--proxy-headers"]
