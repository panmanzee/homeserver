import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("SERVICE_API_KEY", "test-service-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-bot-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "648810")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("TASKBOT_RUN_WORKERS", "false")
