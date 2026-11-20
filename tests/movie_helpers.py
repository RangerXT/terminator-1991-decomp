"""Native movie service contract shared by direct and opponent composition tests."""
import ctypes
from test_imageload import ImageIO
from test_mapsetupreal import Resources
from test_travel import Services
class MovieServices(ctypes.Structure):
    _fields_ = [('files', ctypes.POINTER(ImageIO)), ('platform', ctypes.POINTER(Resources)),
              ('screen', ctypes.c_void_p), ('palette', ctypes.c_void_p), ('other', ctypes.POINTER(Services))]
