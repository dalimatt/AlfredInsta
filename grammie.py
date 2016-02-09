# coding: utf-8

from __future__ import print_function
from favorites import Favorites
from sys import stderr
from dependencies.workflow import web
from dependencies.workflow import ICON_ERROR
from urllib import urlopen
from os.path import isfile, getmtime
import os
from time import time
import random
import requests
import shutil
from dependencies.instagram import models
from dependencies.instagram.bind import InstagramAPIError

HOME = os.environ['HOME']

CACHE_DIR = HOME + '/Library/Caches/com.runningwithcrayons.Alfred-2/Workflow Data/com.dalimatt.Instastalk'
DATA_DIR = HOME + '/Library/Application Support/Alfred 2/Workflow Data/com.dalimatt.Instastalk'
CLIENT_SECRET = '16cf9a1467b740d295631397e17512e5'
FROM_CACHE = 0
HOUR = 60*60
DAY = 24*HOUR

SEARCH = 0
LOAD_USER = 1
FAVORITES = 2
ADD_FAV = 3
REMOVE_FAV = 4
COMMANDS = ['Search', 'Load_User', 'Favorites', 'Add_Fav', 'Remove_Fav']


    
class EmptySearchError(Exception):
    def __init__(self, query):
        self.query = query

    def __str__(self):
            return u'Search for "{0}" returned no results'.format(self.query)
        
        
class AlfredItems(object):
    
    def __init__(self, wf, previous_selected_unicode_value=None, name='special_info'):
        self.wf = wf  # Alfred-Workflow instance
        self.log = self.wf.logger
        self.name = name
        self.special_unicode_value = self.non_printing_unicode_characters(previous_selected_unicode_value)
        self.special_info = self.special_item_info()
        self.special_info.send(None)
        
    @staticmethod     
    def non_printing_univals(exclude=None):   
        x = range(0x80,0x85)
        x.extend(range(0x86,0xA0))    
        if exclude:
            try:
                x.remove(exclude)
            except ValueError as err:
                self.log('non_printing_univals: ' + err)   
        return x
        
    def non_printing_unicode_characters(self, exclude_unival=None):   
        special_chars = self.non_printing_univals(exclude_unival)
        for char in special_chars:
            yield char
        
    def special_item_info(self):    
        special = {}   
        try:
            while True:
                data = yield
                special.update(data)
        finally:
            if special != {}:
                self.wf.cache_data(self.name, special)


class Grammie(object):


        
    def dict2info(self, user_dict):
        """Decode info from dictionary into instance variables"""
        
        for k, v in user_dict.iteritems():
            setattr(self, k, v)
                
    def info2dict(self):
        """Encode important attribute information to dictionary for caching"""
        
        attributes = self.__dict__
        r = dict()
        for key in attributes.keys():
            match = re.match('^[a-z][_a-z]*$', key)
            if match:
                r[key] = attributes[key]
        if r == {}:
            return None
        else:
            return r
        
    def __init__(self, wf, user_id, username, command=None, update=True, age_info=HOUR):
        self._wf = wf
        self.log = self._wf.logger
        self.type = None
        self.user_id = user_id
        self.username = username
        self._search_file = os.path.join( 'user_info', u'{id}_search'.format(id=self.user_id) )
        self._info_file = os.path.join( 'user_info', u'{id}_info'.format(id=self.user_id) )
        self._url_file = os.path.join('profile_photos', 'pic_urls', u'{0}_picurl'.format(self.user_id))
        # self.access_token = wf.settings['access_token']
        self._command_on_select = command
        self._api = wf.api
        if update:
            self.update_info(age_info)
        
       
    
    def cache_item_data(self):
        """Add information needed to load an alfred item if the user selects 
        it from the list of alfred items. In particular the command, such as 
        LOAD_USER, or ADD_FAV, and information specific to the item such as 
        the user_id"""
        special_unicode_value = self._wf.alfred_items.special_unicode_value.next()
        data = {special_unicode_value: (self._command_on_select,
                                          {'user_id': self.user_id,
                                           'username': self.username}) }
        self._wf.alfred_items.special_info.send(data)
        return special_unicode_value
         
    def display_info(self):
        self.log.debug(u'display_info: {id}: {name}: type:{type}'.format(
                id=self.user_id, name=self.username, type=self.type))
        if self._command_on_select:
            valid = False
            special_unicode_value = self.cache_item_data()
            autocomplete = unichr(special_unicode_value)
        else:
            valid = True
            autocomplete = self.user_id
        if self.type == 'public':
            webUrl = 'http://iconosquare.com/viewer.php#/user/'
            item = self._wf.add_item(title=u'{username} ({media} photos)'.format(
                                    username=self.username,  
                                    media = str(self.counts['media'])), 
                        subtitle=u'{name}: {bio}'.format(
                                name=self.full_name, bio=self.bio),
                        copytext=self.user_id,
                        valid=valid,
                        autocomplete=autocomplete,
                        arg=webUrl + self.user_id + '/',
                        icon=self.get_pic()
                        )
        elif self.type == 'private':
            webUrl = 'http://instagram.com/'
            item = self._wf.add_item(title=self.username, 
                        valid=valid,
                        copytext=self.user_id,
                        autocomplete=autocomplete,
                        arg=webUrl + self.username, 
                        icon=self.get_pic()
                        )
        elif self.type ==  'unknown':
            if self._command_on_select == REMOVE_FAV:
                item = self._wf.add_item(title=u'Deleted account, username changed, or you\'ve been blocked',
                            subtitle=u'Remove {username} from favorites'.format(username=self.username),
                            valid=False,
                            autocomplete=autocomplete,
                            icon=ICON_ERROR
                            )
            else:
                item = self._wf.add_item(title=u'User: {user}'.format(user=self.username),
                            subtitle=u'Deleted account, username changed, or you\'ve been blocked',
                            valid=False,
                            copytext=self.user_id,
                            icon=ICON_ERROR
                            )
        else:
            item = self._wf.add_item(u'{uname}: {id}.'.format(
                                uname=self.username, id=self.user_id)
                            )
            
        
    def update_info(self, max_age=1):
        """Get basic user info from cache or from web if stale"""
    
        # Make the directory where user information stored
        user_info_dir = os.path.join(self._wf.cachedir, 'user_info')
        if not os.path.exists(user_info_dir):
            os.makedirs(user_info_dir)
            
        # First try to get basic info (from cache if under maxAge)
        user = self._wf.cached_data(self._info_file, 
                                    self.info_basic_web, 
                                    max_age=max_age)
        if not user:
        # Else try to get info from search (from cache if under maxAge)
            user = self._wf.cached_data(self._search_file, 
                                        self.info_search_web, 
                                        max_age=max_age)
        # Check for positive result, user_dict is None if no matching username
        if not user:
            self.type = 'unknown'
            # If user is a favorite, ask to remove from favorites
            favs = Favorites(self._wf)
            if favs.is_a_favorite(self.user_id):
                self._command_on_select = REMOVE_FAV
            else:
                self._command_on_select = None
        else:  
            # Set attributes for everything in the dictionary  
            for k, v in user.iteritems():
                setattr(self, k, v)
    
    def info_basic_web(self):
        """Retrieve basic information of Instagram user from user_id"""
        
        try:
            user = self._api.user(self.user_id)
            user = user.dictionary_from_object()
            user.update({'type': 'public'})
        except InstagramAPIError as err:
            if err.error_type == 'APINotAllowedError':
                user = None  # User is private, nothing to be done
            elif err.error_type == 'APINotFoundError':
                user = None  # User may no longer exist
            else:
                raise err
        return user

    def info_search_web(self):
        """Get info about user through an exact username search"""
        
        users = self._api.user_search(self.username, count=20)
        if users != []:
            for match in users:
                if match.username == self.username:
                    match = match.dictionary_from_object()
                    match.update({'type': 'private'})
                    return match
        else: return None
      
    def get_pic(self):
        """Return file path of user's profile photo"""
        
        # Retrieve user photo if old or nonexistent
        pic_dir = os.path.join(self._wf.cachedir, 'profile_photos')
        if not os.path.exists(pic_dir):
            os.makedirs(pic_dir)
        pic_path = os.path.join(pic_dir, '{user}.jpg'.format(user=self.username))
        exists_pic = isfile(pic_path)
        
        # Compare pic url from saved picture to the current one
        url_dir = os.path.join(self._wf.cachedir, 'profile_photos', 'pic_urls')
        if not os.path.exists(url_dir):
            os.makedirs(url_dir)
        old_url = self._wf.cached_data(self._url_file, max_age=FROM_CACHE)
        new_url = self.profile_picture
        if old_url != new_url:
            self.log.debug(u'Downloading picture for username: {0}'.format(self.username))
            
            start = time()
            response = requests.get(new_url, stream=True)
            with open(pic_path, 'wb') as out_file:
                # response.raw.decode_content = True
                shutil.copyfileobj(response.raw, out_file)
            del response
            end = time()
            self.log.debug(u'Download of jpg for {0} took {1:0.2f} seconds'.\
                                format(self.username, end-start))           
            # Save url
            self._wf.cache_data(self._url_file, new_url)
        elif not exists_pic:
            new_pic = urlopen(new_url).read()
            with open(pic_path, 'wb') as pic_file:
                pic_file.write(new_pic)

        return pic_path
        

        
