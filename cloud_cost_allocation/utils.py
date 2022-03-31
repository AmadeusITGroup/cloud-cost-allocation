'''
Created on 31.03.2022

@author: marc.diensberg
'''
import validators
import requests
from csv import DictReader, DictWriter


def readCSV(uri, reader, cost_items):
    if validators.url(uri):
        readCSV_file(uri, reader, cost_items)
    else:
        readCSV_file(uri, reader, cost_items)

def readCSV_file(uri, reader, cost_items):
    with open(uri, 'r') as text_io:
        dictReader = DictReader(text_io)
        reader.read(cost_items, dictReader)

def readCSV_url(uri, reader, cost_items):
    response = requests.get(uri)
    dictReader = DictReader(response.iter_lines())
    reader.read(cost_items, dictReader)

def writeCSV_file(uri, writer):
    # Write allocated costs
    with open(uri, 'w', newline='') as outstream:
        # Open CSV file and write header
        dictWriter = DictWriter(outstream,
                            fieldnames=writer.getHeaders(),
                            restval='',
                            extrasaction='ignore')
        dictWriter.writeheader()
        writer.write(dictWriter)



