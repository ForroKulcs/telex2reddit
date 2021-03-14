import configparser
from datetime import datetime
import json
import logging.config
from pathlib import Path
import praw
import praw.exceptions
import ssl
from jsonfile import JsonGzip
from telexhtmlparser import TelexHTMLParser
import urllib.error
import urllib.request

log = logging.Logger
logging.setLoggerClass(log)


def connect_reddit(name: str, useragent: str) -> praw.Reddit:
    reddit = praw.Reddit(name, user_agent=useragent)
    redditor = reddit.user.me()
    assert redditor is not None
    username = redditor.name
    assert username == name
    return reddit


def download_content(url: str, useragent: str) -> str:
    request = urllib.request.Request(url)
    request.add_header('User-Agent', useragent)
    response = urllib.request.urlopen(request, context=ssl.SSLContext())
    data = response.read()
    response_url = response.url
    if response_url != url:
        log.warning(f'URL changed from {url} to {response_url}')
    if b'\x00' in data:
        raise Exception(f'Content is not text: {response_url}')
    charset = response.headers.get_content_charset()
    return data.decode(encoding=charset, errors='replace')


def main():
    telex_json = JsonGzip('telex.json.gz', log=log)
    telex_json.read()

    config_path = Path('telex2reddit').with_suffix('.ini')
    config = configparser.ConfigParser(interpolation=None)
    config.read(config_path, encoding='utf-8')
    useragent = config['telex']['useragent']

    url = config['collect_links'].get('english', '').strip()
    if url == '':
        raise Exception('English URL not available')
    log.info(f'download url: {url}')
    content = download_content(url, useragent)
    html_parser = TelexHTMLParser(log)
    html_parser.feed(content)
    links = set(html_parser.links)
    if len(links) <= 0:
        raise Exception('No english links')

    for link in links:
        telex_link = link.strip('/')
        if telex_link not in telex_json:
            log.warning(f'Unexpected english url: {telex_link}')
            continue
        if not telex_json[telex_link].get('english', False):
            log.info(f'Add english to {telex_link}')
            telex_json[telex_link]['english'] = True

    reddit_config = config['reddit']
    reddit = connect_reddit(reddit_config['username'], reddit_config['script_author'])
    reddit.validate_on_submit = True
    subreddit = reddit.subreddit(reddit_config['subreddit'])
    collection = subreddit.collections(reddit_config['english_collection_id'])
    for submission in collection:
        telex_link = submission.url.strip()
        telex_link = telex_link.removeprefix('https://')
        telex_link = telex_link.removeprefix('www.')
        telex_link = telex_link.removeprefix('telex.hu')
        telex_link = telex_link.strip('/')
        while telex_link in links:
            links.remove(telex_link)
    for link in links:
        telex_link = link.strip('/')
        if telex_link in telex_json:
            if 'reddit_url' in telex_json[telex_link]:
                reddit_url = 'https://reddit.com' + telex_json[telex_link]['reddit_url']
                log.info(f'Add new english post to collection: {reddit_url}')
                collection.mod.add_post(reddit_url)

    telex_json.write(create_backup=True, check_for_changes=True)


if __name__ == '__main__':
    logging_config = json.loads(Path('telex2reddit').with_suffix('.logging.json').read_text())
    for handler in logging_config['handlers'].values():
        if 'filename' in handler:
            Path(handler['filename']).parent.mkdir(exist_ok=True, parents=True)
    logging.config.dictConfig(logging_config)
    log = logging.getLogger(__name__)
    log.info(f'Started at: {datetime.now().replace(microsecond = 0)}')
    main()
    log.info(f'Finished at: {datetime.now().replace(microsecond = 0)}')
