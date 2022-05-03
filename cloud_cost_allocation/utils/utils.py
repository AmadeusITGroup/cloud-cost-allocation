'''
Created on 31.03.2022

@author: marc.diensberg
'''
import validators
import requests
from csv import DictReader, DictWriter


def read_csv(uri, reader, cost_items):
    if validators.url(uri):
        read_csv_url(uri, reader, cost_items)
    else:
        read_csv_file(uri, reader, cost_items)


def read_csv_file(uri, reader, cost_items):
    with open(uri, 'r') as text_io:
        dictReader = DictReader(text_io)
        reader.read(cost_items, dictReader)


def read_csv_url(uri, reader, cost_items):
    response = requests.get(uri)
    dictReader = DictReader(response.iter_lines())
    reader.read(cost_items, dictReader)


def write_csv_file(uri, writer):
    # Write allocated costs
    with open(uri, 'w', newline='') as outstream:
        # Open CSV file and write header
        dictWriter = DictWriter(outstream,
                                fieldnames=writer.get_headers(),
                                restval='',
                                extrasaction='ignore')
        dictWriter.writeheader()
        writer.write(dictWriter)
