from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker,relationship, backref
from sqlalchemy import create_engine, DateTime, Column, Integer, String, ForeignKey
from datetime import datetime as dt
from urlparse import urlparse
from cStringIO import StringIO

import logging
logger = logging.getLogger(__name__)

import oboe
import requests
import md5
import os

engine = create_engine('sqlite:///{}/test.db'.format(os.path.dirname(os.path.realpath(__file__))))
DBSession = sessionmaker(bind=engine)
session = DBSession()
Base = declarative_base()

class ModelBase(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True)

    @classmethod
    def by_id(cls, id):
        return session.query(cls).filter_by(id=id).first()

    @classmethod
    def all(cls):
        return session.query(cls).all()

    @classmethod
    def count(cls):
        return session.query(cls).count()

    def save(self):
        session.add(self)
        session.commit()

class Gif(ModelBase):
    __tablename__ = 'gifs'

    md5sum = Column(String(32), unique=True)
    firstseen_on = Column(DateTime, default = dt.utcnow())
    urls = relationship('GifUrl', backref='gif')

    def __init__(self, md5sum):
        self.md5sum = md5sum
        self.save()

    @classmethod
    def get_by_md5(cls, md5sum):
        existing_gif = session.query(Gif).filter(Gif.md5sum==md5sum).first()
        return Gif(md5sum=md5sum) if existing_gif is None else existing_gif

class GifUrl(ModelBase):
    __tablename__ = 'gif_urls'

    url = Column(String)
    url_hash = Column(String(32), unique=True)

    gif_id = Column(Integer, ForeignKey('gifs.id'))
    usage = relationship('Usage', uselist=False, backref='gif_url')

    def __init__(self, url):
        self.url = url
        self.url_hash = md5.new(self.url).hexdigest()
        self.save()

    @classmethod
    def get(cls, url):
        existing_url = session.query(cls).filter(cls.url_hash==md5.new(url).hexdigest()).first()
        return GifUrl(url=url) if existing_url is None else existing_url

    @classmethod
    def get_by_gif_id(cls, id):
        return session.query(cls).filter(cls.gif_id==id)
   
    @classmethod
    def exists(cls, url):
        return session.query(cls).filter(cls.url_hash==md5.new(url).hexdigest()).count() > 0

class Usage(ModelBase):
    __tablename__ = 'uses'

    gif_url_id = Column(Integer, ForeignKey('gif_urls.id'))

    url = Column(String, nullable=False)
    url_hash = Column(String(32), unique=True, nullable=False)
    title = Column(String, nullable=False)
    upvotes = Column(Integer, nullable=False)
    author = Column(String(32), nullable=False)
    used_on  = Column(DateTime, default=dt.utcnow())

    def __init__(self, title=None, usage_url=None, gif_url=None, upvotes=None, author=None):
        previous_usage = Usage.get_by_url(usage_url)
        if previous_usage is not None:
            if upvotes != previous_usage.upvotes:
                logger.debug('Usage already recorded, updating new upvote count.')
                previous_usage.upvotes = upvotes
                previous_usage.save()
                return
            else:
                logger.debug('Usage already recorded, skipping.')
                return

        self.title = title
        self.url = usage_url
        self.upvotes = upvotes
        self.author = author
        self.url_hash = md5.new(self.url).hexdigest()
        self.process_gif(gif_url)
        if hasattr(self, 'gif'):
            # if we successfully found or created a new gif record associated with this Usage, save it
            self.save()

    @classmethod
    def get_all_by_gif(cls, gif):
        """ every use has one gif url but every gif can have more than one url """
        return session.query(cls).join(GifUrl).filter(cls.gif_url_id==GifUrl.id).join(Gif).filter(GifUrl.gif_id==gif.id).all()

    @classmethod
    def exists(cls, url):
        return session.query(cls).filter(cls.url_hash==md5.new(url).hexdigest()).count() > 0

    @classmethod
    def get_by_url(cls, url):
        return session.query(cls).filter(cls.url_hash==md5.new(url).hexdigest()).first()

    @oboe.log_method('process_gif')
    def process_gif(self, url):
        """ retrive gif from db or dload it and create a new record of it """
        if GifUrl.exists(url):
            self.gif = GifUrl.get(url).gif
        else:
            req = requests.get(self._safe_url(url), stream=True)
            check_header = True
            buf = StringIO()

            for chunk in req.iter_content(chunk_size=1024):
                if check_header:
                    if chunk[0:6] in  ('GIF89a', 'GIF87a'):
                        check_header = False
                    else:
                        logger.debug('File at this URL is not a GIF, skipping.')
                        return

                buf.write(chunk)

            # record the URL for this usage of the gif
            self.gif_url = GifUrl(url=url)
            # associate this usage with a (new or existing) gif record by the checksum of the gif found at the url
            self.gif = Gif.get_by_md5(md5sum=md5.new(buf.getvalue()).hexdigest())
            # add an entry to gif_urls table and associate it with the gif record 
            self.gif.urls.append(self.gif_url)

    @classmethod
    def _safe_url(self, url):
        """ try to be clever about getting an image url """
        parsed = urlparse(url)
        if 'imgur.com' in parsed.netloc:
            if '.' in parsed.path:
                split = parsed.path.split('.')
                # imgur .gifv urls are just html with a flash webm player so fall back to .gif
                if split[1] == 'gifv':
                    newpath = split[0]
                    return '{}://{}{}.gif'.format(parsed.scheme, parsed.netloc, newpath)
                else:
                    return url
            else:
                # handle links to imgur viewer pages http://imgur.com/lfL0UvH
                return  parsed.geturl() + '.gif'
        else:
            return url
