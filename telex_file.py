import gzip
import json
import logging.config
import os
from pathlib import Path

class JsonFile(dict):
    def __init__(self, filename: [Path, str], encoding: str = 'utf-8', log: logging.Logger = None):
        super().__init__()
        if isinstance(filename, Path):
            self._path = filename
        else:
            self._path = Path(filename)
        self._encoding = encoding
        self._log = log

    def _read(self):
        with open(self._path, 'rt', encoding = self._encoding) as f:
            return f.read()

    def _write(self, text: str):
        with open(self._path, 'wt', encoding = self._encoding) as f:
            f.write(text)

    def read(self):
        text = self._read()
        self.clear()
        self.update(json.loads(text))

    def try_read(self) -> bool:
        try:
            if self._path.is_file():
                self.read()
                return True
            else:
                if self._log:
                    self._log.warning(f'{self._path} not available')
        except:
            if self._log:
                self._log.exception(f'Unable to read: {self._path}')
        return False

    def save_to_text(self):
        return json.dumps(self, ensure_ascii = False, indent = '\t', sort_keys = True)

    def try_write(self, create_backup: bool = False, check_for_changes: bool = False) -> bool:
        try:
            self.write(create_backup, check_for_changes)
            return True
        except:
            if self._log:
                self._log.exception(f'Unable to write: {self._path}')
        return False

    def write(self, create_backup: bool = False, check_for_changes: bool = False):
        text = self.save_to_text()
        if (create_backup or check_for_changes) and self._path.is_file():
            if check_for_changes:
                try:
                    old = self._read()
                    if old == text:
                        if self._log:
                            self._log.info(f'No change: {self._path}')
                        return
                except:
                    if self._log:
                        self._log.exception(f'Unable to read: {self._path}')
            if create_backup:
                ext = self._path.suffix
                backup_path = self._path.with_suffix('.bak' + ext)
                try:
                    self._path.replace(backup_path)
                except:
                    if self._log:
                        self._log.exception(f'Unable to replace: {backup_path}')
        self._write(text)

class JsonGzip(JsonFile):
    def _read(self):
        with gzip.open(self._path, 'rt', encoding = self._encoding) as f:
            return f.read()

    def _write(self, text: str):
        with gzip.open(self._path, 'wt', compresslevel = 9, encoding = self._encoding) as f:
            f.write(text)
