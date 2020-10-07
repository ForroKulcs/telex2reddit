import configparser
from datetime import datetime
import dateutil.parser
import gzip
import html.parser
import json
import logging.config
from pathlib import Path
import praw
import praw.exceptions
import re
import ssl
import time
import urllib.error
import urllib.request

log = logging.Logger
logging.setLoggerClass(log)

class HungarianParserInfo(dateutil.parser.parserinfo):
    MONTHS = ['január',
              'február',
              'március',
              'április',
              'május',
              'június',
              'július',
              'augusztus',
              'szeptember',
              'október',
              'november',
              'december']

class TelexHTMLParser(html.parser.HTMLParser):
    def __init__(self):
        html.parser.HTMLParser.__init__(self)
        self._a_pattern = re.compile(r'(?:(?:https?://)(?:www\.)?telex\.hu)?/+(\w+/+\d+/+\d+/+\d+(?:/+[\w-]+)+)/*', re.IGNORECASE)
        self._in_article_date = False
        self._in_article_title = False
        self.article_date = None
        self.article_title = None
        self.links = []

    def error(self, message):
        raise Exception(message)

    def handle_starttag(self, tag: str, attrs: list):
        lowtag = tag.lower()

        if lowtag == 'div':
            for attr in attrs:
                if len(attr) < 2:
                    continue
                if attr[0].lower() != 'class':
                    continue
                if attr[1] is None:
                    log.warning(f'<{tag} {attrs}>')
                    continue
                if attr[1] == 'article_date':
                    self._in_article_date = True
                elif attr[1] == 'article_title':
                    self._in_article_title = True
            return

        if lowtag == 'a':
            for attr in attrs:
                if len(attr) < 2:
                    continue
                if attr[0].lower() != 'href':
                    continue
                if attr[1] is None:
                    log.warning(f'<{tag} {attrs}>')
                    continue
                match = self._a_pattern.fullmatch(attr[1].strip().lower())
                if match:
                    self.links.append(match.group(1))
                return

    def handle_endtag(self, tag):
        self._in_article_date = False
        self._in_article_title = False

    def handle_data(self, data: str):
        if self._in_article_date:
            self._in_article_date = False
            assert self.article_date is None
            try:
                self.article_date = dateutil.parser.parser(HungarianParserInfo()).parse(data.strip(), fuzzy = True)
            except:
                log.exception(f'Exception: self.article_date = dateutil.parser.parser(HungarianParserInfo()).parse("{data.strip()}", fuzzy = True)')
            return

        if self._in_article_title:
            self._in_article_title = False
            assert self.article_title is None
            self.article_title = data.strip()
            return

def check_config() -> bool:
    global config
    global config_path
    global config_timestamp
    try:
        if not config_path.is_file():
            return False
        mtime_ns = config_path.stat().st_mtime_ns
        if config and config_timestamp:
            if mtime_ns == config_timestamp:
                return True
        config_timestamp = mtime_ns
        config = configparser.ConfigParser(interpolation = None)
        config.read(config_path, encoding = 'utf-8')
        return True
    except:
        log.exception('Exception in check_config()')
        return False

def get_config() -> dict:
    global config
    check_config()
    # noinspection PyTypeChecker
    return config

# noinspection PyUnresolvedReferences
def ensure_category(category: str, category_name: str):
    global config_path
    # noinspection PyShadowingNames
    config = get_config()
    if category not in config['categories']:
        log.warning(f'New category: {category} ({category_name})')
        try:
            config.set('categories', category, category_name)
            with config_path.open('w', encoding = 'utf-8') as ini:
                config.write(ini, space_around_delimiters = False)
        except:
            log.exception(f'Unable to add new category {category} ({category_name}): {config_path}')
    if category_name != config['categories'].get(category, ''):
        log.warning(f'Unexpected category name: {category} (category_name)')

def connect_reddit(name: str, useragent: str) -> praw.Reddit:
    reddit = praw.Reddit(name, user_agent = useragent)
    redditor = reddit.user.me()
    assert redditor is not None
    username = redditor.name
    assert username == name
    return reddit

def download_content(url: str, useragent: str, telex_urls_skip: set = None) -> str:
    request = urllib.request.Request(url)
    request.add_header('User-Agent', useragent)
    try:
        response = urllib.request.urlopen(request, context = ssl.SSLContext())
        data = response.read()
        response_url = response.url
        if response_url != url:
            log.warning(f'URL changed from {url} to {response_url}')
            if telex_urls_skip:
                telex_urls_skip.add(url)
        if b'\x00' in data:
            raise Exception('Content is not text: ' + url)
        charset = response.headers.get_content_charset()
        return data.decode(encoding = charset, errors = 'replace')
    except urllib.error.HTTPError:
        log.error(f'Unable to download URL: {url}')
        time.sleep(get_config()['telex'].getint('check_interval'))
        raise

def datetime2iso8601(value: datetime) -> str:
    return value.isoformat(timespec = 'minutes' if value.second == 0 else 'seconds')

def read_article(url_path: str, telex_json: dict, telex_urls: set, telex_urls_skip: set):
    url = 'https://telex.hu/' + url_path
    log.info(f'read_article: {url}')
    telex_config = get_config()['telex']
    content = ''
    use_article_cache = telex_config.getboolean('use_article_cache')
    if use_article_cache:
        telex_path = Path('log').joinpath('telex.hu')
        telex_path.joinpath(url_path).with_suffix('.html').unlink(missing_ok = True)
        article_path = telex_path.joinpath(url_path).with_suffix('.gz')
        if article_path.exists():
            article_cache_valid_time = telex_config.getfloat('article_cache_valid_time')
            if datetime.utcnow().timestamp() < article_path.stat().st_mtime + article_cache_valid_time:
                with gzip.open(article_path, 'rt', encoding = 'utf-8') as f:
                    content = f.read()
    if content == '':
        content = download_content(url, telex_config['useragent'], telex_urls_skip)
    if use_article_cache:
        # noinspection PyUnboundLocalVariable
        article_path.parent.mkdir(exist_ok = True, parents = True)
        with gzip.open(article_path, 'wt', compresslevel = 9, encoding = 'utf-8') as f:
            f.write(content)
    html_parser = TelexHTMLParser()
    html_parser.feed(content)
    article_date = html_parser.article_date
    assert article_date is not None
    article_title = html_parser.article_title
    assert article_title is not None
    if url_path not in telex_json:
        telex_json[url_path] = {}
    telex_json[url_path]['article_date'] = datetime2iso8601(article_date)
    telex_json[url_path]['article_title'] = html_parser.article_title
    telex_json[url_path]['category'] = None if url_path.find('/') <= 0 else url_path[0:url_path.index('/')]
    telex_json[url_path]['parse_date'] = datetime2iso8601(datetime.utcnow()) + 'Z'
    links = html_parser.links
    for link in links:
        url = link.strip()
        telex_urls.add(url)
        if url not in telex_json:
            telex_json[url] = {}

def collect_links(content: str, telex_json: dict, telex_urls: set, in_english: bool = False):
    html_parser = TelexHTMLParser()
    html_parser.feed(content)
    links = html_parser.links
    counter = 0
    for link in links:
        url = link.strip()
        telex_urls.add(url)
        if url not in telex_json:
            counter += 1
            log.debug(f'{counter}. new article: {url}')
            if in_english:
                telex_json[url] = {'english': True}
            else:
                telex_json[url] = {}

def submit_link(title: str, url: str, flair_id: str):
    reddit_config = get_config()['reddit']
    username = reddit_config['username']
    reddit = connect_reddit(username, f'{username} script by {reddit_config["script_author"]}')
    subreddit = reddit.subreddit(reddit_config['subreddit'])
    subreddit.submit(title, None, url, flair_id)

def main():
    remaining_articles = 0
    articles_json_path = Path('articles.json.gz')
    telex_urls_path = Path('telex.urls.txt')
    telex_urls_skip_path = Path('telex.urls.skip.txt')
    telex_json_path = Path('telex.json.gz')
    while True:
        articles_json = {}
        telex_json = {}
        telex_urls = set()
        telex_urls_skip = set()
        try:
            if telex_urls_path.exists():
                with telex_urls_path.open('rt', encoding = 'utf-8') as f:
                    for line in f:
                        telex_urls.add(line.strip())

            if telex_urls_skip_path.exists():
                with telex_urls_skip_path.open('rt', encoding = 'utf-8') as f:
                    for line in f:
                        telex_urls_skip.add(line.strip())

            if articles_json_path.exists():
                with gzip.open(articles_json_path, 'rt', encoding = 'utf-8') as f:
                    articles_json_text = f.read()
                json_data = json.loads(articles_json_text)
                if not isinstance(json_data, list):
                    raise Exception('not isinstance(json_data, list)')
                for article in json_data:
                    article_id = str(article.pop('id', ''))
                    if article_id == '':
                        raise Exception(f'Invalid article_id: {article}')
                    if not article_id.isnumeric():
                        raise Exception(f'Unexpected article_id: {article_id}')
                    if article_id in articles_json:
                        raise Exception(f'Duplicate article_id: {article_id}')
                    if ('contentType' not in article) or (article['contentType'] != 'article'):
                        raise Exception(f'Invalid contentType: {article}')
                    if ('mainSuperTag' not in article) or (not isinstance(article['mainSuperTag'], dict)):
                        raise Exception(f'Invalid mainSuperTag: {article}')
                    mainSuperTag = article['mainSuperTag']
                    if 'slug' not in mainSuperTag:
                        raise Exception(f'No slug in mainSuperTag: {article}')
                    category = mainSuperTag['slug']
                    category_name = mainSuperTag.get('name', '')
                    ensure_category(category, category_name)
                    articles_json[int(article_id)] = article

            if telex_json_path.exists():
                with gzip.open(telex_json_path, 'rt', encoding = 'utf-8') as f:
                    telex_json_text = f.read()
                telex_json = json.loads(telex_json_text)

            try:
                for file in Path('sample').glob('*.html'):
                    log.info(f'read_sample: {file}')
                    content = file.read_text(encoding = 'utf-8')
                    collect_links(content, telex_json, telex_urls)

                # noinspection PyShadowingNames
                config = get_config()
                useragent = config['telex']['useragent']

                #download_content(config['telex']['api_url'], useragent)

                for k, v in config['collect_links'].items():
                    if v != '':
                        time.sleep(5)
                        log.info(f'read_{k}: {v}')
                        content = download_content(v, useragent)
                        collect_links(content, telex_json, telex_urls, k == 'english')

                new_urls = set()
                for url in telex_urls:
                    if url not in telex_json:
                        new_urls.add(url)
                for k, v in telex_json.items():
                    if 'parse_date' in v:
                        continue
                    new_urls.add(k)
                for url in new_urls:
                    if '.' in url:
                        log.warning(f'URL contains dot: {url}')
                        continue
                    if url.find('/') <= 0:
                        log.warning(f'Unexpected URL: {url}')
                    else:
                        category = url[0:url.index('/')]
                        if category not in config['categories']:
                            log.warning(f'Unexpected category: {url}')
                    if 'https://telex.hu/' + url in telex_urls_skip:
                        continue
                    time.sleep(1)
                    read_article(url, telex_json, telex_urls, telex_urls_skip)
                oldest_url = None
                remaining_articles = 0
                for k, v in telex_json.items():
                    if 'https://telex.hu/' + k in telex_urls_skip:
                        continue
                    if 'reddit_date' in v:
                        continue
                    if 'article_date' not in v:
                        continue
                    remaining_articles += 1
                    if (oldest_url is None) or (telex_json[k]['article_date'] < telex_json[oldest_url]['article_date']):
                        oldest_url = k
                if oldest_url:
                    full_url = 'https://telex.hu/' + oldest_url.strip('/')
                    log.info(f'submit: {full_url}')
                    article_title = telex_json[oldest_url].get('article_title', '').strip()
                    assert article_title != '', f'No article_title: {oldest_url}'
                    reddit = connect_reddit(config['reddit']['username'], config['reddit']['script_author'])
                    reddit.validate_on_submit = True
                    subreddit = reddit.subreddit(config['reddit']['subreddit'])
                    utc_time_str = datetime2iso8601(datetime.utcnow()) + 'Z'
                    submission = None
                    try:
                        submission = subreddit.submit(
                            title = article_title,
                            selftext = None,
                            url = full_url,
                            flair_id = None,
                            flair_text = None,
                            resubmit = False,
                            send_replies = False)
                    except praw.exceptions.RedditAPIException as e:
                        for eitem in e.items:
                            if eitem.error_type != 'ALREADY_SUB':
                                raise
                            if eitem.field != 'url':
                                raise
                            if eitem.message != 'that link has already been submitted':
                                raise
                            log.warning(eitem.error_message)
                    telex_json[oldest_url]['reddit_date'] = utc_time_str
                    telex_json[oldest_url]['reddit_url'] = '' if submission is None else submission.permalink
                    remaining_articles -= 1
                    if submission:
                        if ('english' in telex_json[oldest_url]) and (telex_json[oldest_url]['english']):
                            collection = subreddit.collections(config['reddit']['english_collection_id'])
                            collection.mod.add_post(submission.id)
            finally:
                if '' in telex_urls:
                    telex_urls.remove('')
                telex_urls = list(telex_urls)
                telex_urls.sort()
                telex_urls_path.write_text('\n'.join(telex_urls), encoding = 'utf-8')

                if '' in telex_urls_skip:
                    telex_urls_skip.remove('')
                telex_urls_skip = list(telex_urls_skip)
                telex_urls_skip.sort()
                telex_urls_skip_path.write_text('\n'.join(telex_urls_skip), encoding = 'utf-8')

                json_data = []
                for article_id in sorted(articles_json):
                    article = articles_json[article_id]
                    article['id'] = int(article_id)
                    json_data.append(article)
                articles_json_text = json.dumps(json_data, ensure_ascii = False, indent = '\t', sort_keys = True)
                if articles_json_path.exists():
                    articles_json_path.replace(articles_json_path.with_suffix('.bak.gz'))
                with gzip.open(articles_json_path, 'wt', compresslevel = 9, encoding = 'utf-8') as f:
                    f.write(articles_json_text)

                telex_json_text = json.dumps(telex_json, ensure_ascii = False, indent = '\t', sort_keys = True)
                if telex_json_path.exists():
                    telex_json_path.replace(telex_json_path.with_suffix('.bak.gz'))
                with gzip.open(telex_json_path, 'wt', compresslevel = 9, encoding = 'utf-8') as f:
                    f.write(telex_json_text)
        except:
            log.exception('Exception!')

        check_interval = get_config()['telex'].getint('check_interval')
        log.debug(f'time.sleep({check_interval}) [remaining articles: {remaining_articles} of {len(telex_urls)} (skipping {len(telex_urls_skip)})]')
        time.sleep(check_interval)

if __name__ == '__main__':
    config = None
    config_path = Path(__file__).with_suffix('.ini')
    config_timestamp = None
    if not check_config():
        raise Exception(f'Unable to read config: {config_path}')
    logging_config = json.loads(Path(__file__).with_suffix('.logging.json').read_text())
    for handler in logging_config['handlers'].values():
        if 'filename' in handler:
            Path(handler['filename']).parent.mkdir(exist_ok = True, parents = True)
    logging.config.dictConfig(logging_config)
    log = logging.getLogger(__name__)
    log.info(f'Started at: {datetime.now().replace(microsecond = 0)}')
    main()
    log.info(f'Finished at: {datetime.now().replace(microsecond = 0)}')
