import os
import urllib
import time
from dependencies.instagram import InstagramAPI, InstagramAPIError, InstagramClientError
from dependencies.instagram import models
from string import Template
import subprocess
from operator import attrgetter
from my_instagram_api import MyInstagramAPI, UserSet
import dependencies.simplejson as json
import datetime
from functools import wraps
import inspect


# Errors
from httplib2 import ServerNotFoundError

# Instagram API Errors

PRIVATE_USER = 'APINotAllowedError'
RATE_LIMITED = 'Rate limited'
INVALID_RESOURCE = 'APINotFoundError'
INSUFFICIENT_SCOPE = 'OAuthPermissionsException'
INVALID_TOKEN = 'OAuthAccessTokenException'
INVALID_PARAMETERS = 'APIInvalidParametersError'


# globals
global _api
global DEBUG
DEBUG = False
HOME = os.environ['HOME']
CACHE_DIR = HOME + '/Library/Caches/com.runningwithcrayons.Alfred-2/Workflow Data/com.dalimatt.Instastalk'
DATA_DIR = HOME + '/Library/Application Support/Alfred 2/Workflow Data/com.dalimatt.Instastalk'
    
# Instantiate the instagram api
_api = MyInstagramAPI()

######################################################################
################### Primary Instagram functions ######################
######################################################################


def media_of_users(users, min_timestamp=None, max_timestamp=None):
    """Get recent media of users followed by a particular user"""
    
    # Compute minimum UNIX timestamp, default is 7 days previous to current timestamp
    if not min_timestamp:
        DAY = 24*60*60    # seconds in a day
        now = int(time.time())
        min_timestamp = now - 7*DAY
    
    min_timestamp = int(min_timestamp)  # instagram needs ints
    max_timestamp = int(max_timestamp)   
    # Fetch the media of all the follows of the user within the prescribed timeframe
    total_media  = []
    for idx, user in enumerate(users):
        
        params = {'user_id': user.id,
            'max_timestamp': max_timestamp,
            'min_timestamp': min_timestamp
            }
        new_media = user_media(**params)
        # new_media should be -1 if the user is private and not accessible
        if new_media != -1:
            myprint('{0} of {1}. Got {2} media from user: {3}'.format(
                idx+1, len(users), len(new_media), user.username))
            if new_media:
                total_media += new_media
        else:
            myprint('{0} of {1}. User {2} is private.'.format(
                idx+1, len(users), user.username))
    
    # Return the media sorted from most recent to least
    return sorted(total_media, key=attrgetter('created_time'), reverse=True)


def user_media(user_id, verbose=False, max_pages=10, **kwargs):
    """Grab all media (up to *max_pages*) of a user"""
    try:
        user = _api.user(user_id=user_id)
    except InstagramAPIError as err:
        if err.error_type == PRIVATE_USER:
            return -1
        else:
            raise err
    media_per_page = _api.api_results_per_page['user_recent_media']
    total_media_count = user.counts['media']
    pages_required_for_all_media = int(total_media_count/media_per_page) + 1
    total_media_to_be_retrieved = min(total_media_count,
                                      max_pages * media_per_page)
    if verbose:
        message = 'Retrieved {{len_content}} media of {0} out of a total of {1}'.format(
                        total_media_to_be_retrieved,
                        total_media_count)
    else:
        message = None
    return _api.all_user_recent_media(
                user_id,
                max_pages=max_pages,
                message_template=message,
                **kwargs)


######################################################################
################## Secondary Instagram functions #####################
######################################################################


def liked_media(user_id, media):
    """Return the media that have been liked by *user_id*"""
    # Initialize update message generator
    update_message = print_update_message(len(media))
    update_message.send(None)
    myprint('Commencing search...')
    user_likes = []
    for idx, target_media in enumerate(media):
        try:
            likes = _api.media_likes(target_media.id)
        except InstagramClientError as err:
            repr(err)
            return likes
        except InstagramAPIError as err:
            if err.error_type == INVALID_RESOURCE:
                myprint('Invalid media: {}'.format(target_media.id))
            else:
                raise err
        else:
            like_set = UserSet(likes)
            if user_id in like_set:
                user_likes.append(target_media)
        message = Template('$running_time seconds. Found {0} likes. {1} media searched out of {2}, {3} api calls remaining'\
                    .format(len(user_likes),
                    idx+1,
                    len(media),
                    _api.last_used_api.x_ratelimit_remaining)
                  )
        update_message.send((idx, message))
    
    return user_likes


def media_comments(media, verbose=False):
    """Get comments of media"""
    # Initialize message generator
    if verbose:
        update_message = print_update_message(list_length=len(media), update_interval=5)
        update_message.send(None)
        myprint('Retrieving comments...')
    
    # Retrieve all comments
    all_comments = {}
    comments_total = 0
    for idx, medium in enumerate(media):
        comments = _api.media_comments(media_id = medium.id)
        comments_total += len(comments)
        all_comments.update({medium:comments})
        message = Template('$running_time seconds. Retrieved {0} comments from {1} media out of {2}. {3} api calls remaining'.format(
                            comments_total,
                            idx+1, len(media),
                            _api.last_used_api.x_ratelimit_remaining)
                        )
        if verbose:
            update_message.send( (idx, message) )
    return all_comments


def search_medium(search_queries, medium, ignore_likes=False):
    """Get all info about a media (comments, likes, tags, text) and search for a specific string"""
    results = [False for _ in range(len(search_queries))]
    comments = media_comments([medium])
    try:  # Catch resource not found exception
        if not ignore_likes: likes = _api.media_likes(medium.id)
        for idx, query in enumerate(search_queries):
            # Search users in photo
            for user_in_photo in medium.users_in_photo:
                if query in user_in_photo.user.username: results[idx] = True
            # Search comments
            for comment in comments[medium]:
                if query in comment.user.username or query in comment.text:
                    results[idx] = True
            # Search likes
            if not ignore_likes:
                for like in likes:
                    if query in like.username:
                        results[idx] = True
            # Search the caption
            if medium.caption:
                if query in medium.caption.text:
                    results[idx] = True
            # Search tags
            for tag in medium.tags:
                if query in tag.name:
                    results[idx] = True
    except InstagramAPIError as err:
        if err.error_type == INVALID_RESOURCE:
            return False
        else:
            raise err
    
    return results


def search_media(search_queries, media, ignore_likes=True):
    """Return a list of media matching a queary that searches for a match in the comments, likes, and tags in a list of media"""
    
    # Initialize update message
    update_message = print_update_message(len(media))
    update_message.send(None)
    # Initialize result data
    if type(search_queries) is not list: search_queries = [search_queries]
    matches = [ [] for _ in range(len(search_queries))]
    # Iterate through media looking for matches to search_queries
    for idx0, medium in enumerate(media):
        results = search_medium(search_queries, medium, ignore_likes=ignore_likes)
        for idx1, result in enumerate(results):
            if result:
                matches[idx1].append(medium)
        # Send update message
        message = Template(
        'Found {} matches in {} media out of {}. {} api calls remaining'.format(
                    repr([len(x) for x in matches]), idx0+1, len(media),
                    _api.last_used_api.x_ratelimit_remaining) )
        update_message.send( (idx0, message) )
    return matches


def user_commented(user_id, comments):
    """Check for a comment from a user given a list of comments"""
    user_comments = []
    media = []
    for medium in comments:
        media_comments = comments[medium]
        for comment in media_comments:
            if comment.user.id == user_id:
                user_comments.append(comment)
                media.append(medium)
    
    return (media, user_comments)


def users_in_media(user_ids, media):
    """Return a list of those media where a user is in the photo"""
    if type(user_ids) is not list: user_ids = [user_ids]
    return [m for m in media if any(
                    user_id in [u.user.id for u in m.users_in_photo]
                    for user_id in user_ids)]
 

######################################################################
########################## Stalk functions ###########################
######################################################################


def stalk_likes_in_follows(user_id, beginning_days_ago=3,
                           until_days_ago=0, filename=None):
    """Find likes of a user from the media of those they follow"""
    # Get all the media of follows within time range
    now = int(time.time())
    DAY = 24*60*60
    follows = _api.all_user_follows(user_id)
    params = {'users': follows,
            'min_timestamp': now - beginning_days_ago*DAY,
            'max_timestamp': now-until_days_ago*DAY}
    total_media = media_of_users(**params)
    # Check if the user in question has liked any of the media
    likes = liked_media(user_id, total_media)
    # write urls of liked media to file
    if filename:
        write_media_urls(likes, filename)
    
    return likes


def stalk_likes_of_user(liker_id, liked_id, **kwargs):
    """Has user liked any media of another particular user"""
    kwargs.setdefault('max_pages', 100)
    media = user_media(liked_id, verbose=True, **kwargs)
    if media != -1:
        likes = liked_media(liker_id, media)
        return likes
    else:
        return -1


def stalk_comments_of_user(commenter_id, commentee_id, max_pages=100):
    """Check if user commented on another users instagram"""
    media = user_media(user_id=commentee_id, verbose=True, max_pages=max_pages)
    comments = media_comments(media)
    media_ids, user_comments = user_commented(commenter_id, comments)
    
    return media_ids, user_comments
    

######################################################################
############### Compare current data to stored data ##################
######################################################################

class compare_follow_data(object):
    
    def __init__(self, follow_data_type):
        if follow_data_type == 'follows':
            self.follow_type = 'follows'
            self.instagram_api_function = _api.all_user_follows
        elif follow_data_type == 'followed_by':
            self.follow_type = 'followed_by'
            self.instagram_api_function = _api.all_user_followed_by
            
    def __call__(self, follow_function):
        @wraps(follow_function)
        def wrapped_follow_function(user_id, update_data=True, data_dir=None):
            if not data_dir:
                data_dir = os.path.join(HOME,'Documents', 'Instagram', 'user_data')
            # Call instagram api for follows of followed_by
            current_data = self.instagram_api_function(user_id, max_pages=500)
            # Retrieve stored version of data if exists
            stored_data_exists = False
            data_path = os.path.join(data_dir, user_id + '_{0}.json'.format(self.follow_type))
            if os.path.exists(data_path):
                with open(data_path, 'r') as data_file:
                    temp_user_data = json.load(data_file)
                    # Convert data to user objects
                    stored_data = [models.User.object_from_dictionary(u)
                                        for u in temp_user_data]
                    stored_data_exists = True
            # Update stored data to current version
            if update_data:
                # Make directory structure
                if not os.path.exists(data_dir):
                    os.makedirs(data_dir)
                with open(data_path, 'w') as data_file:
                    data_dict = [u.dictionary_from_object() for u in current_data]
                    data_file.write(json.dumps(data_dict))
            # Compare current and stored data (if stored version exists)
            if stored_data_exists:
                # Convert data objects to UserSets
                set_stored_data = UserSet(stored_data)
                set_current_data = UserSet(current_data)
                # Compare sets to find new and removed users
                new_users = set_current_data - set_stored_data
                removed_users = set_stored_data - set_current_data
                myprint( 'New {0}:'.format(self.follow_type).replace('_', ' ') )
                for u in new_users:
                    myprint('\t{0}'.format(u.username))
                myprint('Removed {0}:'.format(self.follow_type).replace('_', ' '))
                for u in removed_users:
                    myprint('\t{0}'.format(u.username))
                return (list(new_users), list(removed_users))
            else:
                myprint('No stored version of '.format(self.follow_type).replace('_',' '))
                return None
            if update_data: 
                myprint( 'Updated {0} data to current information'.\
                       format(self.follow_type).replace('_',' ') )
        
        return wrapped_follow_function
        
@compare_follow_data('follows')
def compare_new_follows(user_id, update_data=True):
    pass
    
@compare_follow_data('followed_by')
def compare_new_followed_by(user_id, update_data=True):
    pass
    
        
######################################################################
######################### Helper functions ###########################
######################################################################


def write_media_urls(media, path='/Desktop/urls.txt'):
    """Write urls of media to file"""
    urls = []
    media_url = 'http://iconosquare.com/viewer.php#/detail/'
    for medium in media:
        urls.append(media_url + medium.id)
    
    home = os.environ['HOME']
    with open(home + path, 'wb') as url_file:
        for url in urls:
            url_file.write(url + '\n')

def download_images(media, media_dir, resolution='standard_resolution'):
    """Download images of instagram media"""
    # Make the directory
    if not os.path.exists(media_dir):
        os.makedirs(media_dir)
        pass  # Directory already exists
    for m in media:
        media_url = m.images[resolution].url
        filetype = media_url.split('.')[-1]
        media_path = media_dir + '/' + m.id + '.' + filetype
        image = urllib.urlopen(media_url).read()
        with open(media_path, 'wb') as media_file:
            media_file.write(image)
        

def download_media_of_user(media, media_dir=None, resolution='standard_resolution'):
    """Download media of a user to drive"""
    media_urls = []
    for medium in media:
        media_id = medium.id
        media_url = ''
        try:
            media_url = medium.videos[resolution].url
        except:
            media_url = medium.images[resolution].url
        media_urls.append((media_id, media_url))
    
    if not media_dir:
        media_dir = os.path.join(HOME, 'Desktop', 'Downloaded Media')
    now = time.time()
    date = datetime.datetime.fromtimestamp(now).strftime('(%b%d_%Y)')
    username = media[0].user.username
    media_dir = media_dir + username + date
    # Check directory structure
    if not os.path.exists(media_dir):
        os.makedirs(media_dir)
    
    for media_id, media_url in media_urls:
        filetype = media_url.split('.')[-1]
        filename = media_id + '.' + filetype
        data = urllib.urlopen(media_url).read()
        with open( os.path.join(media_dir, filename), 'wb' ) as media_file:
            media_file.write(data)
        

def print_update_message(list_length, update_interval=5):
    # Display updates of the information every 5 seconds
    
    start = time.time()
    interval_start = start
    
    while True:
        (idx, message_template) = yield
        now = time.time()
        interval = now - interval_start
        
        if interval > update_interval or \
                    interval_start is start or \
                    (idx + 1) == list_length:
            myprint(message_template.substitute(running_time='{0:0.2f}'.\
                                            format(now-start)))
            interval_start = now


def open_media(media):
    """Create urls of media and open in webbrowser"""
    
    media_url = 'http://iconosquare.com/viewer.php#/detail/'
    if type(media) is list:
        for medium in media:
            url = media_url + medium.id
            subprocess.Popen(['open', url])
            time.sleep(2)
    else:
        url = media_url + media.id
        subprocess.Popen(['open', url])


######################################################################
######################## Utility functions ###########################
######################################################################

def myprint(the_string):
    if DEBUG: print the_string

if __name__ == '__main__':
    DEBUG = True
