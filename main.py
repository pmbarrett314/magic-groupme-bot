import webapp2
import logging
import urllib2
import urllib
import re
import hashlib
from webapp2_extras import json
from google.appengine.api import urlfetch
from google.appengine.ext import ndb
from secret import token, bot_id



card_re=re.compile("\[\[([^\[\]]+)\]\]")
groupme_api="https://api.groupme.com/v3/bots/post"
back_hash='db0c48db407a907c16ade38de048a441'

class CardHandler(webapp2.RequestHandler):
    def post(self):
        request_data=json.decode(self.request.body)
        text=request_data["text"]
        sender_type=request_data["sender_type"]
        if sender_type !="bot":
            for card_name in parse_cards(text):
                card_image=get_card_image(card_name)
                card_hash=hashlib.md5(card_image).hexdigest()
                if card_hash!=back_hash:
                    image_url=upload_image(card_image)
                    send_message(card_name,image_url)

def parse_cards(text):
    return card_re.findall(text)

def get_card_image(card_name):
    gatherer_url="http://gatherer.wizards.com/Handlers/Image.ashx?name={}&type=card&.jpg".format(urllib.quote(card_name))
    return urlfetch.fetch(gatherer_url).content

def upload_image(card_image):
    image_len=len(card_image)
    url="https://image.groupme.com/pictures"
    headers={"X-Access-Token":token,"Content-Type":'image/jpeg','Content-Length':image_len}
    upload_response=urlfetch.fetch(url,payload=str(card_image),method=urlfetch.POST,headers=headers)
    logging.info(json.decode(upload_response.content))
    return json.decode(upload_response.content)['payload']["url"]

def send_message(text, image_url=None):
    headers = {'Content-Type': 'application/json'}
    obj={"text":text,"bot_id":bot_id}
    if image_url is not None:
        obj['attachments']=[{"type":"image","url":image_url}]
    payload=json.encode(obj)
    result=urlfetch.fetch(groupme_api,payload=payload,method=urlfetch.POST,headers=headers)
    logging.info(str(result.content))    


app = webapp2.WSGIApplication([
    ('/', CardHandler),
], debug=True)