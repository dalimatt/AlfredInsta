import scratch
from dependencies.instagram import models
import os
import sys
import dependencies.simplejson as json
from dependencies.pync import Notifier

# NUM_UNICODE_CHARS = 30
MAX_LIKED_MEDIA = 50

user_id = sys.argv[1]
likes_dir = sys.argv[2]
media_dir = sys.argv[3]

# Retrive user information from insagram
user = scratch._api.user(user_id)
username = user.username
count_follows = user.counts['follows']
count_followed_by = user.counts['followed_by']

# Issue notification that a search is started
Notifier.notify( title='Instastalk',
				 subtitle='User: {user}'.format(user=username),
				 message='Searching {follows} follows for likes'.format(follows=count_follows)
			)

# Find recent likes
likes = scratch.stalk_likes_in_follows(user_id)
likes_recent = likes[0:MAX_LIKED_MEDIA]  # Only process up to first 50 items
# Convert likes to a saveable format
likes_recent_dict = [models.Media.dictionary_from_object(u) for u in likes]
# Save the liked media
if not os.path.exists(likes_dir):
	os.makedirs(likes_dir)
user_likes_path = os.path.join(likes_dir, user_id + '.json')
with open(user_likes_path, 'wb') as likes_file:
    likes_file.write(json.dumps(likes_recent_dict))
# Download the media
scratch.download_images(likes, media_dir, resolution='thumbnail')

# Issue notification that the search is complete
num_likes = len(likes_recent_dict)
Notifier.notify( title='Instastalk',
				  subtitle='User: {user}'.format(user=username),
				  message='Found {likes} liked media'.format(likes=num_likes),
				  sound='default'
				)
