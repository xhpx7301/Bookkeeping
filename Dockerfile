FROM python:3.12-slim
WORKDIR /app
COPY loan-ledger.html server.py bookkeeping_store.py manage.py ./
RUN mkdir -p /app/data
ENV PORT=8080 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "server.py"]
