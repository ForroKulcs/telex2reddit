import gzip
import json
from jsonfile import JsonFile

class ListAsDictJsonFile(JsonFile):
    def __str__(self):
        json_list = []
        for item_id in sorted(self):
            item = self[item_id]
            item['id'] = int(item_id)
            json_list.append(item)
        return json.dumps(json_list, ensure_ascii = False, indent = '\t', sort_keys = True)

    def read(self):
        text = self._read()
        json_list = json.loads(text)
        if not isinstance(json_list, list):
            raise Exception(f'JSON list expected: {self.path}')
        self.clear()
        for item in json_list:
            item_id = str(item.pop('id', ''))
            if item_id == '':
                raise Exception(f'Missing id: {item}')
            if not item_id.isnumeric():
                raise Exception(f'Unexpected id: {item_id}')
            if item_id in self:
                raise Exception(f'Duplicate id: {item_id}')
            self[int(item_id)] = item

class ListAsDictJsonGzip(ListAsDictJsonFile):
    def _read(self):
        with gzip.open(self.path, 'rt', encoding = self.encoding) as f:
            return f.read()

    def _write(self, text: str):
        with gzip.open(self.path, 'wt', compresslevel = 9, encoding = self.encoding) as f:
            f.write(text)
