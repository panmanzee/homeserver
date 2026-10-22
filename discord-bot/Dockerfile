FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Asia/Bangkok
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
