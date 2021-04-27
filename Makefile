init:
	pip install -r requirements.txt

docker-start:
	docker run --name telex2reddit --restart unless-stopped -d -v "`pwd`/.config:/srv/.config" -v "`pwd`/.data:/srv/.data" -v "`pwd`/log:/srv/log" -e HOME=/srv rutkai/telex2reddit

docker-build:
	docker build . -t telex2reddit
	docker tag telex2reddit rutkai/telex2reddit:latest

docker-push:
	docker push rutkai/telex2reddit:latest
