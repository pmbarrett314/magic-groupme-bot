# magic-groupme-bot

A serverless bot that posts images of Magic the Gathering cards when requested in groupme. To set up, create a project in Google Cloud Platform, set it up in App Engine, and point, and then create an account at https://dev.groupme.com/bots/ and add the bot with a callback url pointing at the App Engine endpoint with a query parameter called `botid` with the bot id. I'll make this into a step by step walkthrough at some point. Disclaimer that I haven't quite figured out how the pricing structure works, so this may cost money.
