FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install flask apig-wsgi boto3 --no-cache-dir
COPY app/ ./app/
COPY static/ ./static/
COPY lambda_handler.py .
ENV PYTHONPATH=/app/app
EXPOSE 8082
CMD ["python", "app/main.py"]
