from .helper import timestamp_to_datetime, datetime_to_timestamp
from datetime import datetime
import six


class ApiModel(object):

    @classmethod
    def object_from_dictionary(cls, entry):
        # make dict keys all strings
        if entry is None:
            return ""
        entry_str_dict = dict([(str(key), value) for key, value in entry.items()])
        return cls(**entry_str_dict)
        
    def dictionary_from_object(self):
        return self.__dict__
        
    def __repr__(self):
        return str(self)
        # if six.PY2:
        #     return six.text_type(self).encode('utf8')
        # else:
        #     return self.encode('utf8')

    def __str__(self):
        if six.PY3:
            return self.__unicode__()
        else:
            return unicode(self).encode('utf-8')


class Image(ApiModel):

    def __init__(self, url, width, height):
        self.url = url
        self.height = height
        self.width = width

    def __unicode__(self):
        return "Image: %s" % self.url


class Video(Image):

    def __unicode__(self):
        return "Video: %s" % self.url


class Media(ApiModel):

    def __init__(self, id=None, **kwargs):
        self.id = id
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)

    def get_standard_resolution_url(self):
        if self.type == 'image':
            return self.images['standard_resolution'].url
        else:
            return self.videos['standard_resolution'].url

    def get_low_resolution_url(self):
        if self.type == 'image':
            return self.images['low_resolution'].url
        else:
            return self.videos['low_resolution'].url


    def get_thumbnail_url(self):
        return self.images['thumbnail'].url


    def __unicode__(self):
        return "Media: %s" % self.id

    @classmethod
    def object_from_dictionary(cls, entry):
        new_media = Media(id=entry['id'])
        new_media.type = entry['type']

        new_media.user = User.object_from_dictionary(entry['user'])

        new_media.images = {}
        for version, version_info in six.iteritems(entry['images']):
            new_media.images[version] = Image.object_from_dictionary(version_info)

        if new_media.type == 'video':
            new_media.videos = {}
            for version, version_info in six.iteritems(entry['videos']):
                new_media.videos[version] = Video.object_from_dictionary(version_info)

        if 'user_has_liked' in entry:
            new_media.user_has_liked = entry['user_has_liked']
        new_media.like_count = entry['likes']['count']
        new_media.likes = []
        if 'data' in entry['likes']:
            for like in entry['likes']['data']:
                new_media.likes.append(User.object_from_dictionary(like))

        new_media.comment_count = entry['comments']['count']
        new_media.comments = []
        for comment in entry['comments']['data']:
            new_media.comments.append(Comment.object_from_dictionary(comment))

        new_media.created_time = timestamp_to_datetime(entry['created_time'])

        if entry['location'] and 'id' in entry:
            new_media.location = Location.object_from_dictionary(entry['location'])

        new_media.caption = None
        if entry['caption']:
            new_media.caption = Comment.object_from_dictionary(entry['caption'])
        
        new_media.tags = []
        if entry['tags']:          
            for tag in entry['tags']:
                new_media.tags.append(Tag.object_from_dictionary({'name': tag}))

        new_media.link = entry['link']

        new_media.filter = entry.get('filter')
        

        if entry['users_in_photo']:
            new_media.users_in_photo = [UserInPhoto.object_from_dictionary(user_in_photo) 
                                                for user_in_photo in entry['users_in_photo']]
        else:
            new_media.users_in_photo = []
            
        return new_media
        
    def dictionary_from_object(self):
        exit_dict = {'id': self.id}
        exit_dict.update([('type', self.type)])
        exit_dict.update([('user', self.user.dictionary_from_object())])
        # Update dictionary with images information
        images_dict = {}
        for version, image in self.images.iteritems():
            images_dict[version] = image.dictionary_from_object()
        exit_dict.update([('images', images_dict)])
        # Update dictionary with 'video' attribute if it exists
        if self.type == 'video':
            videos_dict = {}
            for version, video in self.videos.iteritems():
                videos_dict[version] = video.dictionary_from_object()
            exit_dict.update([('videos', videos_dict)])
        # Update dictionary with 'user_has_liked' attribute if it exists
        liked = getattr(self, 'user_has_liked', False)
        exit_dict.update([('user_has_liked', liked)])
        # Create likes dictionary
        likes_data = []
        for like in self.likes:
            likes_data.append(like.dictionary_from_object())
        likes_dict = {'count': self.like_count, 'data': likes_data}
        exit_dict.update([('likes', likes_dict)])
        # Create comments dictionary
        comment_data = []
        for comment in self.comments:
            comment_data.append(comment.dictionary_from_object())
        comment_dict = {'count': self.comment_count, 'data': comment_data}
        exit_dict.update([('comments', comment_dict)])
        # Update dictionary with created time
        exit_dict.update([('created_time', datetime_to_timestamp(self.created_time))])
        # Update dictionary with location if it exists
        location = getattr(self, 'location', None)
        if location:
            location = location.dictionary_from_object()
        exit_dict.update([('location', location)])
        # Update dictionary with caption if it exists
        caption = None
        if self.caption:
            caption = self.caption.dictionary_from_object()
        exit_dict.update([('caption', caption)])
        # Update dictionary with tags
        tags = []
        for tag in self.tags:
            tags.append(tag.name)
        exit_dict.update([('tags', tags)])
        # Update with link
        exit_dict.update([('link', self.link)])
        # Update with filter
        exit_dict.update([('filter', self.filter)])
        # Update with 'users_in_photo'
        users_in_photo = [u.dictionary_from_object() for u in self.users_in_photo]
        exit_dict.update([('users_in_photo', users_in_photo)])
        # Return
        return exit_dict
        
            


class UserInPhoto(ApiModel):
    def __init__(self, **kwargs):
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)
            
    @classmethod
    def object_from_dictionary(cls, entry):
        user = User.object_from_dictionary(entry['user'])
        position = Position.object_from_dictionary(entry['position'])
        return UserInPhoto(user=user, position=position)
        
    def dictionary_from_object(self):
        user_dict = self.user.dictionary_from_object()
        position_dict = self.position.dictionary_from_object()
        return {'user': user_dict, 'position': position_dict}
        
    def __unicode__(self):
        return "UserInPhoto: %s" % self.user.username
        
        
class Position(ApiModel):
    def __init__(self, **kwargs):
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)
            
    def __unicode__(self):
        return "Position: x=%s, y=%s" % (self.x, self.y)

class MediaShortcode(Media):

    def __init__(self, shortcode=None, **kwargs):
        self.shortcode = shortcode
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)


class Tag(ApiModel):
    def __init__(self, name, **kwargs):
        self.name = name
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)

    def __unicode__(self):
        return "Tag: %s" % self.name


class Comment(ApiModel):
    def __init__(self, *args, **kwargs):
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)

    @classmethod
    def object_from_dictionary(cls, entry):
        user = User.object_from_dictionary(entry['from'])
        text = entry['text']
        created_at = timestamp_to_datetime(entry['created_time'])
        id = entry['id']
        return Comment(id=id, user=user, text=text, created_at=created_at)
        
    def dictionary_from_object(self):
        user_dict = self.user.dictionary_from_object()
        timestamp = datetime_to_timestamp(self.created_at)
        return {'from': user_dict, 'text': self.text, 
                'created_time': timestamp, 'id': self.id}

    def __unicode__(self):
        return "Comment: %s said \"%s\"" % (self.user.username, self.text)


class Point(ApiModel):
    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude

    def __unicode__(self):
        return "Point: (%s, %s)" % (self.latitude, self.longitude)


class Location(ApiModel):
    def __init__(self, id, *args, **kwargs):
        self.id = str(id)
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)

    @classmethod
    def object_from_dictionary(cls, entry):
        point = None
        if 'latitude' in entry:
            point = Point(entry.get('latitude'),
                          entry.get('longitude'))
        location = Location(entry.get('id', 0),
                       point=point,
                       name=entry.get('name', ''))
        return location
        
    def dictionary_from_object(self):
        return {'id': self.id, 
                'name': self.name, 
                'latitude': self.point.latitude, 
                'longitude': self.point.longitude}

    def __unicode__(self):
        return "Location: %s (%s)" % (self.id, self.point)


class User(ApiModel):

    def __init__(self, id, *args, **kwargs):
        self.id = id
        for key, value in six.iteritems(kwargs):
            setattr(self, key, value)

    def __unicode__(self):
        return "User: %s" % self.username


class Relationship(ApiModel):

    def __init__(self, incoming_status="none", outgoing_status="none", target_user_is_private=False):
        self.incoming_status = incoming_status
        self.outgoing_status = outgoing_status
        self.target_user_is_private = target_user_is_private

    def __unicode__(self):
        follows = False if self.outgoing_status == 'none' else True
        followed = False if self.incoming_status == 'none' else True

        return "Relationship: (Follows: %s, Followed by: %s)" % (follows, followed)
