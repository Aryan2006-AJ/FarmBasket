FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p instance uploads/products uploads/kyc logs

EXPOSE 5000
ENV FARMBASKET_HOST=0.0.0.0
CMD ["python", "app.py"]
