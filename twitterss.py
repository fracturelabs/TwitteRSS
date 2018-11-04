import boto3
import datetime
import hashlib
import json
import rfeed
import tweepy


def twitterss_handler(event, context):

    with open('config.json', 'r') as f:
        config = json.load(f)

    consumer_key = config['account']['consumer_key']
    consumer_secret = config['account']['consumer_secret']
    access_token = config['account']['access_token']
    access_token_secret = config['account']['access_token_secret']

    max_items = config['preferences']['max_items']
    bucket = config['preferences']['bucket']
    folder = config['preferences']['folder']

    rss_base_url = "https://s3.amazonaws.com/{}/{}/".format(bucket, folder)

    lists = config['lists']

    # Init API
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth)

    user = api.me()

    key = "{}-{}-{}".format(user.id, user.screen_name, '-'.join(lists))
    hash_object = hashlib.sha256(key)
    rss_key = hash_object.hexdigest()
    file_name = rss_key + ".xml"

    rss_items = []

    # Get list timeline
    for list_name in lists:
        for tweet in tweepy.Cursor(api.list_timeline, user.screen_name,
                                   list_name).items(max_items):

            if tweet.is_quote_status:
                tweet_url = tweet.entities['urls'][0]['expanded_url']
            else:
                tweet_url = tweet.retweeted_status.entities['urls'][0][
                    'expanded_url']

            item = rfeed.Item(
                title="Tweet from {}".format(tweet.author.screen_name),
                link=tweet_url,
                description=tweet.text,
                author=tweet.author.name,
                guid=rfeed.Guid(tweet.id),
                pubDate=tweet.created_at
            )

            rss_items.append(item)

    # Create the feed
    feed = rfeed.Feed(
        title="TwitteRSS Feed".format(user.screen_name),
        link=rss_base_url,
        description="TwitteRSS Feed".format(user.screen_name),
        language="en-US",
        lastBuildDate=datetime.datetime.now(),
        items=rss_items)

    # Save to S3
    encoded_feed = feed.rss().encode("utf-8")

    s3 = boto3.resource("s3")
    s3.Bucket(bucket).put_object(
        Key=folder + "/" + file_name,
        Body=encoded_feed,
        ACL='public-read',
        ContentType='text/xml')

    print "Done saving to S3: {}{}".format(rss_base_url, file_name)

    return "DONE"
