import boto3
import datetime
import hashlib
import json
import mimetypes
import rfeed
import tweepy

from distutils.util import strtobool


class TweetArticle(object):
    def __init__(self, tweet):
        self._tweet = tweet
        self._is_retweet = hasattr(tweet, 'retweeted_status')
        self._is_quote = tweet.is_quote_status

        # Quoted Retweet
        if self._is_quote and self._is_retweet:
            self._title_prefix = 'Quoted RT from @'
            original_tweet = tweet.retweeted_status.quoted_status

            self._body = (f"<p>{tweet.retweeted_status.full_text}</p>"
                          f"<p>*** Quoted @{original_tweet.user.screen_name} "
                          f"({original_tweet.user.name}) ***</p>"
                          f"<p>{original_tweet.full_text}</p>"
                          .replace('\n', '\n<br />'))

        # Quote
        elif self._is_quote and not self._is_retweet:
            self._title_prefix = 'Quote from @'
            original_tweet = tweet.quoted_status

            self._body = (f"<p>{tweet.full_text}</p>"
                          f"<p>*** Quoted @{original_tweet.user.screen_name} "
                          f"({original_tweet.user.name}) ***</p>"
                          f"<p>{original_tweet.full_text}</p>"
                          .replace('\n', '\n<br />'))

        # Retweet
        elif self._is_retweet and not self._is_quote:
            self._title_prefix = 'RT from @'
            original_tweet = tweet.retweeted_status

            self._body = (f"<p><i>Originally tweeted by "
                          f"@{original_tweet.user.screen_name} "
                          f"({original_tweet.user.name})</i></p>"
                          f"<p>{original_tweet.full_text}</p>"
                          .replace('\n', '\n<br />'))

        # Regular
        else:
            self._title_prefix = 'Tweet from @'
            self._body = tweet.full_text.replace('\n', '\n<br />')
            original_tweet = tweet

        if 'media' in original_tweet.entities:
            self._media_url = (
                original_tweet.entities['media'][0]['media_url_https'])
        else:
            self._media_url = None

    @property
    def id(self):
        return self._tweet.id_str

    @property
    def url(self):
        return ("https://twitter.com/"
                f"{self.author_handle}/status/{self.id}")

    @property
    def created_at(self):
        return self._tweet.created_at

    @property
    def author_handle(self):
        return self._tweet.author.screen_name

    @property
    def author_name(self):
        return self._tweet.author.name

    @property
    def title(self):
        return f"{self._title_prefix}{self.author_handle}"

    @property
    def body(self):
        return self._body

    @property
    def media_url(self):
        return self._media_url

    @property
    def is_retweet(self):
        return self._is_retweet

    @property
    def is_quote(self):
        return self._is_quote

    def __repr__(self):
        return (
            'TweetArticle:\n'
            f'\tid={self.id}\n'
            f'\turl={self.url}\n'
            f'\tcreated_at={self.created_at}\n'
            f'\tauthor_handle={self.author_handle}\n'
            f'\tauthor_name={self.author_name}\n'
            f'\ttitle={self.title}\n'
            f'\tbody={self.body}\n'
            f'\tmedia_url={self.media_url}\n'
            f'\tis_retweet={self.is_retweet}\n'
            f'\tis_quote={self.is_quote}\n'
        )


def twitterss_handler(event, context):

    with open('config.json', 'r') as f:
        config = json.load(f)

    consumer_key = config['twitter']['consumer_key']
    consumer_secret = config['twitter']['consumer_secret']
    access_token = config['twitter']['access_token']
    access_token_secret = config['twitter']['access_token_secret']

    bucket = config['s3']['bucket']
    folder = config['s3']['folder']
    filename_salt = config['s3']['filename_salt']
    rss_base_url = "https://s3.amazonaws.com/{}/{}/".format(bucket, folder)

    feeds = config['feeds']

    # Init API
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth)

    user = api.me()

    for feed in feeds:
        print("Feed Title: {}".format(feed['title']))

        max_items = feed['preferences']['max_items']
        exclude_retweets = bool(strtobool(
            feed['preferences']['exclude_retweets']))
        require_retweets = bool(strtobool(
            feed['preferences']['require_retweets']))
        exclude_quotes = bool(strtobool(
            feed['preferences']['exclude_quotes']))
        require_quotes = bool(strtobool(
            feed['preferences']['require_quotes']))
        exclude_tweets_with_media = bool(strtobool(
            feed['preferences']['exclude_tweets_with_media']))
        require_tweets_with_media = bool(strtobool(
            feed['preferences']['require_tweets_with_media']))

        lists = feed['lists']

        # Create the RSS filename. Force a change by updating the salt.
        key = f"{user.id}{user.screen_name}{''.join(lists)}{filename_salt}"
        hash_object = hashlib.sha256(key.encode('utf-8'))
        rss_key = hash_object.hexdigest()
        file_name = rss_key + ".xml"

        rss_items = {}

        # Get list timeline
        for list_name in lists:
            tweets = tweepy.Cursor(api.list_timeline, user.screen_name,
                                   list_name, tweet_mode="extended")

            for tweet in tweets.items(max_items):

                # Don't store duplicates
                if tweet.id_str in rss_items.keys():
                    continue

                tweet_article = TweetArticle(tweet)

                if exclude_retweets and tweet_article.is_retweet:
                    continue

                if require_retweets and not tweet_article.is_retweet:
                    continue

                if exclude_quotes and tweet_article.is_quote:
                    continue

                if require_quotes and not tweet_article.is_quote:
                    continue

                if exclude_tweets_with_media and tweet_article.media_url:
                    continue

                if require_tweets_with_media and not tweet_article.media_url:
                    continue

                # print(tweet_article)

                if tweet_article.media_url:
                    tweet_media_type = mimetypes.guess_type(
                        tweet_article.media_url)[0]

                    media = rfeed.Enclosure(
                        url=tweet_article.media_url,
                        length=0,
                        type=tweet_media_type)
                else:
                    media = None

                item = rfeed.Item(
                    title=tweet_article.title,
                    link=tweet_article.url,
                    description=tweet_article.body,
                    author=tweet_article.author_name,
                    guid=rfeed.Guid(tweet_article.id, isPermaLink=False),
                    pubDate=tweet_article.created_at,
                    enclosure=media
                )

                rss_items[tweet_article.id] = item

        feed = rfeed.Feed(
            title=feed['title'],
            link=rss_base_url,
            description="{}'s TwitteRSS Feed".format(user.screen_name),
            language="en-US",
            lastBuildDate=datetime.datetime.now(),
            items=list(rss_items.values()))

        # Save to S3
        s3 = boto3.resource("s3")
        s3.Bucket(bucket).put_object(
            Key=folder + "/" + file_name,
            Body=feed.rss(),
            ACL='public-read',
            ContentType='application/xml',
            CacheControl='max-age=300',
            ContentEncoding='utf-8')

        print(f"Saved {len(rss_items)} records to {rss_base_url}{file_name}")

    return "DONE"
