FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --create-home app && mkdir /state && chown app:app /state
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
