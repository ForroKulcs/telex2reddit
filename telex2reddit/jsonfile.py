import gzip
import json
import logging.config
from pathlib import Path


class JsonText(dict):
    def __str__(self):
        return json.dumps(self, ensure_ascii=False, indent='\t', sort_keys=True)

    def read_text(self, text: str):
        data = json.loads(text)
        self.clear()
        self.update(data)


class JsonFile(JsonText):
    def __init__(self, filename: [Path, str], encoding: str = 'utf-8', log: logging.Logger = None):
        super().__init__()
        if isinstance(filename, Path):
            self._path = filename
        else:
            self._path = Path(filename)
        self._encoding = encoding
        self._log = log

    @property
    def encoding(self) -> str:
        return self._encoding

    @property
    def log(self) -> logging.Logger:
        return self._log

    @property
    def path(self) -> Path:
        return self._path

    def _read(self):
        with open(self.path, 'rt', encoding=self.encoding) as f:
            return f.read()

    def read(self):
        self.read_text(self._read())

    def try_read(self) -> bool:
        try:
            if self.path.is_file():
                self.read()
                return True
            else:
                if self.log:
                    self.log.warning(f'{self.path} not available')
        except:
            if self.log:
                self.log.exception(f'Unable to read: {self.path}')
        return False

    def _write(self, text: str):
        with open(self.path, 'wt', encoding=self.encoding, newline='\n') as f:
            f.write(text)

    def try_write(self, create_backup: bool = False, check_for_changes: bool = False) -> bool:
        try:
            self.write(create_backup, check_for_changes)
            return True
        except:
            if self.log:
                self.log.exception(f'Unable to write: {self.path}')
        return False

    def write(self, create_backup: bool = False, check_for_changes: bool = False):
        text = str(self)
        if (create_backup or check_for_changes) and self.path.is_file():
            if check_for_changes:
                try:
                    old = self._read()
                    if old == text:
                        if self.log:
                            self.log.debug(f'No change: {self.path}')
                        return
                except:
                    if self.log:
                        self.log.exception(f'Unable to check for changes: {self.path}')
            if create_backup:
                ext = self._path.suffix
                backup_path = self.path.with_suffix('.bak' + ext)
                try:
                    self.path.replace(backup_path)
                except:
                    if self.log:
                        self.log.exception(f'Unable to replace backup: {backup_path}')
        self._write(text)


class JsonGzip(JsonFile):
    def _read(self):
        with gzip.open(self.path, 'rt', encoding=self.encoding) as f:
            return f.read()

    def _write(self, text: str):
        with gzip.open(self.path, 'wt', compresslevel=9, encoding=self.encoding, newline='\n') as f:
            f.write(text)
