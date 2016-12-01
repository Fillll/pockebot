#encoding:utf-8

from os.path import join

from gtts import gTTS
from newspaper import Article


def make_an_audio(url, filename, lang=None):
    if lang is None:
        lang = 'en'
    article = Article(url)
    article.download()
    article.parse()

    tts = gTTS(text=article.text, lang=lang)
    f = open(join('audio', filename), 'wb')
    tts.write_to_fp(f)
    f.close()
