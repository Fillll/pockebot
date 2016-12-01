#encoding:utf-8

from pprint import pprint
from collections import OrderedDict

from pymongo import MongoClient

def main():
    client = MongoClient('localhost', 27025)
    db = client['pockebot']
    req = db['tags']
    res = req.find({})  
    overall = {}
    for doc in res:
        for tag in doc['stat']:
            overall[tag] = overall.get(tag, 0) + doc['stat'][tag]
    return OrderedDict(sorted(overall.items(), key=lambda t: t[1]))


if __name__ == '__main__':
    pprint(main())
