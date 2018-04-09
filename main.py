import webapp2
import logging
import os
import re
import hashlib
import pprint
import urllib
import time

import cloudstorage as gcs
from webapp2_extras import json
from google.appengine.api import urlfetch
from secret import token


card_re = re.compile("\[\[([^\[\]]+)\]\]")
booster_re = re.compile("\*([^\*]+)\*")
groupme_api = "https://api.groupme.com/v3/bots/post"
back_hash = 'db0c48db407a907c16ade38de048a441'


class HTTPEcxception(Exception):
    def __init__(self, status_code, *args, **kwargs):
        self.status_code = status_code
        super(HTTPEcxception, self).__init__(*args, **kwargs)


class NotJsonException(Exception):
    pass


class MagicGroupmeBot(webapp2.RequestHandler):
    def post(self):
        self.bot_id = self.request.get('botid')

        request_data = json.decode(self.request.body)
        sender_type = request_data["sender_type"]

        if sender_type != "bot":
            text = request_data["text"]
            for card_string in parse_cards(text):
                self.handle_card_lookup(card_string)
            for set_id in parse_boosters(text):
                self.handle_booster(set_id)

    def handle_card_lookup(self, card_string):
        s = card_string.split("|")
        card_name = s[0]
        set_id = s[1] if len(s) > 1 else None

        card_data = get_card_data(card_name, set_id)

        gatherer_url = card_data["imageUrl"]
        groupme_image_url = get_and_upload_card_image(gatherer_url)

        if groupme_image_url is not None:
            self.send_message(card_name, groupme_image_url)
        else:
            groupme_image_url = get_and_upload_spoiler_image(card_name)
            if groupme_image_url is not None:
                self.send_message(card_name, groupme_image_url)

    def send_message(self, text, image_url=None):
        headers = {'Content-Type': 'application/json'}
        obj = {"text": text, "bot_id": self.bot_id}
        if image_url is not None:
            obj['attachments'] = [{"type": "image", "url": image_url}]
        payload = json.encode(obj)

        _ = post_with_retries(url=groupme_api, payload=payload, method=urlfetch.POST, headers=headers)

    def handle_booster(self, set_id):
        url = "https://api.magicthegathering.io/v1/sets/{}/booster".format(set_id)
        try:
            search_results = fetch_json_with_retries(url=url)
        except HTTPEcxception as e:
            if e.status_code == 404:
                logging.warn(e.message)
                return
            else:
                raise e

        if "cards" in search_results:
            cards = search_results["cards"]
            for card_data in cards:
                gatherer_url = card_data["imageUrl"]
                card_name = card_data["name"]
                groupme_image_url = get_and_upload_card_image(gatherer_url)

                if groupme_image_url is not None:
                    self.send_message(card_name, groupme_image_url)
                    time.sleep(0.5)
        else:
            logging.warn("No cards found {} {}".format(set_id, search_results))


def get_and_upload_card_image(gatherer_url):
    card_image = get_card_image(gatherer_url+"&.png")
    image_hash = hashlib.md5(card_image).hexdigest()
    image_url = None
    if image_hash != back_hash:
        image_url = upload_image(card_image, "png")
    return image_url


def get_and_upload_spoiler_image(card_name):
    card_set = "dom"
    card_lower_name = ''.join(e for e in card_name if e.isalnum()).lower()
    spoiler_url = "http://mythicspoiler.com/{}/cards/{}1.jpg".format(card_set, card_lower_name)
    spoiler_image = get_card_image(spoiler_url)
    image_url = None
    if spoiler_image is not None:
        image_url = upload_image(spoiler_image, "jpeg")
    else:
        spoiler_url = "http://mythicspoiler.com/{}/cards/{}.jpg".format(card_set, card_lower_name)
        spoiler_image = get_card_image(spoiler_url)
        if spoiler_image is not None:
            image_url = upload_image(spoiler_image, "jpeg")
    return image_url


def parse_cards(text):
    return card_re.findall(text)


def parse_boosters(text):
    return booster_re.findall(text)


def get_card_data(name, set_id):
    shortname_re = re.compile("^{}(([,])|( of )|( the )).*".format(name.lower()))
    url = "https://api.magicthegathering.io/v1/cards?orderBy=releaseDate&name={}".format(urllib.quote(name))

    if set_id is not None:
        url = url+"&set={}".format(set_id)

    search_results = json.decode(urlfetch.fetch(url).content)
    cards = search_results["cards"]

    exact_matches = []
    shortname_matches = []
    others_with_images = []
    for card in cards:
        if "imageUrl" in card:
            if card["name"].lower() == name.lower():
                exact_matches.append(card)
            elif shortname_re.match(card["name"].lower()):
                shortname_matches.append(card)
            else:
                others_with_images.append(card)

    if len(exact_matches) > 0:
        return exact_matches[0]
    elif len(shortname_matches) > 0:
        return shortname_matches[0]
    elif len(others_with_images) > 0:
        return others_with_images[0]
    else:
        return {"imageUrl": "http://gatherer.wizards.com/Handlers/Image.ashx?name={}&type=card&.png".format(urllib.quote(name))}


def get_card_image(image_url):
    result = urlfetch.fetch(image_url)
    if int(result.status_code) == 404:
        return None
    return result.content


def upload_image(card_image, filetype):
    image_len = len(card_image)
    url = "https://image.groupme.com/pictures"
    content_type = "image/{}".format("filetype")
    headers = {"X-Access-Token": token, "Content-Type": content_type, 'Content-Length': image_len}

    response_json = fetch_json_with_retries(url=url, payload=str(card_image), method=urlfetch.POST, headers=headers)

    return response_json['payload']["url"]


def fetch_json_with_retries(max_tries=3, rate=3, **args):
    response = post_with_retries(max_tries, rate, **args)
    if "Content-Type" not in response.headers or "application/json" not in response.headers["Content-Type"]:
        logging.warn("Response may not be json \nHeaders: {} \nContent: {}".format(response.headers, response.content))
    response_json = json.decode(response.content)
    return response_json


def post_with_retries(max_tries=3, rate=3, **args):
    response = urlfetch.fetch(**args)
    status_code = int(response.status_code)
    if status_code == 404:
        error_message = "Http error code 404 for url {}, {}".format(args["url"], response.content)
        raise HTTPEcxception(status_code, error_message)

    tries = 1
    while tries < max_tries and not 200 <= status_code <= 299:
        time.sleep(rate)
        response = urlfetch.fetch(**args)
        status_code = int(response.status_code)
        if not 200 <= status_code <= 299:
            error_message = "Http error code {} for url {}, {}".format(status_code, args["url"], response.content)
            logging.warn(error_message)
        tries += 1

    if not 200 <= status_code <= 299:
        error_message = "Http error code {} for url {}, {}".format(status_code, args["url"], response.content)
        raise HTTPEcxception(status_code, error_message)

    return response


app = webapp2.WSGIApplication([
    ('/', MagicGroupmeBot),
], debug=True)
