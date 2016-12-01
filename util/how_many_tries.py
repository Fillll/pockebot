#encoding:utf-8

from pymongo import MongoClient

def main():
    client = MongoClient('localhost', 27025)
    db = client['pockebot']
    req = db['request_keys_v2']
    res = req.find({})  
    chats = []
    for i in res:
        chats.append(i['chat_id'])
    return len(set(chats))


if __name__ == '__main__':
    print(main())
