from models import  Gif, GifUrl, Usage, session, Base, engine
from urlparse import urlparse
import argparse
import os
import praw

__version__ = 0.1
user_agent = 'gifsnarfer/{}'.format(__version__)

def snarf_gifs():
    env_var = 'GIFSNARFER_SUBS'

    reddit = praw.Reddit(user_agent=user_agent)
    configured_subs = os.environ.get(env_var)

    if configured_subs is None:
        print 'Error: subreddit environment variable not found!'
        print 'eg. $ export {}=funny,gifs,...'.format(env_var)
        return
    else:
        subs = configured_subs.split(',')

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


def report_gifs():
    for gif in Gif.all():
        uses = Usage.get_all_by_gif(gif)
        if len(uses) > 1:
            for use in uses:
                print use.url, use.title, use.used_on

def main():
    parser = argparse.ArgumentParser(description='Snarf gifs found on the front page of your favourite subreddits.')
    parser.add_argument('--report', action='store_true', help='generate a report')
    parser.add_argument('--version', action='version', version=user_agent)
    args = parser.parse_args()

    if args.report:
        report_gifs()
    else:
        snarf_gifs()

if __name__ == '__main__':
    Base.metadata.create_all(engine)
    main()
