'''
Created on 31.03.2022

@author: marc.diensberg
'''

import csv
import io
import logging
import re
import requests
import validators


def deserialize_tags(tags_str: str):
    deserialized = re.sub(r'([^\\]):', r'\g<1>\a', tags_str)  # Replace non-escaped : by \a (control character)
    deserialized = re.sub(r'([^\\]),', r'\g<1>\b', deserialized)  # Replace non-escaped , by \b (control character)
    deserialized = re.sub(r'\\([:,\\])', r'\g<1>', deserialized)  # Remove escape characters
    tags = {}
    for tag_str in deserialized.split('\b'):
        if tag_str:
            key_value_match = re.match("([^\a]+)\a([^\a]*)", tag_str)
            if key_value_match:
                key = key_value_match.group(1).strip().lower()
                value = key_value_match.group(2).strip().lower()
                tags[key] = value
            else:
                logging.error("Unexpected tag format: '" + tag_str + "'")
    return tags


def is_float(value):
    try:
        float(value)
        return True
    except(TypeError, ValueError):
        return False


def read_csv(uri, reader, cost_items):
    if validators.url(uri):
        read_csv_url(uri, reader, cost_items)
    else:
        read_csv_file(uri, reader, cost_items)


def read_csv_file(uri, reader, cost_items):
    with open(uri, 'r', encoding='utf-8') as text_io:
        dict_reader = csv.DictReader(text_io)
        reader.read(cost_items, dict_reader)


def read_csv_url(uri, reader, cost_items):
    response = requests.get(uri)
    dict_reader = csv.DictReader(response.iter_lines())
    reader.read(cost_items, dict_reader)


def serialize_tag_key_or_value(tag_key_or_value: str):
    return re.sub(r'([,:\\])', r'\\\g<1>', tag_key_or_value)


def serialize_tags(tags: dict[str, str]):
    tags_str = io.StringIO()
    for key, value in tags.items():
        tags_str.write(serialize_tag_key_or_value(key) + ":" + serialize_tag_key_or_value(value) + ",")
    return tags_str.getvalue()


def write_csv_file(uri, writer):
    # Write allocated costs
    with open(uri, 'w', encoding='utf-8', newline='') as out_stream:
        # Open CSV file and write header
        dict_writer = csv.DictWriter(out_stream,
                                     fieldnames=writer.get_headers(),
                                     restval='',
                                     extrasaction='ignore')
        dict_writer.writeheader()
        writer.write(dict_writer)
