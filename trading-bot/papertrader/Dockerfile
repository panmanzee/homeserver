FROM python:3.12-slim
RUN pip install --no-cache-dir pandas==2.2.3 numpy yfinance requests exchange_calendars
WORKDIR /app
COPY *.py /app/
CMD ["python", "/app/engine.py", "--loop"]
