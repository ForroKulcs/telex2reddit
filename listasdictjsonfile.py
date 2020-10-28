import json
import jsonfile

class ListAsDictJsonText(jsonfile.JsonText):
    def __str__(self):
        json_list = []
        for item_id in sorted(self):
            item = self[item_id]
            item['id'] = item_id
            json_list.append(item)
        return json.dumps(json_list, ensure_ascii = False, indent = '\t', sort_keys = True)

    def read_text(self, text: str):
        json_list = json.loads(text)
        if not isinstance(json_list, list):
            raise Exception(f'JSON list expected')
        ids = set()
        for item in json_list:
            item_id = str(item.get('id', ''))
            if item_id == '':
                raise Exception(f'Missing id: {item}')
            if not item_id.isnumeric():
                raise Exception(f'Unexpected id: {item_id}')
            if item_id in ids:
                raise Exception(f'Duplicate id: {item_id}')
            ids.add(item_id)
        del ids
        self.clear()
        for item in json_list:
            item_id = item.pop('id')
            self[item_id] = item

class ListAsDictJsonFile(ListAsDictJsonText, jsonfile.JsonFile):
    pass

class ListAsDictJsonGzip(ListAsDictJsonFile, jsonfile.JsonGzip):
    pass
