FROM python:3.9-alpine

WORKDIR /srv
ENV PYTHONPATH=/srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
VOLUME /srv/.data
VOLUME /srv/.config
VOLUME /srv/log

CMD ["python", "./bin/telex2reddit"]
