FROM python:3.9-alpine

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
VOLUME /srv/data

CMD ["python", "./bin/telex2reddit"]
