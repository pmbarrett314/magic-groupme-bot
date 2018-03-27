import webapp2
import logging
import re
import hashlib
import pprint
import urllib
from webapp2_extras import json
from google.appengine.api import urlfetch
from secret import token

card_re = re.compile("\[\[([^\[\]]+)\]\]")
groupme_api = "https://api.groupme.com/v3/bots/post"
back_hash = 'db0c48db407a907c16ade38de048a441'


class CardHandler(webapp2.RequestHandler):
    def post(self):
        bot_id = self.request.get('botid')

        request_data = json.decode(self.request.body)
        text = request_data["text"]
        sender_type = request_data["sender_type"]
        if sender_type != "bot":
            for card_string in parse_cards(text):
                s = card_string.split("|")
                card_name = s[0]
                set_id = s[1] if len(s) > 1 else None

                card_data = get_card_data(card_name, set_id)
                image_url = card_data["imageUrl"]+"&.png"

                card_image = get_card_image(image_url)
                card_hash = hashlib.md5(card_image).hexdigest()
                if card_hash != back_hash:
                    image_url = upload_image(card_image)
                    send_message(card_name, bot_id, image_url)


def parse_cards(text):
    return card_re.findall(text)


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
    return urlfetch.fetch(image_url).content


def upload_image(card_image):
    image_len = len(card_image)
    url = "https://image.groupme.com/pictures"
    headers = {"X-Access-Token": token, "Content-Type": 'image/png', 'Content-Length': image_len}
    upload_response = urlfetch.fetch(url, payload=str(card_image), method=urlfetch.POST, headers=headers)
    return json.decode(upload_response.content)['payload']["url"]


def send_message(text, bot_id, image_url=None):
    headers = {'Content-Type': 'application/json'}
    obj = {"text": text, "bot_id": bot_id}
    if image_url is not None:
        obj['attachments'] = [{"type": "image", "url": image_url}]
    payload = json.encode(obj)
    result = urlfetch.fetch(groupme_api, payload=payload, method=urlfetch.POST, headers=headers)


app = webapp2.WSGIApplication([
    ('/', CardHandler),
], debug=True)
