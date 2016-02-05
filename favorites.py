
from __future__ import print_function
import sys

class Favorites():
    
    def __init__(self, wfObject):
        self.wf = wfObject
        self.favorites = self.wf.stored_data('favorites')
        
    def add(self, newId, newUsername):
        # newId and newUsername should be strings
        # favorites = self.wf.stored_data('favorites')
        # Check if data stucture already exists in favorites
        if self.favorites is None:
            self.favorites = dict([(newId, newUsername)])
        else:
            self.favorites.update(dict([(newId, newUsername)]))
        self.wf.store_data('favorites', self.favorites)
            
    def remove(self, oldFavId):
        # oldFav should be <userId> string
        # favorites = self.wf.stored_data('favorites')
        try:
            self.favorites.pop(oldFavId)
        except KeyError:
            # The item does not exist
            print('Warning: Attempted to remove favorite that did' +
                    ' not exist, userId:<{0}>'.format(oldFavId), 
                    file=sys.stderr)
        except AttributeError:
            # favorites is not a dict, remove file
            print('Warning: Class of favorites is not a dictionary,' +
                    ' deleting file "favorites.cpickle"',
                    file=sys.stderr)
            with open(self.wf.datafile('favorites'), 'wb') as favFile:
                os.remove(favFile)
            favFile.close()
        # Removal of fav was successful, save file
        else:
            self.wf.store_data('favorites', self.favorites)
            
    def get_favorites(self):
        # favorites = self.wf.stored_data('favorites')
        if self.favorites is not None:
            if len(self.favorites) is not 0:
                return self.favorites
            # Otherwise there are no favorites
            else:
                return None
        # Otherwise the file does not exist
        else:
            return None
    
    def is_a_favorite(self, user_id):
        """Check if a user is a favorite"""
        if self.favorites is not None:
            return True if user_id in self.favorites else False
            
    def update_info(self, fav_user_id, fav_username):
        self.favorites.update({fav_user_id: fav_username})
        
    def cache_favs(self):
        self.wf.store_data('favorites', self.favorites)