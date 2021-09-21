import configparser
from datetime import datetime
import json
from .jsonfile import JsonGzip
from .listasdictjsonfile import ListAsDictJsonGzip, ListAsDictJsonText
from . import log_config
import logging.config
import os
from pathlib import Path
import praw
import praw.exceptions
import prawcore.exceptions
import re
import ssl
import time
import urllib.error
import urllib.request

log = None
config = None
config_path = Path(__file__).parent.parent / '.config' / 'telex2reddit.ini'
config_timestamp = None


def get_config() -> configparser.ConfigParser:
    global config
    global config_timestamp
    global config_path

    if not config_path.is_file():
        raise Exception(f'Config {config_path} is not a readable file')

    mtime_ns = config_path.stat().st_mtime_ns
    if config and config_timestamp:
        if mtime_ns == config_timestamp:
            return config

    config_timestamp = mtime_ns
    config = configparser.ConfigParser(interpolation=None)
    config.read(config_path, encoding='utf-8')
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
            with config_path.open('w', encoding='utf-8') as ini:
                config.write(ini, space_around_delimiters=False)
        except:
            log.exception(f'Unable to add new category: {category} ({category_name}): {config_path}')
    if category_name != config['categories'].get(category, ''):
        log.warning(f'Unexpected category name: {category} ({category_name})')


def download_content(url: str, useragent: str, default_encoding: str = 'utf-8') -> str:
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
    if charset is None:
        charset = default_encoding
    return data.decode(encoding=charset, errors='replace')


def datetime2iso8601(value: datetime) -> str:
    return value.isoformat(timespec='minutes' if value.second == 0 else 'seconds')


def connect_reddit(name: str, useragent: str) -> praw.Reddit:
    reddit = praw.Reddit(name, user_agent=useragent)
    redditor = reddit.user.me()
    assert redditor is not None
    username = redditor.name
    assert username == name
    return reddit


def get_reddit() -> praw.Reddit:
    # noinspection PyShadowingNames
    config = get_config()
    reddit = connect_reddit(config['reddit']['username'], 'Script by u/' + config['reddit']['script_author'])
    reddit.validate_on_submit = True
    return reddit


def same_objects(a, b):
    return str(a) == str(b)


def update_list(path: str, src: list, dest: list):
    if len(src) == 0 and len(dest) == 0:
        return
    only_append = True
    for i in range(len(src)):
        if i < len(dest):
            if not same_objects(src[i], dest[i]):
                only_append = False
                break
        else:
            log.info(f'{path} appended {i}.: {src[i]}')
            dest.append(src[i])
    if only_append:
        i = len(dest) - 1
        while i >= len(src):
            log.info(f'{path} deleted {i}.: {dest[i]}')
            dest.pop(i)
            i -= 1
        return
    src_list = sorted([str(item) for item in src])
    dest_list = sorted([str(item) for item in dest])
    if src_list == dest_list:
        return
    for item in src:
        if not isinstance(item, dict):
            raise Exception(f'{path} unexpected list item: {item}')
    for item in dest:
        if not isinstance(item, dict):
            raise Exception(f'{path} unexpected list item: {item}')
    if 'id' in src[0]:
        key_name = 'id'
    elif 'slug' in src[0]:
        key_name = 'slug'
    else:
        raise Exception(f'{path} unable to get id: {src[0]}')

    src_dict = {item[key_name]: item for item in src}
    dest_dict = {item[key_name]: item for item in dest}
    for k, v in src_dict.items():
        if k in dest_dict:
            for i in range(len(dest)):
                if dest[i][key_name] == k:
                    update_item(f'{path}/{i}', v, dest[i])
                    break
        else:
            log.info(f'{path} appended: {v}')
            dest.append(v)
    for k, v in dest_dict.items():
        if k not in src_dict:
            for i in range(len(dest)):
                if dest[i][key_name] == k:
                    log.info(f'{path} deleted {i}.: {dest[i]}')
                    dest.pop(i)
                    break


def update_item(path: str, src: dict, dest: dict):
    for k, v in src.items():
        if k in dest:
            if str(dest[k]) != str(v):
                if isinstance(dest[k], dict) and isinstance(v, dict):
                    update_item(f'{path}/{k}', v, dest[k])
                    continue
                if isinstance(dest[k], list) and isinstance(v, list):
                    update_list(f'{path}/{k}', v, dest[k])
                    continue
                log.info(f'{path} changed {k}: from {dest[k]} to {v}')
                dest[k] = v
        else:
            log.info(f'{path} added {k}: {v}')
            dest[k] = v
    delete_ids = set()
    for k in dest:
        if k == 'id':
            continue
        if k not in src:
            delete_ids.add(k)
    for k in delete_ids:
        log.info(f'{path} deleted {k}: {dest[k]}')
        dest.pop(k)


def check_categories():
    # noinspection PyShadowingNames
    config = get_config()
    categories = config['categories']
    flair_classes = {}
    subreddit = get_reddit().subreddit(config['reddit']['subreddit'])
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
    pattern = r'---\s+url: \["telex.hu/([\w-]+)/"]\s+action:\s*approve\s+set_flair:\s+template_id:\s*([\da-f-]+)\s*'
    last_pos = 0
    automod_flairs = {}
    automoderator_content_md = automoderator.content_md.strip()
    for match in re.compile(pattern).finditer(automoderator_content_md):
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


def main():
    log.info(f'Started at: {datetime.now().replace(microsecond=0)}')

    check_categories()

    remaining_articles = 0
    articles_json = ListAsDictJsonGzip(Path(__file__).parent.parent / '.data' / 'articles.json.gz', log=log)
    telex2_json = JsonGzip(Path(__file__).parent.parent / '.data' / 'telex2.json.gz', log=log)
    while True:
        try:
            articles_json.read()
            for k, v in articles_json.items():
                if ('contentType' in v) and (v['contentType'] != 'article'):
                    raise Exception(f'Unexpected contentType: {v}')
                if ('mainSuperTag' not in v) or (not isinstance(v['mainSuperTag'], dict)):
                    raise Exception(f'Invalid mainSuperTag: {v}')
                main_super_tag = v['mainSuperTag']
                if 'slug' not in main_super_tag:
                    raise Exception(f'No slug in mainSuperTag: {v}')
                if 'facebookEngagement' in v:
                    v.pop('facebookEngagement')
                category = main_super_tag['slug']
                category_name = main_super_tag.get('name', '')
                ensure_category(category, category_name)
                articles_json[int(k)] = v

            telex2_json.read()

            try:
                # noinspection PyShadowingNames
                config = get_config()
                telex_config = config['telex']
                useragent = telex_config['useragent']

                articles_per_page = telex_config.getint('articles_per_page', fallback=25)
                articles = ListAsDictJsonText()
                page = 1
                while True:
                    telex_api_url = telex_config['api_url'] + f'?perPage={articles_per_page}&page={page}'
                    log.debug(f'API: {telex_api_url}')
                    content = download_content(telex_api_url, useragent)
                    Path(Path(__file__).parent.parent / '.data' / 'articles.api.json').write_text(content, encoding='utf-8')
                    json_data = json.loads(content)
                    if isinstance(json_data, list):
                        articles.read_list(json_data)
                    else:
                        if isinstance(json_data, dict) and ('items' in json_data):
                            articles.read_list(json_data['items'])
                        else:
                            raise Exception(f'Unexpected JSON structure')
                    new_article = False
                    for k, v in articles.items():
                        if 'facebookEngagement' in v:
                            v.pop('facebookEngagement')
                        if k in articles_json:
                            update_item(str(k), v, articles_json[k])
                        else:
                            articles_json[k] = v
                            new_article = True
                    if not new_article:
                        break
                    if len(articles) < articles_per_page:
                        break
                    page += 1

                expected_types = telex_config.get('expected_types', '').split(',')
                ignore_types = telex_config.get('ignore_types', '').split(',')
                for k, v in articles_json.items():
                    item_type = v['type']
                    if item_type in ignore_types:
                        continue
                    if item_type not in expected_types:
                        log.warning(f'Unexpected type ({item_type}): {k}')
                    if not v['active']:
                        log.warning(f'not active: {k}')
                        continue
                    article_date = datetime.utcfromtimestamp(v['pubDate'])
                    url_path = v['slug']
                    if not re.fullmatch(r'[\w-]+', url_path):
                        log.error(url_path)
                    if url_path not in telex2_json:
                        log.info(f'New article: {url_path}')
                        telex2_json[url_path] = {}
                    telex2_json[url_path]['article_date'] = datetime2iso8601(article_date) + 'Z'
                    telex2_json[url_path]['article_title'] = v['title']
                    telex2_json[url_path]['category'] = v['mainSuperTag']['slug']
                    telex2_json[url_path]['date_dir'] = article_date.strftime('%Y/%m/%d')
                    if v['english']:
                        telex2_json[url_path]['english'] = True

                submissions_already_posted = 0
                while submissions_already_posted < 25:
                    oldest_url = None
                    remaining_articles = 0
                    for k, v in telex2_json.items():
                        if 'parse_date' in v:
                            v.pop('parse_date')
                        if v.get('reddit_date', None) not in [None, '']:
                            continue
                        article_date = v.get('article_date', None)
                        if article_date in [None, '']:
                            log.warning('No article_date: ' + str(v))
                            continue
                        remaining_articles += 1
                        if (oldest_url is None) or (article_date < telex2_json[oldest_url]['article_date']):
                            oldest_url = k
                    if oldest_url is None:
                        break
                    oldest = telex2_json[oldest_url]
                    article_title = oldest.get('article_title', '').strip()
                    if article_title == '':
                        raise Exception(f'No article_title: {oldest_url}')
                    full_url = 'https://telex.hu/' + oldest['category'] + '/' + oldest['date_dir'] + '/' + oldest_url
                    log.info(f'Submit: {full_url}')
                    reddit = get_reddit()
                    subreddit = reddit.subreddit(config['reddit']['subreddit'])
                    utc_time_str = ''
                    submission = None
                    submission_already_posted = False
                    for old_submission in subreddit.search('url:' + full_url, sort='new', limit=1):
                        submission_already_posted = True
                        submission = old_submission
                        log.info(f'Submission already posted: {submission.permalink}')
                    if submission is None:
                        try:
                            submission = subreddit.submit(
                                title=article_title,
                                selftext=None,
                                url=full_url,
                                flair_id=None,
                                flair_text=None,
                                resubmit=False,
                                send_replies=False)
                        except praw.exceptions.RedditAPIException as e:
                            for eitem in e.items:
                                if eitem.error_type != 'ALREADY_SUB':
                                    raise
                                if eitem.field != 'url':
                                    raise
                                log.warning(eitem.error_message)
                                submission_already_posted = True
                                utc_time_str = datetime2iso8601(datetime.now())
                    if submission_already_posted:
                        submissions_already_posted += 1
                    if submission:
                        utc_time_str = datetime2iso8601(datetime.fromtimestamp(submission.created_utc)) + 'Z'
                    telex2_json[oldest_url]['reddit_date'] = utc_time_str
                    telex2_json[oldest_url]['reddit_url'] = '' if submission is None else submission.permalink
                    remaining_articles -= 1
                    if submission:
                        if ('english' in telex2_json[oldest_url]) and (telex2_json[oldest_url]['english']):
                            collection = subreddit.collections(config['reddit']['english_collection_id'])
                            reddit_url = 'https://reddit.com' + submission.permalink
                            log.info(f'Add new english post to collection: {reddit_url}')
                            try:
                                collection.mod.add_post(reddit_url)
                            except praw.exceptions.RedditAPIException as e:
                                for eitem in e.items:
                                    log.error(eitem.error_message)
                            if 'telex' in article_title.lower():
                                log.warning(f'Telex in title (internal post?): {article_title}')
                            subreddit_english = config['reddit']['subreddit_english']
                            log.info(f'Submit to {subreddit_english}: {full_url}')
                            subreddit_english = reddit.subreddit(subreddit_english)
                            submission = None
                            for old_submission in subreddit_english.search('url:' + full_url, sort='new', limit=1):
                                submission = old_submission
                                log.info(f'Submission already posted: {submission.permalink}')
                            if submission is None:
                                try:
                                    submission = subreddit_english.submit(
                                        title=article_title,
                                        selftext=None,
                                        url=full_url,
                                        flair_id=None,
                                        flair_text=None,
                                        resubmit=False,
                                        send_replies=False)
                                except praw.exceptions.RedditAPIException as e:
                                    for eitem in e.items:
                                        if eitem.error_type != 'ALREADY_SUB':
                                            raise
                                        if eitem.field != 'url':
                                            raise
                                        log.warning(eitem.error_message)
                            if submission:
                                telex2_json[oldest_url]['reddit_english_url'] = submission.permalink
                    if not submission_already_posted:
                        break
            finally:
                articles_json.write(create_backup=True, check_for_changes=True)
                telex2_json.write(create_backup=True, check_for_changes=True)
        except urllib.error.HTTPError as e:
            log.error(f'Unable to download URL ({e}): {e.url}')
            time.sleep(10 * 60)
        except prawcore.exceptions.ServerError as e:
            log.error(f'Reddit error: {e}')
        except:
            log.exception('Exception!')

        check_interval = get_config()['telex'].getint('check_interval')
        if remaining_articles > 0:
            check_interval /= 5
        log.debug(f'time.sleep({check_interval}) [remaining articles: {remaining_articles}]')
        time.sleep(check_interval)


def init():
    global log
    log = init_logging()
    get_config()
    log_path = Path('log')
    log_config_path = log_path.joinpath('config')
    log_config.load_log_config(log_config_path, log_config_path.joinpath('handler'))


def init_logging():
    log_config_path = Path(__file__).parent.parent / '.config' / 'telex2reddit.logging.json'
    if os.path.exists(log_config_path):
        with open(log_config_path, 'rt') as f:
            config_dict = json.load(f)
        logging.config.dictConfig(config_dict)
    else:
        logging.basicConfig(level=0)

    return logging.getLogger()
