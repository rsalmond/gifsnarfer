from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker,relationship, backref
from sqlalchemy import create_engine, DateTime, Column, Integer, String, ForeignKey
from datetime import datetime as dt
from urlparse import urlparse
from cStringIO import StringIO
import requests
import md5

engine = create_engine('sqlite:///test.db')
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
    used_on  = Column(DateTime, default=dt.utcnow())

    def __init__(self, title, usage_url, gif_url):
        if Usage.exists(usage_url):
            raise ValueError('Usage already exists!')

        self.title = title
        self.url = usage_url
        self.url_hash = md5.new(self.url).hexdigest()
        self.process_gif(gif_url)
        self.save()

    @classmethod
    def get_all_by_gif(cls, gif):
        """ every use has one gif url but every gif can have more than one url """
        return session.query(cls).join(GifUrl).filter(cls.gif_url_id==GifUrl.id).join(Gif).filter(GifUrl.gif_id==gif.id).all()

    @classmethod
    def exists(cls, url):
        return session.query(cls).filter(cls.url_hash==md5.new(url).hexdigest()).count() > 0

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
                    # because fuck you GIF87a 
                    if chunk[0:6] == 'GIF89a':
                        check_header = False
                    else:
                        raise ValueError('File at this URL is not a GIF!')

                buf.write(chunk)
            # record the URL for this usage of the gif
            self.gif_url = GifUrl(url=url)
            # associate this usage with a (new or existing) gif record by the checksum of the gif found at the url
            self.gif = Gif.get_by_md5(md5sum=md5.new(buf.getvalue()).hexdigest())
            # add an entry to gif_urls table and associate it with the gif record 
            self.gif.urls.append(self.gif_url)

    def _safe_url(self, url):
        """ try to be clever about getting an image url """
        parsed = urlparse(url)
        if 'imgur.com' in parsed.netloc:
            if '.' in parsed.path:
                split = parsed.path.split('.')
                # imgur .gifv urls are just html witha flash webm player, so fall back to .gif
                if split[1] == '.gifv':
                    newpath = split[0]
                    return parsed.scheme + parsed.netloc + newpath + '.gif'
                else:
                    return url
            else:
                # handle links to imgur viewer pages http://imgur.com/lfL0UvH
                return  parsed.geturl() + '.gif'
        else:
            return url
