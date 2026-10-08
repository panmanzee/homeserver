FROM python:3.12-slim
ENV LOGNAME=pandeploy USER=pandeploy
RUN useradd -m -u 10002 compute && mkdir /data && chown compute /data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py pve.py sizes.py ./
USER compute
EXPOSE 8110
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8110", "--proxy-headers"]
