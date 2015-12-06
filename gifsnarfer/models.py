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

    def save(self):
        session.add(self)
        session.commit()

class Gif(ModelBase):
    __tablename__ = 'gifs'

    md5sum = Column(String(32), unique=True)
    firstseen_on = Column(DateTime, default = dt.utcnow())
    urls = relationship('Url', backref='gif')

    def __init__(self, md5sum):
        self.md5sum = md5sum
        #self.save()

    @classmethod
    def get_by_md5(cls, m5dsum):
        existing_gif = session.query(Gif).filter(Gif.m5dsum==md5sum).first()
        return Gif(md5sum=md5sum) if existing_gif is None else existing_gif

class Url(ModelBase):
    __tablename__ = 'urls'

    url = Column(String)
    url_hash = Column(String(32), unique=True)

    gif_id = Column(Integer, ForeignKey('gifs.id'))
    usage_id = Column(Integer, ForeignKey('uses.id'))

    def __init__(self, url):
        self.url = url
        self.url_hash = md5.new(self.url).hexdigest()
        #self.save()

    @classmethod
    def get(cls, url):
        existing_url = session.query(Url).filter(Url.url_hash==md5.new(url).hexdigest()).first()
        return Url(url=url) if existing_url is None else existing_url
    
    @classmethod
    def exists(cls, url):
        return session.query(Url).filter(Url.url_hash==md5.new(url).hexdigest()).count() > 0

class Usage(ModelBase):
    __tablename__ = 'uses'

    gif_url_id = Column(Integer, ForeignKey('urls.id'))
    gif_url = relationship(Url, primaryjoin=gif_url_id == Url.id)

    usage_url_id = Column(Integer, ForeignKey('urls.id'))
    usage_url = relationship(Url, primaryjoin=usage_url_id == Url.id)

    title = Column(String, nullable=False)
    used_on  = Column(DateTime, default=dt.utcnow())

    def __init__(self, title, usage_url, gif_url):
        if Url.exists(usage_url):
            raise ValueError('Usage already exists!')

        self.get_gif(gif_url)
        self.title = title
        self.usage_url = Url(usage_url)
        self.gif_url = Url.get(gif_url)
        self.save()

    def get_gif(self, url):
        """ retrive gif from db or dload it and create a new record of it """
        if Url.exists(url):
            self.gif = Url.get(url).gif
        else:
            req = requests.get(self._safe_url(url), stream=True)
            check_header = True
            buf = StringIO()

            for chunk in req.iter_content(chunk_size=1024):
                if check_header:
                    if chunk[0:6] == 'GIF89a':
                        check_header = False
                    else:
                        raise ValueError('File at this URL is not a GIF!')

                buf.write(chunk)
            
            self.gif = Gif(md5sum=md5.new(buf.getvalue()).hexdigest())
                    

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
