FROM python:3-alpine

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

CMD [ "python", "-u", "./app.py" ]

EXPOSE 80

HEALTHCHECK CMD python -c "import requests; requests.get('http://localhost:80/healthz')"
