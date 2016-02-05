# coding: utf-8

"""Track an instagram users followers/follows and what posts they like"""

from __future__ import print_function
import sys
from dependencies.workflow import Workflow, web, manager
from dependencies.workflow import ICON_WARNING, ICON_GROUP, ICON_INFO, ICON_FAVORITE
from dependencies.workflow import background
from favorites import Favorites
from grammie import AlfredItems, Grammie
from dependencies.instagram.client import InstagramAPI
from dependencies.instagram import models
from dependencies.instagram.bind import InstagramAPIError
import string
import os
from my_instagram_api import MyInstagramAPI
import scratch
import time
from datetime import datetime, timedelta
import dependencies.simplejson as json

# System icons
ICON_ROOT = '/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources'
ICON_SEARCH = os.path.join(ICON_ROOT, 'MagnifyingGlassIcon.icns')
ICON_RECENT = os.path.join(ICON_ROOT, 'SidebarRecents.icns')
ICON_PICTURE = os.path.join(ICON_ROOT, 'ClippingPicture.icns')
ICON_BACK = os.path.join(ICON_ROOT, 'BackwardArrowIcon.icns')
ICON_TRASH = os.path.join(ICON_ROOT, 'TrashIcon.icns')

# ACCESS_TOKEN = '1977306979.6104a3c.3aa88e8cc84f4229a79a64c0f1d7ec33'
FROM_CACHE = 0  # To access cached data regardless of age use value of 0
HOUR = 60*60
LOCAL_URL = 'http://localhost:8515'
NUM_UNICODE_CHARS = 30  # Number of non-printing unicode values minus 1
# Instagram API configuration
CONFIG = {
    'client_id': '6104a3c347304a54909d5dc8b7253c36',
    'client_secret': '16cf9a1467b740d295631397e17512e5',
    'redirect_uri': 'http://localhost:8515/oauth_callback'
}

# Actionable commands
SEARCH = 0
LOAD_USER = 1
FAVORITES = 2
ADD_FAV = 3
REMOVE_FAV = 4
TEST = 5
CHECK_FOLLOWS = 6
MAKE_FAVORITE = 7
GET_LIKES = 8
CACHED_LIKES = 9
RECENT_LIKES = 10
CHECK_FOLLOWED_BY = 11
RECENT_MEDIA = 12
# Text value of commands used for debugging
COMMANDS = ['Search', 'Load_User', 'Favorites', 'Add_Fav', 
            'Remove_Fav', 'Test', 'Check_Follows', 'Make_favorite',
            'Get_likes', 'Cached_likes', 'Recent_likes',
            'Check_followed_by', 'Recent_media']

_wf = None
global api

def wf():
    global _wf
    if _wf is None:
        _wf = Workflow()
    return _wf

######################################################################
##################### Main workflow functions ########################
######################################################################  
            
def search_users(query):
    """Search for a user by username"""
    users = api.user_search(query, count=16)
    for user in users:
        guser = Grammie(wf(), user.id, user.username, command=MAKE_FAVORITE, update=False)
        guser.type = 'private'
        guser.profile_picture = user.profile_picture
        guser.full_name = user.full_name
        guser.display_info()
        
def add_or_remove_favorite(user_id, username):
    """Page to display basic user information and ask to add as a favorite"""
    # Display user
    user = Grammie(wf(), user_id, username, age_info=1)
    user.display_info()
    
    # Ask to add or remove as a favorite
    make_add_or_remove_favorite_item(user_id, username)

def load_favorites():
    """Display favorite users"""   
    max_age_fav = HOUR
    favs = Favorites(wf())
    fav_users = favs.get_favorites()
    if fav_users is not None:
        fav_ids = sorted(fav_users, key=fav_users.get)
        for fav_id in fav_ids:
            fav_username = fav_users[fav_id]
            fav = Grammie(wf(), fav_id, fav_username, command=LOAD_USER, age_info=max_age_fav)
            # Update the cached value of a favorite in case the username changes
            favs.update_info(fav_id, fav.username)          
            fav.display_info()
        # Save favorites to cache
        favs.cache_favs()
    else:
        # No stored favorites, prompt user to add some
        wf().add_item('Add users as favorites to see them here')
              
def load_user(user_id, username):
    """Display details for a particular user"""
    # Get informaiton about user from instagram api
    user_info = get_user_info(user_id)
     
    # Display user
    user = Grammie(wf(), user_id, username, age_info=1)
    user.display_info()
    
    # Items to display only if there is user information
    if user_info:
        # Display item to show recent media
        special_unicode_value = prepare_item_with_command(RECENT_MEDIA, user_id, username)
        wf().add_item( title='Recent media ({media} total media)'.format(media=user_info['media_count']),
                       autocomplete=unichr(special_unicode_value),
                       icon=ICON_PICTURE )
        
        # Display item to search for recent likes
        special_unicode_value = prepare_item_with_command(RECENT_LIKES, user_id, username)
        if background.is_running(user_id + '.get_likes'):
            subtitle = '...Now searching for media liked by {user}'.format(user=username)
        else:
            subtitle = ''
        wf().add_item( title='Recent liked media',
                       subtitle=subtitle,
                       autocomplete=unichr(special_unicode_value),
                       icon=ICON_FAVORITE )
        
        # Display item to check new and removed follows
        special_unicode_value = prepare_item_with_command(CHECK_FOLLOWS, user_id, username)
        # Find age of data
        follow_data_path = os.path.join(wf().followdir, user_id + '_follows.json')
        follow_data_age = get_age_cached_data(follow_data_path)
        if follow_data_age != '':
            subtitle = 'Age of data: {age}'.format(age=follow_data_age)
        else:
            subtitle = ''
        wf().add_item( title='New and removed follows ({follows} current follows)'.format(follows=user_info['follows']),
                       subtitle=subtitle,
                       autocomplete=unichr(special_unicode_value),
                       icon=ICON_GROUP )
                       
        # Display item to check for new and removed users following our user
        special_unicode_value = prepare_item_with_command(CHECK_FOLLOWED_BY, user_id, username)
        # Find age of data
        followers_data_path = os.path.join(wf().followdir, user_id + '_followed_by.json')
        followers_data_age = get_age_cached_data(followers_data_path)
        if followers_data_age != '':
            subtitle = 'Age of data: {age}'.format(age=followers_data_age)
        else:
            subtitle = ''
        wf().add_item( title='New and removed followers ({followers} current followers)'.format(followers=user_info['followers']),
                       subtitle=subtitle,
                       autocomplete=unichr(special_unicode_value),
                       icon=ICON_GROUP )
    
    # Ask to add or remove as a favorite
    make_add_or_remove_favorite_item(user_id, username)
    
def recent_media(user_id, username):
    """Retrieve and display recent media"""
    # Make a go back item
    special_unicode_value = prepare_item_with_command(LOAD_USER, user_id, username)
    wf().add_item( title='Go back',
                   valid=False,
                   autocomplete=unichr(special_unicode_value),
                   icon=ICON_BACK)
                   
    # Get recent media information
    media = scratch.user_media(user_id, max_pages=1)
    needed_media_ids = [m.id for m in media]
    thumbnail_dir = os.path.join(wf().mediadir, user_id)
    if not os.path.exists(thumbnail_dir):
        os.makedirs(thumbnail_dir)
    # Get list of thumbnails already downloaded
    dir_contents = os.listdir(thumbnail_dir)
    have_media_ids = [thumb.split('.')[0] for thumb in dir_contents]
    # Download thumbnails not already available
    wanting_media_ids = list( set(needed_media_ids) - set(have_media_ids) )
    wanting_media = [m for m in media if m.id in wanting_media_ids]
    scratch.download_images(wanting_media, thumbnail_dir, resolution='thumbnail')
    display_media(media, media_dir=thumbnail_dir)

def recent_likes(user_id, username):
    """Prompt to search to get recent likes or open cached likes"""
    # Make a go back item
    special_unicode_value = prepare_item_with_command(LOAD_USER, user_id, username)
    wf().add_item( title='Go back',
                   valid=False,
                   autocomplete=unichr(special_unicode_value),
                   icon=ICON_BACK)
                   
    # Check if there is an ongoing search for this user's likes
    process_alias = user_id + '.get_likes'
    if background.is_running(process_alias):
        # Add alfred item informing that a search is underway
        wf().add_item( title='...A search is currently ongoing',
                       icon=ICON_SEARCH)
    else:
        # Prompt to search to get recent likes
        special_unicode_value = prepare_item_with_command(GET_LIKES, user_id, username)
        wf().add_item( title=u'Search for recently liked media from user\'s follows'.format(user=username),
                       subtitle=u'Search may take approximately 1 to 10 minutes',
                       valid=False,
                       autocomplete=unichr(special_unicode_value),
                       icon=ICON_SEARCH)
    
    # Open cached version of recent likes if one exists
    # Check if likes directory exists
    if not os.path.exists(wf().likesdir):
        os.makedirs(wf().likesdir)
    # Check if directory for user exists in likes directory
    user_likes_path = os.path.join(wf().likesdir, user_id + '.json')
    # Check if cached version exists
    if os.path.exists(user_likes_path):
        # Get the age of the cached data
        age_data = get_age_cached_data(user_likes_path)
        
        # Display an alfred item to open the cached likes
        # Find number of likes
        with open(user_likes_path, 'r') as likes_file:
            likes_dict = json.load(likes_file)
        num_likes = len(likes_dict)
        special_unicode_value = prepare_item_with_command(CACHED_LIKES, user_id, username)
        wf().add_item( title=u'{num_likes} recent likes found'.format(num_likes=num_likes),
                       subtitle=u'Age of data: {age}'.format(age=age_data),
                       valid=False,
                       autocomplete=unichr(special_unicode_value),
                       icon=ICON_RECENT)

def cached_likes(user_id, username):
    """Display cached likes"""
    # Make a go back item
    special_unicode_value = prepare_item_with_command(RECENT_LIKES, user_id, username)
    wf().add_item( title='Go back',
                   valid=False,
                   autocomplete=unichr(special_unicode_value),
                   icon=ICON_BACK)
                   
    # Retrieve the liked media that is cached
    user_likes_path = os.path.join(wf().likesdir, user_id + '.json')
    with open(user_likes_path, 'r') as likes_file:
        likes = json.load(likes_file)
    # Convert dictionary to media objects
    likes = [models.Media.object_from_dictionary(m) for m in likes]
    
    # Display likes
    if len(likes):
        display_media(likes, wf().mediadir)
    else:
        # No recent likes to display
        wf().add_item( title='No recent likes found')
       
def check_user_follows(user_id, username):
    """Compare current follows of user to stored version"""
    max_items = 15
    # Make a go back item
    special_unicode_value = prepare_item_with_command(LOAD_USER, user_id, username)
    wf().add_item( title='Go back',
                   valid=False,
                   autocomplete=unichr(special_unicode_value),
                   icon=ICON_BACK)
                   
    follow_data_dir = os.path.join(wf().datadir, 'follow_data')
    result = scratch.compare_new_follows(user_id, data_dir=follow_data_dir)
    if result:  # if result is None there wasnt any stored data
        new_follows, removed_follows = result
        if len(new_follows)==0:
            wf().add_item(title=u'No new users followed by {user}'.format(user=username),
                          icon=ICON_INFO)
        else:
            wf().add_item(title=u'{user} started following {follows} users:'.\
                            format(user=username, follows=len(new_follows)),
                          icon=ICON_GROUP)            
            for follow in new_follows[:max_items]:
                user = Grammie(wf(), follow.id, follow.username, age_info=HOUR)
                user.display_info()
        if len(removed_follows)==0:
            wf().add_item(title=u'No users unfollowed by {user}'.format(user=username),
                          icon=ICON_INFO)
        else:
            wf().add_item(title=u'{user} unfollowed by {unfollows} users:'.\
                            format(user=username, unfollows=len(removed_follows)),
                          icon=ICON_GROUP)
            for follow in removed_follows[:max_items]:
                user = Grammie(wf(), follow.id, follow.username, age_info=HOUR)
                user.display_info()
    else:
        # No stored data
        wf().add_item(u'No information previously stored for {}'.format(username))
        
def check_user_followed_by(user_id, username):
    """Compare current followers of user to stored version"""
    max_items = 15  # Alfred is limited to the number of items it can display
    # Make a go back item
    special_unicode_value = prepare_item_with_command(LOAD_USER, user_id, username)
    wf().add_item( title='Go back',
                   valid=False,
                   autocomplete=unichr(special_unicode_value),
                   icon=ICON_BACK)
                   
    follow_data_dir = os.path.join(wf().datadir, 'follow_data')
    result = scratch.compare_new_followed_by(user_id, data_dir=follow_data_dir)
    if result:  # if result is None there wasnt any stored data
        new_followers, removed_followers = result
        if len(new_followers)==0:
            wf().add_item(title=u'No new users following {user}'.format(user=username),
                          icon=ICON_INFO)
        else:
            wf().add_item(title=u'{user} has {followers} new followers:'.\
                            format(user=username, followers=len(new_followers)),
                          icon=ICON_GROUP)            
            for follow in new_followers[:max_items]:
                user = Grammie(wf(), follow.id, follow.username, age_info=HOUR)
                user.display_info()
        if len(removed_followers)==0:
            wf().add_item(title=u'No users unfollowed {user}'.format(user=username),
                          icon=ICON_INFO)
        else:
            wf().add_item(title=u'{user} was unfollowed by {unfollows} users:'.\
                            format(user=username, unfollows=len(removed_followers)),
                          icon=ICON_GROUP)
            for follow in removed_followers[:max_items]:
                user = Grammie(wf(), follow.id, follow.username, age_info=HOUR)
                user.display_info()
    else:
        # No stored data
        wf().add_item(u'No information previsously stored for {}'.format(username))
        
######################################################################
########################## Main function #############################
######################################################################
    
def main(wf):
    global api
    api = MyInstagramAPI()
    
    # Check settings for access_token
    settings = wf.settings
    if 'access_token' not in settings.keys():
        unauthorized_api = InstagramAPI(**CONFIG)
        scope = ['comments', 'likes', 'relationships']
        authorize_url = unauthorized_api.get_authorize_url(scope=None)
        args = ['/usr/bin/python', wf.workflowfile('instagram_connect.py')]
        if background.is_running('connect'):
            log.debug('Process `connect` is already running')
        else:
            background.run_in_background('connect', args, timeout=120)
                                  
        wf.add_item('Connect your instagram account', valid=True,
                    arg=authorize_url)
    else:
        data = None
        command = None
        # Get query passed from Alfred
        if len(wf.args):
            query = wf.args[0]
            log.debug(u'Query: <{0}>, len(query) = {1}'.format(query, len(query)))
            
            # An empty query means the script is being run for the first time
            if query == '': # or query == ' ':
                command = FAVORITES
            
            else:
                firstchar = query[0]
                unival = ord(firstchar)
                if unival in AlfredItems.non_printing_univals():
                    log.debug('Found special unicode! value={0}'.format(unival))
                    # We have a special character key from autocomplete of previous script
                    # Check for cached information in 'info', if there is none the info has most likely already been processed
                    info = wf.cached_data('special_info', max_age=FROM_CACHE)
                    if info and len(query) == 1:
                        # The query passed from Alfred should contain a special, non-printing, unicode character whose ordinal is the key for the cached info dict
                        command, data = info[unival]                       
                        # Cache value to exclude it from next time script is run. Alfred will not rerun the script if the autocomplete value is the same as before
                        wf.cache_data('unival',unival)
                
                        log.debug(u'COMMAND={0}'.format(COMMANDS[command]))
                    
                    elif len(query) == 1:
                        command = FAVORITES   
                    
                    else:
                        # Info has already been processed and deleted and an additional query has been added
                        command = SEARCH
                        query = query[1:]
                
                else:
                    command = SEARCH
        
        # Initialize generators for special info
        # First find previously chosen unival to exclude it from new range
        previous_unival = wf.cached_data('unival', max_age=FROM_CACHE)
        if previous_unival:
            wf.alfred_items = AlfredItems(wf, previous_unival)
            os.unlink(wf.cachefile('unival.cpickle'))
        else:
            wf.alfred_items = AlfredItems(wf)
        if data:
            # If user scrolls through alfred history the previous command and data may be recovered if reissued here. The previous unicode value is excluded from new data that is issued so there is no conflict of items using the same unicode value
            old_data = {previous_unival: (command, data) }
            wf.alfred_items.special_info.send(old_data)
            
                          
        log.debug('Final COMMAND:{0}'.format(COMMANDS[command]))    
        # Execute command
        if command is LOAD_USER:
            load_user(data['user_id'], data['username'])
        elif command is FAVORITES:
            load_favorites()
        elif command is ADD_FAV:
            add_favorite(data['user_id'], data['username'])
        elif command is REMOVE_FAV:
            remove_favorite(data['user_id'], data['username'])
            load_favorites()
        elif command is SEARCH:
            search_users(query)
        elif command is CHECK_FOLLOWS:
            check_user_follows(data['user_id'], data['username'])
        elif command is MAKE_FAVORITE:
            add_or_remove_favorite(data['user_id'], data['username'])
        elif command is GET_LIKES:
            user_id = data['user_id']
            process_alias = user_id + '.get_likes'
            args = ['/usr/bin/python', wf.workflowfile('get_recent_likes.py'),
                    user_id, wf.likesdir, wf.mediadir]
            if background.is_running(process_alias):
                log.debug('Process `{alias}` is already running'.format(alias=process_alias))
            else:
                background.run_in_background(process_alias, args)
            load_user(data['user_id'], data['username'])
            
        elif command is RECENT_LIKES:
            recent_likes(data['user_id'], data['username'])
        elif command is CACHED_LIKES:
            cached_likes(data['user_id'], data['username'])
        elif command is CHECK_FOLLOWED_BY:
            check_user_followed_by(data['user_id'], data['username'])
        elif command is RECENT_MEDIA:
            recent_media(data['user_id'], data['username'])
        else:
            # Bad command
            log.debug(u'Received unknown command=<{0}>'.format(str(command)))
        # Write the item data to a file so the item the user selected determines how the script is run next
        wf.alfred_items.special_info.close()
    # Send XML formatted result to Alred
    wf.send_feedback()
    
######################################################################
######################## Helper functions ############################
######################################################################

def add_favorite(user_id, username):
    """Add a user to favorites"""
    # Add favorite to dictionary
    favs = Favorites(wf())
    favs.add(user_id, username)
    # Reload user
    load_user(user_id, username)
    
def remove_favorite(user_id, username):
    """Remove a user from favorites"""   
    # Remove favorite from dictionary
    favs = Favorites(wf())
    favs.remove(user_id)
    
def make_add_or_remove_favorite_item(user_id, username):
    """Create an alfred item to add or remove a user from favorites"""
    # Add item depending on if this user is a favorite
    favs = Favorites(wf())
    favUsers = favs.get_favorites()
    special_unicode_value = wf().alfred_items.special_unicode_value.next()
    command = None
    if favUsers is not None:
        if user_id in favUsers:
            wf().add_item( title=u'Remove from favorites',
                           autocomplete=unichr(special_unicode_value),
                           icon=ICON_TRASH)
            command = REMOVE_FAV
        else:
            wf().add_item(title=u'Add to favorites',
                        autocomplete=unichr(special_unicode_value))
            command = ADD_FAV
    # Else user is not a favorite because the 'favorites' file doesnt exist
    else:
        wf().add_item(title=u'Create a favorite',
                    autocomplete=unichr(new_unival))
        command = ADD_FAV
    # Update special info
    data = {special_unicode_value: (command, {'user_id': user_id, 'username': username})}
    wf().alfred_items.special_info.send(data)

def display_media(media, media_dir, download_thumbnails=False):
    """Display a thumbnail, username, and caption for each media as an Alfred item"""
    # Download thumbnail images of liked media
    if download_thumbnails:
        scratch.download_images(media, wf().mediadir, resolution='thumbnail')
    # Create an alfred item for each like
    for m in media:
        media_url = m.images['thumbnail'].url
        filetype = media_url.split('.')[-1]
        # Check if image exists
        thumbnail_path = os.path.join( wf().mediadir, '{id}.{type}'.format(id=m.id, type=filetype) )
        if not os.path.exists(thumbnail_path):
            # Download the media
            scratch.download_images([m], wf().mediadir, resolution='thumbnail')
        try:
            # Caption might be null
            caption = m.caption.text.replace('\n', '\t')
        except:
            caption = ''
        wf().add_item( title=u'User: {user}'.format(user=m.user.username),
                       subtitle=u'Caption: {caption}'.format(caption=caption),
                       valid=True,
                       arg=m.link,
                       icon=thumbnail_path)

def get_recent_likes(user_id):
    """Find recently liked media"""
    # Find recent likes
    likes = scratch.stalk_likes_in_follows(user_id)
    likes = likes[0:NUM_UNICODE_CHARS]  # Only process up to first 30 items
    # Convert likes to a saveable format
    likes = [models.media.dictionary_from_object(u) for u in likes]
    # Save the liked media
    user_likes_dir = os.path.join(wf().likesdir, user_id + '.json')
    with open(user_likes_dir, 'wb') as likes_file:
        likes_file.write(json.dumps(likes))
    # Download the media
    scratch.download_images(likes, wf().mediadir, resolution='thumbnail')

def get_age_cached_data(file_path):
    if not os.path.exists(file_path):
        return u''
    else:  
        current_time = int(time.time())
        age_data_seconds = current_time - os.path.getmtime(file_path)
        age_data = timedelta(seconds=age_data_seconds)
        d = datetime(1,1,1) + age_data
        return '{days} days, {hours} hours, {minutes} minutes'.format(
                        days=d.day - 1, hours=d.hour, minutes=d.minute)
                    
def prepare_item_with_command(command, user_id, username):
    special_unicode_value = wf().alfred_items.special_unicode_value.next()
    data = {special_unicode_value: (command, {'user_id': user_id, 'username': username})}
    wf().alfred_items.special_info.send(data)
    return special_unicode_value

def get_user_info(user_id):
    try:
        user_info = scratch._api.user(user_id)
    except InstagramAPIError as err:
        if err.error_type == 'APINotAllowedError':
            user_info = None  # private user account
        elif err.error_type == 'APINotFoundError':
            user_info = None  # account not found, doesnt exist, or blocked
        else:
            raise err
    else:
        follows = user_info.counts['follows']
        followers = user_info.counts['followed_by']
        media_count = user_info.counts['media']
        user_info = dict(follows=follows, followers=followers, media_count=media_count)
    return user_info
                       
######################## End of functions ############################
  
if __name__ == '__main__':
    log = wf().logger
    wf().mediadir = os.path.join(wf().cachedir, 'media')
    wf().likesdir = os.path.join(wf().cachedir, 'likes')
    wf().followdir = os.path.join(wf().datadir, 'follow_data')
    wf().api = scratch._api
    sys.exit(wf().run(main))
