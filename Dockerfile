FROM python:3.11-slim

WORKDIR /app

COPY pdf_management_system/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN rm -rf /app/requirements.txt

COPY pdf_management_system/ .

EXPOSE 8080

CMD ["python3", "-m", "app.main"]