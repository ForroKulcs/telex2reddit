import dateutil.parser
import html.parser
import logging.config
import re

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
    def __init__(self, log: logging.Logger = None):
        html.parser.HTMLParser.__init__(self)
        self._link_pattern = re.compile(r'(?:(?:https?://)(?:www\.)?telex\.hu)?/+(\w+/+\d+/+\d+/+\d+(?:/+[\w-]+)+)/*', re.IGNORECASE)
        self._in_article_date = False
        self._in_article_title = False
        self._log = log
        self.article_date = None
        self.article_title = None
        self.links: list[str] = []

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
                    if self._log:
                        self._log.warning(f'<{tag} {attrs}>')
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
                    if self._log:
                        self._log.warning(f'<{tag} {attrs}>')
                    continue
                match = self._link_pattern.fullmatch(attr[1].strip().lower())
                if match:
                    self.links.append(match.group(1))
                return

    def handle_endtag(self, tag: str):
        self._in_article_date = False
        self._in_article_title = False

    def handle_data(self, data: str):
        if self._in_article_date:
            self._in_article_date = False
            assert self.article_date is None
            date_text = data.strip()
            if '(' in date_text:
                date_text = date_text[0:date_text.index('(')].rstrip()
            if date_text == '':
                return
            try:
                self.article_date = dateutil.parser.parser(HungarianParserInfo()).parse(date_text, fuzzy = True)
            except:
                if self._log:
                    self._log.exception(f'Exception: self.article_date = dateutil.parser.parser(HungarianParserInfo()).parse("{data.strip()}", fuzzy = True)')
                else:
                    raise
            return

        if self._in_article_title:
            self._in_article_title = False
            assert self.article_title is None
            self.article_title = data.strip()
            return
