import gzip
import json
import os

def read_gzip_as_json(filename: [str, bytes, os.PathLike]) -> dict:
    with gzip.open(filename, 'rt', encoding = 'utf-8') as f:
        telex_json_text = f.read()
    return json.loads(telex_json_text)

def write_text_to_gzip(filename: [str, bytes, os.PathLike], data: str):
    with gzip.open(filename, 'wt', compresslevel = 9, encoding = 'utf-8') as f:
        f.write(data)
