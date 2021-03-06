#!/usr/bin/env python

"""
Reads album information as line-oriented JSON from stdin or a supplied filename
and looks up the album on spotify and rdio and writes out line-oriented JSON 
with streaming information.
"""

import re
import sys
import json
import time
import logging
import fileinput
from urllib import quote, urlopen, urlencode

import oauth2 as oauth

import config


def main():
    logging.basicConfig(filename="compare.log", level=logging.INFO)
    aoty = json.loads(open("aoty_dedupe.json").read())
    for line in fileinput.input():
        a = json.loads(line)
        try:
            artist = a['artist']
            album = a['album']
            a['spotify'] = spotify(artist, album)
            a['rdio'] = rdio(artist, album)
            logging.info(a)
            print json.dumps(a)
        except Exception, e:
            logging.exception("error while comparing")
            sys.exit(1)
        time.sleep(1)

def spotify(artist, album):
    q = '%s AND "%s"' % (artist, album)
    q = quote(q.encode('utf-8'))
    url = 'http://ws.spotify.com/search/1/album.json?q=' + q

    # spotify search api throws sporadic 502 errors
    tries = 0
    max_tries = 100
    response = None
    while True:
        tries += 1
        r = urlopen(url)

        if r.code == 200:
            j = urlopen(url).read()
            response = json.loads(r.read())
            break

        # spotify throws a weird 403 error when searching for 
        # !!! / Strange Weather Isn't It
        # e.g. http://ws.spotify.com/search/1/album.json?q=%21%21%21%20AND%20%22Strange%20Weather%2C%20Isn%27t%20It%3F%22

        elif r.code == 403:
            logging.info("got 403 when searching spotify for %s/%s", artist, album)
            return {"can_stream": False, "url": None}

        if tries > max_tries: 
            raise Exception("no more tries searching %s/%s at spotify" % (artist, album))

        backoff = tries ** 2 
        logging.warn("received %s when fetching %s, sleeping %s", r.code, url, backoff)
        time.sleep(backoff)

    if not response:
        raise Exception("couldn't talk to Spotify for %s/%s", artist, album)

    can_stream = False
    url = None

    for a in response['albums']:
        if clean(a['name']) == clean(album) and spotify_artist(a, artist):
            url = a['href']
            if config.COUNTRY in a['availability']['territories'].split(' ') or a['availability']['territories'] == 'worldwide': 
                can_stream = True

    return {'can_stream': can_stream, 'url': url}

def spotify_artist(a, artist_name):
    for artist in a['artists']:
        if clean(artist['name']) == clean(artist_name): 
            return True
    return False

def rdio(artist, album):
    consumer = oauth.Consumer(config.RDIO_CONSUMER_KEY, 
                              config.RDIO_CONSUMER_SECRET)
    client = oauth.Client(consumer)
    q = {
        'method': 'search', 
        'query': ('%s %s' % (artist, album)).encode('utf-8'), 
        'types': 'Album',
        '_region': config.COUNTRY
    }

    response = None
    tries = 0
    max_tries = 100
    while True:
        r, content = client.request('http://api.rdio.com/1/', 'POST', urlencode(q))
        if r['status'] == '200':
            response = json.loads(content)
            if response and response.get('result', {}).get('results', None) != None:
                break
            else:
                logging.info("unexpected json from rdio for %s/%s: %s", artist, album, response)
        else:
            logging.warn("received %s when searching rdio for %s/%s", (r['status'], artist, album))

        tries += 1
        if tries > max_tries:
            raise Exception("no more tries left searching rdio for %s/%s" % (artist, album))

        backoff = tries ** 2
        logging.debug("sleeping %s" % backoff)
        time.sleep(backoff)

    can_stream = False
    url = None
    for r in response['result']['results']:
        if clean(r['name']) == clean(album) and clean(r['artist']) == clean(artist):
            url = "http://rdio.com" + r['url']
            if r['canStream'] == True:
                can_stream = True

    return {'can_stream': can_stream, 'url': url}

def clean(a):
    a = a.lower()
    a = re.sub(' and ', '', a)
    a = re.sub('^the ', '', a)
    a = re.sub(' \(.+\)$', '', a)
    a = re.sub(r'''[\.,-\/#!$%\^&\*;:{}=\-_`~() ]''', '', a)
    return a

if __name__ == "__main__":
    main()
