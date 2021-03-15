import gzip
import logging.config
from pathlib import Path


class SetReadFile(set):
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

    def __str__(self):
        return '\n'.join(self.as_sorted_list())

    def _read(self, filehandle, keepends: bool = False):
        self.clear()
        for line in filehandle:
            if keepends:
                self.add(line)
            else:
                self.add(line.rstrip('\n\r'))

    def as_sorted_list(self) -> list[str]:
        strings = list(self)
        strings.sort()
        return strings

    def read(self):
        with open(self.path, 'rt', encoding=self.encoding) as f:
            self._read(f)

    def read_text(self, text: str):
        self._read(text.splitlines(), keepends=True)

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


class SetFile(SetReadFile):
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
                    old = SetReadFile(self.path, self.encoding, self.log)
                    old.read()
                    if str(old) == text:
                        if self.log:
                            self.log.info(f'No change: {self.path}')
                        return
                except:
                    if self.log:
                        self.log.exception(f'Unable to check for changes: {self.path}')
            if create_backup:
                ext = self.path.suffix
                backup_path = self.path.with_suffix('.bak' + ext)
                try:
                    self.path.replace(backup_path)
                except:
                    if self.log:
                        self.log.exception(f'Unable to replace backup: {backup_path}')
        self._write(text)

    def _write(self, text: str):
        with open(self.path, 'wt', encoding=self.encoding) as f:
            f.write(text)


class SetGzip(SetFile):
    def read(self):
        with gzip.open(self.path, 'rt', encoding=self.encoding) as f:
            self._read(f)

    def _write(self, text: str):
        with gzip.open(self.path, 'wt', compresslevel=9, encoding=self.encoding) as f:
            f.write(text)
