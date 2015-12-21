import logging
from logging.config import fileConfig
import os

fileConfig('{}/logging.ini'.format(os.path.dirname(os.path.realpath(__file__))))
logger = logging.getLogger(__name__)

from models import  Gif, GifUrl, Usage, session, Base, engine
from jinja2 import Environment, PackageLoader
from urlparse import urlparse
from pprint import pprint
import argparse
import praw
from oboeware.loader import load_inst_modules
import oboe

__version__ = 0.1
user_agent = 'gifsnarfer/{}'.format(__version__)
oboe.config['tracing_mode'] = 'always'
load_inst_modules()

def snarf_gifs():
    env_var = 'GIFSNARFER_SUBS'

    reddit = praw.Reddit(user_agent=user_agent)
    configured_subs = os.environ.get(env_var)

    logger.info('Starting to snarf!')

    if configured_subs is None:
        print 'Error: subreddit environment variable not found!'
        print 'eg. $ export {}=funny,gifs,...'.format(env_var)
        return
    else:
        subs = configured_subs.split(',')

    for sub in subs:
        for submission in reddit.get_subreddit(sub).get_hot(limit=25):
            oboe.start_trace('snarfer')

            parsed = urlparse(submission.url)
            # good chance of a gif in these two scenarios
            if 'imgur.com' in parsed.netloc  or parsed.path.endswith('.gif'):
                title = submission.title
                author = submission.author.name
                usage_url = submission.permalink
                gif_url = submission.url
                ups = submission.ups
                try:
                    Usage(title=title, usage_url=usage_url, gif_url=gif_url, upvotes=ups, author=author)
                except Exception as e:
                    logger.error(e)
                    oboe.log_exception()
                    continue

            oboe.end_trace('snarfer')

    logger.info('Snarf complete!')

def report_gifs(multi=False, count=False, html=False, dump_all=False):
    """ report gifs sorted by number of upvotes per use
     optionally filter to only gifs used multiple times """

    if count:
        print 'gifs: {}'.format(Gif.count())
        print 'gif urls: {}'.format(GifUrl.count())
        print 'uses: {}'.format(Usage.count())

    #TODO: iterate all uses in the last 24 hours
    #   - break down by subreddit
    #   - normalize per subreddit upvotes
    #   - return top gifs ranked by normalized upvote

    gifscores = [] 
    for gif in Gif.all():
        uses = Usage.get_all_by_gif(gif)
        use = uses[0]
        if use.recent():
            gifscores.append({
                'score_per_use': sum([use.upvotes for use in uses]) / len(uses),
                'uses': len(uses),
                'imgur_id': GifUrl.by_id(use.gif_url_id).get_imgur_id(),
                'url': GifUrl.by_id(use.gif_url_id).url })

    env = Environment(loader=PackageLoader(__name__, 'templates'))
    template = env.get_template('gif.html')
    gifs=sorted(gifscores, key=lambda k: k['score_per_use'], reverse=True)

    if not dump_all:
        gifs = gifs[:30]

    if html:
        print template.render(gifs=gifs)
    else:
        for gif in gifs:
            pprint(gif)

    #from pprint import pprint
    #for thing in sorted(gifscores, key=lambda k: k['score_per_use']):
    #    if multi:
    #        if thing['uses'] > 1:
    #            pprint(thing)
    #    else:
    #        pprint(thing)

def main():
    parser = argparse.ArgumentParser(description='Snarf gifs found on the front page of your favourite subreddits.')
    parser.add_argument('--report', action='store_true', help='generate a report')
    parser.add_argument('--html', action='store_true', help='produce html output')
    parser.add_argument('--all', action='store_true', help='report every gif in the db')
    parser.add_argument('--count', action='store_true', help='produce total count of records')
    parser.add_argument('--multi', action='store_true', help='report only gifs with multiple uses')
    parser.add_argument('--version', action='version', version=user_agent)
    args = parser.parse_args()

    if args.report:
        report_gifs(multi=args.multi, count=args.count, html=args.html, dump_all=args.all)
    else:
        snarf_gifs()

if __name__ == '__main__':
    Base.metadata.create_all(engine)
    main()
