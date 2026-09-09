import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("SERVICE_API_KEY", "test-service-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
