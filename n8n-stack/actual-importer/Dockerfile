FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 make g++ ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json .
RUN npm install --omit=dev

COPY importer.mjs .

# Polling loop: check the sms-gateway queue for new transactions every 60s
# and write any not-yet-imported ones into Actual Budget.
CMD ["node", "importer.mjs"]
