# TwitteRSS

This project allows you to turn Twitter list timelines into an RSS feed using AWS Lambda and S3.

## Initial Configuration

### Twitter API keys
You need to create a Twitter application first in order to obtain your API keys.  More information can be found here: https://developer.twitter.com/en/docs/basics/developer-portal/guides/apps.  You will need four key pieces of data to put into your `config.json` file:
- consumer_key
- consumer_secret
- access_token
- access_token_secret

### AWS S3
You need to create an S3 bucket to store the RSS XML file, and then configure the bucket for Static Website Hosting.  More information can be found here: https://docs.aws.amazon.com/AmazonS3/latest/dev/WebsiteHosting.html

Also, create the folder you want to store the files in.

### AWS Lambda
You will need to create an AWS Lambda Python function for this.

When creating the function, choose CloudWatch Events as an input trigger.  The schedule can be setup for any rate, but one example would be `rate(5 minutes)`.  This will trigger the Lambda function every five minutes.

You also need to setup and assign a new role that will allow Lambda to upload files to the S3 bucket.  Here is a sample policy (you will need to replace the bucket and folder info with yours):

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:PutObjectAcl"
            ],
            "Resource": "arn:aws:s3:::<bucket_name>/<folder_name>/*"
        }
    ]
}
```
## Building the Package

The following commands will
* install the required packages to the project root (needed for AWS Lambda)
* create a ZIP package for deployment. Run the following from the project directory:

```shell
pip install -r requirements.txt -t .
zip -r TwitteRSS.zip *
```

When this is complete, you will have a ZIP package ready for AWS Lambda.

## Deploying / Publishing

Upload the file to AWS Lambda and set the handler to `twitterss.twitterss_handler`.  Depending on how many lists you are checking, you might also want to increase the default Lambda execution timeout beyond the three second default.

## Features

The feature set is pretty low at this time.  Mainly, this package will:
* Check the specified Twitter lists for new tweets
* Create an RSS feed based on those tweets

### Areas for Improvement

There are probably more things than this, but at least the following could use some work:
* Only request tweets that are new since the last run
* Handle retweets and retweets with comments better
* Add images

## Contributing

Pull requests are welcomed - let's make this project better!


## Licensing

The code in this project is licensed under GNU GPLv3.