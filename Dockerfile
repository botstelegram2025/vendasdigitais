FROM python:3.11
WORKDIR /app
COPY . .
CMD ["python", "bot_final_postgres.py"]
COPY requirements.txt .
RUN pip install -r requirements.txt
