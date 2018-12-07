import boto3
import datetime
import hashlib
import json
import mimetypes
import tweepy

from distutils.util import strtobool
from feedgen.feed import FeedGenerator


class TweetArticle(object):
    def __init__(self, tweet):
        self._tweet = tweet
        self._is_retweet = hasattr(tweet, 'retweeted_status')
        self._is_quote = tweet.is_quote_status
        self._created_at = tweet.created_at.replace(
            tzinfo=datetime.timezone.utc)

        original_tweet = None

        if self._is_quote and self._is_retweet:
            self._title_prefix = 'Quoted RT from @'

            if hasattr(tweet.retweeted_status, 'quoted_status'):
                original_tweet = tweet.retweeted_status.quoted_status

                self._body = (f"<p>{tweet.retweeted_status.full_text}</p>"
                              "<p>*** Quoted @"
                              f"{original_tweet.user.screen_name} "
                              f"({original_tweet.user.name}) ***</p>"
                              f"<p>{original_tweet.full_text}</p>")

            else:
                self._body = (f"<p>{tweet.retweeted_status.full_text}</p>"
                              "<p>*** original tweet is unavailable ***</p>")

        # Quote
        elif self._is_quote and not self._is_retweet:
            self._title_prefix = 'Quote from @'

            if hasattr(tweet, 'quoted_status'):
                original_tweet = tweet.quoted_status

                self._body = (f"<p>{tweet.full_text}</p>"
                              "<p>*** Quoted @"
                              f"{original_tweet.user.screen_name} "
                              f"({original_tweet.user.name}) ***</p>"
                              f"<p>{original_tweet.full_text}</p>")

            else:
                self._body = (f"<p>{tweet.full_text}</p>"
                              "<p>*** original tweet is unavailable ***</p>")

        # Retweet
        elif self._is_retweet and not self._is_quote:
            self._title_prefix = 'RT from @'

            if hasattr(tweet, 'retweeted_status'):
                original_tweet = tweet.retweeted_status

                self._body = (f"<p><i>Originally tweeted by "
                              f"@{original_tweet.user.screen_name} "
                              f"({original_tweet.user.name})</i></p>"
                              f"<p>{original_tweet.full_text}</p>")

            else:
                self._body = "<p>*** original tweet is unavailable ***</p>"

        # Regular
        else:
            self._title_prefix = 'Tweet from @'
            self._body = tweet.full_text.replace('\n', '\n<br />')
            original_tweet = tweet

        if original_tweet and 'media' in original_tweet.entities:
            self._media_url = (
                original_tweet.entities['media'][0]['media_url_https'])

            self._body += (
                f"<br /><img src='{self._media_url}' />")

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
        return self._created_at

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
        return self._body.replace('\n', '\n<br />')

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
    folder = config['s3']['folder'].replace("\\", "/").strip("/")
    
    if folder:
        folder += "/"
    
    filename_salt = config['s3']['filename_salt']
    feed_base_url = f"https://s3.amazonaws.com/{bucket}/{folder}"

    feeds = config['feeds']

    # Init API
    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    api = tweepy.API(auth)

    user = api.me()

    for feed in feeds:
        print(f"Processing Feed: {feed['title']}")

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
        file_name = rss_key + "-atom.xml"

        # Create the base feed
        feed_generator = FeedGenerator()
        feed_generator.id(feed_base_url + file_name)
        feed_generator.title(feed['title'])
        feed_generator.author({'name': user.screen_name})
        feed_generator.subtitle(f"{user.screen_name}'s TwitteRSS Feed")
        feed_generator.link(href=feed_base_url + file_name, rel='self')
        feed_generator.language('en')

        entries = {}

        # Get list timeline
        for list_name in lists:
            tweets = tweepy.Cursor(api.list_timeline, user.screen_name,
                                   list_name, tweet_mode="extended")

            for tweet in tweets.items(max_items):

                # Don't store duplicates
                if tweet.id_str in entries.keys():
                    continue

                entry = TweetArticle(tweet)

                if exclude_retweets and entry.is_retweet:
                    continue

                if require_retweets and not entry.is_retweet:
                    continue

                if exclude_quotes and entry.is_quote:
                    continue

                if require_quotes and not entry.is_quote:
                    continue

                if exclude_tweets_with_media and entry.media_url:
                    continue

                if require_tweets_with_media and not entry.media_url:
                    continue

                # print(entry)

                # Create the feed item
                feed_entry = feed_generator.add_entry()
                feed_entry.id(entry.url)
                feed_entry.pubDate(entry.created_at)
                feed_entry.title(entry.title)
                feed_entry.description(entry.body)
                feed_entry.author(name=entry.author_name)
                feed_entry.link(href=entry.url)

                if entry.media_url:
                    tweet_media_type = mimetypes.guess_type(
                        entry.media_url)[0]

                    feed_entry.enclosure(
                        url=entry.media_url,
                        length=0,
                        type=tweet_media_type)

                entries[entry.id] = feed_entry

        # Save to S3
        s3 = boto3.resource("s3")
        s3.Bucket(bucket).put_object(
            Key=folder + file_name,
            Body=feed_generator.atom_str(pretty=True),
            ACL='public-read',
            ContentType='application/xml',
            CacheControl='max-age=300',
            ContentEncoding='utf-8')

        print(f"Saved {len(entries)} records to {feed_base_url}{file_name}")

    return "DONE"
