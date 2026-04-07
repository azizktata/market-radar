FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
EXPOSE 8000
VOLUME /data
CMD ["sh", "-c", "python create_superadmin.py && uvicorn main:app --host 0.0.0.0 --port 8000"]
