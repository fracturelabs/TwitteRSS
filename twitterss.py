import boto3
import datetime
import hashlib
import json
import mimetypes
import rfeed
import tweepy

from distutils.util import strtobool


def twitterss_handler(event, context):

    with open('config.json', 'r') as f:
        config = json.load(f)

    consumer_key = config['twitter']['consumer_key']
    consumer_secret = config['twitter']['consumer_secret']
    access_token = config['twitter']['access_token']
    access_token_secret = config['twitter']['access_token_secret']

    bucket = config['s3']['bucket']
    folder = config['s3']['folder']
    filename_nonce = config['s3']['filename_nonce']

    max_items = config['preferences']['max_items']
    exclude_retweets = bool(strtobool(
        config['preferences']['exclude_retweets']))
    require_retweets = bool(strtobool(
        config['preferences']['require_retweets']))
    exclude_quotes = bool(strtobool(
        config['preferences']['exclude_quotes']))
    require_quotes = bool(strtobool(
        config['preferences']['require_quotes']))
    exclude_tweets_with_media = bool(strtobool(
        config['preferences']['exclude_tweets_with_media']))
    require_tweets_with_media = bool(strtobool(
        config['preferences']['require_tweets_with_media']))
    exclude_tweets_with_urls = bool(strtobool(
        config['preferences']['exclude_tweets_with_urls']))
    require_tweets_with_urls = bool(strtobool(
        config['preferences']['require_tweets_with_urls']))

    rss_base_url = "https://s3.amazonaws.com/{}/{}/".format(bucket, folder)

    lists = config['lists']

    # Init API
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth)

    user = api.me()

    # Create the RSS filename.  You can force a change by updating the nonce.
    key = "{}-{}-{}-{}".format(user.id, user.screen_name,
                               '-'.join(lists), filename_nonce)
    hash_object = hashlib.sha256(key)
    rss_key = hash_object.hexdigest()
    file_name = rss_key + ".xml"

    rss_items = {}

    # Get list timeline
    for list_name in lists:
        for tweet in tweepy.Cursor(api.list_timeline, user.screen_name,
                                   list_name,
                                   tweet_mode="extended").items(max_items):

            # Don't store duplicates
            if tweet.id_str in rss_items.keys():
                continue

            tweet_is_retweet = hasattr(tweet, 'retweeted_status')
            tweet_is_quote = tweet.is_quote_status
            tweet_media_url = None

            if exclude_retweets and tweet_is_retweet:
                continue

            if require_retweets and not tweet_is_retweet:
                continue

            if exclude_quotes and tweet_is_quote:
                continue

            if require_quotes and not tweet_is_quote:
                continue

            # Retweets
            if tweet_is_retweet:
                tweet_title = "Retweet from @{}".format(
                    tweet.author.screen_name)
                tweet_id = tweet.id_str
                tweet_text = tweet.retweeted_status.full_text.encode('utf-8')
                tweet_author_handle = tweet.retweeted_status.user.screen_name
                tweet_author_name = tweet.retweeted_status.user.name.encode(
                    'utf-8')
                tweet_url = "https://twitter.com/{}/status/{}".format(
                        tweet_author_handle, tweet_id)

                if 'media' in tweet.retweeted_status.entities:
                    tweet_media_url = tweet.retweeted_status.entities[
                            'media'][0]['media_url_https']

            # Quotes
            if tweet_is_quote:
                tweet_title = "Quote from @{}".format(tweet.author.screen_name)
                tweet_id = tweet.id_str

                if tweet_is_retweet:
                    tweet_text = "{}\n\n*** Quoted @{} ({}) ***\n\n{}".format(
                        tweet.retweeted_status.full_text.encode('utf-8'),
                        (tweet.retweeted_status.quoted_status
                            .user.screen_name.encode('utf-8')),
                        (tweet.retweeted_status.quoted_status
                            .user.name.encode('utf-8')),
                        (tweet.retweeted_status.quoted_status
                            .full_text.encode('utf-8')))

                    if 'media' in (tweet.retweeted_status
                                   .quoted_status.entities):
                        tweet_media_url = (
                                tweet.retweeted_status.quoted_status
                                .entities['media'][0]['media_url_https'])

                else:
                    tweet_text = "{}\n\n*** Quoted @{} ({}) ***\n\n{}".format(
                        tweet.full_text.encode('utf-8'),
                        tweet.quoted_status.user.screen_name.encode('utf-8'),
                        tweet.quoted_status.user.name.encode('utf-8'),
                        tweet.quoted_status.full_text.encode('utf-8'))

                    if 'media' in tweet.quoted_status.entities:
                        tweet_media_url = (
                            tweet.quoted_status.entities
                            ['media'][0]['media_url_https'])

                tweet_author_handle = tweet.author.screen_name
                tweet_author_name = tweet.author.name.encode('utf-8')
                tweet_url = "https://twitter.com/{}/status/{}".format(
                        tweet_author_handle, tweet_id)

            # Regular tweet
            if not tweet_is_retweet and not tweet_is_quote:
                tweet_title = "Tweet from @{}".format(tweet.author.screen_name)
                tweet_id = tweet.id_str
                tweet_text = tweet.full_text.encode('utf-8')
                tweet_author_handle = tweet.author.screen_name.encode('utf-8')
                tweet_author_name = tweet.author.name.encode('utf-8')
                tweet_url = "https://twitter.com/{}/status/{}".format(
                        tweet_author_handle, tweet_id)

                if 'media' in tweet.entities:
                    tweet_media_url = (
                        tweet.entities['media'][0]['media_url_https'])

            # print("TITLE: {}\nID: {}\nTEXT: {}\nAUTHOR: {}\nURL: {}\n".format(
            #     tweet_title, tweet_id, tweet_text.replace('\n', '\n<br />'),
            #     tweet_author_handle, tweet_url))

            if tweet_media_url:
                tweet_media_type = mimetypes.guess_type(tweet_media_url)[0]
                media = rfeed.Enclosure(
                    url=tweet_media_url, length=0, type=tweet_media_type)
            else:
                media = None

            item = rfeed.Item(
                title=tweet_title,
                link=tweet_url,
                description=tweet_text.replace('\n', '\n<br />'),
                author=tweet_author_name,
                guid=rfeed.Guid(tweet_id, isPermaLink=False),
                pubDate=tweet.created_at,
                enclosure=media
            )

            rss_items[tweet_id] = item

    # Create the feed
    feed = rfeed.Feed(
        title="{}'s TwitteRSS Feed".format(user.screen_name),
        link=rss_base_url,
        description="{}'s TwitteRSS Feed".format(user.screen_name),
        language="en-US",
        lastBuildDate=datetime.datetime.now(),
        items=rss_items.values())

    # Save to S3
    s3 = boto3.resource("s3")
    s3.Bucket(bucket).put_object(
        Key=folder + "/" + file_name,
        Body=feed.rss(),
        ACL='public-read',
        ContentType='application/xml',
        CacheControl='max-age=300',
        ContentEncoding='utf-8')

    print "Saved {} records to: {}{}".format(
        len(rss_items), rss_base_url, file_name)

    return "DONE"
