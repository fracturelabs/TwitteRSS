# TwitteRSS

This project allows you to turn Twitter list timelines into an RSS feed using AWS Lambda and S3.

For a detailed how-to, please see https://www.fracturelabs.com/posts/2018/threat-intel-rss-feeds-via-twitter-lists/.

In short, the final solution will:

1. Run a python script to turn Twitter List Timeline's into an RSS feed
2. Publish the RSS feed to an S3 bucket
3. Your feed reader polls the S3 bucket looking for new tweets 

## Prerequisites

1. Install [Python 3](https://www.python.org/downloads/) and pip3 (refer to your OS-specific installation instructions)
2. Install the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html) and [configure your credentials](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html)
3. Install [git](https://git-scm.com/downloads) or just download the packaged zip file manually
4. Install [jq](https://stedolan.github.io/jq/download/)

## Initial Configuration

### Twitter API keys
You need to create a Twitter application first in order to obtain your API keys.  More information can be found here: https://developer.twitter.com/en/docs/basics/developer-portal/guides/apps.  You will need four key pieces of data to put into your `config.json` file:
- consumer_key
- consumer_secret
- access_token
- access_token_secret

### AWS S3
You need to create an S3 bucket to store the RSS XML file, and then configure the bucket for Static Website Hosting.  This is really simple using the AWS CLI:

1. `aws s3api create-bucket --acl private --bucket <REPLACE_WITH_BUCKET_NAME>`
2. `aws s3 website s3://<REPLACE_WITH_BUCKET_NAME>/ --index-document index.html`

You'll also have to edit the `lambda-exec-policy.json` file and set the `Resource` by updating `bucket_and_folder_path` with your bucket and folder path. 

## Building and deploying the code

### Get the code
This project requires Python v3.6 - it will not work with 2.x, and I've had problems with 3.7.

```bash
git clone https://github.com/fracturelabs/TwitteRSS
cd TwitteRSS
pip3 install -r requirements.txt --system -t packages
```

### Config updates
You'll need to edit the `config.json` file to meet your needs:

* Enter your Twitter API keys in the `twitter` section
* Enter your S3 bucket name in the `s3.bucket` section
* Enter the S3 folder name (or `""` if none) in the `s3.folder` section
* Enter any random string in the `s3.filename_salt` section.  This is only to help give the final RSS filename some uniqueness so people don't just stumble upon your RSS feed.  Not that it's very sensitive, but there's no reason to incur any S3 costs for someone accessing your files!
* Edit the `feeds` section to meet your needs.
* Edit the `preferences` section to whatever fits your needs.  Usually the defaults will do just fine.


### Build and deploy the code
We'll build a deployable package and load it into AWS with:

```bash
# Build the package
(cd packages; zip -r9 ../build.zip .); zip -g build.zip twitterss.py config.json

# Create a Lambda role and attach a policy to it
policy_arn=$(aws iam create-policy --policy-name Twitter-Lambda-Policy --policy-document file://lambda-exec-policy.json | jq -r ".Policy.Arn")
role_arn=$(aws iam create-role --role-name TwitteRSS-Lambda-Role --assume-role-policy-document file://assume-lambda-policy.json | jq -r ".Role.Arn")
aws iam attach-role-policy --role-name TwitteRSS-Lambda-Role --policy-arn ${policy_arn}

# Create the Lambda function
function_arn=$(aws lambda create-function --function-name TwitteRSS-Function --runtime python3.6 --handler twitterss.twitterss_handler --zip-file fileb://build.zip --role ${role_arn} --timeout 30 | jq -r ".FunctionArn")

# Create the scheduling (every five minutes)
rule_arn=$(aws events put-rule --name TwitteRSS-Lambda-Trigger --schedule-expression 'rate(5 minutes)' | jq -r ".RuleArn")  
aws lambda add-permission --function-name TwitteRSS-Function --statement-id TwitteRSS-Lambda-Demo --action lambda:InvokeFunction --principal events.amazonaws.com --source-arn ${rule_arn}
aws events put-targets --rule TwitteRSS-Lambda-Trigger --targets "Id"="1","Arn"="${function_arn}"

# Test the new function - should return DONE
aws lambda invoke --function-name TwitteRSS-Function output.log && cat output.log

# Look for the RSS feed filenames in S3
aws s3api list-objects --bucket <REPLACE_WITH_BUCKET_NAME> | jq ".Contents[].Key"
```

Troubleshooting Lambda can be difficult, so if you have any problems, it's best to go into the console and run tests from there and/or look at the Cloudwatch logs for any errors.

### Making updates
To rebuild and redeploy your package after making any config adjustments:
```bash
(cd packages; zip -r9 ../build.zip .); zip -g build.zip twitterss.py config.json
aws lambda update-function-code --function-name TwitteRSS-Function --zip-file fileb://build.zip
aws lambda invoke --function-name TwitteRSS-Function test.log && cat test.log
```

## Add the feeds to your RSS reader
At this point, you'll have an RSS feed (or multiple if you configured multiple in your config file) stored in your S3 bucket.  The filenames are all output to Cloudwatch, so you could go into there to get the full URLs or you can just assemble it yourself like this:

`https://s3.amazonaws.com/` + `<bucket_name>/` + `<folder_name>/` + `<object_key>`

You can also get a list of the objects with this command:

```bash
aws s3api list-objects --bucket <REPLACE_WITH_BUCKET_NAME> | jq ".Contents[].Key"
```

## Features

Mainly, this package will:
* Check the specified Twitter lists for new tweets
* Filter to exclude or require any combination of: retweets, quotes, and media.
* Create an RSS feed based on those tweets
* Supports creating multiple feeds based upon multiple lists

### Areas for Improvement

There are probably more things than this, but at least the following could use some work:
* Only request tweets that are new since the last run
* De-duplicate across all feeds

## Contributing

Pull requests are welcomed - let's make this project better!


## Licensing

The code in this project is licensed under GNU GPLv3.
