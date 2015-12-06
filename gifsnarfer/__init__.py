from models import  Gif, Usage, Url, session, Base, engine
from urlparse import urlparse
import os
import praw

version = 0.1
user_agent = 'gifsnarfer/{}'.format(version)

if __name__ == '__main__':
    Base.metadata.create_all(engine)

    reddit = praw.Reddit(user_agent=user_agent)
    subs = os.environ.get('GIFSNARFER_SUBS').split(',')
    for sub in subs:
        for submission in reddit.get_subreddit(sub).get_hot():
            parsed = urlparse(submission.url)
            # good chance of a gif in these two scenarios
            if 'imgur.com' in parsed.netloc  or submission.url.endswith('.gif'):
                title = submission.title
                author = submission.author
                usage_url = submission.permalink
                gif_url = submission.url
                try:
                    Usage(title=title, usage_url=usage_url, gif_url=gif_url)
                except ValueError as e:
                    print e.message
                    print usage_url
