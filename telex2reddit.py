import configparser
from datetime import datetime
import gzip
import json
from jsonfile import JsonGzip
from listasdictjsonfile import ListAsDictJsonGzip
import logging.config
from pathlib import Path
import praw
import praw.exceptions
import re
from setfile import SetFile
import ssl
from telexhtmlparser import TelexHTMLParser
import time
import urllib.error
import urllib.request

log = logging.Logger
logging.setLoggerClass(log)

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

def get_config() -> configparser.ConfigParser:
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
            log.exception(f'Unable to add new category: {category} ({category_name}): {config_path}')
    if category_name != config['categories'].get(category, ''):
        log.warning(f'Unexpected category name: {category} ({category_name})')

def download_content(url: str, useragent: str, telex_urls_skip: set = None) -> str:
    request = urllib.request.Request(url)
    request.add_header('User-Agent', useragent)
    response = urllib.request.urlopen(request, context = ssl.SSLContext())
    data = response.read()
    response_url = response.url
    if response_url != url:
        log.warning(f'URL changed from {url} to {response_url}')
        if telex_urls_skip:
            telex_urls_skip.add(url)
    if b'\x00' in data:
        raise Exception(f'Content is not text: {response_url}')
    charset = response.headers.get_content_charset()
    return data.decode(encoding = charset, errors = 'replace')

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
    html_parser = TelexHTMLParser(log)
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
    html_parser = TelexHTMLParser(log)
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

def connect_reddit(name: str, useragent: str) -> praw.Reddit:
    reddit = praw.Reddit(name, user_agent = useragent)
    redditor = reddit.user.me()
    assert redditor is not None
    username = redditor.name
    assert username == name
    return reddit

# noinspection PyUnresolvedReferences
def get_subreddit() -> praw.models.Subreddit:
    # noinspection PyShadowingNames
    config = get_config()
    reddit = connect_reddit(config['reddit']['username'], 'Script by u/' + config['reddit']['script_author'])
    reddit.validate_on_submit = True
    return reddit.subreddit(config['reddit']['subreddit'])

def check_categories():
    # noinspection PyShadowingNames
    config = get_config()
    categories = config['categories']
    flair_classes = {}
    subreddit = get_subreddit()
    for flair in subreddit.flair.link_templates:
        if flair['type'] != 'text':
            continue
        if not flair['mod_only']:
            continue
        flair_class = flair['css_class']
        flair_text = flair['text']
        if flair_class in flair_classes:
            raise Exception(f'Duplicate flair: {flair_class}')
        if flair_class not in categories:
            raise Exception(f'Flair missing from config: {flair_class}')
        if flair_text != categories[flair_class].upper():
            raise Exception(f'Unexpected flair text ({flair_class}): {flair_text} != {categories[flair_class]}')
        flair_classes[flair_class] = flair['id']
    for flair_class in categories:
        if flair_class not in flair_classes:
            raise Exception(f'Unexpected flair in config: {flair_class}')
    automoderator = subreddit.wiki['config/automoderator']
    for revision in automoderator.revisions():
        revision_author = revision['author']
        if revision_author != config['reddit']['script_author']:
            raise Exception(f'Unexpected automoderator author: {revision_author}')
    pattern = re.compile(r'---\s+url: \["telex.hu/(\w+)/"]\s+action:\s*approve\s+set_flair:\s+template_id:\s*([\da-f-]+)\s*')
    last_pos = 0
    automod_flairs = {}
    automoderator_content_md = automoderator.content_md
    for match in pattern.finditer(automoderator_content_md):
        if last_pos != match.start():
            raise Exception(f'Unexpected position of match: {match}')
        last_pos = match.end()
        flair_class = match.group(1)
        if flair_class in automod_flairs:
            raise Exception(f'Automoderator duplicate flair: {flair_class}')
        if flair_class not in flair_classes:
            raise Exception(f'Automoderator flair missing from config: {flair_class}')
        template_id = match.group(2)
        for k, v in automod_flairs.items():
            if v == template_id:
                raise Exception(f'Automoderator flair ({k}) template_id redundant: {template_id}')
        automod_flairs[flair_class] = template_id
        if flair_classes[flair_class] != template_id:
            raise Exception(f'Automoderator flair ({flair_class}) template_id mismatch: {template_id}')
    if last_pos != len(automoderator_content_md):
        raise Exception(f'Unexpected content at the end of automoderator')
    for flair_class in automod_flairs:
        if flair_class not in flair_classes:
            raise Exception(f'Automoderator flair unexpected: {flair_class}')
    automod_path = Path('automod.txt')
    if automod_path.read_text(encoding = 'utf-8') != automoderator_content_md:
        automod_path.write_text(automoderator_content_md, encoding = 'utf-8')

def main():
    check_categories()

    remaining_articles = 0
    articles_json = ListAsDictJsonGzip('articles.json.gz', log = log)
    telex_urls = SetFile('telex.urls.txt', log = log)
    telex_urls_skip = SetFile('telex.urls.skip.txt', log = log)
    telex_json = JsonGzip('telex.json.gz', log = log)
    while True:
        try:
            telex_urls.read()
            telex_urls_skip.read()

            articles_json.read()
            for k, v in articles_json.items():
                if ('contentType' not in v) or (v['contentType'] != 'article'):
                    raise Exception(f'Invalid contentType: {v}')
                if ('mainSuperTag' not in v) or (not isinstance(v['mainSuperTag'], dict)):
                    raise Exception(f'Invalid mainSuperTag: {v}')
                mainSuperTag = v['mainSuperTag']
                if 'slug' not in mainSuperTag:
                    raise Exception(f'No slug in mainSuperTag: {v}')
                category = mainSuperTag['slug']
                category_name = mainSuperTag.get('name', '')
                ensure_category(category, category_name)
                articles_json[int(k)] = v

            telex_json.read()

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
                    subreddit = get_subreddit()
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
                            reddit_url = 'https://reddit.com' + submission.permalink
                            log.info(f'Add new english post to collection: {reddit_url}')
                            collection.mod.add_post(reddit_url)
            finally:
                if '' in telex_urls:
                    telex_urls.remove('')
                telex_urls.write(create_backup = True, check_for_changes = True)

                if '' in telex_urls_skip:
                    telex_urls_skip.remove('')
                telex_urls_skip.write(create_backup = True, check_for_changes = True)

                articles_json.write(create_backup = True, check_for_changes = True)
                telex_json.write(create_backup = True, check_for_changes = True)
        except urllib.error.HTTPError as e:
            if (
                    (e.code == 500) and (e.reason == 'RuntimeError')) or (
                    (e.code == 503) and (e.reason == 'Service Unavailable')) or (
                    (e.code == 408) and (e.reason == 'Request Time-out')) or (
                    (e.code == 10060) and (e.reason == 'WinError')
            ):
                log.error(f'Unable to download URL ({e}): {e.url}')
                time.sleep(10 * 60)
            else:
                log.exception('Exception!')
        except:
            log.exception('Exception!')

        check_interval = get_config()['telex'].getint('check_interval')
        if remaining_articles > 0:
            check_interval /= 2
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
