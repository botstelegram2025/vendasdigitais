FROM python:3.11
WORKDIR /app
COPY . .
CMD ["python", "bot_final_postgres.py"]
