
from functools import wraps
import re
from dependencies.instagram import InstagramAPI, InstagramAPIError, InstagramClientError
import time
import collections
import plistlib
from dependencies import simplejson as json
import os


class HandleAPIErrors(object):
    """Handle errors of type InstagramAPIErrors"""
    
    
    def __init__(self, my_api):
        self.api = my_api
        
    def handle_error(self, err):
        """General handler of InstagramAPIErrors"""
        if err.error_type in self.instagram_api_errors:
            handler = self.instagram_api_errors[err.error_type]
            return handler(self, err)
        else:
            raise err
            
    def handle_privacy_error(self, err):
        """The requested resource is from a private user"""
        raise err
        
    def handle_rate_limited(self, err):
        """Exceeded the limit of requests per hour. If the offending api is the secondary api then try to create a new one. There is only one primary api, another onecannot be created"""
        last_used_api = self.api.last_used_api        
        last_used_api.is_good = False
        self.api.api_calls_remaining[self.api.secondary_idx] = 0
        if last_used_api is self.api.primary_api:
            # Only one primary api, cant get a new one
            raise err
        else:  # last used api is secondary api
            self.api.secondary_api = self.api.secondary_api_gen.next()
            if self.api.secondary_api:
                # Change last_used_api to reference the new secondary_api
                self.api.last_used_api = self.api.secondary_api
                return 0
            else:
                raise err
                
    def handle_not_found(self, err):
        """The requested resource was not found on the Instagram servers"""
        raise err
        
    def handle_insufficient_scope(self, err):
        """Tried to use an api without suffiecient scope (e.g. likes, comments, relationships)"""
        match = re.search('scope=(?P<scope>\w+)', err.error_message)
        required_scope = match.groupdict()['scope']
        raise err
        
    def handle_invalid_token(self, err):
        """Access token is not valid"""
        self.api.last_used_api.is_good = False
        err.error_message = 'Invalid token: {}'.format(self.api.last_used_api.access_token)
        raise err
        
    def handle_invalid_parameters(self, err):
        """Parameters used invalid"""
        raise err
                
    instagram_api_errors = {
        'APINotAllowedError':           handle_privacy_error,
        'Rate limited':                 handle_rate_limited,
        'APINotFoundError':             handle_not_found,
        'OAuthPermissionsException':    handle_insufficient_scope,
        'OAuthAccessTokenException':    handle_invalid_token,
        'APIInvalidParametersError':    handle_invalid_parameters
    }
        
######################################################################
###################   InstagramAPI Decorators    #####################
######################################################################
    
class api_type(object):
    
    def __init__(self, data_type, access_type):
        self.data_type = data_type
        self.access_type = access_type
            
    def __call__(self, f):
        @wraps(f)
        def wrapped_f(outer_self, *args, **kwargs):
            # Cast arguments to required type
            try: 
                kwargs.update({'max_timestamp': int(kwargs.pop('max_timestamp', None))})
                kwargs.update({'min_timestamp': int(kwargs.pop('min_timestamp', None))})
            except:
                # If argument is NoneType the cast to int will cause an exception. Leave argument as None
                pass  
            if not kwargs.has_key('api'):
                self.data_id = self.get_data_id(*args, **kwargs)
                if self.data_id == 'self':
                    api = outer_self.primary_api
                elif self.access_type == 'personal':
                    api = outer_self.primary_api
                elif self.access_type == 'private':
                    api = self.exchange_data_id_for_api(outer_self)
                elif self.access_type == 'public':
                    if outer_self.secondary_api:
                        api = outer_self.secondary_api
                    else:
                        api = outer_self.primary_api
                else:
                    raise ValueError('Unknown access_type: {}'.format(access_type))
            else:
                api = kwargs.pop('api')
            outer_self.last_used_api = api
            
            # Iterate over function until successful or unrecoverable failure
            result = None
            while outer_self.primary_api.is_good: # and outer_self.secondary_api.is_good:
                try:
                    result = f(outer_self, *args, **kwargs)
                except InstagramAPIError as err:
                    outer_self.api_error_handler.handle_error(err)
                else:
                    break
            outer_self.update_api()
            return result
        return wrapped_f
                               
    def get_data_id(self, *args, **kwargs):
        """Return data (e.g. user_id) for a given data type (e.g. user)"""
        # If there are args the data_id (e.g. user_id, media_id) should be the first positional argument
        if self.data_type == 'search':
            return None
        elif args:
            return args[0]
        elif kwargs:
            if self.data_type == 'media':
                return kwargs['media_id']
            elif self.data_type == 'user':
                return kwargs['user_id']
       
    def exchange_data_id_for_api(self, outer_self):
        if self.data_type == 'media':
            matches = re.match('\d+_(?P<user_id>\d+)', self.data_id)
            if matches:
                user_id = matches.groupdict()['user_id']
        elif self.data_type == 'user':
            user_id = self.data_id
        else:
            raise ValueError('Unknown data_type: {}'.format(self.data_type))

        if user_id in outer_self.primary_follows:
            return outer_self.primary_api
        else:
            for idx, follows in enumerate(outer_self.secondary_follows):
                if user_id in follows:
                    return outer_self.secondary_apis[idx]
            # If not a follow in primary or any secondary apis return a secondary_api
            if outer_self.secondary_api:
                return outer_self.secondary_api
            else:
                return outer_self.primary_api
            
            
class MyInstagramAPI(object):
    """InstagramAPI wrapper, allows for multiple access tokens"""

    # primary_access_token = '1977306979.6104a3c.d49ec03bfe484e46a7be8f35bcd997ed'
    # secondary_access_tokens = ['1593955519.6104a3c.91152da00e96457eb5abad054d45b0af',
    #             '1699042.6104a3c.834088edd4a6474e8d28fdf8bb1ab58b']
    client_secret = '16cf9a1467b740d295631397e17512e5'
    
    def __init__(self):
        # Get the access tokens saved in settings.json file
        info = plistlib.readPlist('info.plist')
        bundleid = info['bundleid']
        settings_path = os.path.join(
                os.path.expanduser('~/Library/Application Support/Alfred 2/Workflow Data/'),
                bundleid,
                'settings.json')
        with open(settings_path, 'rb') as settings_file:
            settings = json.load(settings_file)
        primary_access_token = settings.get('primary_access_token', None)
        secondary_access_tokens = settings.get('secondary_access_tokens', [])

        # Do not initialize without a primary_access_token
        if primary_access_token:

            self._num_secondary_tokens = len(secondary_access_tokens)
            self.api_calls_remaining = [None for i in range(self._num_secondary_tokens)]
            self.api_last_call = [None for i in range(self._num_secondary_tokens)]
            # Instantiate primary api
            self.primary_api = InstagramAPI(access_token=primary_access_token, 
                                            client_secret=MyInstagramAPI.client_secret)
            # Instantiate secondary api's
            self.secondary_apis = []
            for secondary_token in secondary_access_tokens:
                self.secondary_apis.append( InstagramAPI(access_token=secondary_token,
                                                    client_secret=MyInstagramAPI.client_secret) )
            self.test_api(self.primary_api)
            self.primary_follows = self.get_primary_follows()
            self.secondary_idx = -1  # Will be incremented to 0 in new_secondary_api
            self.secondary_api_gen = self.new_secondary_api()
            self.secondary_api = self.secondary_api_gen.next()
            self.secondary_follows = self.get_secondary_follows()
            self.api_error_handler = HandleAPIErrors(self)
            self.last_used_api = None
        
         
    ######################################################################
    ###################   InstagramAPI Wrappers    #######################
    ######################################################################
    
    @api_type('search', 'public')    
    def media_popular(self, *args, **kwargs):
        """Return currently popular media.
        (up to count=64)
        
        Accepts parameters:
            count, max_id
        """
        return self.last_used_api.media_popular(*args, **kwargs)
                    
    @api_type('search', 'public')
    def media_search(self, lat, lng, *args, **kwargs):
        """Return recent media matching a search query and optionally a location
        
        Accepts parameters:
            lat, lng, min_timestamp, max_timestamp, distance, count
        """
        return self.last_used_api.media_search(lat, lng, *args, **kwargs)
        
            
    @api_type('media', 'public')
    def media_shortcode(self, shortcode, *args, **kwargs):
        """Return a media using its corresponding shortcode
        
        Accepts parameter:
            shortcode
        """
        return self.last_used_api.media_shortcode(shortcode)
                       
    @api_type('media', 'private')            
    def media_likes(self, media_id, *args, **kwargs):
        """Return a list of likes for a media given its media_id
        
        Accepts parameter:
            media_id
        """
        return self.last_used_api.media_likes(media_id)
                
    @api_type('media', 'personal')
    def like_media(self, media_id, *args, **kwargs):
        """Submit a like to an Instagram post given its media_id
        
        Accepts parameter:
            media_id
        """
        return self.last_used_api.like_media(media_id)
                        
    @api_type('media', 'personal')            
    def unlike_media(self, media_id, *args, **kwargs):
        """Remove a like from an Instagram post
        
        Accepts parameter:
            media_id
        """
        return self.last_used_api.unlike_media(media_id)
                        
    @api_type('media', 'personal')            
    def create_media_comment(self, media_id, text, *args, **kwargs):
        """Post a comment to an Instagram photo given its media_id
        
        Accepts parameters:
            media_id, text
        """
        return self.last_used_api.create_media_comment(media_id, text)
                                
    @api_type('media', 'personal')
    def delete_comment(self, media_id, comment_id, *args, **kwargs):
        """Delete a comment from an Instagram photo given its media_id and comment_id
        
        Accepts parameters:
            media_id, comment_id
        """
        return self.last_used_api.delete_comment(media_id, comment_id)
                                
    @api_type('media', 'private')                    
    def media_comments(self, media_id, *args, **kwargs):
        """Return comments on an Instagram post given its media_id
        
        Accepts parameter:
            media_id
        """
        return self.last_used_api.media_comments(media_id)
            
    @api_type('media', 'private')
    def media(self, media_id, *args, **kwargs):
        """Return the information about a single instagram post given its media_id
        
        Accepts parameters:
            media_id
        """
        return self.last_used_api.media(media_id)
        
    @api_type('search', 'personal')
    def user_media_feed(self, *args, **kwargs):
        """Return a list of most recent media from user's followers
        
        Accepts parameters:
            max_id, min_id, count
        Paginates: True
        """
        return self.last_used_api.user_media_feed(*args, **kwargs)
    
    @api_type('search', 'personal')
    def user_liked_media(self, *args, **kwargs):
        """Return media liked by self
        
        Accepts parameters:
            max_like_id, count
        Paginates: True
        """
        return self.last_used_api.user_liked_media(*args, **kwargs)
    
    @api_type('user', 'private')
    def user_recent_media(self, user_id, *args, **kwargs):
        """Return recent media of another user given their user_id
        
        Accepts parameters:
            user_id, max_id, min_id, count, max_timestamp, min_timestamp
        Paginates: True
        """
        return self.last_used_api.user_recent_media(user_id, *args, **kwargs)
        
    @api_type('search', 'public')
    def user_search(self, q, *args, **kwargs):
        """Search for a user by username
        
        Accepts parameters:
            q, count
        """
        return self.last_used_api.user_search(q, *args, **kwargs)
    
    @api_type('user', 'private')
    def user_follows(self, user_id, *args, **kwargs):
        """Return the 50 most recent follows of a user as well as a pagination url
        
        Accepts parameter:
            user_id
        Paginates: True
        """
        return self.last_used_api.user_follows(user_id, **kwargs)
        
    @api_type('user', 'private')                    
    def user_followed_by(self, user_id, *args, **kwargs):
        """Get the users that follow a particular user given their user_id
        
        Accepts parameters:
            user_id
        Paginates: True
        """
        return self.last_used_api.user_followed_by(user_id, **kwargs)
    
    @api_type('user', 'private')
    def user(self, user_id, *args, **kwargs):
        """Return user object given user_id
        
        Accepts parameter:
            user_id
        """
        return self.last_used_api.user(user_id)
        
    @api_type('search', 'public')
    def location_recent_media(self, location_id, *args, **kwargs):
        """Get a list of recent media objects from a given locaiton given its location_id
        Accepts parameters:
            location_id, max_id, min_id, min_timestamp, max_timestamp
        Paginates: True
        """
        return self.last_used_api.location_recent_media(location_id, *args, **kwargs)
    
    @api_type('search', 'public')
    def location_search(self, *args, **kwargs):
        """
        Search for a location by geographic coordinates or foursquare id
        
        Accepts parameters:
            lat, lng, foursquare_v2_id, distance
        Required parameters:
            (lat AND lng) OR foursquare_v2_id
        """
        return self.last_used_api.location_search(*args, **kwargs)
    
    @api_type('search', 'public')    
    def location(self, location_id, *args, **kwargs):
        """
        Get information about a location given its location_id
        
        Accepts parameters:
            location_id
        Required parameters:
            location_id
        """
        return self.last_used_api.location(location_id)
        
    @api_type('search', 'personal')    
    def geography_recent_media(self, geography_id, *args, **kwargs):
        """
        Get recent media from a geography subscription that you created
        
        Accepts parameters:
            geography_id, min_id, count
        Required parameters:
            geography_id
        Paginates: True
        """
        return self.last_used_api.geography_recent_media(geography_id, *args, **kwargs)
    
    @api_type('search', 'public')  
    def tag_recent_media(self, tag_name, *args, **kwargs):
        """
        Get recent media by tag
        
        Accepts parameters:
            tag_name, count, max_tag_id, min_tag_id
        Required parameters:
            tag_name
        Paginates: True
        """
        return self.last_used_api.tag_recent_media(tag_name, *args, **kwargs)
        
    @api_type('search', 'public')    
    def tag_search(self, q, *args, **kwargs):
        """
        Search for tags by name (without a leading '#')
        
        Accepts parameters:
            q
        Required parameters:
            q
        """
        return self.last_used_api.tag_search(q)
    
    @api_type('search', 'public')    
    def tag(self, tag_name, *args, **kwargs):
        """
        Get information about a tag (without leading '#')
        
        Accepts parameters:
            tag_name
        Required parameters:
            tag_name
        """
        return self.last_used_api.tag(tag_name)
        
    @api_type('search', 'personal')    
    def user_incoming_requests(self, *args, **kwargs):
        """
        Get incoming requests
        
        Accepts parameters:
            None
        Required parameters:
            None
        """
        return self.last_used_api.user_incoming_requests()
    
    @api_type('user', 'personal')    
    def user_relationship(self, user_id, *args, **kwargs):
        """
        Get the status of a relationship with another user
        
        Accepts parameters:
            user_id
        Required parameters:
            user_id
        """
        return self.last_used_api.user_relationship(user_id)
        
    @api_type('user', 'personal')    
    def change_user_relationship(self, user_id, action, *args, **kwargs):
        """
        Modify a relationship with another user.
        Possible actions are follow, unfollow, approve, ignore, block, unblock
        
        Accepts parameters:
            user_id, action
            action={follow, unfollow, approve, ignore, block, unblock}
        Required paramters:
            user_id, action
        """
        return self.last_used_api.change_user_relationship(user_id, action)
    
    ############# Change user relationship action shortcuts ##############
    
    def _make_relationship_shortcut(action):
        def _inner(self, *args, **kwargs):
            if args:
                user_id = args[0]
            else:
                user_id = kwargs.pop('user_id')
            return self.change_user_relationship(user_id=user_id, action=action)
        return _inner
        
    follow_user = _make_relationship_shortcut('follow')
    unfollow_user = _make_relationship_shortcut('unfollow')
    block_user = _make_relationship_shortcut('block')
    unblock_user = _make_relationship_shortcut('unblock')
    approve_user_request = _make_relationship_shortcut('approve')
    ignore_user_request = _make_relationship_shortcut('ignore')  
    
    
    ######################################################################
    ################   Instagram Generator Wrappers    ###################
    ######################################################################
    
    def _make_paginator(func, results_per_page, max_pages, **outer_kwargs):
        def _paginator_wrapper(self, *args, **kwargs):
            maximum_pages = kwargs.pop('max_pages', None) or max_pages
            params = {'as_generator': True,
                      'max_pages': maximum_pages}
            kwargs.update(params)
            kwargs.update(outer_kwargs)
            # Initialize update message
            message_template = kwargs.pop('message_template', None)
            update_after_pages = kwargs.pop('update_after_pages', None)
            if message_template:
                message_gen = self.print_update_message(
                                        maximum_pages, 
                                        update_after_pages=update_after_pages)
                message_gen.send(None)
            
            func_gen = func(self, *args, **kwargs)
            content = []
            pages_read = 0
            while True:
                try:
                    # Iterate over function until successful or unrecoverable failure
                    while self.primary_api.is_good: # and self.secondary_api.is_good:
                        try:
                            content_chunk, _ = func_gen.next()
                        except InstagramAPIError as err:
                            self.api_error_handler.handle_error(err)
                        else:
                            break
                    self.update_api()
                except StopIteration:
                    # Print final update message
                    if message_template:
                        # Set pages_read to max_pages and it will force the message to print
                        message_gen.send( (max_pages, content_len, message_template) )
                    break
                else:
                    content += content_chunk
                    content_len = len(content)
                    pages_read += 1
                    if message_template:
                        message_gen.send( (pages_read, content_len, message_template) )

            return content
        
        doc = "Return muliple pages of content from api function: {}\n\n".format(func.__name__)
        doc += "Results per page:{}\n".format(results_per_page)
        doc += "Default max_pages: {}\n".format(max_pages)
        _paginator_wrapper.__doc__ = doc
        return _paginator_wrapper
        
    def print_update_message(self, max_pages, update_interval=5, update_after_pages=None):
        """Display updates of the information every 5 seconds"""          
        start = time.time()
        interval_start = start
        previous_content_len = None        
        if update_after_pages:
            # Send a debug update message after a certain number of pages are read
            while True:
                (pages_read, content_len, message_template) = yield
                now = time.time()
                interval = now - interval_start
                do_not_reprint = (True if (content_len == previous_content_len) 
                                       else False)
                if not do_not_reprint and ( 
                        (pages_read % update_after_pages == 0) or 
                        (pages_read == max_pages) ):
                    previous_content_len = content_len
                    print message_template.format(
                        running_time='{0:0.2f}'.format(now-start),
                        len_content=content_len)
        
        else:
            # Send an update message after a time interval
            while True:
                (idx, message_template) = yield       
                now = time.time()
                interval = now - interval_start
    
                if interval > update_interval or \
                            interval_start is start or \
                            (idx + 1) == list_length:
                    print message_template.substitute(running_time='{0:0.2f}'.\
                                                    format(now-start))
                    interval_start = now
    
    api_results_per_page = {
        'user_liked_media': 20,
        'user_recent_media': 20,
        'user_media_feed': 20,
        'user_follows': 50,
        'user_followed_by': 50,
        'location_recent_media': 20,
        'geography_recent_media': 20,
        'tag_recent_media': 20
    }
    
    all_user_liked_media = _make_paginator(
            func = user_liked_media,
            results_per_page = api_results_per_page['user_liked_media'],
            max_pages = 10)
            
    all_user_recent_media = _make_paginator(
            func = user_recent_media,
            results_per_page = api_results_per_page['user_recent_media'],
            max_pages = 10,
            update_after_pages = 5)
    
    all_user_media_feed = _make_paginator(
            func = user_media_feed, 
            results_per_page = api_results_per_page['user_media_feed'], 
            max_pages = 3)
                
    all_user_follows = _make_paginator(
            func = user_follows, 
            results_per_page = api_results_per_page['user_follows'], 
            max_pages = 20)
    
    all_user_followed_by = _make_paginator(
            func = user_followed_by,
            results_per_page = api_results_per_page['user_followed_by'],
            max_pages = 20)
    
    all_location_recent_media = _make_paginator(
            func = location_recent_media,
            results_per_page = api_results_per_page['location_recent_media'],
            max_pages = 10)
            
    all_geography_recent_media = _make_paginator(
            func = geography_recent_media,
            results_per_page = api_results_per_page['geography_recent_media'],
            max_pages = 10)
            
    all_tag_recent_media = _make_paginator(
            func = tag_recent_media,
            results_per_page = api_results_per_page['tag_recent_media'],
            max_pages = 5)
                 
    
    ######################################################################
    ######################   Convenience Methods    ######################
    ######################################################################
    
    def get_primary_follows(self):
        """Get follows of the primary account"""
        params = {'as_generator': True, 'max_pages': 50}
        follows_gen = self.primary_api.user_follows('self', **params)
        primary_follows = []
        for follows_chunk, url in follows_gen:
            primary_follows += follows_chunk
        return UserSet(primary_follows)

    def get_secondary_follows(self):
        """Get the follows of the secondary accounts"""
        num_secondary_accounts = len(self.secondary_apis)
        secondary_follows = [None for i in range(num_secondary_accounts)]
        for idx in range(num_secondary_accounts):
            follows = self.all_user_follows('self', max_pages=50, api=self.secondary_apis[idx])
            secondary_follows[idx] = UserSet(follows)
        return secondary_follows
    
    ######################################################################
    ######################   Instance Methods    #########################
    ######################################################################
    
    def new_secondary_api(self):
        
        num_secondary_tokens = len(self.secondary_apis)
        hour = 60*60
        new_api = False
        while 1:
            while 2:
                for i in range(num_secondary_tokens):          
                    self.secondary_idx = (self.secondary_idx + 1) % num_secondary_tokens           
                    num_remaining = self.api_calls_remaining[self.secondary_idx]
                    last_call = self.api_last_call[self.secondary_idx]          
                    if (num_remaining == None) or (num_remaining >= 1000):
                        new_api = True
                        # break for loop through secondary access tokens
                        break  
                    elif time.time() - last_call >= hour:
                        new_api = True
                        # break for loop through secondary access tokens
                        break  
                if new_api:
                    secondary_api = self.secondary_apis[self.secondary_idx]
                    # Test api
                    user_self = self.test_api(secondary_api)
                    if user_self:
                        yield secondary_api
                        # break (while 2), enter final statements of (while 1)
                        break
                    else:
                        # continue (while 2) through secondary access tokens
                        continue         
                else:  # No new api found
                    yield False
            # Re-enter (while 2)

    
    def test_api(self, api):
        try: 
            user = api.user('self')
        except InstagramAPIError as err:
            api.is_good = False
            return False
        else:
            api.is_good = True
            self.update_api(api)
            return user
               
    def update_api(self, api=None):
        if not api:
            api = self.last_used_api
        if api is self.primary_api:
            self.primary_api.api_last_call = time.time()
        else:  # api is secondary_api
            calls_remaining = api.x_ratelimit_remaining
            if calls_remaining is not None:
                self.api_calls_remaining[self.secondary_idx] = int(calls_remaining)
            self.api_last_call[self.secondary_idx] = time.time()
        
    def api_for_media(self, media):
        if media.user.id in self.primary_follows: 
            return self.primary_api
        else: 
            return self.secondary_api

            
            

class UserSet(collections.Set):
    def __init__(self, initvalue=()):
        self._theset = set()
        for x in initvalue: 
            self.add(x)
    def add(self, user):
        self._theset.add(user)
    
    def __contains__(self, user):
        username = None
        user_id = None
        if isinstance(user, (str, unicode)):
            if user.isdigit():
                user_id = user  # A user_id was sent directly in for comparison
            else:
                username = user  # A username was sent directly for comparison
        else:
            user_id = user.id  # A User object is being compared
        # Check username or user_id for membership in set
        if username:
            if username in [u.username for u in self._theset]:
                return True
            else:
                return False
        elif user_id:
            if user_id in [u.id for u in self._theset]: 
                return True
            else: 
                return False
        
    def __iter__(self):
        return self._theset.__iter__()
        
    def __len__(self):
        return len(self._theset)
        
    def __repr__(self):
        return repr(self._theset)